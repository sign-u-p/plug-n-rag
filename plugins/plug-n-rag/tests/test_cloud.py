import subprocess

from plug_n_rag.cli import main
from plug_n_rag.cloud import allowed_domains, check, guide, in_cloud, setup_script
from plug_n_rag.embed.voyage import api_key
from plug_n_rag.sync import sync

LOCAL = {"embedding": {"provider": "local", "model": "intfloat/multilingual-e5-small"}}
VOYAGE = {"embedding": {"provider": "voyage", "model": "voyage-3.5-lite"}}


def test_setup_script_local_is_valid_bash_and_preloads_model():
    script = setup_script(LOCAL)
    assert script.startswith("#!/bin/bash\n") and script.rstrip().endswith("exit 0")
    assert "claude plugin marketplace add sign-u-p/plug-n-rag" in script
    assert "claude plugin install plug-n-rag@plug-n-rag" in script
    assert "modell-laden --modell intfloat/multilingual-e5-small" in script
    assert subprocess.run(["bash", "-n"], input=script, text=True).returncode == 0
    assert "VOYAGE" not in script and "key" not in script.lower()


def test_hosts_depend_on_provider():
    assert allowed_domains(LOCAL) == ["huggingface.co", "*.hf.co"]
    assert allowed_domains(VOYAGE) == []
    assert "modell-laden" not in setup_script(VOYAGE)
    g = guide(None, VOYAGE)
    assert "Netzwerk-Secret" in g and "api.voyageai.com" in g and "huggingface" not in g


def test_guide_warns_about_repo_settings():
    g = guide(None, LOCAL)
    assert ".claude/settings.json" in g and "reicht in" in g and "--einbinden" in g
    assert "huggingface.co" in g and "*.hf.co" in g


def test_check_reports_missing_repo_and_index(layout, fake, monkeypatch):
    sync(layout, embedder=fake)
    monkeypatch.setenv("CLAUDE_CODE_REMOTE", "true")
    assert in_cloud()
    subprocess.run(["git", "init", "-q", str(layout.root)], check=True)
    out = check(layout, network=False)
    assert "✓ Läuft in einer Cloud-Sitzung" in out
    assert "Index-Dateien sind nicht im Repo" in out
    assert "Kein GitHub-Repo verbunden" in out


def test_voyage_key_placeholder_only_in_cloud(monkeypatch):
    monkeypatch.delenv("VOYAGE_API_KEY", raising=False)
    assert api_key() is None
    monkeypatch.setenv("CLAUDE_CODE_REMOTE", "true")
    assert api_key() == "proxy-injected"
    monkeypatch.setenv("VOYAGE_API_KEY", "echt")
    assert api_key() == "echt"


def test_cli_cloud_commands(layout, capsys, monkeypatch):
    monkeypatch.chdir(layout.root)
    main(["cloud", "--skript"])
    assert capsys.readouterr().out.startswith("#!/bin/bash")
    main(["cloud"])
    assert "Setup-Skript einfügen" in capsys.readouterr().out
    main(["cloud", "--pruefen", "--offline"])
    assert "Prüfung für Cloud-Sitzungen" in capsys.readouterr().out
    main(["modell-laden", "--modell", "gibt/es-nicht"])
    assert "Unbekanntes lokales Modell" in capsys.readouterr().out


def test_session_start_points_to_cloud_help(layout, capsys, monkeypatch):
    from plug_n_rag.embed import EmbeddingUnavailable
    import plug_n_rag.sync as sync_mod

    class Broken:
        model_id = "fake:fake-384@1"
        dims = 384
        min_similarity = 0.3
        strong_similarity = 0.5

        def embed(self, texts, kind):
            raise EmbeddingUnavailable("Hugging Face blockiert")

    monkeypatch.setattr(sync_mod, "get_embedder", lambda cfg: Broken())
    monkeypatch.setenv("CLAUDE_CODE_REMOTE", "true")
    monkeypatch.chdir(layout.root)
    main(["session-start", "--budget", "30"])
    out = capsys.readouterr().out
    assert "Hugging Face blockiert" in out and "`plug-n-rag cloud`" in out


# --- Self-setup of the vault (cloud --einbinden) ---

import json
import os

from plug_n_rag.cloud import (BOOTSTRAP_REL, BootstrapError, bootstrap_installed, bootstrap_script,
                              install_bootstrap, remove_bootstrap)


def test_bootstrap_script_is_valid_posix_sh_and_only_acts_in_cloud():
    script = bootstrap_script()
    assert script.startswith("#!/bin/sh\n")
    assert subprocess.run(["sh", "-n"], input=script, text=True).returncode == 0
    assert '[ "$CLAUDE_CODE_REMOTE" = "true" ] || exit 0' in script
    assert "claude plugin install plug-n-rag@plug-n-rag" in script
    assert "/reload-plugins" in script and "anleitung" in script


