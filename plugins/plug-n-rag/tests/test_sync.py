import json
import shutil

from plug_n_rag import index_store as ix
from plug_n_rag.search import search
from plug_n_rag.sync import sync


def index_files(layout):
    return sorted(ix.source_of(layout.index_dir, p) for p in ix.iter_index_files(layout.index_dir))


def test_first_sync_indexes_expected_files(layout, fake):
    r = sync(layout, embedder=fake)
    files = index_files(layout)
    assert "wissen/Gesundes Raumklima.md" in files
    assert "quellen/Leitfaden Sanierung.pdf" in files
    assert "themen/Leere Notiz.md" in files
    # templates excluded, private folder and private note never indexed
    assert not any(f.startswith("Vorlagen/") for f in files)
    assert not any(f.startswith("Tagebuch/") for f in files)
    assert "besprechungen/Persönliches Gespräch.md" not in files
    assert not r.errors
    meta = ix.read_meta(layout.index_dir)
    assert meta["model"] == "fake:fake-384@1" and meta["dims"] == 384
    assert meta["chunking"] == "v1"


def test_index_file_has_no_note_text(layout, fake):
    sync(layout, embedder=fake)
    raw = ix.index_path(layout.index_dir, "wissen/NPS.md").read_text(encoding="utf-8")
    rec = json.loads(raw)
    assert "deutlich spürbar" not in raw
    assert rec["source"] == "wissen/NPS.md" and rec["file_hash"].startswith("sha256:")
    assert rec["chunks"] and all("vec" in c and "lines" in c for c in rec["chunks"])
    vec = ix.decode_vec(rec["chunks"][0]["vec"])
    assert vec.shape == (384,)


def test_sync_is_idempotent(layout, fake):
    sync(layout, embedder=fake)
    before = fake.texts_embedded
    r2 = sync(layout, embedder=fake)
    assert not r2.changed and fake.texts_embedded == before
    assert r2.embedded_chunks == 0


def test_rename_and_move_reuse_vectors(layout, fake):
    sync(layout, embedder=fake)
    before = fake.texts_embedded
    root = layout.root
    (root / "archiv").mkdir()
    shutil.move(root / "wissen" / "NPS.md", root / "archiv" / "NPS Methode.md")
    r = sync(layout, embedder=fake)
    assert fake.texts_embedded == before, "Umbenennen darf nichts neu einbetten"
    assert r.reused_chunks > 0 and r.embedded_chunks == 0
    files = index_files(layout)
    assert "wissen/NPS.md" not in files and "archiv/NPS Methode.md" in files
    out = search(layout, "Weiterempfehlung Zufriedenheit NPS", embedder=fake)
    assert "archiv/NPS Methode.md" in out and "wissen/NPS.md" not in out


def test_delete_removes_index_file(layout, fake):
    sync(layout, embedder=fake)
    (layout.root / "besprechungen" / "2026-10-hausversammlung.md").unlink()
    r = sync(layout, embedder=fake)
    assert "besprechungen/2026-10-hausversammlung.md" in r.removed
    assert not ix.index_path(layout.index_dir, "besprechungen/2026-10-hausversammlung.md").exists()
    assert "Hausversammlung" not in search(layout, "Dachsanierungsbedarf Heizlüfter", embedder=fake)


def test_edit_embeds_only_changed_chunks(layout, fake):
    sync(layout, embedder=fake)
    p = layout.root / "wissen" / "NPS.md"
    p.write_text(p.read_text(encoding="utf-8").replace("zehn Punkten", "zehn oder mehr Punkten"), encoding="utf-8")
    before = fake.texts_embedded
    r = sync(layout, embedder=fake)
    assert r.updated == ["wissen/NPS.md"]
    assert fake.texts_embedded - before == 1


def test_note_becoming_private_is_removed(layout, fake):
    sync(layout, embedder=fake)
    p = layout.root / "wissen" / "NPS.md"
    p.write_text("---\nprivat: true\n---\n" + p.read_text(encoding="utf-8"), encoding="utf-8")
    r = sync(layout, embedder=fake)
    assert "wissen/NPS.md" in r.private_removed
    assert not ix.index_path(layout.index_dir, "wissen/NPS.md").exists()
    assert "NPS" not in search(layout, "Net Promoter Score", embedder=fake)


def test_private_contents_never_searchable(layout, fake):
    sync(layout, embedder=fake)
    for word in ("Zitronenfalter", "Pfauenauge"):
        assert "Nichts Passendes gefunden" in search(layout, word, embedder=fake)
    db_bytes = layout.db_path.read_bytes()
    assert b"Zitronenfalter" not in db_bytes and b"Pfauenauge" not in db_bytes


def test_conflicted_index_file_is_recomputed(layout, fake):
    sync(layout, embedder=fake)
    p = ix.index_path(layout.index_dir, "wissen/NPS.md")
    p.write_text("<<<<<<< HEAD\n{}\n=======\n{}\n>>>>>>> other\n", encoding="utf-8")
    r = sync(layout, embedder=fake)
    assert "wissen/NPS.md" in r.updated
    assert ix.read_index(p) is not None


def test_embedding_failure_keeps_keyword_search(layout):
    from plug_n_rag.embed import EmbeddingUnavailable

    class Broken:
        model_id = "fake:fake-384@1"
        dims = 384
        min_similarity = 0.3
        strong_similarity = 0.5

        def embed(self, texts, kind):
            raise EmbeddingUnavailable("offline")

    r = sync(layout, embedder=Broken())
    assert r.embed_error and r.pending
    out = search(layout, "Dachsanierung", embedder=Broken())
    assert "besprechungen/2026-10-hausversammlung.md" in out


def test_model_mismatch_means_keyword_only(layout, fake):
    sync(layout, embedder=fake)
    meta = ix.read_meta(layout.index_dir)
    meta["model"] = "local:other@123"
    ix.write_meta(layout.index_dir, meta)
    r = sync(layout, embedder=fake)
    assert r.model_mismatch
    out = search(layout, "Dachsanierung", embedder=fake)
    assert "Suchmodus: nur Stichwort · Index passt nicht zum Modell" in out
    assert "Vorläufiges Ergebnis" in out and "/plug-n-rag:reindex" in out
    assert "2026-10-hausversammlung.md" in out


def test_time_budget_leaves_pending(layout, fake):
    r = sync(layout, embedder=fake, time_budget=0)
    assert len(r.pending) == r.total_files
    r2 = sync(layout, embedder=fake)
    assert not r2.pending and len(r2.added) == r.total_files - 1  # the private note is skipped
