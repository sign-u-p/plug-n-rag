import json
import os
import subprocess
from pathlib import Path

from plug_n_rag.cli import main

from .conftest import copy_vault

REPO = Path(__file__).resolve().parents[1]


def run(capsys, *args):
    code = main(list(args))
    return code, capsys.readouterr().out


def test_session_start_unconfigured_vault_hint(tmp_path, capsys, monkeypatch):
    root = copy_vault(tmp_path)
    monkeypatch.chdir(root)
    _, out = run(capsys, "session-start")
    assert out.strip() == ("plug-n-rag: Obsidian-Vault erkannt, aber noch nicht eingerichtet. "
                           "/plug-n-rag:setup startet die Einrichtung.")
    assert not (root / ".plug-n-rag").exists()


def test_session_start_silent_in_foreign_folder(tmp_path, capsys, monkeypatch):
    d = tmp_path / "irgendwas"
    d.mkdir()
    (d / "notiz.md").write_text("Hallo", encoding="utf-8")
    monkeypatch.chdir(d)
    _, out = run(capsys, "session-start")
    assert out == ""
    _, out = run(capsys, "stop")
    assert out == ""


def test_init_sync_search_via_cli(tmp_path, capsys, monkeypatch):
    root = copy_vault(tmp_path)
    monkeypatch.chdir(root)
    _, out = run(capsys, "init", "--provider", "fake", "--privat", "Tagebuch/**", "--formate", "markdown", "pdf")
    assert "Eingerichtet" in out and "Vorlagen/**" in out
    gi = (root / ".gitignore").read_text(encoding="utf-8")
    assert ".plug-n-rag/cache/" in gi
    _, out = run(capsys, "init", "--provider", "fake")
    assert "nichts überschrieben" in out
    _, out = run(capsys, "session-start", "--budget", "30")
    assert out.startswith("Vault: 7 Dateien in 4 Bereichen")
    _, out = run(capsys, "suche", "Reizverarbeitung", "--zweck", "frage")
    assert "gespraeche/2026-10-supervision.md" in out
    _, out = run(capsys, "gliederung", "COPM")
    assert "## Ablauf" in out
    _, out = run(capsys, "lesen", "COPM#Auswertung")
    assert "klinisch bedeutsam" in out
    _, out = run(capsys, "verwandt", "COPM")
    assert "Betätigungsanalyse" in out
    _, out = run(capsys, "status", "--schnell")
    assert "plug-n-rag · Vault" in out
    _, out = run(capsys, "lernen", "--tiefer", "--zweck", "recherche")
    assert "Recherche: bis zu 10 Notizen" in out
    (root / "themen" / "Neue Notiz.md").write_text("# Neu\n\nErgotherapie im Seniorenheim.", encoding="utf-8")
    _, out = run(capsys, "stop")
    assert out == ""
    _, out = run(capsys, "suche", "Seniorenheim")
    assert "themen/Neue Notiz.md" in out
    _, out = run(capsys, "konfig", "--setzen", "tuning.commit_learning=true")
    assert "commit_learning: true" in out


def test_launcher_script_runs_core(tmp_path):
    """The bin/ launcher used by hooks and the Bash tool works end to end."""
    root = copy_vault(tmp_path)
    env = dict(os.environ, XDG_CACHE_HOME=str(tmp_path / "c"), XDG_CONFIG_HOME=str(tmp_path / "cfg"),
               CLAUDE_PROJECT_DIR=str(root), PLUG_N_RAG_VENV=str(REPO / ".venv"))
    env.pop("UV_NATIVE_TLS", None)
    out = subprocess.run([str(REPO / "bin" / "plug-n-rag"), "session-start"], capture_output=True, text=True,
                         env=env, cwd=tmp_path, timeout=300)
    assert "noch nicht eingerichtet" in out.stdout, out.stderr


def test_plugin_manifest_and_hooks_are_valid_json():
    plugin = json.loads((REPO / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    market = json.loads((REPO / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    hooks = json.loads((REPO / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    assert plugin["name"] == market["plugins"][0]["name"] == "plug-n-rag"
    assert set(hooks["hooks"]) == {"SessionStart", "Stop"}
    for skill in (REPO / "skills").iterdir():
        text = (skill / "SKILL.md").read_text(encoding="utf-8")
        assert text.startswith("---\nname: ") and "description:" in text
