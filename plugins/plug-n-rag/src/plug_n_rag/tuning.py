"""Adaptive token steering: usage log, learned values per purpose, guard rails, overrides.

Level 1 (per request) lives in search.py (knee cut, paging). Level 2 (per task) is the
``--zweck`` start profile. Level 3 (over time) is implemented here: every tool call appends
one line to ``log.jsonl`` (paths, counts and ranks only, never query text or note content),
``learn`` turns the log into slowly moving values in ``tuning.json``.
"""

from __future__ import annotations

import datetime as _dt
import json
import math
import time
from pathlib import Path

from .config import Layout
from .i18n import tr
from .util import atomic_write_json, read_json

PURPOSES = ("frage", "recherche", "erstellen")
PURPOSE_EN = {"frage": "question", "recherche": "research", "erstellen": "create"}
PURPOSE_FROM_EN = {v: k for k, v in PURPOSE_EN.items()}
DEFAULT_PURPOSE = "frage"

START = {
    "frage": {"max_notes": 3, "neighbors": 0, "chunks_per_note": 2},
    "recherche": {"max_notes": 8, "neighbors": 0, "chunks_per_note": 3},
    "erstellen": {"max_notes": 4, "neighbors": 1, "chunks_per_note": 3},
}
# Fixed per purpose (not learned): how many notes at least, and how deep a score step must be
# to cut there. Research wants breadth, a question wants precision.
CUT = {
    "frage": {"min_notes": 1, "knee_ratio": 0.55},
    "recherche": {"min_notes": 3, "knee_ratio": 0.35},
    "erstellen": {"min_notes": 2, "knee_ratio": 0.45},
}
BOUNDS = {"max_notes": [1, 20], "neighbors": [0, 2], "chunks_per_note": [1, 3]}
ALPHA = 0.15  # moving average weight of one learning step: one session moves values only a little
MIN_OBS = 5  # observations per purpose before learned values are used


def default_tuning() -> dict:
    return {
        "schema": 1,
        "updated": _dt.date.today().isoformat(),
        "observations": 0,
        "purpose": {p: dict(v) for p, v in START.items()},
        "learned_from": {p: 0 for p in PURPOSES},
        "bounds": {k: list(v) for k, v in BOUNDS.items()},
        "user_overrides": {},
    }


def load_tuning(layout: Layout) -> dict:
    data = read_json(layout.tuning_path)
    if not isinstance(data, dict):
        # fall back to the other location (setting may have changed)
        alt = layout.cache_dir / "tuning.json" if layout.tuning_path != layout.cache_dir / "tuning.json" \
            else layout.state_dir / "tuning.json"
        data = read_json(alt)
    if not isinstance(data, dict):
        return default_tuning()
    base = default_tuning()
    for key in ("purpose", "learned_from", "bounds", "user_overrides"):
        if isinstance(data.get(key), dict):
            for k, v in data[key].items():
                if isinstance(v, dict) and isinstance(base[key].get(k), dict):
                    base[key][k].update(v)
                else:
                    base[key][k] = v
    for key in ("observations", "updated"):
        if key in data:
            base[key] = data[key]
    return base


def save_tuning(layout: Layout, data: dict) -> None:
    data["updated"] = _dt.date.today().isoformat()
    atomic_write_json(layout.tuning_path, data)


def _clamp(name: str, value: float, bounds: dict) -> int:
    lo, hi = bounds.get(name, BOUNDS.get(name, [0, 99]))
    return int(max(lo, min(hi, round(value))))


def params(layout: Layout, purpose: str) -> dict:
    """Effective parameters for a purpose: overrides > learned values > start values."""
    purpose = PURPOSE_FROM_EN.get(purpose, purpose)
    purpose = purpose if purpose in PURPOSES else DEFAULT_PURPOSE
    t = load_tuning(layout)
    out = dict(START[purpose])
    if t.get("learned_from", {}).get(purpose, 0) >= MIN_OBS:
        out.update({k: v for k, v in t["purpose"].get(purpose, {}).items() if k in out})
    out.update({k: v for k, v in t.get("user_overrides", {}).get(purpose, {}).items() if k in out})
    for k in list(out):
        out[k] = _clamp(k, out[k], t.get("bounds", BOUNDS))
    out["purpose"] = purpose
    out.update(CUT[purpose])
    return out


def set_override(layout: Layout, purpose: str, *, deeper: bool | None = None, **values) -> dict:
    """User feedback such as 'zu oberflächlich' (deeper=True) or 'zu viel' (deeper=False)."""
    t = load_tuning(layout)
    cur = params(layout, purpose)
    ov = t["user_overrides"].setdefault(purpose, {})
    if deeper is True:
        ov["max_notes"] = cur["max_notes"] + 2
        ov["neighbors"] = min(cur["neighbors"] + 1, BOUNDS["neighbors"][1])
        ov["chunks_per_note"] = min(cur["chunks_per_note"] + 1, 3)
    elif deeper is False:
        ov["max_notes"] = max(cur["max_notes"] - 1, 1)
        ov["neighbors"] = max(cur["neighbors"] - 1, 0)
    for k, v in values.items():
        if v is not None and k in BOUNDS:
            ov[k] = int(v)
    for k in list(ov):
        ov[k] = _clamp(k, ov[k], t.get("bounds", BOUNDS))
    save_tuning(layout, t)
    return ov


def reset(layout: Layout, *, keep_overrides: bool = False) -> None:
    t = default_tuning()
    if keep_overrides:
        t["user_overrides"] = load_tuning(layout).get("user_overrides", {})
    save_tuning(layout, t)


# --- usage log ----------------------------------------------------------------------------

