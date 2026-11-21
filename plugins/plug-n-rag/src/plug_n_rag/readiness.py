"""How complete is search by meaning right now? One answer for ``suche``, ``status`` and ``--warten``.

Search by meaning needs three things: vectors for every file (index complete), an index made with
the configured model, and the query model on this computer. Until all three hold, the search runs
with keywords only or with part of the vectors, and its results are provisional. The search output
says so in every answer, so that an agent does not treat an early result as complete.
"""

from __future__ import annotations

import datetime as _dt
import os
import sqlite3
import time
from dataclasses import dataclass

from .config import Layout
from .embed import model_id_for
from .i18n import tr
from .index_store import read_meta
from .util import fmt_int, read_json

# reasons why search by meaning is not (fully) available
MODEL_LOADING = "model_loading"  # local model is being downloaded right now
MODEL_MISSING = "model_missing"  # local model not on this computer, no download running
MODEL_ERROR = "model_error"  # download or provider failed
MISMATCH = "mismatch"  # index made with another model
NO_VECTORS = "no_vectors"  # nothing embedded yet
PENDING = "pending"  # some files not embedded yet


@dataclass
class Readiness:
    semantic: bool  # query vectors can be used at all
    complete: bool  # results are final: every file searchable by meaning
    reason: str | None = None
    percent: int | None = None  # model download progress
    pending: int = 0
    total: int = 0
    error: str | None = None
    ready_at: float | None = None  # when search by meaning became complete

    @property
    def provisional(self) -> bool:
        return not self.complete


def _local_model(layout: Layout) -> tuple[str, str | None] | None:
    emb = layout.config.get("embedding", {}) or {}
    if emb.get("provider", "local") != "local":
        return None
    return emb.get("model", "intfloat/multilingual-e5-small"), emb.get("revision")


def model_state(layout: Layout) -> tuple[str | None, int | None, str | None, float | None]:
    """(reason or None if ready, download percent, error, time the model files were complete)."""
    lm = _local_model(layout)
    if lm is None:
        return None, None, None, None
    from .embed.local import (LOCAL_MODELS, download_percent, download_state, is_model_cached,
                              model_dir)

    name, rev = lm
    if is_model_cached(name, rev):
        spec = LOCAL_MODELS.get(name, {})
        try:
            t = (model_dir(name, rev or spec["revision"]) / spec["onnx"]).stat().st_mtime
        except (OSError, KeyError):
            t = None
        return None, None, None, t
    st = download_state(name, rev)
    if st and st.get("state") == "laedt":
        return MODEL_LOADING, download_percent(st), None, None
    if st and st.get("state") == "fehler":
        return MODEL_ERROR, None, st.get("error"), None
    return MODEL_MISSING, None, None, None


def _vector_counts(layout: Layout) -> tuple[int, int, int]:
    """(files in the search database, files with vectors, vectors) from the database."""
    from .db import open_db

    try:
        conn, _ = open_db(layout)  # builds the database from the index files if missing (fresh clone)
        try:
            n_notes = conn.execute("SELECT count(*) FROM notes").fetchone()[0]
            n_vec = conn.execute("SELECT count(*) FROM vecs").fetchone()[0]
            n_with = conn.execute("SELECT count(DISTINCT c.note_id) FROM chunks c JOIN vecs v "
                                  "ON v.chunk_id = c.id").fetchone()[0]
        finally:
            conn.close()
    except sqlite3.Error:
        return 0, 0, 0
    return n_notes, n_with, n_vec


