"""0.6.0: one .plug-n-rag folder everywhere, volatile data central, transcript placement."""

import json
import shutil
import subprocess

import tests.fixtures.make_pdf as mp
from plug_n_rag.cli import main
from plug_n_rag.config import find_layout, init_layout
from plug_n_rag.ingest import complete, ingest
from plug_n_rag.search import search
from plug_n_rag.sync import sync

from .conftest import copy_vault, make_layout


def _scan(path, pages=1):
    old = mp.PAGES
    mp.PAGES = [[""] for _ in range(pages)]
    try:
        path.write_bytes(mp.build())
    finally:
        mp.PAGES = old


def _fake_transcribe(out: str, text: str):
    plan = json.loads(next(ln for ln in out.splitlines() if ln.startswith("{")))
    from pathlib import Path

    pages = Path(plan["pages_dir"])
    pages.mkdir(parents=True, exist_ok=True)
    (pages / "0001.md").write_text(f"<!-- Seite 1 -->\n{text}", encoding="utf-8")


def test_vault_has_only_the_shareable_folder(layout, fake):
    sync(layout, embedder=fake)
    root = layout.root
    assert layout.config_path == root / ".plug-n-rag" / "plug-n-rag.yml"
    inside = sorted(p.relative_to(root / ".plug-n-rag").parts[0] for p in (root / ".plug-n-rag").iterdir())
    assert inside == ["index", "plug-n-rag.yml"]
    assert not (root / "plug-n-rag.yml").exists()
    assert layout.db_path.exists() and root not in layout.db_path.parents  # volatile data is central


def test_old_layout_is_still_recognised(tmp_path, fake):
    root = copy_vault(tmp_path)
    (root / ".plug-n-rag").mkdir()
    (root / "plug-n-rag.yml").write_text("embedding:\n  provider: fake\n", encoding="utf-8")
    layout = find_layout(root)
    assert layout.configured and layout.legacy
    sync(layout, embedder=fake)
    assert (root / ".plug-n-rag" / "index" / "wissen" / "COPM.md.json").exists()


def test_collection_location_defaults(tmp_path, capsys, monkeypatch):
    plain = tmp_path / "Ordner"
    plain.mkdir()
    (plain / "a.txt").write_text("Hallo", encoding="utf-8")
    main(["init", str(plain), "--modus", "sammlung", "--provider", "fake"])
    assert "zentral auf diesem Rechner" in capsys.readouterr().out
    assert sorted(p.name for p in plain.iterdir()) == ["a.txt"]
    repo = tmp_path / "Repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    main(["init", str(repo), "--modus", "sammlung", "--provider", "fake"])
    assert "(im Ordner)" in capsys.readouterr().out
    assert (repo / ".plug-n-rag" / "plug-n-rag.yml").is_file()
    choice = tmp_path / "Wahl"
    choice.mkdir()
    main(["init", str(choice), "--modus", "sammlung", "--ort", "ordner", "--provider", "fake"])
    assert (choice / ".plug-n-rag" / "plug-n-rag.yml").is_file()


def test_central_index_lives_in_data_dir_not_cache(tmp_path, fake):
    lib = tmp_path / "Lib"
    lib.mkdir()
    layout = init_layout(lib, mode="collection", location="external", provider="fake")
    assert "xdg-cache" not in str(layout.state_dir)


def test_aufnehmen_asks_for_place_once(layout, fake):
    _scan(layout.root / "quellen" / "Scan.pdf")
    out = ingest(layout, [layout.root / "quellen" / "Scan.pdf"])
    assert out.startswith("FRAGE AN NUTZER:IN (einmalig, wird gemerkt): Wohin sollen Abschriften")
    assert "neben_original" in out and "ordner" in out


