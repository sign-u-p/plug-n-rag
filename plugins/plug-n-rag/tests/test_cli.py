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
    assert ".obsidian/workspace*.json" in gi
    # new layout: one folder with config and index; nothing volatile inside it
    assert (root / ".plug-n-rag" / "plug-n-rag.yml").is_file() and not (root / "plug-n-rag.yml").exists()
    _, out = run(capsys, "init", "--provider", "fake")
    assert "nichts überschrieben" in out
    _, out = run(capsys, "session-start", "--budget", "30")
    assert out.startswith("Vault: 7 Dateien in 4 Bereichen")
    _, out = run(capsys, "suche", "Dachsanierung", "--zweck", "frage")
    assert "besprechungen/2026-10-hausversammlung.md" in out
    _, out = run(capsys, "gliederung", "NPS")
    assert "## Ablauf" in out
    _, out = run(capsys, "lesen", "NPS#Auswertung")
    assert "deutlich spürbar" in out
    _, out = run(capsys, "verwandt", "NPS")
    assert "Bedürfnisanalyse" in out
    _, out = run(capsys, "status", "--schnell")
    assert "plug-n-rag · Vault" in out
    _, out = run(capsys, "lernen", "--tiefer", "--zweck", "recherche")
    assert "Recherche: bis zu 10 Notizen" in out
    (root / "themen" / "Neue Notiz.md").write_text("# Neu\n\nGartenarbeit im Kleingartenverein.", encoding="utf-8")
    _, out = run(capsys, "stop")
    assert out == ""
    _, out = run(capsys, "suche", "Kleingartenverein")
    assert "themen/Neue Notiz.md" in out
    _, out = run(capsys, "konfig", "--setzen", "tuning.commit_learning=true")
    assert "commit_learning: true" in out


def test_launcher_script_runs_core(tmp_path):
    """The scripts/ launcher used by hooks and the Bash tool works end to end."""
    root = copy_vault(tmp_path)
    env = dict(os.environ, XDG_CACHE_HOME=str(tmp_path / "c"), XDG_CONFIG_HOME=str(tmp_path / "cfg"),
               CLAUDE_PROJECT_DIR=str(root), PLUG_N_RAG_VENV=str(REPO / ".venv"))
    env.pop("UV_NATIVE_TLS", None)
    out = subprocess.run([str(REPO / "scripts" / "plug-n-rag"), "session-start"], capture_output=True, text=True,
                         env=env, cwd=tmp_path, timeout=300)
    assert "noch nicht eingerichtet" in out.stdout, out.stderr


def test_plugin_manifest_and_hooks_are_valid_json():
    plugin = json.loads((REPO / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    market = json.loads((REPO.parents[1] / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    hooks = json.loads((REPO / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    entry = next(e for e in market["plugins"] if e["name"] == "plug-n-rag")
    assert plugin["name"] == "plug-n-rag" and entry["source"] == "./plugins/plug-n-rag"
    # every marketplace entry points at its own folder below plugins/
    for e in market["plugins"]:
        assert e["source"] == f"./plugins/{e['name']}"
        assert (REPO.parents[1] / e["source"] / ".claude-plugin" / "plugin.json").is_file()
    assert set(hooks["hooks"]) == {"SessionStart", "Stop"}
    for skill in (REPO / "skills").iterdir():
        text = (skill / "SKILL.md").read_text(encoding="utf-8")
        assert text.startswith("---\nname: ") and "description:" in text


def test_anleitung_prints_skill_without_frontmatter(capsys, monkeypatch):
    monkeypatch.setenv("PLUG_N_RAG_PLUGIN_ROOT", str(REPO))
    main(["anleitung", "setup"])
    out = capsys.readouterr().out
    assert "Cloud-Weg" in out and "name: setup" not in out
    assert "${CLAUDE_PLUGIN_ROOT}" not in out and str(REPO / "scripts" / "plug-n-rag") in out
    main(["anleitung"])
    assert "nach-main" in capsys.readouterr().out


def test_no_top_level_bin_dir_for_claude_ai():
    """claude.ai rejects plugins with a top-level bin/ directory."""
    assert not (REPO / "bin").exists()
    hooks = (REPO / "hooks" / "hooks.json").read_text(encoding="utf-8")
    assert "/scripts/plug-n-rag" in hooks and "/bin/" not in hooks


def test_session_start_puts_launcher_on_path(tmp_path):
    env_file = tmp_path / "env.sh"
    env = dict(os.environ, CLAUDE_ENV_FILE=str(env_file), CLAUDE_PROJECT_DIR=str(tmp_path),
               XDG_CACHE_HOME=str(tmp_path / "c"), PLUG_N_RAG_VENV=str(REPO / ".venv"))
    env.pop("UV_NATIVE_TLS", None)
    for _ in range(2):
        subprocess.run([str(REPO / "scripts" / "plug-n-rag"), "session-start"], env=env, cwd=tmp_path,
                       capture_output=True, timeout=300)
    lines = env_file.read_text(encoding="utf-8").splitlines()
    assert lines == [f'export PATH="{REPO}/scripts:$PATH"']


def test_launcher_does_not_start_python_outside_vaults(tmp_path):
    """Hooks in an unrelated project must cost nothing: no uv, no Python."""
    fakebin = tmp_path / "bin"
    fakebin.mkdir()
    marker = tmp_path / "uv-was-started"
    (fakebin / "uv").write_text(f'#!/bin/sh\necho "$@" >> "{marker}"\n', encoding="utf-8")
    (fakebin / "uv").chmod(0o755)
    env = {"PATH": f"{fakebin}:/usr/bin:/bin", "HOME": str(tmp_path / "home"),
           "XDG_CONFIG_HOME": str(tmp_path / "cfg"), "XDG_CACHE_HOME": str(tmp_path / "cache")}
    other = tmp_path / "anderes-projekt"
    (other / "src").mkdir(parents=True)
    for hook in ("session-start", "stop"):
        r = subprocess.run([str(REPO / "scripts" / "plug-n-rag"), hook], cwd=other, capture_output=True,
                           text=True, env={**env, "CLAUDE_PROJECT_DIR": str(other)}, timeout=30)
        assert r.returncode == 0 and r.stdout == ""
    assert not marker.exists()
    # inside a vault (also from a subfolder) the hook does run
    vault = copy_vault(tmp_path)
    subprocess.run([str(REPO / "scripts" / "plug-n-rag"), "session-start"], cwd=vault, capture_output=True,
                   env={**env, "CLAUDE_PROJECT_DIR": str(vault / "wissen")}, timeout=30)
    assert marker.exists()
    marker.unlink()
    # a centrally stored collection is found through the list in the user config
    lib = tmp_path / "Sammlung"
    lib.mkdir()
    (tmp_path / "cfg" / "plug-n-rag").mkdir(parents=True)
    (tmp_path / "cfg" / "plug-n-rag" / "collections.json").write_text(
        json.dumps({str(lib): "/irgendwo"}), encoding="utf-8")
    subprocess.run([str(REPO / "scripts" / "plug-n-rag"), "stop"], cwd=lib, capture_output=True,
                   env={**env, "CLAUDE_PROJECT_DIR": str(lib)}, timeout=30)
    assert marker.exists()
