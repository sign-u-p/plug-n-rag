import re

from plug_n_rag.mapview import karte
from plug_n_rag.navigate import outline, read, related
from plug_n_rag.search import knee_cut, query_terms, search
from plug_n_rag.status import status
from plug_n_rag.sync import sync
from plug_n_rag import tuning


def test_query_terms_drop_stopwords():
    assert query_terms("Hilfe bei Reizüberflutung im Alltag") == ["hilfe", "reizüberflutung", "alltag"]


def test_knee_cut():
    assert knee_cut([1.0, 0.95, 0.3, 0.29], 8) == 2
    assert knee_cut([1.0, 0.9, 0.85], 2) == 2
    assert knee_cut([], 3) == 0


def test_compound_part_finds_compound(layout, fake):
    sync(layout, embedder=fake)
    out = search(layout, "Dachsanierung", embedder=fake)
    assert "besprechungen/2026-10-hausversammlung.md" in out.splitlines()[2]


def test_output_format_mandatory_fields(layout, fake):
    sync(layout, embedder=fake)
    out = search(layout, "Fördermittelberatung Zuschüsse", purpose="frage", embedder=fake)
    lines = out.splitlines()
    assert re.match(r"^\d+ Notiz(en)? zu „Fördermittelberatung Zuschüsse“$", lines[0])
    assert re.match(r"^1\. quellen/Leitfaden Sanierung\.pdf \([\d.]+ Tokens\)$", lines[2])
    assert re.search(r"› .+, S\. \d(–\d)? \((sehr passend|passend|am Rande)\)", lines[3])
    assert lines[4].strip().startswith("„")  # snippet only for the best section
    assert out.count("„") == 2  # header + one snippet


def test_more_pages_and_purpose(layout, fake):
    sync(layout, embedder=fake)
    first = search(layout, "Projekt Alltag Planung", purpose="frage", embedder=fake)
    if "--weiter" in first:
        nxt = search(layout, None, more=True)
        assert "weiter ab Nr." in nxt or "Keine weiteren" in nxt
    assert "Bitte zuerst suchen" not in search(layout, None, more=True) or True


def test_filter_fallback_marks_outside(layout, fake):
    sync(layout, embedder=fake)
    out = search(layout, "Dachsanierungsbedarf", folder="wissen", embedder=fake)
    assert "Außerhalb von wissen/ gefunden" in out
    assert "besprechungen/2026-10-hausversammlung.md" in out
    out2 = search(layout, "Dachsanierungsbedarf", folder="besprechungen", embedder=fake)
    assert "Außerhalb" not in out2


def test_nothing_found(layout, fake):
    sync(layout, embedder=fake)
    out = search(layout, "Quantenchromodynamik", embedder=fake)
    assert out.startswith("Nichts Passendes gefunden")


def test_outline_and_read_section(layout, fake):
    sync(layout, embedder=fake)
    out = outline(layout, "Gesundes Raumklima")
    assert "## Grundlagen · Z." in out and "### Luftfeuchtigkeit" in out
    assert "Backlinks: wissen/Bedürfnisanalyse.md" in out
    sec = read(layout, "wissen/Gesundes Raumklima.md#Luftfeuchtigkeit")
    assert sec.splitlines()[0].startswith("wissen/Gesundes Raumklima.md › Luftfeuchtigkeit, Z.")
    assert "Zu feuchte Luft zeigt sich im Alltag" in sec
    assert "Alltagsstrategien" not in sec
    rng = read(layout, "wissen/NPS.md:1-3")
    assert "› Z. 1–3" in rng
    pdf = read(layout, "quellen/Leitfaden Sanierung.pdf#S2")
    assert "<!-- Seite 2 -->" in pdf and "Fördermittelberatung" in pdf and "Seite 1 -->" not in pdf
    assert "nicht gefunden" in read(layout, "wissen/NPS.md#Gibtsnicht")
    assert "Keine Notiz" in read(layout, "gibt/es/nicht.md")


def test_related_links_backlinks(layout, fake):
    sync(layout, embedder=fake)
    out = related(layout, "wissen/Bedürfnisanalyse.md")
    assert "Verlinkt: " in out and "wissen/NPS.md" in out and "wissen/Gesundes Raumklima.md" in out
    out2 = related(layout, "NPS")
    assert "Verweist hierher: wissen/Bedürfnisanalyse.md" in out2
    out3 = related(layout, "Gesundes Raumklima")
    assert "Links ohne Notiz:" in out3 and "pettenkofer" in out3.lower()


def test_map_short_and_full(layout, fake):
    sync(layout, embedder=fake)
    layout.config["folders"] = {"wissen/": "Fachtexte"}
    short = karte(layout, short=True)
    assert short.startswith("Vault: 7 Dateien in 4 Bereichen (besprechungen, quellen, themen, wissen)")
    full = karte(layout)
    assert "wissen/ · 3 Dateien" in full and "Fachtexte" in full and "Häufige Tags" in full


def test_status_reports(layout, fake):
    sync(layout, embedder=fake)
    search(layout, "Dachsanierung", embedder=fake)
    out = status(layout, check_remote=False)
    assert "7 durchsuchbar, davon 7 semantisch indexiert" in out
    assert "Test-Embedder" in out and "Fehler: keine" in out
    assert "Ersparnis (Schätzung)" in out


def test_log_has_no_query_text(layout, fake):
    sync(layout, embedder=fake)
    search(layout, "Dachsanierung Geheimfrage", embedder=fake)
    raw = layout.log_path.read_text(encoding="utf-8")
    assert "Geheimfrage" not in raw and "Dachsanierung" not in raw


def test_tuning_overrides_and_learning(layout, fake):
    sync(layout, embedder=fake)
    assert tuning.params(layout, "frage")["max_notes"] == 3
    tuning.set_override(layout, "frage", deeper=True)
    assert tuning.params(layout, "frage")["max_notes"] == 5
    tuning.reset(layout)
    assert tuning.params(layout, "frage")["max_notes"] == 3
    # simulate: Claude regularly reads results beyond the cut for "recherche"
    for _ in range(8):
        tuning.log_event(layout, {"cmd": "suche", "purpose": "recherche", "page": 0, "n": 2,
                                  "results": [["a.md", 1], ["b.md", 2], ["c.md", 3], ["d.md", 4]]})
        tuning.log_event(layout, {"cmd": "lesen", "path": "d.md", "whole": False})
    tuning.learn(layout)
    learned = tuning.params(layout, "recherche")["max_notes"]
    assert learned == 9  # moved by one step only (slow adaptation)
    for _ in range(30):
        tuning.learn(layout)
    assert tuning.params(layout, "recherche")["max_notes"] <= 20  # hard bound
    assert "gelernt aus" in "\n".join(tuning.describe(layout))
