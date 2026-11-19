from plug_n_rag.chunk import chunk_document
from plug_n_rag.formats import load_document
from plug_n_rag.formats.markdown import parse_markdown

from .conftest import FIXTURE


def test_markdown_frontmatter_tags_links_headings():
    p = FIXTURE / "wissen" / "Sensorische Integration.md"
    doc, h = load_document(p, "wissen/Sensorische Integration.md", "markdown", None)
    assert h.startswith("sha256:")
    assert doc.title == "Sensorische Integration"
    assert doc.explicit_title == "Sensorische Integration"
    assert {"paediatrie", "sensorik", "betätigungsorientiert"} <= set(doc.tags)
    assert "Ayres" in doc.links and "Modulationsstörungen" in doc.links
    heads = [(o.heading, o.level) for o in doc.outline]
    assert ("Grundlagen", 2) in heads and ("Modulation", 3) in heads
    mod = next(s for s in doc.sections if s.heading == "Modulation")
    assert mod.heading_path == "Sensorische Integration > Grundlagen > Modulation"
    lines = p.read_text(encoding="utf-8").splitlines()
    assert lines[mod.start - 1].startswith("### Modulation")
    assert doc.meta.get("typ") == "wissen"
    assert not doc.private


def test_wikilink_with_heading_and_alias():
    doc = parse_markdown("x.md", "Siehe [[Sensorische Integration#Alltagsstrategien|Alltag]] und ![[Bild.png]]")
    assert doc.links[0] == "Sensorische Integration"


def test_private_frontmatter():
    doc = parse_markdown("a.md", "---\nprivat: true\n---\n# Geheim\nText")
    assert doc.private
    doc = parse_markdown("a.md", "---\nprivate: ja\n---\nText")
    assert doc.private


def test_headings_in_code_blocks_are_ignored():
    doc = parse_markdown("a.md", "# Echt\n\n```\n# kein Titel\n```\n\n## Zwei\nText")
    assert [o.heading for o in doc.outline] == ["Echt", "Zwei"]


def test_pdf_with_text_layer_has_pages():
    p = FIXTURE / "quellen" / "Leitlinie Ergotherapie.pdf"
    doc, _ = load_document(p, "quellen/Leitlinie Ergotherapie.pdf", "pdf", None)
    assert doc.unit == "pages" and doc.total_units == 2
    assert doc.meta["author"] == "Testautorin"
    text = " ".join(b.text for s in doc.sections for b in s.blocks)
    assert "Hilfsmittelversorgung" in text and "Gespräch über die Betätigungen" in text
    chunks = chunk_document(doc)
    assert all(1 <= c.start <= c.end <= 2 for c in chunks)


def test_empty_note_gets_stub_chunk():
    doc = parse_markdown("themen/Leere Notiz.md", "")
    chunks = chunk_document(doc)
    assert len(chunks) == 1 and chunks[0].stub
    assert "Leere Notiz" in chunks[0].embed_text


def test_long_section_is_split_with_positions():
    p = FIXTURE / "themen" / "Handlungsplanung.md"
    doc, _ = load_document(p, "themen/Handlungsplanung.md", "markdown", None)
    chunks = [c for c in chunk_document(doc) if c.heading_path.endswith("Intervention")]
    assert len(chunks) >= 2
    lines = p.read_text(encoding="utf-8").splitlines()
    for c in chunks:
        assert c.tokens <= 600
        first_text_line = next(i for i in range(c.start, c.end + 1) if lines[i - 1].strip() and not lines[i - 1].startswith("#"))
        assert lines[first_text_line - 1].strip()[:30] in c.text
    # overlap: consecutive pieces may share a paragraph, but positions never go backwards past start
    assert chunks[1].start >= chunks[0].start


def test_chunk_hash_ignores_file_name_and_folder():
    text = "# Titel\n\n## Teil\nGleicher Inhalt hier."
    a = chunk_document(parse_markdown("a/Eins.md", text))
    b = chunk_document(parse_markdown("b/Zwei.md", text))
    assert [c.hash for c in a] == [c.hash for c in b]
    # but the explicit title is part of the hash
    c = chunk_document(parse_markdown("a/Eins.md", text.replace("# Titel", "# Anderer Titel")))
    assert a[-1].hash != c[-1].hash


def test_embed_text_has_breadcrumb():
    doc = parse_markdown("wissen/si.md", "---\ntitle: SI\n---\n## Grundlagen\nText dazu.")
    ch = chunk_document(doc)[0]
    assert ch.embed_text.startswith("si > SI > Grundlagen\n\n")
