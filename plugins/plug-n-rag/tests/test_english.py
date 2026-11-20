"""English: messages, options and aliases (the German texts are covered by the other tests)."""

import json

import pytest

from plug_n_rag import i18n
from plug_n_rag.cli import main
from plug_n_rag.config import find_layout

NOTES = {
    "projects/Garden plan.md": "# Garden plan\n\n## Beds\n\nTomatoes and beans along the south fence.\n\n"
                               "## Watering\n\nDrip irrigation every morning in July and August.\n",
    "reading/Deep Work.md": "---\ntags: [books]\n---\n# Deep Work\n\n## Key idea\n\n"
                            "Focused work without distraction is rare and valuable. See [[Garden plan]].\n",
    "daily/2026-11-02.md": "# Monday\n\nCalled the plumber about the leaking kitchen tap.\n",
    ".obsidian/app.json": "{}",
}


def make_vault(tmp_path):
    root = tmp_path / "vault"
    for rel, text in NOTES.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    return root


def run(capsys, *args):
    main(list(args))
    return capsys.readouterr().out


@pytest.fixture
def english(monkeypatch):
    monkeypatch.delenv("PLUG_N_RAG_LANG", raising=False)
    monkeypatch.setenv("LANG", "en_GB.UTF-8")
    monkeypatch.delenv("LC_ALL", raising=False)
    monkeypatch.delenv("LC_MESSAGES", raising=False)
    i18n.set_language(None)


def test_language_precedence(monkeypatch, english):
    assert i18n.system_language() == "en"
    monkeypatch.setenv("LANG", "de_DE.UTF-8")
    assert i18n.system_language() == "de"
    # configurations from before 0.9 have no language key: they were German
    assert i18n.from_config({"mode": "vault"}, configured=True) == "de"
    assert i18n.from_config({"language": "en"}, configured=True) == "en"
    assert i18n.from_config({"sprache": "English"}, configured=True) == "en"
    assert i18n.from_config(None, configured=False) == "de"  # from LANG
    monkeypatch.setenv("PLUG_N_RAG_LANG", "en")
    assert i18n.from_config({"language": "de"}, configured=True) == "en"


def test_english_cli_end_to_end(tmp_path, capsys, monkeypatch, english):
    root = make_vault(tmp_path)
    monkeypatch.chdir(root)
    out = run(capsys, "init", "--provider", "fake", "--language", "en", "--private", "daily/**")
    assert "Set up:" in out and "Language of messages: English" in out
    assert find_layout(root).config["language"] == "en"

    out = run(capsys, "session-start", "--budget", "30")
    assert out.startswith("Vault: 2 files in 2 areas")
    assert "`plug-n-rag map` for details" in out

    out = run(capsys, "search", "drip irrigation", "--purpose", "question")
    assert "projects/Garden plan.md" in out and "for “drip irrigation”" in out
    assert "Read: plug-n-rag read" in out
    assert "daily/" not in out  # private folders stay out of the index
    assert "Nothing relevant found" in run(capsys, "search", "quantum chromodynamics")

    out = run(capsys, "outline", "Garden plan")
    assert "## Watering" in out
    out = run(capsys, "read", "Garden plan#Watering")
    assert "every morning" in out
    out = run(capsys, "related", "Garden plan")
    assert "Deep Work" in out

    out = run(capsys, "status", "--quick")
    assert "plug-n-rag · Vault" in out and "files" in out
    out = run(capsys, "learn", "--deeper", "--purpose", "research")
    assert "Preference for “research” saved" in out
    out = run(capsys, "config", "--set", "tuning.commit_learning=true")
    assert "Configuration saved." in out and "language: en" in out
    out = run(capsys, "reindex")
    assert "Please confirm with the user" in out and "--yes" in out


def test_german_configuration_wins_over_english_system(tmp_path, capsys, monkeypatch, english):
    """An existing German vault keeps speaking German on an English computer."""
    root = make_vault(tmp_path)
    monkeypatch.chdir(root)
    run(capsys, "init", "--provider", "fake", "--sprache", "de")
    out = run(capsys, "suche", "drip irrigation")
    assert "Notiz" in out and "Lesen: plug-n-rag lesen" in out


def test_unconfigured_vault_hint_in_english(tmp_path, capsys, monkeypatch, english):
    root = make_vault(tmp_path)
    monkeypatch.chdir(root)
    out = run(capsys, "session-start")
    assert out.strip() == ("plug-n-rag: Obsidian vault detected, but not set up yet. "
                           "/plug-n-rag:setup starts the setup.")
    with pytest.raises(SystemExit):
        main(["search", "anything"])
    assert "Nothing is set up for plug-n-rag here yet" in capsys.readouterr().out


