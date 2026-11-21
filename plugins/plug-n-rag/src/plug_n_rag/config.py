"""Locating a vault or collection and reading its configuration.

plug-n-rag separates what it creates by kind:

* **shareable** (configuration, index files, optional transcripts) lives in exactly one
  folder, ``.plug-n-rag/``: inside the vault/collection (``inside``) or, if nothing may be
  written into the folder, in the user's data directory (``external``)::

      <root>/.plug-n-rag/plug-n-rag.yml   configuration
      <root>/.plug-n-rag/index/           one index file per source file
      <root>/.plug-n-rag/abschriften/     readable transcripts (collections, optional)
      <root>/.plug-n-rag/tuning.json      learned values (only if committing them is wanted)

* **volatile** (search database, logs, extracts, page images, state) always lives in the user
  cache, ``<user cache>/state/<folder name>-<hash>/``. It is never synced or committed.

Older installations (``plug-n-rag.yml`` in the root, cache in ``.plug-n-rag/cache``) are still
recognised; ``plug-n-rag umziehen`` moves them to the current layout.
"""

from __future__ import annotations

import copy
import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .util import atomic_write_json, atomic_write_text, read_json, user_cache_dir, user_config_dir, user_data_dir

CONFIG_NAME = "plug-n-rag.yml"
STATE_DIR_NAME = ".plug-n-rag"

VAULT_DEFAULT_EXCLUDE = [
    ".obsidian/**",
    ".trash/**",
    ".git/**",
    ".plug-n-rag/**",
    ".claude/**",
    "node_modules/**",
]

DEFAULTS: dict[str, Any] = {
    "mode": "vault",
    "index_location": "inside",
    "embedding": {"provider": "local", "model": "intfloat/multilingual-e5-small"},
    "formats": ["markdown"],
    "exclude": list(VAULT_DEFAULT_EXCLUDE),
    "private_folders": [],
    "folders": {},
    "tuning": {"commit_learning": False},
    "transcription": "ask",
    "abschriften": {"ort": None, "ordner": "Abschriften"},
    "anzeige": "kompakt",  # kompakt | aus: source line in sessions where nothing is drawn
    "updates": "fragen",  # fragen | automatisch | aus: newer plug-n-rag at session start (update.py)
    "git": {"auto_commit": "off", "auto_push": False},
}

COLLECTION_FORMATS = ["markdown", "text", "pdf"]


