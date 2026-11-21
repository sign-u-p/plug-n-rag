"""Is there a newer plug-n-rag? Checked at session start, updated on request (``plug-n-rag aktualisieren``).

The newest version is the one in the marketplace repo on GitHub (``plugin.json`` on ``main``). The
check is time-boxed and remembered for a few hours, so a session start without network stays fast.
In cloud sessions, where every container starts fresh, it runs at each start (a few hundred ms).

Updating uses Claude Code's own commands (``claude plugin marketplace update`` and
``claude plugin update``), so plug-n-rag never writes into Claude Code's plugin folders itself.
The new version takes effect after ``/reload-plugins`` or in the next session.

Setting ``updates`` in the configuration: ``fragen`` (default: Claude asks), ``automatisch``
(updates in the background) or ``aus``. ``updates_skip`` holds a version the user declined; it is
not offered again, only a newer one. Both live in the vault's configuration, because cloud
containers forget everything else.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from . import __version__
from .i18n import tr
from .util import atomic_write_json, read_json, user_cache_dir

REPO = "sign-u-p/plug-n-rag"
MARKETPLACE = "plug-n-rag"
PLUGIN_ID = "plug-n-rag@plug-n-rag"
DISPLAY_ID = "plug-n-rag-anzeige@plug-n-rag"
MANIFEST_PATH = "plugins/plug-n-rag/.claude-plugin/plugin.json"
RAW_URL = f"https://raw.githubusercontent.com/{REPO}/main/{MANIFEST_PATH}"
GIT_URL = f"https://github.com/{REPO}.git"
CHECK_EVERY = 6 * 3600  # seconds a successful check is trusted
RETRY_AFTER = 3600  # seconds before a failed check is tried again
HTTP_TIMEOUT = 3.0
GIT_TIMEOUT = 8.0

MODES = {"fragen": "fragen", "ask": "fragen", "automatisch": "automatisch", "auto": "automatisch",
         "aus": "aus", "off": "aus", False: "aus", True: "fragen"}


@dataclass
class UpdateInfo:
    installed: str
    latest: str | None
    error: str | None = None

    @property
    def newer(self) -> bool:
        return bool(self.latest) and parse_version(self.latest) > parse_version(self.installed)


def parse_version(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", v or "")[:4]) or (0,)


def mode(config: dict) -> str:
    env = os.environ.get("PLUG_N_RAG_UPDATES")
    raw = env if env else config.get("updates", "fragen")
    return MODES.get(raw if not isinstance(raw, str) else raw.strip().lower(), "fragen")


def _cache_path() -> Path:
    return user_cache_dir() / "update-check.json"


def _fetch_http() -> str:
    req = urllib.request.Request(RAW_URL, headers={"User-Agent": "plug-n-rag", "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))["version"]


def _fetch_git() -> str:
    """Fallback where only git reaches GitHub (cloud sessions often allow github.com via git only)."""
    if not shutil.which("git"):
        raise OSError("git fehlt")
    repo = user_cache_dir() / "update-repo.git"
    if not repo.exists():
        subprocess.run(["git", "init", "--bare", "-q", str(repo)], check=True, capture_output=True,
                       timeout=GIT_TIMEOUT)
    subprocess.run(["git", "-C", str(repo), "fetch", "-q", "--depth", "1", GIT_URL, "main"], check=True,
                   capture_output=True, timeout=GIT_TIMEOUT)
    out = subprocess.run(["git", "-C", str(repo), "show", f"FETCH_HEAD:{MANIFEST_PATH}"], check=True,
                         capture_output=True, text=True, timeout=GIT_TIMEOUT).stdout
    return json.loads(out)["version"]


def latest_version(*, force: bool = False, fetchers=None) -> tuple[str | None, str | None]:
    """(newest version or None, error). Remembered in the user cache for a few hours."""
    cached = read_json(_cache_path(), {}) or {}
    age = time.time() - float(cached.get("t", 0))
    if not force and cached:
        if cached.get("latest") and age < CHECK_EVERY:
            return cached["latest"], None
        if not cached.get("latest") and age < RETRY_AFTER:
            return None, cached.get("error")
    errors = []
    for fetch in fetchers or (_fetch_http, _fetch_git):
        try:
            v = str(fetch())
        except (urllib.error.URLError, OSError, TimeoutError, ValueError, KeyError,
                subprocess.SubprocessError) as exc:
            errors.append(str(getattr(exc, "reason", exc)))
            continue
        try:
            atomic_write_json(_cache_path(), {"t": time.time(), "latest": v}, indent=None)
        except OSError:
            pass
        return v, None
    err = "; ".join(errors) or "unbekannt"
    try:
        atomic_write_json(_cache_path(), {"t": time.time(), "latest": None, "error": err}, indent=None)
    except OSError:
        pass
    return None, err


def check(*, force: bool = False, fetchers=None) -> UpdateInfo:
    latest, err = latest_version(force=force, fetchers=fetchers)
    return UpdateInfo(__version__, latest, err)


def installed_from_marketplace() -> bool:
    """Only an installed plugin can be updated by Claude Code (not one run from a folder)."""
    root = (os.environ.get("PLUG_N_RAG_PLUGIN_ROOT") or os.environ.get("CLAUDE_PLUGIN_ROOT") or "")
    return "/.claude/plugins/cache/" in root.replace("\\", "/")


# --- session start -----------------------------------------------------------------------------

def session_notes(config: dict, *, spawn=None, fetchers=None) -> list[str]:
    """Lines for the session start. Silent when off, up to date, or the check failed."""
    m = mode(config)
    if m == "aus":
        return []
    info = check(fetchers=fetchers)
    if not info.newer:
        return []
    skip = str(config.get("updates_skip") or "")
    if m == "fragen" and skip and parse_version(skip) >= parse_version(info.latest or ""):
        return []
    if not installed_from_marketplace():
        return [tr(f"Neue Version von plug-n-rag: {info.latest} (läuft: {info.installed}). Dieses Plugin läuft "
                   "aus einem Ordner, nicht aus dem Marketplace: dort mit `git pull` aktualisieren.",
                   f"New plug-n-rag version: {info.latest} (running: {info.installed}). This plugin runs from "
                   "a folder, not from the marketplace: update it there with `git pull`.")]
    if m == "automatisch":
        (spawn or spawn_update)()
        return [tr(f"plug-n-rag wird im Hintergrund von {info.installed} auf {info.latest} aktualisiert. Die neue "
                   "Version gilt nach /reload-plugins oder ab der nächsten Sitzung. Kurz der Nutzer:in sagen.",
                   f"plug-n-rag is being updated from {info.installed} to {info.latest} in the background. The "
                   "new version applies after /reload-plugins or from the next session. Briefly tell the user.")]
    return [tr(f"Neue Version von plug-n-rag verfügbar: {info.latest} (installiert: {info.installed}). Die "
               "Nutzer:in einmal fragen, ob aktualisiert werden soll (Neuerungen: "
               f"https://github.com/{REPO}/blob/main/DECISIONS.md). Ja: `plug-n-rag aktualisieren`. "
               "Nein, nicht diese Version: `plug-n-rag aktualisieren --spaeter`. Immer automatisch bzw. nie "
               "fragen: `plug-n-rag konfig --setzen updates=automatisch` bzw. `updates=aus`.",
               f"New plug-n-rag version available: {info.latest} (installed: {info.installed}). Ask the user "
               f"once whether to update (what's new: https://github.com/{REPO}/blob/main/DECISIONS.md). Yes: "
               "`plug-n-rag update`. No, not this version: `plug-n-rag update --later`. Always automatic or "
               "never ask: `plug-n-rag config --set updates=auto` or `updates=off`.")]


def spawn_update() -> None:
    """Run ``plug-n-rag aktualisieren --still`` detached (setting ``updates: automatisch``)."""
    import sys

    log = user_cache_dir() / "update.log"
    try:
        log.parent.mkdir(parents=True, exist_ok=True)
        with open(log, "ab") as fh:
            kwargs = {"stdout": fh, "stderr": fh, "stdin": subprocess.DEVNULL}
            if os.name == "nt":
                kwargs["creationflags"] = 0x00000008
            else:
                kwargs["start_new_session"] = True
            subprocess.Popen([sys.executable, "-m", "plug_n_rag.cli", "aktualisieren", "--still"], **kwargs)  # noqa: S603
    except OSError:
        pass


# --- updating ------------------------------------------------------------------------------------

def _claude(args: list[str], timeout: float = 180.0) -> subprocess.CompletedProcess:
    return subprocess.run(["claude", *args], capture_output=True, text=True, timeout=timeout,
                          stdin=subprocess.DEVNULL)


def _installed(run=_claude) -> dict[str, dict]:
    try:
        p = run(["plugin", "list", "--json"], 60.0)
        return {e["id"]: e for e in json.loads(p.stdout or "[]") if isinstance(e, dict) and "id" in e}
    except (OSError, ValueError, subprocess.SubprocessError):
        return {}


def update(*, run=_claude, fetchers=None) -> tuple[bool, list[str]]:
    """Update plug-n-rag (and plug-n-rag Display, if installed). Returns (updated, report lines)."""
    info = check(force=True, fetchers=fetchers)
    if info.latest and not info.newer:
        return False, [tr(f"plug-n-rag ist aktuell ({info.installed}).", f"plug-n-rag is up to date ({info.installed}).")]
    if not installed_from_marketplace():
        return False, [tr("Dieses Plugin läuft aus einem Ordner, nicht aus dem Marketplace. Dort mit `git pull` "
                          "aktualisieren.",
                          "This plugin runs from a folder, not from the marketplace. Update it there with `git pull`.")]
    if not shutil.which("claude"):
        return False, [tr("Der Befehl `claude` ist hier nicht verfügbar. Aktualisieren in Claude Code: "
                          f"`claude plugin marketplace update {MARKETPLACE}` und `claude plugin update {PLUGIN_ID}`.",
                          "The `claude` command is not available here. Update in Claude Code: "
                          f"`claude plugin marketplace update {MARKETPLACE}` and `claude plugin update {PLUGIN_ID}`.")]
    lines: list[str] = []
    try:
        run(["plugin", "marketplace", "update", MARKETPLACE])
    except (OSError, subprocess.SubprocessError) as exc:
        return False, [tr(f"Marketplace konnte nicht aktualisiert werden: {exc}",
                          f"The marketplace could not be updated: {exc}")]
    before = _installed(run)
    targets = [PLUGIN_ID] + ([DISPLAY_ID] if DISPLAY_ID in before else [])
    ok_all = True
    for pid in targets:
        scope = (before.get(pid) or {}).get("scope")
        cmd = ["plugin", "update", pid] + (["-s", scope] if scope else [])
        try:
            p = run(cmd)
            ok = p.returncode == 0
            msg = (p.stderr or p.stdout or "").strip().splitlines()[-1:] if not ok else []
        except (OSError, subprocess.SubprocessError) as exc:
            ok, msg = False, [str(exc)]
        ok_all &= ok
        if not ok:
            lines.append(tr(f"{pid}: Aktualisierung fehlgeschlagen", f"{pid}: update failed")
                         + (f" ({msg[0]})" if msg else ""))
    after = _installed(run)
    new = (after.get(PLUGIN_ID) or {}).get("version")
    path = (after.get(PLUGIN_ID) or {}).get("installPath")
    if path:
        from .cli import write_launcher

        write_launcher(Path(path))  # `plug-n-rag` on the PATH points to the new version from now on
    if new and parse_version(new) > parse_version(info.installed):
        lines.insert(0, tr(f"plug-n-rag aktualisiert: {info.installed} → {new}. Die neue Version gilt nach "
                           "/reload-plugins oder ab der nächsten Sitzung.",
                           f"plug-n-rag updated: {info.installed} → {new}. The new version applies after "
                           "/reload-plugins or from the next session."))
        if DISPLAY_ID in targets:
            dv = (after.get(DISPLAY_ID) or {}).get("version")
            if dv:
                lines.append(tr(f"plug-n-rag Display: {dv}", f"plug-n-rag Display: {dv}"))
        return True, lines
    if ok_all:
        lines.insert(0, tr("Keine neuere Version installiert; der Marketplace kennt noch keine. Später erneut versuchen.",
                           "No newer version installed; the marketplace does not offer one yet. Try again later."))
    return False, lines
