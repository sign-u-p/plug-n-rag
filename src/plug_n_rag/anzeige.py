"""Machine-readable snapshot for the display mod ``plug-n-rag-anzeige`` (``anzeige-daten``).

Local and fast: no network, no embedding, no model. The mod runs it when a session starts,
after each plug-n-rag call and when its side pane opens. Never contains note text or queries.
"""

from __future__ import annotations

import json
import time

from . import __version__, tuning
from .config import Layout, find_layout
from .embed import model_id_for
from .index_store import read_meta
from .util import _pid_alive, read_json


def _indexing(layout: Layout) -> dict:
    lock = read_json(layout.lock_path, None)
    running = bool(lock) and _pid_alive(int(lock.get("pid", 0))) and time.time() - float(lock.get("t", 0)) < 3600
    prog = read_json(layout.cache_dir / "progress.json", {}) or {}
    if not running:
        return {"running": False}
    return {"running": True, "done": int(prog.get("done", 0)), "total": int(prog.get("total", 0))}


def snapshot(layout: Layout | None) -> dict:
    out: dict = {"version": __version__, "configured": False, "vault_detected": False}
    if layout is None:
        return out
    if not layout.configured:
        out["vault_detected"] = True
        out["root"] = str(layout.root)
        out["name"] = layout.root.name
        return out
    from .migrate import needs_update
    from .status import _model_label
    from .sync import pending_count

    todo, total = pending_count(layout)
    pend = read_json(layout.cache_dir / "pending.json", {}) or {}
    errors = read_json(layout.cache_dir / "errors.json", {}) or {}
    meta = read_meta(layout.index_dir) or {}
    want = model_id_for(layout.config)
    n, delivered, full = tuning.savings(layout)
    cached_map = read_json(layout.cache_dir / "map.json", {}) or {}
    out.update({
        "configured": True,
        "name": layout.root.name,
        "root": str(layout.root),
        "mode": layout.mode,
        "location": layout.location,
        "files": total,
        "indexed": total - todo,
        "pending": todo,
        "awaiting": list(pend.get("awaiting") or [])[:50],
        "errors": len(errors),
        "embed_error": pend.get("embed_error"),
        "model": _model_label(want),
        "model_mismatch": bool(meta.get("model") and meta["model"] != want),
        "indexing": _indexing(layout),
        "needs_update": needs_update(layout),
        "savings": {"searches": n, "delivered": delivered, "full": full},
        "tuning": tuning.describe(layout),
        "map": [{"folder": f["folder"], "count": f["count"], "topics": f.get("topics", [])[:3],
                 "desc": f.get("desc", "")} for f in cached_map.get("folders", [])][:20],
    })
    return out


def render_json(layout: Layout | None) -> str:
    return json.dumps(snapshot(layout), ensure_ascii=False)


def main_for(start=None) -> str:
    return render_json(find_layout(start))