def readiness(layout: Layout) -> Readiness:
    """Cheap check (no scan, no embedding) of what the next search can do."""
    pend = read_json(layout.cache_dir / "pending.json", {}) or {}
    n_notes, _, n_vec = _vector_counts(layout)
    pending = len(pend.get("pending") or [])
    total = int(pend.get("total") or 0) or n_notes
    meta = read_meta(layout.index_dir) or {}
    if meta.get("model") and meta.get("model") != model_id_for(layout.config):
        return Readiness(False, False, MISMATCH, pending=pending, total=total)
    m_reason, pct, m_error, m_time = model_state(layout)
    if m_reason:
        return Readiness(False, False, m_reason, percent=pct, pending=pending, total=total, error=m_error)
    if n_vec == 0:
        return Readiness(False, False, NO_VECTORS, pending=pending or total, total=total,
                         error=pend.get("embed_error"))
    if pending:
        return Readiness(True, False, PENDING, pending=pending, total=total, error=pend.get("embed_error"))
    done = pend.get("complete_at")
    ready_at = max(t for t in (done, m_time) if t) if (done or m_time) else None
    return Readiness(True, True, None, pending=0, total=total, ready_at=ready_at)


def mode_line(r: Readiness) -> str:
    """One line for the head of every search output."""
    if r.complete:
        return tr(f"Suchmodus: semantisch + Stichwort · Index vollständig ({fmt_int(r.total)} Dateien)",
                  f"Search mode: by meaning + keyword · index complete ({fmt_int(r.total)} files)")
    head = tr("Suchmodus: ", "Search mode: ")
    if r.semantic:
        done = max(r.total - r.pending, 0)
        return head + tr(f"semantisch + Stichwort, aber erst {fmt_int(done)} von {fmt_int(r.total)} Dateien "
                         "semantisch indexiert",
                         f"by meaning + keyword, but only {fmt_int(done)} of {fmt_int(r.total)} files "
                         "indexed by meaning")
    head += tr("nur Stichwort", "keyword only")
    why = {
        MODEL_LOADING: tr("Suchmodell lädt" + (f" ({r.percent} %)" if r.percent is not None else ""),
                          "search model is loading" + (f" ({r.percent}%)" if r.percent is not None else "")),
        MODEL_MISSING: tr("Suchmodell noch nicht geladen", "search model not loaded yet"),
        MODEL_ERROR: tr("Suchmodell nicht ladbar", "search model cannot be loaded"),
        MISMATCH: tr("Index passt nicht zum Modell", "index does not match the model"),
        NO_VECTORS: tr("noch keine Datei semantisch indexiert", "no file indexed by meaning yet"),
    }.get(r.reason or "", "")
    return head + (f" · {why}" if why else "")


def provisional_warning(r: Readiness, *, can_wait: bool = True) -> list[str]:
    """Warning right at the results, with what the agent should do about it."""
    if r.complete:
        return []
    if r.reason == MISMATCH:
        return [tr("⚠ Vorläufiges Ergebnis: Treffer, die nur sinngemäß passen, fehlen. Antwort als vorläufig "
                   "kennzeichnen und /plug-n-rag:reindex anbieten.",
                   "⚠ Provisional result: hits that only match by meaning are missing. Mark the answer as "
                   "provisional and offer /plug-n-rag:reindex.")]
    if r.reason == MODEL_ERROR:
        out = [tr("⚠ Vorläufiges Ergebnis: Treffer, die nur sinngemäß passen, fehlen. Antwort als vorläufig "
                  "kennzeichnen.",
                  "⚠ Provisional result: hits that only match by meaning are missing. Mark the answer as "
                  "provisional.")]
        if r.error:
            out.append(tr(f"Grund: {r.error}", f"Reason: {r.error}"))
        out.append(tr("In Cloud-Sitzungen /plug-n-rag:cloud anbieten (Netzwerkfreigabe für Hugging Face).",
                      "In cloud sessions offer /plug-n-rag:cloud (network access for Hugging Face)."))
        return out
    what = (tr("Notizen, die nur sinngemäß passen, fehlen womöglich, und die Reihenfolge kann sich noch ändern.",
               "notes that only match by meaning may be missing, and the order may still change.")
            if r.semantic else
            tr("Treffer, die nur sinngemäß passen, fehlen, und die Reihenfolge kann sich noch ändern.",
               "hits that only match by meaning are missing, and the order may still change."))
    out = [tr("⚠ Vorläufiges Ergebnis: ", "⚠ Provisional result: ") + what]
    if can_wait:
        out.append(tr("Antwort als vorläufig kennzeichnen oder dieselbe Suche mit --warten wiederholen "
                      "(wartet, bis der semantische Index bereit ist).",
                      "Mark the answer as provisional or repeat the same search with --wait "
                      "(waits until search by meaning is ready)."))
    else:
        out.append(tr("Antwort als vorläufig kennzeichnen.", "Mark the answer as provisional."))
    return out