def _deep_merge(base: dict, extra: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in (extra or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _folder_key(root: Path) -> str:
    digest = hashlib.sha256(str(root.resolve()).encode("utf-8")).hexdigest()[:16]
    return f"{root.name}-{digest}"


@dataclass
class Layout:
    root: Path
    location: str  # "inside" | "external"
    state_dir: Path  # the shareable folder (.plug-n-rag/ inside, or the central data folder)
    config_path: Path
    configured: bool = True
    config: dict = field(default_factory=dict)

    @property
    def index_dir(self) -> Path:
        return self.state_dir / "index"

    @property
    def transcripts_dir(self) -> Path:
        return self.state_dir / "abschriften"

    @property
    def legacy(self) -> bool:
        """Old layout: configuration in the root folder instead of inside .plug-n-rag/."""
        return self.location == "inside" and self.config_path.parent == self.root

    @property
    def cache_dir(self) -> Path:
        override = os.environ.get("PLUG_N_RAG_CACHE_DIR")
        if override:
            return Path(override)
        return user_cache_dir() / "state" / _folder_key(self.root)

    @property
    def db_path(self) -> Path:
        return self.cache_dir / "search.db"

    @property
    def log_path(self) -> Path:
        return self.cache_dir / "log.jsonl"

    @property
    def lock_path(self) -> Path:
        return self.cache_dir / "sync.lock"

    @property
    def mode(self) -> str:
        return self.config.get("mode", "vault")

    @property
    def tuning_path(self) -> Path:
        if self.config.get("tuning", {}).get("commit_learning") and self.location == "inside":
            return self.state_dir / "tuning.json"
        return self.cache_dir / "tuning.json"

    def ensure_dirs(self) -> None:
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        if (self.state_dir / "cache").is_dir():  # old layout: keep extracts and transcripts
            from .migrate import carry_over_old_cache

            carry_over_old_cache(self)

    def rel(self, path: Path) -> str:
        return path.resolve().relative_to(self.root.resolve()).as_posix()


def load_config(path: Path) -> dict:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        raw = {}
    if not isinstance(raw, dict):
        raw = {}
    cfg = _deep_merge(DEFAULTS, raw)
    if raw.get("mode") == "collection" and "formats" not in raw:
        cfg["formats"] = list(COLLECTION_FORMATS)
    return cfg


def save_config(path: Path, cfg: dict) -> None:
    header = (
        "# plug-n-rag – Konfiguration / configuration. Am besten über den Chat mit Claude ändern /\n"
        "# best changed by asking Claude. Nie API-Keys hier / never API keys here (VOYAGE_API_KEY).\n"
    )
    body = yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False, default_flow_style=False)
    atomic_write_text(path, header + body)


# --- registry for external collections -------------------------------------------------

def _registry_path() -> Path:
    return user_config_dir() / "collections.json"


def _registry() -> dict:
    return read_json(_registry_path(), {}) or {}


def external_state_dir(root: Path) -> Path:
    return user_data_dir() / "collections" / _folder_key(root)


def unregister_external(root: Path) -> None:
    reg = _registry()
    if reg.pop(str(root.resolve()), None) is not None:
        atomic_write_json(_registry_path(), reg)


def register_external(root: Path, state_dir: Path) -> None:
    reg = _registry()
    reg[str(root.resolve())] = str(state_dir)
    atomic_write_json(_registry_path(), reg)


# --- discovery ---------------------------------------------------------------------------

def find_layout(start: Path | None = None) -> Layout | None:
    """Find the configured vault/collection containing ``start`` (default: cwd).

    Returns an unconfigured Layout for an Obsidian vault that has not been set up yet,
    or None if nothing relevant was found.
    """
    env_root = os.environ.get("PLUG_N_RAG_ROOT")
    start = Path(env_root) if env_root and start is None else (start or Path.cwd())
    start = start.resolve()
    reg = _registry()
    candidates = [start, *start.parents]
    for d in candidates:
        cfg = d / STATE_DIR_NAME / CONFIG_NAME
        if cfg.is_file():
            return Layout(d, "inside", d / STATE_DIR_NAME, cfg, True, load_config(cfg))
        cfg = d / CONFIG_NAME  # old layout
        if cfg.is_file():
            return Layout(d, "inside", d / STATE_DIR_NAME, cfg, True, load_config(cfg))
        if str(d) in reg:
            state = Path(reg[str(d)])
            cfg = state / CONFIG_NAME
            if cfg.is_file():
                return Layout(d, "external", state, cfg, True, load_config(cfg))
    for d in candidates:
        if (d / ".obsidian").is_dir():
            return Layout(d, "inside", d / STATE_DIR_NAME, d / STATE_DIR_NAME / CONFIG_NAME, False, dict(DEFAULTS))
        if (d / ".git").exists():
            break
    return None


def init_layout(
    root: Path,
    *,
    mode: str = "vault",
    location: str = "inside",
    provider: str = "local",
    model: str | None = None,
    extra: dict | None = None,
) -> Layout:
    """Create configuration and folders. Never overwrites an existing configuration."""
    root = root.resolve()
    if location == "inside":
        state = root / STATE_DIR_NAME
        cfg_path = state / CONFIG_NAME
        if (root / CONFIG_NAME).exists():  # old layout: keep using it
            cfg_path = root / CONFIG_NAME
    else:
        state = external_state_dir(root)
        cfg_path = state / CONFIG_NAME
    if cfg_path.exists():
        layout = Layout(root, location, state, cfg_path, True, load_config(cfg_path))
        layout.ensure_dirs()
        if location == "external":
            register_external(root, state)
        return layout
    cfg: dict[str, Any] = {
        "mode": mode,
        "index_location": location,
        "embedding": {"provider": provider, "model": model or _default_model(provider)},
    }
    if mode == "collection":
        cfg["formats"] = list(COLLECTION_FORMATS)
        cfg["exclude"] = [".git/**", ".plug-n-rag/**", ".obsidian/**", ".trash/**"]
    else:
        cfg["exclude"] = list(VAULT_DEFAULT_EXCLUDE)
    cfg["private_folders"] = []
    cfg["folders"] = {}
    cfg["tuning"] = {"commit_learning": False}
    cfg["transcription"] = "ask"
    cfg["abschriften"] = {"ort": None, "ordner": "Abschriften"}
    cfg["git"] = {"auto_commit": "off", "auto_push": False}
    if extra:
        cfg = _deep_merge(cfg, extra)
    state.mkdir(parents=True, exist_ok=True)
    save_config(cfg_path, cfg)
    if location == "external":
        register_external(root, state)
    layout = Layout(root, location, state, cfg_path, True, load_config(cfg_path))
    layout.ensure_dirs()
    return layout


def _default_model(provider: str) -> str:
    if provider == "voyage":
        return "voyage-3.5-lite"
    if provider == "fake":
        return "fake-384"
    return "intfloat/multilingual-e5-small"
