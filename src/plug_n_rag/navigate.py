"""Step-wise reading: outline (gliederung), read a section (lesen), related notes (verwandt)."""

from __future__ import annotations

import json
import re
import sqlite3

import numpy as np

from . import tuning
from .config import Layout
from .db import open_db
from .formats import read_units
from .formats.base import format_range, printed_suffix
from .util import estimate_tokens, fmt_int

RANGE_RE = re.compile(r"^(?P<ref>.+?)(?::|#\s*(?:[ZzSs]\.?|Zeilen?|Seiten?)\s*)(?P<a>\d+)(?:\s*[-–]\s*(?P<b>\d+))?$")


class NotFound(LookupError):
    pass


def _meta(note) -> dict:
    try:
        return json.loads(note["meta"] or "{}")
    except (ValueError, KeyError, IndexError):
        return {}


def resolve_note(conn: sqlite3.Connection, ref: str) -> sqlite3.Row:
    ref = ref.strip().strip('"').strip("'").replace("\\", "/")
    if ref.startswith("./"):
        ref = ref[2:]
    if ref.startswith("[[") and ref.endswith("]]"):
        ref = ref[2:-2].split("|")[0]
    q = "SELECT * FROM notes WHERE "
    for cond, arg in (
        ("path = ?", ref),
        ("path = ?", ref + ".md"),
        ("lower(path) = lower(?)", ref),
        ("lower(path) = lower(?)", ref + ".md"),
    ):
        row = conn.execute(q + cond, (arg,)).fetchone()
        if row:
            return row
    low = ref.lower().removesuffix(".md")
    rows = conn.execute(
        q + "lower(stem) = ? OR lower(title) = ? OR lower(path) LIKE ?",
        (low.split("/")[-1], low, "%/" + low.split("/")[-1] + ".%"),
    ).fetchall()
    if len(rows) == 1:
        return rows[0]
    if len(rows) > 1:
        names = ", ".join(r["path"] for r in rows[:6])
        raise NotFound(f"„{ref}“ ist mehrdeutig: {names}. Bitte den Pfad angeben.")
    raise NotFound(f"Keine Notiz „{ref}“ gefunden. Tipp: zuerst `plug-n-rag suche` nutzen.")


def _split_ref(target: str) -> tuple[str, str | None, tuple[int, int] | None]:
    m = RANGE_RE.match(target.strip())
    if m:
        a = int(m.group("a"))
        b = int(m.group("b") or a)
        return m.group("ref"), None, (min(a, b), max(a, b))
    if "#" in target:
        ref, heading = target.rsplit("#", 1)
        return ref, heading.strip(), None
    return target, None, None


def outline(layout: Layout, ref: str) -> str:
    conn, _ = open_db(layout)
    try:
        try:
            note = resolve_note(conn, ref)
        except NotFound as exc:
            return str(exc)
        items = json.loads(note["outline"] or "[]")
        unit = note["unit"]
        nmeta = _meta(note)
        head = f"{note['path']} – „{note['title']}“ ({fmt_int(note['tokens'])} Tokens"
        if note["tags"]:
            head += ", Tags: " + ", ".join(note["tags"].split())
        head += ")"
        lines = [head]
        if items:
            for it in items:
                indent = "  " * max(0, it["level"] - 1)
                lines.append(f"{indent}{'#' * it['level']} {it['heading']} · "
                             f"{format_range(unit, it['start'], it['end'])}"
                             f"{printed_suffix(nmeta, unit, it['start'], it['end'])} · {fmt_int(it['tokens'])} Tokens")
        else:
            rows = conn.execute('SELECT heading_path, start, "end", tokens FROM chunks WHERE note_id=? ORDER BY ord',
                                (note["id"],)).fetchall()
            lines.append("Keine Überschriften. Abschnitte:")
            for r in rows:
                lines.append(f"  {format_range(unit, r['start'], r['end'])}"
                             f"{printed_suffix(nmeta, unit, r['start'], r['end'])} · {fmt_int(r['tokens'])} Tokens")
        links_out = [r[0] for r in conn.execute("SELECT DISTINCT dst FROM links WHERE src=?", (note["id"],))]
        back = _backlinks(conn, note)
        if links_out or back:
            parts = []
            if links_out:
                parts.append("Links: " + ", ".join(links_out[:10]))
            if back:
                parts.append("Backlinks: " + ", ".join(back[:10]))
            lines.append(" · ".join(parts))
        tuning.log_event(layout, {"cmd": "gliederung", "path": note["path"]})
        return "\n".join(lines)
    finally:
        conn.close()