def test_vault_transcripts_in_own_folder(layout, fake, capsys, monkeypatch):
    pdf = layout.root / "quellen" / "Scan.pdf"
    _scan(pdf)
    monkeypatch.chdir(layout.root)
    main(["aufnehmen", "quellen/Scan.pdf", "--ablage", "ordner", "--transkription", "erlaubt"])
    out = capsys.readouterr().out
    _fake_transcribe(out, "Befund: Feinmotorik altersgerecht.")
    found = find_layout(layout.root)
    assert found.config["abschriften"]["ort"] == "ordner"  # remembered
    msg = complete(found, [pdf], "haiku")
    note = layout.root / "Abschriften" / "quellen" / "Scan.md"
    assert note.exists() and "als neue Notiz Abschriften/quellen/Scan.md" in msg
    assert 'datei_hash: "sha256:' in note.read_text(encoding="utf-8")


def test_collection_transcript_travels_with_folder(tmp_path, fake):
    lib = tmp_path / "Bibliothek"
    lib.mkdir()
    _scan(lib / "alt.pdf")
    layout = init_layout(lib, mode="collection", location="inside", provider="fake",
                         extra={"abschriften": {"ort": "ordner"}})
    out = ingest(layout, [lib / "alt.pdf"], transcribe="erlaubt")
    _fake_transcribe(out, "Hilfsmittelberatung im Pflegeheim, handschriftlich ergänzt.")
    msg = complete(layout, [lib / "alt.pdf"], "haiku")
    assert "als lesbare Abschrift .plug-n-rag/abschriften/alt.pdf.md" in msg
    sync(layout, embedder=fake)
    assert "alt.pdf" in search(layout, "Hilfsmittelberatung Pflegeheim", embedder=fake)
    # a colleague gets a copy of the folder: no cache, no new transcription needed
    copy = tmp_path / "Kopie"
    shutil.copytree(lib, copy)
    other = find_layout(copy)
    assert other.cache_dir != layout.cache_dir and not other.db_path.exists()
    before = fake.texts_embedded
    r = sync(other, embedder=fake)
    assert not r.awaiting and not r.errors
    assert fake.texts_embedded == before  # index travelled with the folder: nothing re-embedded
    assert "alt.pdf" in search(other, "Hilfsmittelberatung Pflegeheim", embedder=fake)


def _old_vault(tmp_path, fake):
    """Build a 0.5-style vault: config in the root, cache in .plug-n-rag/cache."""
    root = copy_vault(tmp_path, "alt")
    layout = make_layout(root)
    sync(layout, embedder=fake)
    (root / ".plug-n-rag" / "plug-n-rag.yml").rename(root / "plug-n-rag.yml")
    old_cache = root / ".plug-n-rag" / "cache"
    shutil.copytree(layout.cache_dir, old_cache)
    (old_cache / "extract" / "teuer.json").parent.mkdir(parents=True, exist_ok=True)
    (old_cache / "extract" / "teuer.json").write_text('{"version": "x", "pages": ["Haiku-Abschrift"]}', encoding="utf-8")
    (root / ".plug-n-rag" / ".gitignore").write_text("# Lokaler Cache von plug-n-rag, wird nie committet\ncache/\n",
                                                     encoding="utf-8")
    shutil.rmtree(layout.cache_dir)
    return root


def test_old_cache_is_carried_over_automatically(tmp_path, fake):
    root = _old_vault(tmp_path, fake)
    layout = find_layout(root)
    assert layout.legacy
    sync(layout, embedder=fake)
    assert (layout.cache_dir / "extract" / "teuer.json").exists()  # paid transcripts survive


def test_umziehen_modernises_old_vault(tmp_path, fake, capsys, monkeypatch):
    root = _old_vault(tmp_path, fake)
    import plug_n_rag.sync as sync_mod

    monkeypatch.setattr(sync_mod, "get_embedder", lambda cfg: fake)
    before = fake.texts_embedded
    main(["--ordner", str(root), "umziehen"])
    out = capsys.readouterr().out
    assert "plug-n-rag.yml in den Ordner .plug-n-rag/ verschoben" in out
    assert sorted(p.name for p in (root / ".plug-n-rag").iterdir()) == ["index", "plug-n-rag.yml"]
    assert not (root / "plug-n-rag.yml").exists()
    assert fake.texts_embedded == before  # nothing recomputed
    layout = find_layout(root)
    assert not layout.legacy and (layout.cache_dir / "extract" / "teuer.json").exists()