def test_install_bootstrap_keeps_existing_settings_and_is_idempotent(tmp_path):
    (tmp_path / ".claude").mkdir()
    settings = tmp_path / ".claude" / "settings.json"
    settings.write_text(json.dumps({"permissions": {"allow": ["Bash(ls)"]},
                                    "hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "echo hi"}]}]}}))
    changed = install_bootstrap(tmp_path)
    assert set(changed) == {BOOTSTRAP_REL, ".claude/settings.json"}
    data = json.loads(settings.read_text())
    assert data["permissions"] == {"allow": ["Bash(ls)"]}
    cmds = [h["command"] for e in data["hooks"]["SessionStart"] for h in e["hooks"]]
    assert cmds[0] == "echo hi" and "cloud-start.sh" in cmds[1]
    assert os.access(tmp_path / BOOTSTRAP_REL, os.X_OK)
    assert bootstrap_installed(tmp_path)
    assert install_bootstrap(tmp_path) == []  # second run changes nothing
    assert len(json.loads(settings.read_text())["hooks"]["SessionStart"]) == 2

    assert set(remove_bootstrap(tmp_path)) == {BOOTSTRAP_REL, ".claude/settings.json"}
    data = json.loads(settings.read_text())
    assert data["hooks"]["SessionStart"] == [{"hooks": [{"type": "command", "command": "echo hi"}]}]
    assert not bootstrap_installed(tmp_path)


def test_remove_bootstrap_drops_empty_hooks(tmp_path):
    install_bootstrap(tmp_path)
    remove_bootstrap(tmp_path)
    assert json.loads((tmp_path / ".claude" / "settings.json").read_text()) == {}


def test_install_bootstrap_refuses_broken_settings(tmp_path):
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "settings.json").write_text("{ kaputt")
    try:
        install_bootstrap(tmp_path)
    except BootstrapError as exc:
        assert "kein gültiges JSON" in str(exc)
    else:
        raise AssertionError("BootstrapError expected")
    assert (tmp_path / ".claude" / "settings.json").read_text() == "{ kaputt"


def test_install_bootstrap_refuses_vault_in_repo_subfolder(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "vault").mkdir()
    try:
        install_bootstrap(tmp_path / "vault")
    except BootstrapError as exc:
        assert "Unterordner" in str(exc)
    else:
        raise AssertionError("BootstrapError expected")


def _run_bootstrap(tmp_path, *, cloud, preinstalled=False, install_works=True):
    """Run the start script with a fake `claude` that 'installs' a fake plugin."""
    home = tmp_path / "home"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True)
    home.mkdir()
    plugin = home / ".claude/plugins/cache/plug-n-rag/plug-n-rag/9.9.9"
    fake_plugin = (f'mkdir -p "{plugin}/scripts"; printf \'#!/bin/sh\\necho KARTE "$@"\\n\' > "{plugin}/scripts/plug-n-rag"; '
                   f'chmod +x "{plugin}/scripts/plug-n-rag"')
    (bin_dir / "claude").write_text("#!/bin/sh\necho \"$@\" >> \"$HOME/calls\"\n"
                                    + (f'case "$*" in "plugin install"*) {fake_plugin};; esac\n' if install_works else "exit 1\n"))
    (bin_dir / "claude").chmod(0o755)
    if preinstalled:
        (plugin / "scripts").mkdir(parents=True)
    script = tmp_path / "start.sh"
    script.write_text(bootstrap_script())
    env = {"PATH": f"{bin_dir}:/usr/bin:/bin", "HOME": str(home)}
    if cloud:
        env["CLAUDE_CODE_REMOTE"] = "true"
    r = subprocess.run(["sh", str(script)], input="{}", text=True, capture_output=True, env=env)
    calls = (home / "calls").read_text() if (home / "calls").exists() else ""
    return r, calls


def test_bootstrap_does_nothing_locally(tmp_path):
    r, calls = _run_bootstrap(tmp_path, cloud=False)
    assert r.returncode == 0 and r.stdout == "" and calls == ""


def test_bootstrap_installs_and_starts_in_cloud(tmp_path):
    r, calls = _run_bootstrap(tmp_path, cloud=True)
    assert r.returncode == 0
    assert "marketplace add sign-u-p/plug-n-rag" in calls and "plugin install plug-n-rag@plug-n-rag" in calls
    assert "/reload-plugins" in r.stdout and "KARTE session-start" in r.stdout


def test_bootstrap_leaves_preinstalled_plugin_alone(tmp_path):
    r, calls = _run_bootstrap(tmp_path, cloud=True, preinstalled=True)
    assert r.returncode == 0 and r.stdout == "" and calls == ""


def test_bootstrap_reports_failed_install(tmp_path):
    r, _ = _run_bootstrap(tmp_path, cloud=True, install_works=False)
    assert r.returncode == 0 and "nicht installieren" in r.stdout and "github.com/sign-u-p/plug-n-rag" in r.stdout


def test_cli_einbinden_and_check(layout, capsys, monkeypatch):
    monkeypatch.chdir(layout.root)
    main(["cloud", "--pruefen", "--offline"])
    main(["cloud", "--einbinden"])
    out = capsys.readouterr().out
    assert "Selbst-Einrichtung für Cloud-Sitzungen ist eingebunden" in out and "nach-main" in out
    subprocess.run(["git", "init", "-q", str(layout.root)], check=True)
    main(["cloud", "--pruefen", "--offline"])
    assert "✓ Selbst-Einrichtung für Cloud-Sitzungen ist eingebunden" in capsys.readouterr().out
    main(["cloud", "--ausbinden"])
    assert "Selbst-Einrichtung entfernt" in capsys.readouterr().out
