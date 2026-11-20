import shutil

from plug_n_rag.config import find_layout, init_layout
from plug_n_rag.navigate import read
from plug_n_rag.search import search
from plug_n_rag.sync import sync

from .conftest import FIXTURE


def _snapshot(root):
    return sorted((p.relative_to(root).as_posix(), p.stat().st_mtime) for p in root.rglob("*"))


def test_collection_external_writes_nothing_into_folder(tmp_path, fake):
    lib = tmp_path / "Fachliteratur"
    lib.mkdir()
    shutil.copy(FIXTURE / "quellen" / "Leitlinie Ergotherapie.pdf", lib / "Leitlinie.pdf")
    (lib / "notizen.txt").write_text("Hilfsmittelberatung im Sanitätshaus.\n\nZweiter Absatz zur Sitzschale.",
                                     encoding="utf-8")
    (lib / "kapitel.md").write_text("# Kapitel\n\nDie Handlungsplanung bei Dyspraxie.", encoding="utf-8")
    before = _snapshot(lib)
    layout = init_layout(lib, mode="collection", location="external", provider="fake")
    assert layout.location == "external" and not str(layout.state_dir).startswith(str(lib))
    r = sync(layout, embedder=fake)
    assert len(r.added) == 3 and not r.errors
    assert _snapshot(lib) == before, "Sammlungs-Modus darf nichts in den Ordner schreiben"
    # found again via registry
    again = find_layout(lib)
    assert again and again.location == "external" and again.mode == "collection"
    out = search(again, "Sitzschale", embedder=fake)
    assert "notizen.txt" in out and "Z. 1–3" in out
    out = search(again, "Hilfsmittelversorgung", embedder=fake)
    assert "Leitlinie.pdf" in out and "S. 2" in out
    pdf = read(again, "Leitlinie.pdf:2")
    assert "Hilfsmittelversorgung" in pdf
    assert _snapshot(lib) == before


def test_scanned_pdf_reports_error(tmp_path, fake):
    lib = tmp_path / "scans"
    lib.mkdir()
    # a PDF page without any text operator = no text layer
    import tests.fixtures.make_pdf as mp

    old = mp.PAGES
    mp.PAGES = [[""]]
    try:
        (lib / "scan.pdf").write_bytes(mp.build())
    finally:
        mp.PAGES = old
    layout = init_layout(lib, mode="collection", location="external", provider="fake")
    r = sync(layout, embedder=fake)
    # a scan is not an error: it waits for "aufnehmen"
    assert "scan.pdf" not in r.errors and r.awaiting == ["scan.pdf"]
    from plug_n_rag.status import status

    out = status(layout, check_remote=False)
    assert "wartet auf Aufnahme" in out and "Fehler: keine" in out
