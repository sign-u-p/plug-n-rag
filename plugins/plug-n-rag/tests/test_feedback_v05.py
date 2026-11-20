"""Fixes from the first real setup (Windows 11, collection mode, ~1,450 PDF pages)."""

import logging
import tomllib
from pathlib import Path

import tests.fixtures.make_pdf as mp
from plug_n_rag.config import init_layout
from plug_n_rag.formats.base import printed_suffix
from plug_n_rag.formats.pdf import printed_page_labels
from plug_n_rag.ingest import RenderError, ingest
from plug_n_rag.inventory import inventory, render
from plug_n_rag.search import is_reference_list, search
from plug_n_rag.sync import sync

from .conftest import FIXTURE

REPO = Path(__file__).resolve().parents[1]


def test_python_311_or_newer_required():
    data = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["requires-python"] == ">=3.11"
    assert any(d.startswith("pillow") for d in data["project"]["optional-dependencies"]["aufnahme"])
    assert 'requires-python = ">=3.11"' in (REPO / "uv.lock").read_text(encoding="utf-8")


def test_render_failure_is_reported_not_swallowed(tmp_path, monkeypatch):
    lib = tmp_path / "scans"
    lib.mkdir()
    old = mp.PAGES
    mp.PAGES = [[""], [""]]
    try:
        (lib / "scan.pdf").write_bytes(mp.build())
    finally:
        mp.PAGES = old
    layout = init_layout(lib, mode="collection", location="external", provider="fake",
                         extra={"abschriften": {"ort": "intern"}})
    import plug_n_rag.ingest as ing

    def broken(pdf, page, out_png, dpi=200):
        raise RenderError("Python-Paket fehlt (PIL); pdftoppm nicht installiert")

    monkeypatch.setattr(ing, "_render_page", broken)
    out = ingest(layout, [lib / "scan.pdf"], transcribe="erlaubt")
    assert "FEHLER: Für 2 Seiten konnten keine Seitenbilder erzeugt werden" in out
    assert "PIL" in out and '"batches": []' not in out


def test_inventory_counts_pdf_text_in_collections(tmp_path):
    lib = tmp_path / "Fachliteratur"
    lib.mkdir()
    (lib / "Leitfaden.pdf").write_bytes((FIXTURE / "quellen" / "Leitfaden Sanierung.pdf").read_bytes())
    (lib / "notizen.txt").write_text("Wort " * 400, encoding="utf-8")
    inv = inventory(lib)
    assert inv["pdf_tokens"] > 50 and inv["text_tokens"] > 300
    coll = inv["estimate_collection"]
    assert coll["tokens"] >= inv["pdf_tokens"] + inv["text_tokens"]
    assert coll["chunks"] >= 3  # at least one per PDF page plus the text file
    assert inv["estimate"] == coll  # no .obsidian: collection estimate is the main one
    text = render(inv)
    assert "Schätzung Sammlungs-Modus" in text and "mit Textebene 2 Seiten" in text


def test_pypdf_warnings_are_silenced():
    assert logging.getLogger("pypdf").getEffectiveLevel() >= logging.ERROR


BIB = """Berger, A. (2012). Bauphysik im Altbau. 3. Aufl. Stuttgart: Fraunhofer IRB Verlag.
Keller, M. (2009). Feuchte und Schimmel in Wohnräumen. Berlin: Beuth.
Lang, S., Roth, P. & Weber, T. (2015). Energieberatung. 5. Aufl. Köln: Rudolf Müller. ISBN 978-3-481-00000-0.
Novak, H. J. & Brandt, E. (2004). Lüften im Wohnungsbau. Kassel: Bauverlag.
Sommer, R. C. (2014). Wirksamkeit von Dachdämmungen im Bestand. Bauphysik,
36(5), S. 1–10. doi:10.1002/bapi.2014.012345"""


def test_reference_list_detection():
    assert is_reference_list("", BIB)
    assert is_reference_list("Buch > Literaturverzeichnis", "kurz")
    prose = ("Die Gruppe plant gemeinsam, welche Aufgaben im Mittelpunkt stehen. Nach Keller (2009) "
             "lohnt die Begehung in der gewohnten Umgebung. Die Leitung achtet auf Rollen, Ziele und "
             "Zeitrahmen, damit alle Teilnehmenden aktiv werden können und Erfolge erleben.")
    assert not is_reference_list("Gruppenplanung", prose)


def test_reference_list_is_demoted_in_search(layout, fake):
    (layout.root / "wissen" / "Literatur.md").write_text("# Literatur\n\n" + BIB, encoding="utf-8")
    sync(layout, embedder=fake)
    out = search(layout, "Bauphysik Altbau Dämmung Berger", purpose="recherche", embedder=fake)
    if "wissen/Literatur.md" in out:
        assert "Literaturliste" in out
        assert out.index("wissen/Literatur.md") > out.index("1.")
    explicit = search(layout, "Literatur zu Berger", embedder=fake)
    assert "Literaturliste" not in explicit


def test_printed_page_numbers_from_page_text():
    pages = [f"Kapitel\nText auf der Seite\n{i + 10}" for i in range(1, 9)]
    labels = printed_page_labels(_NoLabels(), pages)
    assert labels[0] == "11" and labels[7] == "18"
    assert printed_suffix({"page_labels": labels}, "pages", 1, 2) == " (gedruckt S. 11–12)"
    assert printed_suffix({"page_labels": labels}, "pages", 3, 3) == " (gedruckt S. 13)"
    assert printed_suffix({}, "pages", 1, 1) == ""
    assert printed_page_labels(_NoLabels(), ["ohne Zahl"] * 5) is None


class _NoLabels:
    trailer = {"/Root": {}}
