import json

import tests.fixtures.make_pdf as mp
from plug_n_rag.config import init_layout
from plug_n_rag.ingest import complete, ingest, word_share
from plug_n_rag.search import search
from plug_n_rag.sync import sync


def _scan_pdf(path, pages=2):
    old = mp.PAGES
    mp.PAGES = [[""] for _ in range(pages)]
    try:
        path.write_bytes(mp.build())
    finally:
        mp.PAGES = old


def test_word_share():
    assert word_share("Die Befunderhebung beginnt mit einem Gespräch.") > 0.9
    assert word_share("§$% ~~ |||| 0x9f ##") < 0.3


def test_text_layer_pdf_becomes_new_note_in_vault(layout, fake):
    pdf = layout.root / "quellen" / "Leitlinie Ergotherapie.pdf"
    before = sorted(p.name for p in pdf.parent.iterdir())
    out = ingest(layout, [pdf])
    assert "Textebene 2" in out and "offen 0" in out
    note = layout.root / "quellen" / "Leitlinie Ergotherapie.md"
    text = note.read_text(encoding="utf-8")
    assert text.startswith('---\nquelle: "quellen/Leitlinie Ergotherapie.pdf"\ntranskription: text')
    assert "<!-- Seite 2 -->" in text and "Hilfsmittelversorgung" in text
    assert sorted(p.name for p in pdf.parent.iterdir()) == sorted(before + ["Leitlinie Ergotherapie.md"])
    # a second run never overwrites
    again = ingest(layout, [pdf])
    assert "nichts überschrieben" in again or "Transkription).md" in again


def test_scanned_pdf_asks_first_then_uses_subagent_pages(layout, fake):
    pdf = layout.root / "quellen" / "Scan.pdf"
    _scan_pdf(pdf, pages=2)
    out = ingest(layout, [pdf])
    assert "FRAGE AN NUTZER:IN: 2 Seiten" in out and "an Anthropic" in out
    assert not (layout.root / "quellen" / "Scan.md").exists()
    out = ingest(layout, [pdf], transcribe="erlaubt")
    plan = json.loads(next(ln for ln in out.splitlines() if ln.startswith("{")))
    assert len(plan["batches"]) == 1 and len(plan["batches"][0]) == 2
    assert all(p.endswith(".png") for p in plan["batches"][0])
    assert str(layout.cache_dir) in plan["pages_dir"]  # images stay in the local cache
    # simulate the transkription subagent
    from pathlib import Path

    pages = Path(plan["pages_dir"])
    pages.mkdir(parents=True, exist_ok=True)
    (pages / "0001.md").write_text("<!-- Seite 1 -->\nHandschriftlicher Befund: Feinmotorik [unleserlich].", encoding="utf-8")
    (pages / "0002.md").write_text("<!-- Seite 2 -->\nEmpfehlung: Ergotherapie zweimal wöchentlich.", encoding="utf-8")
    out = complete(layout, [pdf], "haiku")
    assert "2 transkribierte Seiten" in out
    note = (layout.root / "quellen" / "Scan.md").read_text(encoding="utf-8")
    assert "transkription: haiku" in note and "Feinmotorik" in note
    sync(layout, embedder=fake)
    assert "quellen/Scan.md" in search(layout, "Feinmotorik Befund", embedder=fake)


def test_collection_transcription_stays_in_cache(tmp_path, fake):
    lib = tmp_path / "Bibliothek"
    lib.mkdir()
    _scan_pdf(lib / "alt.pdf", pages=1)
    layout = init_layout(lib, mode="collection", location="external", provider="fake")
    out = ingest(layout, [lib / "alt.pdf"], transcribe="lokal")
    assert "im lokalen Cache" in out
    assert sorted(p.name for p in lib.iterdir()) == ["alt.pdf"]
