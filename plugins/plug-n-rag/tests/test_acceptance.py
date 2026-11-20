"""SPEC acceptance criteria for version 1, run with the real local model (multilingual-e5-small).

The model is downloaded once (about 470 MB) into ~/.cache/plug-n-rag/models.
Skip with: pytest -m "not model"
"""

import shutil

import pytest

from plug_n_rag import index_store as ix
from plug_n_rag.config import find_layout
from plug_n_rag.search import search
from plug_n_rag.sync import sync

from .conftest import FIXTURE, copy_vault, make_layout

pytestmark = pytest.mark.model


class Counting:
    """Wraps a real embedder and counts document embeddings."""

    def __init__(self, inner):
        self.inner = inner
        self.model_id = inner.model_id
        self.dims = inner.dims
        self.min_similarity = inner.min_similarity
        self.strong_similarity = inner.strong_similarity
        self.documents = 0
        self.queries = 0

    def embed(self, texts, kind="document"):
        if kind == "document":
            self.documents += len(texts)
        else:
            self.queries += len(texts)
        return self.inner.embed(texts, kind)


@pytest.fixture(scope="module")
def real_embedder():
    from plug_n_rag.embed import EmbeddingUnavailable
    from plug_n_rag.embed.local import LocalEmbedder

    emb = LocalEmbedder("intfloat/multilingual-e5-small")
    try:
        emb.embed(["test"], "query")
    except EmbeddingUnavailable as exc:
        pytest.skip(f"Lokales Modell nicht verfügbar: {exc}")
    return emb


@pytest.fixture
def real(tmp_path, real_embedder):
    root = copy_vault(tmp_path)
    layout = make_layout(root, provider="local")
    emb = Counting(real_embedder)
    sync(layout, embedder=emb)
    return layout, emb


def test_rename_triggers_no_new_embedding(real):
    layout, emb = real
    before = emb.documents
    shutil.move(layout.root / "wissen" / "Bedürfnisanalyse.md", layout.root / "themen" / "Analyse der Bedürfnisse.md")
    r = sync(layout, embedder=emb)
    assert emb.documents == before
    assert r.embedded_chunks == 0 and r.reused_chunks > 0
    out = search(layout, "Vorgehen nach Kano", embedder=emb)
    assert "themen/Analyse der Bedürfnisse.md" in out


def test_delete_removes_index_file(real):
    layout, emb = real
    (layout.root / "wissen" / "NPS.md").unlink()
    sync(layout, embedder=emb)
    assert not ix.index_path(layout.index_dir, "wissen/NPS.md").exists()


def test_fresh_cloud_session_is_ready_without_embedding(real, tmp_path):
    layout, emb = real
    # A fresh clone: same files and index files, but no local cache/database.
    clone = tmp_path / "clone"
    shutil.copytree(layout.root, clone, ignore=shutil.ignore_patterns("cache"))
    assert not (clone / ".plug-n-rag" / "cache").exists()
    fresh = find_layout(clone)
    counting = Counting(emb.inner)
    r = sync(fresh, embedder=counting)
    assert counting.documents == 0 and r.embedded_chunks == 0 and not r.changed
    out = search(fresh, "Unter dem Dach ist es morgens zu kalt", embedder=counting)
    assert "besprechungen/2026-10-hausversammlung.md" in out
    assert counting.documents == 0 and counting.queries == 1


def test_compound_dachsanierung(real):
    layout, emb = real
    out = search(layout, "Dachsanierung", embedder=emb)
    first = out.splitlines()[2]
    assert first.startswith("1. besprechungen/2026-10-hausversammlung.md")
    text = (FIXTURE / "besprechungen" / "2026-10-hausversammlung.md").read_text(encoding="utf-8")
    assert "Dachsanierungsbedarf" in text and "Dachsanierung " not in text


@pytest.mark.parametrize("question", [
    "Rezept für Apfelkuchen backen",
    "Wie lange dauert die Steuererklärung?",
    "Quantenphysik Teilchen",
])
def test_nothing_found_for_unrelated_question(real, question):
    layout, emb = real
    out = search(layout, question, embedder=emb)
    assert out.startswith("Nichts Passendes gefunden"), out


@pytest.mark.parametrize("question,expected", [
    ("Welche Aufgaben bestimmen die Projektdauer?", "themen/Projektplanung.md"),
    ("Zuschüsse für neue Fenster", "quellen/Leitfaden Sanierung.pdf"),
    ("Wie messe ich, ob Kund:innen uns weiterempfehlen würden?", "wissen/NPS.md"),
    ("Unter dem Dach ist es morgens zu kalt", "besprechungen/2026-10-hausversammlung.md"),
])
def test_semantic_questions_hit_the_right_note(real, question, expected):
    layout, emb = real
    out = search(layout, question, embedder=emb)
    assert out.splitlines()[2].startswith(f"1. {expected}"), out


def test_setup_and_sync_never_change_notes(tmp_path, real_embedder):
    root = copy_vault(tmp_path, "unberuehrt")
    notes = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    layout = make_layout(root, provider="local")
    sync(layout, embedder=Counting(real_embedder))
    search(layout, "Pufferzeit", embedder=real_embedder)
    for p, data in notes.items():
        assert p.read_bytes() == data, f"{p} wurde verändert"


def test_research_purpose_gives_breadth(real):
    layout, emb = real
    q = "Das Dachgeschoss ist kalt und feucht: was hilft, und gibt es Zuschüsse für die Dämmung?"
    frage = search(layout, q, purpose="frage", embedder=emb)
    recherche = search(layout, q, purpose="recherche", embedder=emb)
    n_frage = int(frage.split()[0])
    n_recherche = int(recherche.split()[0])
    assert frage.splitlines()[2].startswith("1. besprechungen/2026-10-hausversammlung.md")
    assert n_recherche >= 3 and n_recherche >= n_frage
    assert search(layout, "Wie lange dauert die Steuererklärung", purpose="recherche",
                  embedder=emb).startswith("Nichts Passendes")