def _keys(note) -> list[str]:
    keys = {note["stem"].lower(), note["title"].lower(), note["path"].lower().rsplit(".", 1)[0]}
    return sorted(k for k in keys if k)


def _backlinks(conn, note) -> list[str]:
    keys = _keys(note)
    marks = ",".join("?" * len(keys))
    return [r[0] for r in conn.execute(
        f"SELECT DISTINCT n.path FROM links l JOIN notes n ON n.id=l.src WHERE l.dst IN ({marks}) AND n.id != ?",
        (*keys, note["id"]))]


def _find_heading(items: list[dict], wanted: str) -> dict | None:
    w = wanted.strip().lower()
    for it in items:
        if it["heading"].strip().lower() == w:
            return it
    for it in items:
        if w in it["heading"].strip().lower():
            return it
    return None


def read(layout: Layout, target: str) -> str:
    conn, _ = open_db(layout)
    try:
        ref, heading, rng = _split_ref(target)
        try:
            note = resolve_note(conn, ref)
        except NotFound as exc:
            return str(exc)
        unit = note["unit"]
        abs_path = layout.root / note["path"]
        whole = False
        if rng:
            start, end = rng
            label = format_range(unit, start, end) + printed_suffix(_meta(note), unit, start, end)
        elif heading:
            items = json.loads(note["outline"] or "[]")
            it = _find_heading(items, heading.split(">")[-1])
            if it is None:
                avail = ", ".join(i["heading"] for i in items[:12]) or "keine"
                return f"Überschrift „{heading}“ nicht gefunden in {note['path']}. Vorhanden: {avail}"
            start, end = it["start"], it["end"]
            label = f"{it['heading']}, {format_range(unit, start, end)}{printed_suffix(_meta(note), unit, start, end)}"
        else:
            whole = True
            start, end = 1, 10 ** 9
            label = "ganze Notiz"
        try:
            text = read_units(abs_path, note["format"], start, end, layout.cache_dir)
        except OSError as exc:
            return f"Datei nicht lesbar: {exc}"
        tok = estimate_tokens(text)
        tuning.log_event(layout, {"cmd": "lesen", "path": note["path"], "whole": whole, "tokens": tok})
        return f"{note['path']} › {label} ({fmt_int(tok)} Tokens)\n\n{text}"
    finally:
        conn.close()


def related(layout: Layout, ref: str, limit: int = 5) -> str:
    conn, _ = open_db(layout)
    try:
        try:
            note = resolve_note(conn, ref)
        except NotFound as exc:
            return str(exc)
        lines = [f"Verwandt mit {note['path']}:"]
        listed = {note["path"]}
        out_rows = []
        missing = []
        for (dst,) in conn.execute("SELECT DISTINCT dst FROM links WHERE src=?", (note["id"],)):
            r = conn.execute("SELECT path FROM notes WHERE lower(stem)=? OR lower(title)=? LIMIT 1",
                             (dst, dst)).fetchone()
            if r:
                out_rows.append(r[0])
            else:
                missing.append(dst)
        back = _backlinks(conn, note)
        if out_rows:
            lines.append("Verlinkt: " + ", ".join(out_rows))
            listed.update(out_rows)
        if back:
            lines.append("Verweist hierher: " + ", ".join(back))
            listed.update(back)
        if missing:
            lines.append("Links ohne Notiz: " + ", ".join(missing[:8]))
        if note["vec"] is not None:
            me = np.frombuffer(note["vec"], dtype=np.float32)
            rows = conn.execute("SELECT path, vec FROM notes WHERE vec IS NOT NULL AND id != ?", (note["id"],)).fetchall()
            scored = sorted(((float(np.frombuffer(r[1], dtype=np.float32) @ me), r[0]) for r in rows), reverse=True)
            sem = [(s, p) for s, p in scored if p not in listed][:limit]
            if sem:
                lines.append("Inhaltlich ähnlich:")
                for s, p in sem:
                    lines.append(f"  {p} ({'sehr ähnlich' if s >= 0.9 else 'ähnlich' if s >= 0.8 else 'entfernt ähnlich'})")
        if len(lines) == 1:
            lines.append("Nichts Verwandtes gefunden.")
        tuning.log_event(layout, {"cmd": "verwandt", "path": note["path"]})
        return "\n".join(lines)
    finally:
        conn.close()
