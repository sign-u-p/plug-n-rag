import subprocess
from pathlib import Path

import pytest

from plug_n_rag import gitops
from plug_n_rag.cli import main

from .conftest import copy_vault

REPO = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(not gitops.shutil.which("git"), reason="git fehlt")


def g(root, *args):
    return subprocess.run(["git", "-C", str(root), "-c", "user.name=Test", "-c", "user.email=t@example.invalid",
                           *args], capture_output=True, text=True, check=True).stdout


def test_precommit_hook_keeps_index_in_same_commit(tmp_path, monkeypatch, capsys):
    root = copy_vault(tmp_path)
    g(root, "init", "-q")
    monkeypatch.chdir(root)
    monkeypatch.setenv("PLUG_N_RAG_PLUGIN_ROOT", str(REPO))
    monkeypatch.setenv("PLUG_N_RAG_VENV", str(REPO / ".venv"))
    monkeypatch.delenv("UV_NATIVE_TLS", raising=False)
    main(["init", "--provider", "fake", "--privat", "Tagebuch/**"])
    main(["sync"])
    main(["git-hook"])
    assert "Git-Hook installiert" in capsys.readouterr().out
    hook = (root / ".git" / "hooks" / "pre-commit").read_text(encoding="utf-8")
    assert "plug-n-rag pre-commit" in hook
    g(root, "add", "-A")
    g(root, "commit", "-q", "-m", "Vault")
    (root / "themen" / "Neu.md").write_text("# Neu\n\nNotizen zur Fahrradreparatur.", encoding="utf-8")
    g(root, "add", "themen/Neu.md")
    g(root, "commit", "-q", "-m", "Neue Notiz")
    files = g(root, "show", "--name-only", "--format=", "HEAD").split()
    assert "themen/Neu.md" in files and ".plug-n-rag/index/themen/Neu.md.json" in files
    # cache is never committed
    assert not any(f.startswith(".plug-n-rag/cache") for f in g(root, "ls-files").split())
    # installing again only updates
    main(["git-hook"])
    assert "aktualisiert" in capsys.readouterr().out


def test_pull_is_skipped_with_local_changes(tmp_path):
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
    root = copy_vault(tmp_path)
    g(root, "init", "-q", "-b", "main")
    g(root, "add", "-A")
    g(root, "commit", "-q", "-m", "Vault")
    g(root, "remote", "add", "origin", str(origin))
    g(root, "push", "-q", "-u", "origin", "main")
    assert gitops.pull(root) is None  # clean: pulls silently
    (root / "wissen" / "NPS.md").write_text("geändert", encoding="utf-8")
    msg = gitops.pull(root)
    assert msg and "ungesicherte Änderungen" in msg
    assert (root / "wissen" / "NPS.md").read_text(encoding="utf-8") == "geändert"
