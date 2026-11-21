"""Notes in time: chronological listing (``suche --chronologisch``) and dated neighbours (``verwandt``).

A relevance search answers "where is X?", not "what happened next?". For the second kind of
question notes are listed by their own date: from the file name (``2024-02-12``, ``2024-W07``,
``2024-02``) or the frontmatter (``date``/``datum``). The modification time is not used: in a git
clone (cloud sessions) every file has the time of the checkout.
"""

from __future__ import annotations

import datetime as _dt
import json
import re
import sqlite3

from .config import Layout
from .db import open_db
from .i18n import tr
from .util import fmt_int

DAY_RE = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")
WEEK_RE = re.compile(r"(?<!\d)(\d{4})-W(\d{2})(?!\d)", re.IGNORECASE)
MONTH_RE = re.compile(r"(?<!\d)(\d{4})-(\d{2})(?!\d|-\d)")
MAX_LIST = 40

DAY, WEEK, MONTH = "tag", "woche", "monat"


def note_date(path: str, meta: dict | None = None) -> tuple[_dt.date, str] | None:
    """(date, kind) of a note, or None. A week note gets the Monday of its ISO week."""
    stem = path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    for text in (stem, str((meta or {}).get("date") or (meta or {}).get("datum") or "")):
        if not text:
            continue
        m = DAY_RE.search(text)
        if m:
            try:
                return _dt.date(int(m[1]), int(m[2]), int(m[3])), DAY
            except ValueError:
                pass
        m = WEEK_RE.search(text)
        if m:
            try:
                return _dt.date.fromisocalendar(int(m[1]), int(m[2]), 1), WEEK
            except ValueError:
                pass
        m = MONTH_RE.search(text)
        if m and 1 <= int(m[2]) <= 12:
            return _dt.date(int(m[1]), int(m[2]), 1), MONTH
    return None


def _label(d: _dt.date, kind: str) -> str:
    if kind == WEEK:
        y, w, _ = d.isocalendar()
        return tr(f"{y}-W{w:02d} (Woche ab {d:%d.%m.})", f"{y}-W{w:02d} (week from {d:%b %d})")
    if kind == MONTH:
        return f"{d:%Y-%m}"
    return f"{d:%Y-%m-%d}"


def _rows(conn: sqlite3.Connection, folder=None, tag=None) -> list[sqlite3.Row]:
    cond, args = [], []
    if folder:
        f = folder.strip().strip("/")
        cond.append("(path LIKE ? OR path = ?)")
        args += [f + "/%", f]
    if tag:
        cond.append("(' ' || tags || ' ') LIKE ?")
        args.append(f"% {tag.lstrip('#').lower()} %")
    sql = "SELECT id, path, title, tokens, meta, folder FROM notes" + (" WHERE " + " AND ".join(cond) if cond else "")
    return conn.execute(sql, args).fetchall()


def _meta(row) -> dict:
    try:
        return json.loads(row["meta"] or "{}")
    except (ValueError, KeyError, IndexError):
        return {}


def dated_notes(conn: sqlite3.Connection, folder=None, tag=None):
    """[(date, kind, row)] sorted by date (week and month notes before the days they cover), and undated rows."""
    dated, undated = [], []
    for r in _rows(conn, folder, tag):
        nd = note_date(r["path"], _meta(r))
        if nd:
            dated.append((nd[0], nd[1], r))
        else:
            undated.append(r)
    order = {MONTH: 0, WEEK: 1, DAY: 2}
    dated.sort(key=lambda t: (t[0], order[t[1]], t[2]["path"]))
    undated.sort(key=lambda r: r["path"])
    return dated, undated


