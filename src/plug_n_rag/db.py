"""The volatile local search database (``<cache>/search.db``), never committed.

Built by ``hydrate`` from the source files plus the index files: text comes from the
sources, vectors from the index files (matched by chunk hash). Files without a current
index file still get full-text search, so keyword search works while embedding is pending
or the provider is unavailable.

Vector search uses sqlite-vec when the extension can be loaded and falls back to a NumPy
scan otherwise (e.g. Python builds without extension loading).
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

import numpy as np

from . import index_store as ix
from .chunk import chunk_document
from .config import Layout
from .formats import ExtractionError, load_document
from .scan import scan
from .util import file_lock, read_json

DB_SCHEMA = "3"


def _try_load_vec(conn: sqlite3.Connection) -> bool:
    try:
        import sqlite_vec

        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        return True
    except Exception:  # noqa: BLE001 - extension loading is optional
        return False


def connect(path: Path) -> tuple[sqlite3.Connection, bool]:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    has_vec = _try_load_vec(conn)
    return conn, has_vec


def _meta_get(conn, key: str, default=None):
    try:
        row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    except sqlite3.Error:
        return default
    return row[0] if row else default


def _create(conn: sqlite3.Connection, dims: int, has_vec: bool) -> None:
    conn.executescript(
        """
        DROP TABLE IF EXISTS meta; DROP TABLE IF EXISTS notes; DROP TABLE IF EXISTS chunks;
        DROP TABLE IF EXISTS links; DROP TABLE IF EXISTS vecs;
        DROP TABLE IF EXISTS chunks_fts; DROP TABLE IF EXISTS chunks_trigram;
        DROP TABLE IF EXISTS chunks_vec;
        CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE notes(
            id INTEGER PRIMARY KEY, path TEXT UNIQUE, folder TEXT, stem TEXT, title TEXT,
            tags TEXT, format TEXT, unit TEXT, tokens INTEGER, file_hash TEXT, index_sig TEXT,
            mtime REAL, outline TEXT, meta TEXT, vec BLOB);
        CREATE TABLE chunks(
            id INTEGER PRIMARY KEY, note_id INTEGER, ord INTEGER, heading_path TEXT,
            start INTEGER, "end" INTEGER, tokens INTEGER, hash TEXT, body TEXT, has_vec INTEGER);
        CREATE INDEX chunks_note ON chunks(note_id);
        CREATE TABLE links(src INTEGER, dst TEXT);
        CREATE INDEX links_dst ON links(dst);
        CREATE TABLE vecs(chunk_id INTEGER PRIMARY KEY, v BLOB);
        CREATE VIRTUAL TABLE chunks_fts USING fts5(
            body, heading_path, title, tokenize='unicode61 remove_diacritics 2');
        CREATE VIRTUAL TABLE chunks_trigram USING fts5(body, tokenize='trigram');
        """
    )
    if has_vec:
        conn.execute(
            f"CREATE VIRTUAL TABLE chunks_vec USING vec0(embedding float[{dims}] distance_metric=cosine)"
        )
    conn.executemany(
        "INSERT INTO meta VALUES(?,?)",
        [("schema", DB_SCHEMA), ("dims", str(dims)), ("vec_ext", "1" if has_vec else "0")],
    )


def _delete_note(conn, note_id: int, has_vec: bool) -> None:
    ids = [r[0] for r in conn.execute("SELECT id FROM chunks WHERE note_id=?", (note_id,))]
    for cid in ids:
        conn.execute("DELETE FROM chunks_fts WHERE rowid=?", (cid,))
        conn.execute("DELETE FROM chunks_trigram WHERE rowid=?", (cid,))
        conn.execute("DELETE FROM vecs WHERE chunk_id=?", (cid,))
        if has_vec:
            conn.execute("DELETE FROM chunks_vec WHERE rowid=?", (cid,))
    conn.execute("DELETE FROM chunks WHERE note_id=?", (note_id,))
    conn.execute("DELETE FROM links WHERE src=?", (note_id,))
    conn.execute("DELETE FROM notes WHERE id=?", (note_id,))


def hydrate(layout: Layout, *, rebuild: bool = False) -> dict:
    """Bring search.db in line with sources and index files. Incremental unless ``rebuild``."""
    t0 = time.monotonic()
    layout.ensure_dirs()
    meta = ix.read_meta(layout.index_dir) or {}
    dims = int(meta.get("dims") or 384)
    model = meta.get("model", "")
    with file_lock(layout.cache_dir / "hydrate.lock", wait=60):
        conn, has_vec = connect(layout.db_path)
        try:
            if (
                rebuild
                or _meta_get(conn, "schema") != DB_SCHEMA
                or _meta_get(conn, "dims") != str(dims)
                or _meta_get(conn, "model") != model
                or _meta_get(conn, "vec_ext") != ("1" if has_vec else "0")
            ):
                _create(conn, dims, has_vec)
                conn.execute("INSERT OR REPLACE INTO meta VALUES('model', ?)", (model,))
            stats = _hydrate(conn, layout, has_vec, model)
            conn.execute("INSERT OR REPLACE INTO meta VALUES('hydrated', ?)", (str(time.time()),))
            conn.commit()
        finally:
            conn.close()
    stats["elapsed"] = time.monotonic() - t0
    return stats


def _hydrate(conn, layout: Layout, has_vec: bool, model: str) -> dict:
    sr = scan(layout)
    state = read_json(layout.cache_dir / "state.json", {}) or {}
    cached_hash = state.get("files", {})
    private_cache = state.get("private", {})
    existing = {r["path"]: (r["id"], r["file_hash"], r["index_sig"])
                for r in conn.execute("SELECT id, path, file_hash, index_sig FROM notes")}
    seen: set[str] = set()
    added = updated = 0
    for f in sr.files:
        c = cached_hash.get(f.rel)
        fh = c["hash"] if c and c.get("mtime") == f.mtime and c.get("size") == f.size else None
        if fh is not None and private_cache.get(f.rel) == fh:
            continue
        ipath = ix.index_path(layout.index_dir, f.rel)
        try:
            isig = f"{ipath.stat().st_mtime}"
        except OSError:
            isig = "none"
        prev = existing.get(f.rel)
        if prev and fh is not None and prev[1] == fh and prev[2] == isig:
            seen.add(f.rel)
            continue
        try:
            doc, file_hash = load_document(f.abs, f.rel, f.fmt, layout.cache_dir)
        except (ExtractionError, OSError):
            continue
        if doc.private:
            continue
        if prev and prev[1] == file_hash and prev[2] == isig:
            seen.add(f.rel)
            continue
        if prev:
            _delete_note(conn, prev[0], has_vec)
            updated += 1
        else:
            added += 1
        seen.add(f.rel)
        rec = ix.read_index(ipath)
        vecs: dict[str, np.ndarray] = {}
        if rec and rec.get("model") == model:
            for ch in rec.get("chunks", []):
                if ch.get("vec"):
                    vecs[ch["hash"]] = ix.decode_vec(ch["vec"])
        _insert_doc(conn, doc, file_hash, isig, f.mtime, vecs, has_vec)
    removed = 0
    for path, (nid, _, _) in existing.items():
        if path not in seen:
            _delete_note(conn, nid, has_vec)
            removed += 1
    return {"added": added, "updated": updated, "removed": removed, "notes": len(seen)}


def _insert_doc(conn, doc, file_hash: str, isig: str, mtime: float, vecs: dict, has_vec: bool) -> None:
    folder = doc.source.split("/")[0] if "/" in doc.source else ""
    outline = [{"heading": o.heading, "level": o.level, "start": o.start, "end": o.end,
                "tokens": o.tokens} for o in doc.outline]
    chunks = chunk_document(doc)
    note_vecs = [vecs[c.hash] for c in chunks if c.hash in vecs]
    note_vec = None
    if note_vecs:
        mv = np.mean(np.stack(note_vecs), axis=0)
        mv /= (np.linalg.norm(mv) or 1.0)
        note_vec = mv.astype(np.float32).tobytes()
    cur = conn.execute(
        "INSERT INTO notes(path, folder, stem, title, tags, format, unit, tokens, file_hash,"
        " index_sig, mtime, outline, meta, vec) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (doc.source, folder, doc.stem, doc.title, " ".join(doc.tags), doc.format, doc.unit,
         doc.tokens, file_hash, isig, mtime, json.dumps(outline, ensure_ascii=False),
         json.dumps(doc.meta, ensure_ascii=False), note_vec),
    )
    note_id = cur.lastrowid
    for ord_, c in enumerate(chunks):
        v = vecs.get(c.hash)
        cc = conn.execute(
            'INSERT INTO chunks(note_id, ord, heading_path, start, "end", tokens, hash, body, has_vec)'
            " VALUES(?,?,?,?,?,?,?,?,?)",
            (note_id, ord_, c.heading_path, c.start, c.end, c.tokens, c.hash, c.text, 1 if v is not None else 0),
        )
        cid = cc.lastrowid
        conn.execute("INSERT INTO chunks_fts(rowid, body, heading_path, title) VALUES(?,?,?,?)",
                     (cid, c.text, c.heading_path, f"{doc.title} {doc.stem}"))
        conn.execute("INSERT INTO chunks_trigram(rowid, body) VALUES(?,?)",
                     (cid, f"{doc.title}\n{c.heading_path}\n{c.text}"))
        if v is not None:
            blob = np.asarray(v, dtype=np.float32).tobytes()
            conn.execute("INSERT INTO vecs(chunk_id, v) VALUES(?,?)", (cid, blob))
            if has_vec:
                conn.execute("INSERT INTO chunks_vec(rowid, embedding) VALUES(?,?)", (cid, blob))
    for link in doc.links:
        conn.execute("INSERT INTO links(src, dst) VALUES(?,?)", (note_id, link.lower()))


def open_db(layout: Layout) -> tuple[sqlite3.Connection, bool]:
    if not layout.db_path.exists():
        hydrate(layout)
    conn, has_vec = connect(layout.db_path)
    if _meta_get(conn, "vec_ext") != ("1" if has_vec else "0"):
        has_vec = False
    return conn, has_vec


def vector_search(conn, has_vec: bool, qvec: np.ndarray, k: int) -> list[tuple[int, float]]:
    """Return [(chunk_id, cosine similarity)] best first."""
    q = np.asarray(qvec, dtype=np.float32)
    if has_vec:
        try:
            rows = conn.execute(
                "SELECT rowid, distance FROM chunks_vec WHERE embedding MATCH ? AND k = ? ORDER BY distance",
                (q.tobytes(), k),
            ).fetchall()
            return [(r[0], 1.0 - float(r[1])) for r in rows]
        except sqlite3.Error:
            pass
    rows = conn.execute("SELECT chunk_id, v FROM vecs").fetchall()
    if not rows:
        return []
    ids = np.array([r[0] for r in rows])
    mat = np.frombuffer(b"".join(r[1] for r in rows), dtype=np.float32).reshape(len(rows), -1)
    sims = mat @ q
    top = np.argsort(-sims)[:k]
    return [(int(ids[i]), float(sims[i])) for i in top]


def chunk_vectors(conn, chunk_ids: list[int]) -> dict[int, np.ndarray]:
    if not chunk_ids:
        return {}
    marks = ",".join("?" * len(chunk_ids))
    return {r[0]: np.frombuffer(r[1], dtype=np.float32)
            for r in conn.execute(f"SELECT chunk_id, v FROM vecs WHERE chunk_id IN ({marks})", chunk_ids)}
