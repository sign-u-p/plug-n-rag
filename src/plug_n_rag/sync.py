"""Hash-based reconciliation of source files and index files (``plug-n-rag sync``).

Idempotent: a second run right after the first does nothing. Works on the working tree,
not on git history, so uncommitted changes are included. Renames and moves need no special
handling: the old index file is removed as an orphan, the new one is written, and every
vector comes from the hash pool of existing index files.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import index_store as ix
from .chunk import chunk_document
from .config import Layout
from .embed import Embedder, EmbeddingUnavailable, dims_for, get_embedder, model_id_for
from .formats import ExtractionError, load_document
from .formats.base import NeedsTranscription
from .scan import scan
from .util import atomic_write_json, file_lock, read_json, sha256_bytes


@dataclass
class SyncReport:
    added: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    unchanged: int = 0
    embedded_chunks: int = 0
    reused_chunks: int = 0
    private_removed: list[str] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)
    awaiting: list[str] = field(default_factory=list)  # scanned files waiting for "aufnehmen"
    pending: list[str] = field(default_factory=list)  # not indexed yet (budget/provider)
    embed_error: str | None = None
    model_mismatch: tuple[str, str] | None = None  # (configured, index)
    too_large: list[str] = field(default_factory=list)
    elapsed: float = 0.0
    total_files: int = 0

    @property
    def changed(self) -> bool:
        return bool(self.added or self.updated or self.removed or self.private_removed)


def _state_path(layout: Layout) -> Path:
    return layout.cache_dir / "state.json"


def _errors_path(layout: Layout) -> Path:
    return layout.cache_dir / "errors.json"


def current_meta(layout: Layout) -> tuple[dict, bool]:
    """Return (meta, mismatch). Creates meta for a fresh index."""
    want_model = model_id_for(layout.config)
    meta = ix.read_meta(layout.index_dir)
    if meta is None:
        meta = ix.make_meta(want_model, dims_for(layout.config))
        ix.write_meta(layout.index_dir, meta)
        return meta, False
    return meta, meta.get("model") != want_model


def file_hashes(layout: Layout, files, state: dict) -> dict[str, str]:
    """Hash files, reusing cached hashes when mtime and size are unchanged."""
    cached = state.get("files", {})
    out: dict[str, str] = {}
    new_cache: dict[str, dict] = {}
    for f in files:
        c = cached.get(f.rel)
        if c and c.get("mtime") == f.mtime and c.get("size") == f.size:
            h = c["hash"]
        else:
            try:
                h = sha256_bytes(f.abs.read_bytes())
            except OSError:
                continue
        out[f.rel] = h
        new_cache[f.rel] = {"mtime": f.mtime, "size": f.size, "hash": h}
    state["files"] = new_cache
    return out


def _load_records(layout: Layout, state: dict) -> dict[str, tuple[Path, dict | None]]:
    """Map source -> (index path, cheap header or None if unreadable)."""
    out: dict[str, tuple[Path, dict | None]] = {}
    headers = state.get("index", {})
    new_headers: dict[str, dict] = {}
    for p in ix.iter_index_files(layout.index_dir):
        src = ix.source_of(layout.index_dir, p)
        try:
            mt = p.stat().st_mtime
        except OSError:
            continue
        h = headers.get(src)
        if h and h.get("mtime") == mt:
            out[src] = (p, h)
            new_headers[src] = h
            continue
        rec = ix.read_index(p)
        if rec is None:
            out[src] = (p, None)
            continue
        h = {"mtime": mt, "file_hash": rec.get("file_hash"), "model": rec.get("model"),
             "extract": rec.get("extract")}
        out[src] = (p, h)
        new_headers[src] = h
    state["index"] = new_headers
    return out


def build_pool(layout: Layout, model: str) -> dict[str, str]:
    """chunk hash -> encoded vector, from every index file made with ``model``."""
    pool: dict[str, str] = {}
    for p in ix.iter_index_files(layout.index_dir):
        rec = ix.read_index(p)
        if not rec or rec.get("model") != model:
            continue
        for c in rec.get("chunks", []):
            if c.get("hash") and c.get("vec"):
                pool[c["hash"]] = c["vec"]
    return pool


def sync(
    layout: Layout,
    *,
    embedder: Embedder | None = None,
    time_budget: float | None = None,
    force: bool = False,
    progress: Callable[[str], None] | None = None,
    hydrate_after: bool = True,
    lock_wait: float = 30.0,
) -> SyncReport:
    layout.ensure_dirs()
    with file_lock(layout.lock_path, wait=lock_wait):
        report = _sync_locked(layout, embedder, time_budget, force, progress)
    if hydrate_after:
        from .db import hydrate

        hydrate(layout)
    return report


def _sync_locked(layout, embedder, time_budget, force, progress) -> SyncReport:
    t0 = time.monotonic()
    report = SyncReport()
    state = read_json(_state_path(layout), {}) or {}
    meta, mismatch = current_meta(layout)
    if mismatch:
        report.model_mismatch = (model_id_for(layout.config), meta.get("model", "?"))
    model = meta["model"]

    sr = scan(layout)
    report.too_large = sr.too_large
    report.total_files = len(sr.files)
    hashes = file_hashes(layout, sr.files, state)
    records = _load_records(layout, state)
    private_cache: dict[str, str] = state.get("private", {})
    new_private: dict[str, str] = {}

    # Privacy first: index files of private or excluded sources are removed immediately.
    present = {f.rel for f in sr.files}
    for src in list(records):
        if src in sr.private_paths:
            ix.delete_index(layout.index_dir, src)
            report.private_removed.append(src)
            records.pop(src)

    todo = []
    for f in sr.files:
        h = hashes.get(f.rel)
        if h is None:
            continue
        if private_cache.get(f.rel) == h:
            new_private[f.rel] = h
            continue
        _, head = records.get(f.rel, (None, None))
        current = head is not None and ix.record_is_current(head, h, meta, f.fmt)
        if current and not force:
            report.unchanged += 1
            continue
        todo.append((f, h, f.rel in records))
    todo.sort(key=lambda t: -t[0].mtime)  # newest first

    errors: dict[str, str] = {}
    pool: dict[str, str] | None = None
    embed_ok = not mismatch
    progress_path = layout.cache_dir / "progress.json"
    last_progress = time.monotonic()
    for n, (f, h, existed) in enumerate(todo):
        if time_budget is not None and time.monotonic() - t0 > time_budget:
            report.pending.extend(t[0].rel for t in todo[n:])
            break
        try:
            doc, _ = load_document(f.abs, f.rel, f.fmt, layout.cache_dir, layout.transcripts_dir)
        except NeedsTranscription:
            report.awaiting.append(f.rel)
            continue
        except (ExtractionError, OSError) as exc:
            errors[f.rel] = str(exc)
            continue
        if doc.private:
            new_private[f.rel] = h
            if ix.delete_index(layout.index_dir, f.rel):
                report.private_removed.append(f.rel)
            records.pop(f.rel, None)
            continue
        if not embed_ok:
            report.pending.append(f.rel)
            continue
        chunks = chunk_document(doc)
        if pool is None:
            pool = build_pool(layout, model)
        missing = [c for c in chunks if c.hash not in pool]
        if missing:
            try:
                if embedder is None:
                    embedder = get_embedder(layout.config)
                vecs = embedder.embed([c.embed_text for c in missing], "document")
            except EmbeddingUnavailable as exc:
                report.embed_error = str(exc)
                embed_ok = False
                report.pending.append(f.rel)
                continue
            for c, v in zip(missing, vecs):
                pool[c.hash] = ix.encode_vec(v)
            report.embedded_chunks += len(missing)
        report.reused_chunks += len(chunks) - len(missing)
        rec = ix.build_index_record(doc, h, model, chunks, pool)
        ix.write_index(layout.index_dir, rec)
        (report.updated if existed else report.added).append(f.rel)
        if progress:
            progress(f"{n + 1}/{len(todo)} {f.rel}")
        now = time.monotonic()
        if now - last_progress > 2.0:  # for the display mod: progress of long runs
            last_progress = now
            atomic_write_json(progress_path, {"done": n + 1, "total": len(todo), "t": time.time()}, indent=None)

    # Orphans: sources that no longer exist (deleted, renamed, excluded).
    # While files are pending their vectors may still be needed, so only excluded/
    # private orphans are removed then; deleted ones wait for the next complete run.
    for src in list(records):
        if src in present:
            continue
        if report.pending and src not in sr.private_paths:
            # keep the vectors around for a pending rename; excluded files still go
            from .scan import matches_any

            if not matches_any(src, layout.config.get("exclude", [])):
                continue
        ix.delete_index(layout.index_dir, src)
        report.removed.append(src)

    state["private"] = new_private
    # index headers are refreshed lazily next run (mtime changed)
    atomic_write_json(_state_path(layout), state, indent=None)
    old_errors = read_json(_errors_path(layout), {}) or {}
    merged = {k: v for k, v in old_errors.items() if k in present and k not in {t[0].rel for t in todo}}
    merged.update(errors)
    atomic_write_json(_errors_path(layout), merged)
    report.errors = errors
    try:
        progress_path.unlink()
    except OSError:
        pass
    atomic_write_json(layout.cache_dir / "pending.json", {
        "pending": report.pending, "embed_error": report.embed_error,
        "model_mismatch": list(report.model_mismatch) if report.model_mismatch else None,
        "too_large": report.too_large,
        "awaiting": report.awaiting,
    })
    report.elapsed = time.monotonic() - t0
    return report


def reindex(layout: Layout, *, embedder: Embedder | None = None, progress=None) -> SyncReport:
    """Full re-index, e.g. after a model change. Rewrites ``_meta.json`` for the configured model."""
    layout.ensure_dirs()
    want = model_id_for(layout.config)
    old = ix.read_meta(layout.index_dir) or {}
    created = old.get("created") if old.get("model") == want else None
    ix.write_meta(layout.index_dir, ix.make_meta(want, dims_for(layout.config), created))
    db = layout.db_path
    if db.exists():
        db.unlink()
    return sync(layout, embedder=embedder, force=True, progress=progress)


def pending_count(layout: Layout) -> tuple[int, int]:
    """(files needing indexing, total files) without embedding anything."""
    state = read_json(_state_path(layout), {}) or {}
    meta = ix.read_meta(layout.index_dir) or {"model": model_id_for(layout.config)}
    sr = scan(layout)
    hashes = file_hashes(layout, sr.files, dict(state))
    records = _load_records(layout, dict(state))
    private_cache = state.get("private", {})
    todo = 0
    total = 0
    for f in sr.files:
        h = hashes.get(f.rel)
        if h is None or private_cache.get(f.rel) == h:
            continue
        total += 1
        _, head = records.get(f.rel, (None, None))
        if not (head and ix.record_is_current(head, h, meta, f.fmt)):
            todo += 1
    return todo, total