def chronological(layout: Layout, query: str | None, *, folder=None, tag=None, since=None,
                  embedder=None) -> str:
    """Notes by date, optionally only those relevant to ``query``. ``since`` is a note date here."""
    start = None
    if since:
        try:
            start = _dt.date.fromisoformat(since)
        except ValueError:
            return tr(f"--seit erwartet ein Datum wie 2024-02-11, nicht „{since}“.",
                      f"--since expects a date like 2024-02-11, not “{since}”.")
    lines: list[str] = []
    relevant: set[str] | None = None
    if query and query.strip():
        from .readiness import mode_line, provisional_warning, readiness
        from .search import run_query

        state = readiness(layout)
        lines.append(mode_line(state))
        notes, _, notices = run_query(layout, query, folder=folder, tag=tag, embedder=embedder, relaxed=True)
        lines += [tr("Hinweis: ", "Note: ") + n for n in notices]
        lines += provisional_warning(state)
        relevant = {n.path for n in notes}
    conn, _ = open_db(layout)
    try:
        dated, undated = dated_notes(conn, folder, tag)
    finally:
        conn.close()
    if relevant is not None:
        dated = [t for t in dated if t[2]["path"] in relevant]
        undated = [r for r in undated if r["path"] in relevant]
    if start:
        # a week or month note counts from its first day, so it still shows when it covers `since`
        dated = [t for t in dated if t[0] >= start or (t[1] == WEEK and t[0] + _dt.timedelta(days=6) >= start)
                 or (t[1] == MONTH and (t[0].year, t[0].month) == (start.year, start.month))]
        undated = []  # without a date nothing can be said about "since"
    where = (folder.strip("/") + "/") if folder else tr("der ganzen Vault", "the whole vault")
    about = tr(f" zu „{query}“", f" for “{query}”") if relevant is not None else ""
    head = tr(f"Chronologisch: {len(dated)} datierte {'Notiz' if len(dated) == 1 else 'Notizen'} in {where}{about}",
              f"Chronological: {len(dated)} dated {'note' if len(dated) == 1 else 'notes'} in {where}{about}")
    if start:
        head += tr(f", ab {start:%d.%m.%Y}", f", from {start:%Y-%m-%d}")
    lines.append(head)
    if not dated and not undated:
        lines.append(tr("Keine passenden Notizen.", "No matching notes."))
        return "\n".join(lines)
    shown = dated[:MAX_LIST]
    for d, kind, r in shown:
        lines.append(f"  {_label(d, kind)} · {r['path']} ({fmt_int(r['tokens'])} {tr('Tokens', 'tokens')})")
    rest = len(dated) - len(shown)
    if rest > 0:
        nxt = dated[len(shown)][0]
        lines.append(tr(f"  [{rest} weitere: --seit {nxt:%Y-%m-%d}]", f"  [{rest} more: --since {nxt:%Y-%m-%d}]"))
    if undated:
        names = ", ".join(r["path"] for r in undated[:8]) + (" …" if len(undated) > 8 else "")
        lines.append(tr(f"Ohne Datum im Namen oder in der Frontmatter ({len(undated)}): {names}",
                        f"Without a date in the name or frontmatter ({len(undated)}): {names}"))
    lines.append(tr('Lesen: plug-n-rag lesen "<pfad>" bzw. "<pfad>#<Überschrift>"; Nachbarn einer Notiz: '
                    'plug-n-rag verwandt "<pfad>"',
                    'Read: plug-n-rag read "<path>" or "<path>#<Heading>"; neighbours of a note: '
                    'plug-n-rag related "<path>"'))
    return "\n".join(lines)


def neighbours(conn: sqlite3.Connection, note) -> list[str]:
    """Lines for ``verwandt``: previous/next dated note in the same folder, and the matching week note."""
    nd = note_date(note["path"], _meta(note))
    if nd is None:
        return []
    d, kind = nd
    folder = note["path"].rsplit("/", 1)[0] if "/" in note["path"] else ""
    same, _ = dated_notes(conn, folder or None)
    if not folder:
        same = [t for t in same if "/" not in t[2]["path"]]
    same = [t for t in same if t[1] == kind]
    out = []
    idx = next((i for i, t in enumerate(same) if t[2]["path"] == note["path"]), None)
    if idx is not None:
        if idx > 0:
            p = same[idx - 1]
            out.append(tr("Davor: ", "Before: ") + f"{p[2]['path']} ({_label(p[0], p[1])})")
        if idx + 1 < len(same):
            n = same[idx + 1]
            out.append(tr("Danach: ", "After: ") + f"{n[2]['path']} ({_label(n[0], n[1])})")
    everything, _ = dated_notes(conn)
    if kind == DAY:
        y, w, _ = d.isocalendar()
        weeks = [t[2]["path"] for t in everything if t[1] == WEEK and t[0].isocalendar()[:2] == (y, w)]
        if weeks:
            out.append(tr(f"Wochennotiz {y}-W{w:02d}: ", f"Week note {y}-W{w:02d}: ") + ", ".join(weeks))
    elif kind == WEEK:
        days = [t[2]["path"] for t in everything
                if t[1] == DAY and t[0].isocalendar()[:2] == d.isocalendar()[:2]]
        if days:
            out.append(tr("Tage dieser Woche: ", "Days of this week: ") + ", ".join(days))
    return out
