import shutil
from pathlib import Path

import pytest

from plug_n_rag.config import init_layout

FIXTURE = Path(__file__).parent / "fixtures" / "vault"


@pytest.fixture(autouse=True)
def isolated_user_dirs(tmp_path, monkeypatch):
    """Keep user cache/config (registry, launcher) inside the test's tmp dir.

    The real model cache is shared so the local model is downloaded only once.
    """
    real_cache = Path.home() / ".cache" / "plug-n-rag" / "models"
    monkeypatch.setenv("PLUG_N_RAG_MODEL_DIR", str(real_cache))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg-cache"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg-config"))
    monkeypatch.delenv("PLUG_N_RAG_ROOT", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_REMOTE", raising=False)
    yield


def copy_vault(tmp_path: Path, name: str = "vault") -> Path:
    dest = tmp_path / name
    shutil.copytree(FIXTURE, dest)
    return dest


@pytest.fixture
def vault_dir(tmp_path):
    return copy_vault(tmp_path)


def make_layout(root: Path, provider: str = "fake", **extra):
    cfg = {"private_folders": ["Tagebuch/**"], "formats": ["markdown", "pdf"]}
    cfg.update(extra)
    from plug_n_rag.scan import detect_template_folders

    cfg.setdefault("exclude", [".obsidian/**", ".trash/**", ".git/**", ".plug-n-rag/**"]
                   + [f"{t}/**" for t in detect_template_folders(root)])
    return init_layout(root, provider=provider, extra=cfg)


@pytest.fixture
def layout(vault_dir):
    return make_layout(vault_dir)


@pytest.fixture
def fake():
    from plug_n_rag.embed.fake import FakeEmbedder

    return FakeEmbedder()