def log_event(layout: Layout, event: dict) -> None:
    event = {"t": round(time.time(), 1), **event}
    try:
        layout.cache_dir.mkdir(parents=True, exist_ok=True)
        with open(layout.log_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")
    except OSError:
        pass


def read_log(layout: Layout, limit: int = 5000) -> list[dict]:
    try:
        lines = layout.log_path.read_text(encoding="utf-8").splitlines()[-limit:]
    except OSError:
        return []
    out = []
    for ln in lines:
        try:
            out.append(json.loads(ln))
        except ValueError:
            continue
    return out


def analyse(events: list[dict]) -> dict:
    """Per purpose: how deep did reads go after each search?

    A read only counts as 'went deeper' if it targets a note from the search result (reads
    are what proves the hit was used; merely paging does not count on its own).
    """
    stats: dict[str, dict] = {p: {"searches": 0, "beyond": 0, "top_only": 0, "full_after_section": 0,
                                  "section_reads": 0, "reformulated": 0} for p in PURPOSES}
    last = None
    last_time = 0.0
    reads_since = 0
    for ev in events:
        cmd = ev.get("cmd")
        if cmd == "suche":
            p = ev.get("purpose", DEFAULT_PURPOSE)
            if p not in stats:
                continue
            if ev.get("page", 0) > 0 and last is not None:
                last["paged"] = True
                continue
            if last is not None:
                _close(stats, last)
                if reads_since == 0 and ev.get("t", 0) - last_time < 120 and last["purpose"] == p:
                    stats[p]["reformulated"] += 1
            last = {"purpose": p, "shown": ev.get("results", []), "cut": ev.get("n", 0),
                    "read_ranks": [], "paged": False, "more": ev.get("more", 0)}
            last_time = ev.get("t", 0)
            reads_since = 0
        elif cmd in ("lesen", "gliederung", "read") and last is not None:
            path = ev.get("path")
            ranks = {r[0]: r[1] for r in last["shown"]} if last["shown"] else {}
            if path in ranks:
                last["read_ranks"].append(ranks[path])
                reads_since += 1
            if cmd == "lesen":
                p = last["purpose"]
                if ev.get("whole"):
                    if last.get("section_read_paths") and path in last["section_read_paths"]:
                        stats[p]["full_after_section"] += 1
                else:
                    stats[p]["section_reads"] += 1
                    last.setdefault("section_read_paths", set()).add(path)
    if last is not None:
        _close(stats, last)
    return stats


def _close(stats: dict, s: dict) -> None:
    p = s["purpose"]
    stats[p]["searches"] += 1
    if not s["read_ranks"]:
        return
    deepest = max(s["read_ranks"])
    if deepest > s["cut"] or (s["paged"] and deepest > s["cut"]):
        stats[p]["beyond"] += 1
    elif deepest <= 1:
        stats[p]["top_only"] += 1


def learn(layout: Layout) -> dict:
    """Update learned values from the log with a slow moving average inside the bounds."""
    t = load_tuning(layout)
    stats = analyse(read_log(layout))
    bounds = t.get("bounds", BOUNDS)
    total = 0
    for p, s in stats.items():
        n = s["searches"]
        total += n
        if n == 0:
            continue
        cur = t["purpose"].setdefault(p, dict(START[p]))
        target_notes = cur["max_notes"]
        if s["beyond"] / n > 0.3:
            target_notes = cur["max_notes"] + 2
        elif s["top_only"] / n > 0.6:
            target_notes = cur["max_notes"] - 1
        step = ALPHA * (target_notes - cur["max_notes"])
        step = math.ceil(step) if step > 0 else math.floor(step)  # at most +/-1 per session
        cur["max_notes"] = _clamp("max_notes", cur["max_notes"] + step, bounds)
        if s["section_reads"] and s["full_after_section"] / max(1, s["section_reads"]) > 0.6:
            cur["neighbors"] = _clamp("neighbors", cur["neighbors"] + 1, bounds)
        if s["reformulated"] / n > 0.3:
            cur["chunks_per_note"] = _clamp("chunks_per_note", cur.get("chunks_per_note", 2) - 1, bounds)
        t["learned_from"][p] = n
    t["observations"] = total
    save_tuning(layout, t)
    return t


def savings(layout: Layout) -> tuple[int, int, int]:
    """(searches, delivered tokens, tokens if all hit files had been read completely)."""
    n = delivered = full = 0
    for ev in read_log(layout):
        if ev.get("cmd") == "suche":
            n += 1
            delivered += int(ev.get("tokens", 0))
            full += int(ev.get("full_tokens", 0))
    return n, delivered, full


def describe(layout: Layout) -> list[str]:
    t = load_tuning(layout)
    lines = []
    for p in PURPOSES:
        eff = params(layout, p)
        n = t["learned_from"].get(p, 0)
        src = tr("eigene Vorgabe", "your setting") if t["user_overrides"].get(p) else (
            tr(f"gelernt aus {n} Suchen", f"learned from {n} searches")
            if n >= MIN_OBS else tr("Startwert", "default"))
        extra = tr(f", Nachbarabschnitte {eff['neighbors']}", f", neighbouring sections {eff['neighbors']}") \
            if eff["neighbors"] else ""
        name = tr(p.capitalize(), PURPOSE_EN[p].capitalize())
        lines.append(tr(f"{name}: bis zu {eff['max_notes']} Notizen{extra} ({src})",
                        f"{name}: up to {eff['max_notes']} notes{extra} ({src})"))
    return lines


def tuning_location_note(layout: Layout) -> str:
    p: Path = layout.tuning_path
    return tr("im Repo (wird committet)", "in the repo (committed)") if p.parent == layout.state_dir \
        else tr("nur lokal", "local only")