def test_umziehen_between_folder_and_central(tmp_path, fake, capsys, monkeypatch):
    import plug_n_rag.sync as sync_mod

    monkeypatch.setattr(sync_mod, "get_embedder", lambda cfg: fake)
    lib = tmp_path / "Sammlung"
    lib.mkdir()
    (lib / "a.txt").write_text("Sitzschale und Rollstuhl im Alltag.", encoding="utf-8")
    layout = init_layout(lib, mode="collection", location="inside", provider="fake")
    sync(layout, embedder=fake)
    main(["--ordner", str(lib), "umziehen", "--nach", "zentral"])
    capsys.readouterr()
    assert sorted(p.name for p in lib.iterdir()) == ["a.txt"]
    central = find_layout(lib)
    assert central.location == "external" and (central.index_dir / "a.txt.json").exists()
    main(["--ordner", str(lib), "umziehen", "--nach", "ordner"])
    capsys.readouterr()
    back = find_layout(lib)
    assert back.location == "inside" and (lib / ".plug-n-rag" / "index" / "a.txt.json").exists()
    assert "a.txt" in search(back, "Sitzschale", embedder=fake)


def test_vault_refuses_central_without_confirmation(layout, capsys):
    main(["--ordner", str(layout.root), "umziehen", "--nach", "zentral"])
    assert "--trotzdem" in capsys.readouterr().out
    assert (layout.root / ".plug-n-rag" / "plug-n-rag.yml").exists()


def test_old_central_collection_in_cache_dir(tmp_path, fake, capsys, monkeypatch):
    """The real first installation: collection --extern, index and Haiku pages below ~/.cache."""
    import plug_n_rag.sync as sync_mod
    from plug_n_rag.config import register_external, save_config
    from plug_n_rag.util import user_cache_dir, user_data_dir

    monkeypatch.setattr(sync_mod, "get_embedder", lambda cfg: fake)
    lib = tmp_path / "Fachliteratur"
    lib.mkdir()
    _scan(lib / "scan.pdf")
    (lib / "text.txt").write_text("Gruppenplanung in der Ergotherapie.", encoding="utf-8")
    old_state = user_cache_dir() / "collections" / "Fachliteratur-alt"
    (old_state / "index").mkdir(parents=True)
    save_config(old_state / "plug-n-rag.yml", {"mode": "collection", "index_location": "external",
                                                "embedding": {"provider": "fake", "model": "fake-384"},
                                                "formats": ["markdown", "text", "pdf"]})
    register_external(lib, old_state)
    # paid transcript from 0.4: only in the old cache's extract folder
    from plug_n_rag.util import sha256_bytes

    h = sha256_bytes((lib / "scan.pdf").read_bytes()).replace("sha256:", "")
    ext = old_state / "cache" / "extract"
    ext.mkdir(parents=True)
    (ext / f"{h}.json").write_text(json.dumps({"version": "pdf-v1", "transcription": "haiku",
                                               "pages": ["Abgeschrieben mit Haiku: Gruppenleitung und Rollen."],
                                               "outline": [], "meta": {}}), encoding="utf-8")
    layout = find_layout(lib)
    r = sync(layout, embedder=fake)
    assert not r.awaiting, "the transcript from the old cache must still be found"
    main(["--ordner", str(lib), "umziehen"])
    out = capsys.readouterr().out
    assert "aus dem Cache-Ordner" in out
    moved = find_layout(lib)
    assert str(user_data_dir()) in str(moved.state_dir) and not old_state.exists()
    assert "scan.pdf" in search(moved, "Gruppenleitung Rollen", embedder=fake)
    assert sorted(p.name for p in lib.iterdir()) == ["scan.pdf", "text.txt"]
