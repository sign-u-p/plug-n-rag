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
    assert ".claude/settings.json" in g and "reicht in der Cloud nicht" in g
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