def test_inventory_and_display_data_in_english(tmp_path, capsys, monkeypatch, english):
    root = make_vault(tmp_path)
    monkeypatch.chdir(root)
    out = run(capsys, "inventory")
    assert "Inventory" in out or "files" in out
    run(capsys, "init", "--provider", "fake", "--language", "en")
    data = json.loads(run(capsys, "display-data"))
    assert data["configured"] and data["language"] == "en"


def test_english_help(capsys, monkeypatch, english):
    with pytest.raises(SystemExit):
        main(["--help"])
    out = capsys.readouterr().out
    assert "Semantic search in vaults and collections." in out
    assert "{map,karte," in out or "map (karte)" in out or "map" in out.split("positional")[0]
    with pytest.raises(SystemExit):
        main(["search", "--help"])
    assert "--purpose" in capsys.readouterr().out


def test_ingest_place_question_in_english(tmp_path, capsys, monkeypatch, english):
    root = make_vault(tmp_path)
    import shutil
    from pathlib import Path

    pdf = Path(__file__).parent / "fixtures" / "vault" / "quellen" / "Leitlinie Ergotherapie.pdf"
    shutil.copy(pdf, root / "projects" / "Guide.pdf")
    monkeypatch.chdir(root)
    run(capsys, "init", "--provider", "fake", "--language", "en", "--formats", "markdown", "pdf")
    out = run(capsys, "ingest", "projects/Guide.pdf")
    assert "QUESTION FOR THE USER" in out or "pages" in out


# --- with the real model: English works as well as German ---------------------------------

LIFE = {
    "home/Garden plan.md": "# Garden plan\n\n## Beds\n\nTomatoes, beans and courgettes along the south fence. "
                           "Rotate crops every year.\n\n## Watering\n\nDrip irrigation every morning in July and "
                           "August, mulch against evaporation.\n",
    "reading/Deep Work.md": "# Deep Work (Cal Newport)\n\n## Key idea\n\nFocused work without distraction is rare "
                            "and valuable. Schedule blocks of concentration and batch shallow tasks like e-mail.\n",
    "work/Quarterly review.md": "# Quarterly review Q3\n\n## Numbers\n\nRevenue grew 12 percent, churn stayed at "
                                "3 percent. Hiring two engineers is delayed to January.\n",
    "home/Sourdough.md": "# Sourdough\n\nFeed the starter with equal parts flour and water. Bulk fermentation "
                         "5 hours at 24 °C, then shape and proof overnight in the fridge.\n",
    "health/Running log.md": "# Running log\n\nKnee hurt after the 15 km run. Physio suggested strengthening the "
                             "hips and reducing weekly distance for two weeks.\n",
    "travel/Lisbon.md": "# Lisbon trip\n\nTram 28 is crowded; walk up to the Alfama instead. Pastéis de nata in "
                        "Belém, fado in the evening.\n",
}


@pytest.fixture(scope="module")
def english_vault(tmp_path_factory):
    from plug_n_rag.config import init_layout
    from plug_n_rag.embed import EmbeddingUnavailable
    from plug_n_rag.embed.local import LocalEmbedder
    from plug_n_rag.sync import sync

    emb = LocalEmbedder("intfloat/multilingual-e5-small")
    try:
        emb.embed(["test"], "query")
    except EmbeddingUnavailable as exc:
        pytest.skip(f"local model not available: {exc}")
    root = tmp_path_factory.mktemp("life") / "vault"
    for rel, text in LIFE.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    (root / ".obsidian").mkdir()
    layout = init_layout(root, provider="local", extra={"language": "en"})
    sync(layout, embedder=emb)
    return layout, emb


@pytest.mark.model
@pytest.mark.parametrize("question,expected", [
    ("How often should I water the vegetables?", "home/Garden plan.md"),
    ("how to stay concentrated at work", "reading/Deep Work.md"),
    ("Did we make more money last quarter?", "work/Quarterly review.md"),
    ("bread recipe", "home/Sourdough.md"),
    ("my knee hurts when jogging", "health/Running log.md"),
    ("Wie gieße ich die Tomaten?", "home/Garden plan.md"),  # German question, English note
])
def test_english_paraphrases_hit_the_right_note(english_vault, english, question, expected):
    from plug_n_rag.search import search

    layout, emb = english_vault
    i18n.use_layout(layout)
    out = search(layout, question, embedder=emb)
    assert out.splitlines()[2].startswith(f"1. {expected}"), out


@pytest.mark.model
@pytest.mark.parametrize("question", ["chocolate cake recipe", "How do I file my taxes?", "quantum physics particles"])
def test_english_nothing_found_for_unrelated_question(english_vault, english, question):
    from plug_n_rag.search import search

    layout, emb = english_vault
    i18n.use_layout(layout)
    assert search(layout, question, embedder=emb).startswith("Nothing relevant found"), question