def fmt_time(t: float) -> str:
    d = _dt.datetime.fromtimestamp(t)
    if d.date() == _dt.date.today():
        return tr(f"heute, {d:%H:%M} Uhr", f"today, {d:%H:%M}")
    return tr(f"{d:%d.%m.%Y, %H:%M} Uhr", f"{d:%Y-%m-%d %H:%M}")


def status_line(r: Readiness) -> str:
    """For ``plug-n-rag status``: is search by meaning complete, and since when?"""
    if r.complete:
        since = tr(f" seit {fmt_time(r.ready_at)}", f" since {fmt_time(r.ready_at)}") if r.ready_at else ""
        return tr(f"Semantische Suche: bereit{since} (alle {fmt_int(r.total)} Dateien, Modell geladen) ✓",
                  f"Search by meaning: ready{since} (all {fmt_int(r.total)} files, model loaded) ✓")
    return tr("Semantische Suche: noch nicht vollständig · ", "Search by meaning: not complete yet · ") \
        + mode_line(r).split(": ", 1)[1]


# --- waiting ---------------------------------------------------------------------------------

def _download_running(layout: Layout) -> bool:
    lm = _local_model(layout)
    if lm is None:
        return False
    from .embed.local import download_state
    from .util import _pid_alive

    st = download_state(*lm)
    return bool(st and st.get("state") == "laedt" and _pid_alive(int(st.get("pid", 0)))
                and int(st.get("pid", 0)) != os.getpid())


def wait_until_ready(layout: Layout, timeout: float, *, embedder=None,
                     progress=None) -> tuple[Readiness, float]:
    """Block until search by meaning is complete, or ``timeout`` seconds have passed.

    Does the work itself when nothing else does it (loads the model, indexes pending files);
    otherwise waits for the background sync. Returns (state, seconds waited). Stops early when
    waiting cannot help (index for another model, model cannot be loaded).
    """
    from .embed import EmbeddingUnavailable
    from .sync import sync
    from .util import LockBusy

    t0 = time.monotonic()
    r = readiness(layout)
    tried_model = False
    while not r.complete and r.reason != MISMATCH:
        left = timeout - (time.monotonic() - t0)
        if left <= 0:
            break
        if progress:
            progress(mode_line(r))
        lm = _local_model(layout)
        if r.reason in (MODEL_MISSING, MODEL_ERROR, MODEL_LOADING) and lm and embedder is None:
            if r.reason == MODEL_ERROR and tried_model:
                break
            if _download_running(layout):
                time.sleep(min(2.0, max(left, 0)))
            else:
                from .embed.local import LOCAL_MODELS, ensure_model_files

                tried_model = True
                name, rev = lm
                spec = LOCAL_MODELS.get(name)
                if spec is None:
                    break
                try:
                    ensure_model_files(name, rev or spec["revision"], spec)
                except EmbeddingUnavailable:
                    pass
            r = readiness(layout)
            continue
        try:
            rep = sync(layout, embedder=embedder, time_budget=max(left, 1.0), lock_wait=0)
        except LockBusy:
            time.sleep(min(1.0, max(left, 0)))
            r = readiness(layout)
            continue
        r = readiness(layout)
        if rep.embed_error and not r.complete:
            break
    return r, time.monotonic() - t0
