"""Search mode in every output, provisional results, --warten, readiness in status, chronology."""

import json
import os
import time

import pytest

from plug_n_rag import tuning
from plug_n_rag.embed.local import DOWNLOAD_STATE, LOCAL_MODELS, download_percent, download_state, model_dir
from plug_n_rag.navigate import related
from plug_n_rag.readiness import readiness
from plug_n_rag.search import search
from plug_n_rag.status import status
from plug_n_rag.sync import sync

from .conftest import make_layout

E5 = "intfloat/multilingual-e5-small"


@pytest.fixture
def no_model(tmp_path, monkeypatch):
    """Local provider, but the model is not on this computer (fresh cloud session)."""
    d = tmp_path / "models-empty"
    monkeypatch.setenv("PLUG_N_RAG_MODEL_DIR", str(d))
    return model_dir(E5, LOCAL_MODELS[E5]["revision"])


@pytest.fixture
def local_layout(vault_dir, fake, no_model):
    layout = make_layout(vault_dir, provider="local")
    sync(layout, embedder=fake)  # vectors exist (as in a committed index), only the query model is missing
    return layout


def _loading(mdir, pct):
    mdir.mkdir(parents=True, exist_ok=True)
    total = 470_000_000
    (mdir / DOWNLOAD_STATE).write_text(json.dumps({
        "state": "laedt", "pid": os.getppid(), "t": time.time(),
        "done_all": total * pct // 100, "total_all": total}), encoding="utf-8")


def test_complete_index_says_so(layout, fake):
    sync(layout, embedder=fake)
    out = search(layout, "Dachsanierung", embedder=fake)
    assert out.splitlines()[0].startswith("Suchmodus: semantisch + Stichwort · Index vollständig")
    assert "Vorläufig" not in out


def test_model_loading_is_named_with_progress_and_warning(local_layout, no_model, monkeypatch):
    _loading(no_model, 60)
    spawned = []
    monkeypatch.setattr("plug_n_rag.cli.spawn_background_sync", lambda *a, **k: spawned.append(k))
    out = search(local_layout, "Dachsanierung")
    lines = out.splitlines()
    assert lines[0] == "Suchmodus: nur Stichwort · Suchmodell lädt (60 %)"
    # the warning sits directly under the result head, before the hits
    assert lines[1].startswith("1 Notiz") or lines[1][0].isdigit()
    assert lines[2].startswith("⚠ Vorläufiges Ergebnis")
    assert "--warten" in lines[3] and "als vorläufig kennzeichnen" in lines[3]
    assert "besprechungen/2026-10-hausversammlung.md" in out
    assert not spawned  # a download is already running
    assert not (no_model / LOCAL_MODELS[E5]["onnx"]).exists()  # the search itself never downloads


def test_missing_model_starts_background_download(local_layout, monkeypatch):
    spawned = []
    monkeypatch.setattr("plug_n_rag.cli.spawn_background_sync", lambda *a, **k: spawned.append(k))
    out = search(local_layout, "Dachsanierung")
    assert out.splitlines()[0].startswith("Suchmodus: nur Stichwort · Suchmodell lädt")
    assert spawned == [{"load_model": True}]


def test_failed_download_is_reported(local_layout, no_model):
    no_model.mkdir(parents=True, exist_ok=True)
    (no_model / DOWNLOAD_STATE).write_text(json.dumps({"state": "fehler", "t": time.time(),
                                                       "error": "403 Forbidden"}), encoding="utf-8")
    out = search(local_layout, "Dachsanierung")
    assert out.splitlines()[0] == "Suchmodus: nur Stichwort · Suchmodell nicht ladbar"
    assert "403 Forbidden" in out and "/plug-n-rag:cloud" in out


def test_nothing_found_while_provisional_is_not_conclusive(local_layout, no_model):
    _loading(no_model, 10)
    out = search(local_layout, "Quantenchromodynamik")
    assert "Nichts Passendes gefunden" in out
    assert "kein sicheres „steht nicht in den Notizen“" in out


def test_partial_index_counts_files(layout, fake):
    sync(layout, embedder=fake)
    (layout.root / "wissen" / "Neu.md").write_text("# Neu\n\nDachsanierung im Frühjahr planen.\n", encoding="utf-8")
    r = sync(layout, embedder=fake, time_budget=0)
    assert r.pending == ["wissen/Neu.md"]
    out = search(layout, "Dachsanierung", embedder=fake)
    total = readiness(layout).total
    assert out.splitlines()[0] == (f"Suchmodus: semantisch + Stichwort, aber erst {total - 1} von {total} "
                                   "Dateien semantisch indexiert")
    assert "⚠ Vorläufiges Ergebnis: Notizen, die nur sinngemäß passen, fehlen womöglich" in out


def test_wait_finishes_the_index_first(layout, fake):
    sync(layout, embedder=fake)
    (layout.root / "wissen" / "Neu.md").write_text("# Neu\n\nDachsanierung im Frühjahr planen.\n", encoding="utf-8")
    sync(layout, embedder=fake, time_budget=0)
    out = search(layout, "Dachsanierung", embedder=fake, wait=30)
    lines = out.splitlines()
    assert lines[0].startswith("Suchmodus: semantisch + Stichwort · Index vollständig")
    assert lines[1].startswith("Hinweis: Gewartet:") and "bereit war" in lines[1]
    assert "Vorläufig" not in out
    assert "wissen/Neu.md" in out


def test_wait_gives_up_when_waiting_cannot_help(layout, fake):
    from plug_n_rag import index_store as ix

    sync(layout, embedder=fake)
    meta = ix.read_meta(layout.index_dir)
    meta["model"] = "local:other@123"
    ix.write_meta(layout.index_dir, meta)
    t0 = time.monotonic()
    out = search(layout, "Dachsanierung", embedder=fake, wait=60)
    assert time.monotonic() - t0 < 10
    assert "Index passt nicht zum Modell" in out and "/plug-n-rag:reindex" in out


def test_more_pages_point_to_a_fresh_search_once_ready(layout, fake):
    sync(layout, embedder=fake)
    (layout.root / "wissen" / "Neu.md").write_text("# Neu\n\nProjekt Alltag Planung.\n", encoding="utf-8")
    sync(layout, embedder=fake, time_budget=0)
    first = search(layout, "Projekt Alltag Planung", embedder=fake)
    sync(layout, embedder=fake)
    if "--weiter" in first:
        nxt = search(layout, None, more=True)
        assert nxt.splitlines()[0].startswith("Suchmodus: semantisch + Stichwort, aber erst")
        assert "inzwischen bereit" in nxt


def test_status_names_when_the_index_was_complete(layout, fake):
    sync(layout, embedder=fake)
    first = json.loads((layout.cache_dir / "pending.json").read_text(encoding="utf-8"))["complete_at"]
    time.sleep(0.01)
    sync(layout, embedder=fake)  # stays complete: the time is kept
    assert json.loads((layout.cache_dir / "pending.json").read_text(encoding="utf-8"))["complete_at"] == first
    out = status(layout, check_remote=False)
    assert "Semantische Suche: bereit seit heute, " in out


def test_status_while_model_loads(local_layout, no_model):
    _loading(no_model, 25)
    out = status(local_layout, check_remote=False)
    assert "Semantische Suche: noch nicht vollständig · nur Stichwort · Suchmodell lädt (25 %)" in out


def test_download_state_goes_stale(no_model):
    no_model.mkdir(parents=True, exist_ok=True)
    (no_model / DOWNLOAD_STATE).write_text(json.dumps({"state": "laedt", "t": time.time() - 600,
                                                       "done_all": 1, "total_all": 2}), encoding="utf-8")
    st = download_state(E5)
    assert st["state"] == "abgebrochen"
    assert download_percent({"done_all": 235, "total_all": 470}) == 50
    assert download_percent(None) is None


def test_provisional_searches_do_not_teach_depth(layout):
    events = [
        {"cmd": "suche", "purpose": "frage", "n": 2, "results": [["a.md", 1], ["b.md", 2], ["c.md", 3]],
         "provisional": True, "t": 1},
        {"cmd": "lesen", "path": "c.md", "t": 2},
    ]
    stats = tuning.analyse(events)
    assert stats["frage"]["searches"] == 0 and stats["frage"]["beyond"] == 0


# --- chronology ------------------------------------------------------------------------------

@pytest.fixture
def journal(layout, fake):
    d = layout.root / "log"
    d.mkdir()
    notes = {
        "2024-02-11.md": "# Sonntag\n\nSchlecht geschlafen, früh wach.\n",
        "2024-02-12.md": "# Montag\n\nSchlafverhalten besser, Abendroutine begonnen.\n",
        "2024-02-16.md": "# Freitag\n\nSchlaf stabil.\n",
        "2024-W07.md": "# Woche 7\n\nRückblick auf die Woche: Routine hilft.\n",
        "2024-02-19.md": "# Montag\n\nNeue Woche, Schlaf gut.\n",
        "Ideen.md": "# Ideen\n\nOhne Datum.\n",
    }
    for name, text in notes.items():
        (d / name).write_text(text, encoding="utf-8")
    sync(layout, embedder=fake)
    return layout


def test_chronological_listing_includes_week_note(journal, fake):
    out = search(journal, None, folder="log", since="2024-02-12", chronological=True, embedder=fake)
    lines = [ln.strip() for ln in out.splitlines()]
    order = [ln.split(" · ")[1].split(" (")[0] for ln in lines if " · log/" in ln]
    assert order == ["log/2024-W07.md", "log/2024-02-12.md", "log/2024-02-16.md", "log/2024-02-19.md"]
    assert "log/2024-02-11.md" not in out
    assert "2024-W07 (Woche ab 12.02.)" in out


def test_chronological_with_question_keeps_only_matching_notes(journal, fake):
    out = search(journal, "Schlaf", folder="log", chronological=True, embedder=fake)
    assert out.splitlines()[0].startswith("Suchmodus:")
    assert "log/Ideen.md" not in out
    assert out.index("log/2024-02-12.md") < out.index("log/2024-02-19.md")


def test_chronological_lists_undated_notes_separately(journal, fake):
    out = search(journal, None, folder="log", chronological=True, embedder=fake)
    assert "Ohne Datum im Namen oder in der Frontmatter (1): log/Ideen.md" in out


def test_related_shows_neighbours_and_week_note(journal):
    out = related(journal, "log/2024-02-12.md")
    assert "Davor: log/2024-02-11.md" in out
    assert "Danach: log/2024-02-16.md" in out
    assert "Wochennotiz 2024-W07: log/2024-W07.md" in out
    week = related(journal, "log/2024-W07.md")
    assert "Tage dieser Woche: log/2024-02-12.md, log/2024-02-16.md" in week


def test_session_start_loads_the_model_even_if_the_index_is_complete(local_layout, monkeypatch, capsys):
    """Fresh clone with a committed index: nothing to embed, but the query model is missing.

    Before 0.9.3 no background job started in this case, although the start message promised one.
    """
    from plug_n_rag import cli

    spawned = []
    monkeypatch.setattr(cli, "spawn_background_sync", lambda *a, **k: spawned.append(k))
    cli.main(["--ordner", str(local_layout.root), "session-start"])
    out = capsys.readouterr().out
    assert spawned == [{"load_model": True}]
    assert "Suchmodell wird einmalig im Hintergrund geladen" in out
    assert "--warten" in out


def test_sync_accepts_model_first_flag(layout, fake, capsys):
    from plug_n_rag import cli

    cli.main(["--ordner", str(layout.root), "sync", "--modell-vorab"])  # fake provider: nothing to load
    assert "Abgleich" in capsys.readouterr().out
