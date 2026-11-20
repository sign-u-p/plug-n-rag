import json

from plug_n_rag.anzeige import snapshot
from plug_n_rag.cli import main
from plug_n_rag.config import find_layout
from plug_n_rag.search import search
from plug_n_rag.sync import sync

from .conftest import copy_vault


def test_snapshot_for_the_display_mod(layout, fake, capsys, monkeypatch):
    sync(layout, embedder=fake)
    search(layout, "Dachsanierung", embedder=fake)
    monkeypatch.chdir(layout.root)
    main(["anzeige-daten"])
    data = json.loads(capsys.readouterr().out)
    assert data["configured"] and data["name"] == "vault" and data["mode"] == "vault"
    assert data["files"] == 7 and data["indexed"] == 7 and data["pending"] == 0
    assert data["indexing"] == {"running": False}
    assert data["savings"]["searches"] == 1
    assert "Dachsanierung" not in json.dumps(data)  # never the query text


def test_snapshot_unconfigured_vault(tmp_path):
    root = copy_vault(tmp_path)
    data = snapshot(find_layout(root))
    assert data == {"version": data["version"], "configured": False, "vault_detected": True,
                    "language": "de", "root": str(root.resolve()), "name": "vault"}


def test_cloud_session_asks_for_a_source_line(layout, fake, capsys, monkeypatch):
    sync(layout, embedder=fake)
    monkeypatch.chdir(layout.root)
    monkeypatch.setenv("CLAUDE_CODE_REMOTE", "true")
    main(["session-start", "--budget", "30"])
    assert "Beende Antworten" in capsys.readouterr().out
    layout.config["anzeige"] = "aus"
    from plug_n_rag.config import save_config

    save_config(layout.config_path, layout.config)
    main(["session-start", "--budget", "30"])
    assert "Beende Antworten" not in capsys.readouterr().out
