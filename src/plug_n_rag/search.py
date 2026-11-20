"""Hybrid search: FTS5 words + FTS5 trigram (German compounds) + vectors, fused with RRF.

Output is compact German text for the agent: path, note size in tokens, heading and
position of each section, relevance in words, and one short snippet for the best section.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import math
import re
import sqlite3
from dataclasses import dataclass, field

import numpy as np

from . import tuning
from .config import Layout
from .db import chunk_vectors, open_db, vector_search
from .embed import EmbeddingUnavailable, get_embedder, model_id_for
from .formats.base import format_range, printed_suffix
from .index_store import read_meta
from .util import atomic_write_json, estimate_tokens, fmt_int, read_json

RRF_K = 60
CANDIDATES = 60
KNEE_RATIO = 0.55  # cut where the next note scores below 55 % of the previous one

STOPWORDS = set(
    """
    a ab aber alle allem allen aller alles als also am an ander andere anderem anderen anderer anderes
    auch auf aus bei beim bin bis bist da dabei dadurch dafür dagegen daher damit dann darauf darin
    darüber das dass daß dein deine dem den denn der deren des dessen deshalb die dies diese diesem
    diesen dieser dieses doch dort du durch ein eine einem einen einer eines einige er es etwas euch
    euer für gegen gibt hab habe haben hat hatte hier hin hinter ich ihm ihn ihnen ihr ihre im in ins
    ist ja jede jedem jeden jeder jedes jetzt kann kein keine können man manche mehr mein meine meinem
    meinen meiner mich mir mit muss nach nicht nichts noch nun nur ob oder ohne sehr sein seine sich
    sie sind so solche soll sollte sondern sonst über um und uns unser unter viel vom von vor wann war
    waren warum was weil welche welchem welchen welcher wenn wer werden wie wieder will wir wird wo
    wurde zu zum zur zwar zwischen gibt es gab etwa welches womit wozu wofür worüber
    the a an and or of to in on for with is are was what how why which who about from by at
    """.split()
)
WORD_RE = re.compile(r"\w+", re.UNICODE)


@dataclass
class Hit:
    chunk_id: int
    note_id: int
    path: str
    heading_path: str
    start: int
    end: int
    tokens: int
    body: str
    rrf: float = 0.0
    sim: float | None = None
    coverage: float = 0.0
    strength: float = 0.0
    relevant: bool = False
    reference_list: bool = False


@dataclass
class NoteResult:
    path: str
    title: str
    unit: str
    tokens: int
    tags: str
    folder: str
    score: float
    hits: list[Hit] = field(default_factory=list)
    meta: dict = field(default_factory=dict)

    @property
    def best(self) -> Hit:
        return self.hits[0]


@dataclass
class SearchOutcome:
    notes: list[NoteResult]
    shown: int
    page: int
    page_size: int
    keyword_only: bool
    notice: list[str]
    fallback_outside: str | None
    query_terms: list[str]


def query_terms(q: str) -> list[str]:
    words = [w for w in WORD_RE.findall(q.lower()) if len(w) >= 2 and w not in STOPWORDS]
    seen, out = set(), []
    for w in words:
        if w not in seen:
            seen.add(w)
            out.append(w)
    return out


def _fts_quote(w: str) -> str:
    return '"' + w.replace('"', '""') + '"'


def _lexical(conn: sqlite3.Connection, terms: list[str], k: int) -> tuple[list[int], list[int]]:
    words_ids: list[int] = []
    tri_ids: list[int] = []
    if terms:
        q = " OR ".join(_fts_quote(t) + ("*" if len(t) >= 3 else "") for t in terms)
        try:
            words_ids = [r[0] for r in conn.execute(
                "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH ? ORDER BY bm25(chunks_fts, 1.0, 2.0, 2.0) LIMIT ?",
                (q, k))]
        except sqlite3.Error:
            words_ids = []
        long_terms = [t for t in terms if len(t) >= 4]
        if long_terms:
            q3 = " OR ".join(_fts_quote(_variants(t)[-1]) for t in long_terms)
            try:
                tri_ids = [r[0] for r in conn.execute(
                    "SELECT rowid FROM chunks_trigram WHERE chunks_trigram MATCH ? ORDER BY rank LIMIT ?",
                    (q3, k))]
            except sqlite3.Error:
                tri_ids = []
    return words_ids, tri_ids


GERMAN_ENDINGS = ("en", "er", "es", "e", "n", "s")


def _variants(term: str) -> list[str]:
    """The term plus a light German/English plural stem ('assessments' -> 'assessment')."""
    out = [term]
    if len(term) >= 6:
        for end in GERMAN_ENDINGS:
            if term.endswith(end) and len(term) - len(end) >= 5:
                out.append(term[: -len(end)])
                break
    return out


def term_weights(conn: sqlite3.Connection, terms: list[str]) -> dict[str, float]:
    """Weight = length x inverse document frequency: long, rare words (compounds) carry the topic."""
    try:
        n = conn.execute("SELECT count(*) FROM chunks").fetchone()[0] or 1
    except sqlite3.Error:
        n = 1
    weights = {}
    for t in terms:
        df = 0
        if len(t) >= 3:
            try:
                df = conn.execute("SELECT count(*) FROM chunks_trigram WHERE chunks_trigram MATCH ?",
                                  (_fts_quote(_variants(t)[-1]),)).fetchone()[0]
            except sqlite3.Error:
                df = 0
        idf = math.log(1 + n / (1 + df))
        weights[t] = len(t) * max(idf, 0.1)
    return weights


def _coverage(terms: list[str], text: str, weights: dict[str, float] | None = None) -> float:
    if not terms:
        return 0.0
    low = text.lower()
    total = hit = 0.0
    for term in terms:
        w = (weights or {}).get(term, float(len(term)))
        total += w
        for v in _variants(term):
            ok = (v in low) if len(v) >= 4 else re.search(r"\b" + re.escape(v), low) is not None
            if ok:
                hit += w
                break
    return hit / total if total else 0.0


REF_HEADING_RE = re.compile(r"(literatur|quellen|bibliogra|references|reference list|works cited|"
                            r"weiterführende lektüre)", re.IGNORECASE)
REF_YEAR_RE = re.compile(r"\(?\b(?:19|20)\d{2}[a-z]?\)?[.,:;)]")
REF_MARKER_RE = re.compile(r"(Verlag|\bdoi\b|ISBN|Hrsg\.|\(Hg\.\)|\bIn: |\bS\. \d|\bpp?\. ?\d|\bVol\.|\bJg\.|"
                           r"\bAufl\.|https?://)", re.IGNORECASE)
REF_AUTHOR_RE = re.compile(r"\b[A-ZÄÖÜ][\w\-]+, (?:[A-ZÄÖÜ]\.\s?){1,3}")
REF_QUERY_RE = re.compile(r"(literatur|quelle|bibliogra|reference|zitier|autor)", re.IGNORECASE)


def is_reference_list(heading_path: str, body: str) -> bool:
    """A bibliography rather than content: many years, author initials and publisher markers."""
    last = heading_path.split(" > ")[-1] if heading_path else ""
    if last and REF_HEADING_RE.search(last) and len(last) < 60:
        return True
    words = len(body.split())
    if words < 30:
        return False
    years = len(REF_YEAR_RE.findall(body))
    markers = len(REF_MARKER_RE.findall(body))
    authors = len(REF_AUTHOR_RE.findall(body))
    return years * 100 / words >= 3.5 and (markers >= 3 or authors >= 3)


def _filter_sql(folder: str | None, tag: str | None, since: float | None) -> tuple[str, list]:
    cond, args = [], []
    if folder:
        f = folder.strip().strip("/")
        cond.append("(n.path LIKE ? OR n.path = ?)")
        args += [f + "/%", f]
    if tag:
        cond.append("(' ' || n.tags || ' ') LIKE ?")
        args.append(f"% {tag.lstrip('#').lower()} %")
    if since is not None:
        cond.append("n.mtime >= ?")
        args.append(since)
    return (" AND ".join(cond), args)


def _parse_since(s: str | None) -> float | None:
    if not s:
        return None
    try:
        d = _dt.date.fromisoformat(s)
    except ValueError:
        return None
    return _dt.datetime(d.year, d.month, d.day).timestamp()


def run_query(layout: Layout, query: str, *, folder=None, tag=None, since=None,
              embedder=None, relaxed: bool = False) -> tuple[list[NoteResult], bool, list[str]]:
    """Return (relevant notes ranked, keyword_only, notices)."""
    conn, has_vec = open_db(layout)
    notices: list[str] = []
    try:
        terms = query_terms(query)
        filtered = bool(folder or tag or since)
        k = CANDIDATES * (4 if filtered else 1)
        wants_refs = bool(REF_QUERY_RE.search(query))
        lists: list[list[int]] = list(_lexical(conn, terms, k))
        weights = term_weights(conn, terms)
        meta = read_meta(layout.index_dir) or {}
        keyword_only = False
        qvec = None
        sims: dict[int, float] = {}
        n_vec = conn.execute("SELECT count(*) FROM vecs").fetchone()[0]
        if meta.get("model") and meta.get("model") != model_id_for(layout.config):
            keyword_only = True
            notices.append("Index passt nicht zum Modell: nur Stichwortsuche. Neuindexierung mit /plug-n-rag:reindex.")
        elif n_vec == 0:
            keyword_only = True
        else:
            try:
                emb = embedder or get_embedder(layout.config)
                min_sim, strong = emb.min_similarity, emb.strong_similarity
                qvec = emb.embed([query], "query")[0]
            except EmbeddingUnavailable as exc:
                keyword_only = True
                notices.append(f"Semantische Suche nicht verfügbar, nur Stichwortsuche ({exc}).")
            if qvec is not None:
                vres = vector_search(conn, has_vec, qvec, k)
                lists.append([cid for cid, _ in vres])
                sims = {cid: s for cid, s in vres}
        if keyword_only:
            min_sim, strong = 1.0, 1.0

        scores: dict[int, float] = {}
        for lst in lists:
            for rank, cid in enumerate(lst):
                scores[cid] = scores.get(cid, 0.0) + 1.0 / (RRF_K + rank + 1)
        if not scores:
            return [], keyword_only, notices
        ids = list(scores)
        marks = ",".join("?" * len(ids))
        fsql, fargs = _filter_sql(folder, tag, _parse_since(since))
        sql = (f'SELECT c.id, c.note_id, n.path, c.heading_path, c.start, c."end", c.tokens, c.body,'
               f" n.title, n.unit, n.tokens AS ntok, n.tags, n.folder, n.meta AS nmeta FROM chunks c JOIN notes n ON n.id=c.note_id"
               f" WHERE c.id IN ({marks})" + (f" AND {fsql}" if fsql else ""))
        rows = conn.execute(sql, ids + fargs).fetchall()
        if qvec is not None:
            missing = [r["id"] for r in rows if r["id"] not in sims]
            for cid, v in chunk_vectors(conn, missing).items():
                sims[cid] = float(v @ qvec)
        notes: dict[int, NoteResult] = {}
        for r in rows:
            h = Hit(r["id"], r["note_id"], r["path"], r["heading_path"], r["start"], r["end"],
                    r["tokens"], r["body"], rrf=scores[r["id"]], sim=sims.get(r["id"]))
            h.coverage = _coverage(terms, f"{r['title']} {r['tags']} {r['heading_path']} {r['body']}", weights)
            sem = 0.0
            if h.sim is not None:
                lo = min_sim - 0.04
                sem = float(np.clip((h.sim - lo) / max(strong - lo, 1e-6), 0, 1))
            # research wants breadth: slightly lower bars than for a precise question
            lex_ok = h.coverage >= 0.5
            h.relevant = lex_ok or (h.sim is not None and h.sim >= min_sim - (0.01 if relaxed else 0.0))
            h.strength = max(sem, h.coverage) * 0.7 + min(sem, h.coverage) * 0.3
            if not h.relevant:
                continue
            if not wants_refs and is_reference_list(r["heading_path"], r["body"]):
                # literature lists match many topic words but rarely answer the question
                h.reference_list = True
                h.strength *= 0.4
                h.rrf *= 0.5
            nr = notes.get(r["note_id"])
            if nr is None:
                try:
                    nmeta = json.loads(r["nmeta"] or "{}")
                except ValueError:
                    nmeta = {}
                nr = NoteResult(r["path"], r["title"], r["unit"], r["ntok"], r["tags"], r["folder"], 0.0,
                                meta=nmeta)
                notes[r["note_id"]] = nr
            nr.hits.append(h)
        ranked = []
        for nr in notes.values():
            nr.hits.sort(key=lambda h: (-(h.rrf * (0.5 + h.strength)), h.start))
            best = nr.hits[0]
            nr.score = best.rrf * (0.5 + best.strength) + 0.1 * sum(
                h.rrf * (0.5 + h.strength) for h in nr.hits[1:3])
            ranked.append(nr)
        ranked.sort(key=lambda n: -n.score)
        return ranked, keyword_only, notices
    finally:
        conn.close()


def knee_cut(scores: list[float], max_notes: int, *, min_notes: int = 1, ratio: float = KNEE_RATIO) -> int:
    """Number of notes to show: at the clearest score step, between ``min_notes`` and ``max_notes``."""
    if not scores:
        return 0
    n = min(len(scores), max_notes)
    lo = min(max(1, min_notes), n)
    best_i, best_ratio = n, 1.0
    for i in range(lo, n):
        r = scores[i] / scores[i - 1] if scores[i - 1] > 0 else 1.0
        if r < best_ratio:
            best_i, best_ratio = i, r
    return best_i if best_ratio < ratio else n


def label(strength: float) -> str:
    if strength >= 0.75:
        return "sehr passend"
    if strength >= 0.4:
        return "passend"
    return "am Rande"


def _snippet(body: str, terms: list[str], width: int = 160) -> str:
    text = re.sub(r"\s+", " ", body).strip()
    low = text.lower()
    pos = -1
    for t in sorted(terms, key=len, reverse=True):
        pos = low.find(t)
        if pos >= 0:
            break
    if pos < 0:
        pos = 0
    start = max(0, pos - width // 3)
    snip = text[start:start + width].strip()
    return ("…" if start > 0 else "") + snip + ("…" if start + width < len(text) else "")


def _section_label(h: Hit, unit: str) -> str:
    if h.heading_path:
        return h.heading_path.split(" > ")[-1]
    if unit == "pages":
        return "Text"
    return "Anfang" if h.start <= 3 else "Abschnitt"


def _cache_key(query: str, folder, tag, since, purpose) -> str:
    raw = json.dumps([query.strip().lower(), folder, tag, since, purpose], ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def search(layout: Layout, query: str | None, *, purpose: str = "frage", folder=None, tag=None,
           since=None, more: bool = False, embedder=None) -> str:
    params = tuning.params(layout, purpose)
    cache_path = layout.cache_dir / "last_search.json"
    fallback = None
    notices: list[str] = []
    if more:
        cached = read_json(cache_path, {}) or {}
        key = _cache_key(query, folder, tag, since, purpose) if query else cached.get("key")
        if cached.get("key") != key or not cached.get("notes"):
            if not query:
                return "Keine vorherige Suche zum Weiterblättern. Bitte zuerst suchen."
        else:
            return _render_cached(layout, cached, params)
    if not query or not query.strip():
        return "Bitte eine Suchanfrage angeben."
    relaxed = params["purpose"] == "recherche"
    notes, keyword_only, notices = run_query(layout, query, folder=folder, tag=tag, since=since,
                                             embedder=embedder, relaxed=relaxed)
    if not notes and (folder or tag or since):
        notes, keyword_only, n2 = run_query(layout, query, embedder=embedder, relaxed=relaxed)
        notices += [n for n in n2 if n not in notices]
        if notes:
            where = folder.strip("/") + "/" if folder else (f"Tag #{tag}" if tag else f"seit {since}")
            fallback = f"Außerhalb von {where} gefunden" if folder else f"Ohne Filter ({where}) gefunden"
    terms = query_terms(query)
    pending = _pending_notice(layout)
    if pending:
        notices.append(pending)
    n_show = knee_cut([n.score for n in notes], params["max_notes"], min_notes=params["min_notes"],
                      ratio=params["knee_ratio"])
    data = {
        "key": _cache_key(query, folder, tag, since, purpose),
        "title": query,
        "purpose": params["purpose"],
        "terms": terms,
        "page": 0,
        "page_size": max(n_show, 1),
        "first": n_show,
        "keyword_only": keyword_only,
        "notices": notices,
        "fallback": fallback,
        "notes": [_note_to_json(n, params) for n in notes],
    }
    atomic_write_json(cache_path, data, indent=None)
    out = _render(layout, data, 0, n_show, params)
    _log_search(layout, data, 0, n_show, out)
    return out


def _note_to_json(n: NoteResult, params: dict) -> dict:
    hits = []
    for h in n.hits[: params["chunks_per_note"]]:
        hits.append({"heading": h.heading_path, "start": h.start, "end": h.end, "tokens": h.tokens,
                     "strength": round(h.strength, 3), "snippet_src": h.body[:1200],
                     "label": _section_label(h, n.unit) + (" · Literaturliste" if h.reference_list else ""),
                     "printed": printed_suffix(n.meta, n.unit, h.start, h.end)})
    return {"path": n.path, "title": n.title, "unit": n.unit, "tokens": n.tokens,
            "score": round(n.score, 5), "hits": hits}


def _neighbors(layout: Layout, path: str, start: int, end: int, k: int) -> tuple[int, int]:
    if k <= 0:
        return start, end
    try:
        conn, _ = open_db(layout)
        rows = conn.execute(
            'SELECT c.start, c."end" FROM chunks c JOIN notes n ON n.id=c.note_id WHERE n.path=? ORDER BY c.ord',
            (path,)).fetchall()
        conn.close()
    except sqlite3.Error:
        return start, end
    spans = [(r[0], r[1]) for r in rows]
    idx = next((i for i, s in enumerate(spans) if s[0] <= start <= s[1]), None)
    if idx is None:
        return start, end
    lo = spans[max(0, idx - k)][0]
    hi = spans[min(len(spans) - 1, idx + k)][1]
    return min(lo, start), max(hi, end)


def _render(layout: Layout, data: dict, offset: int, count: int, params: dict) -> str:
    notes = data["notes"]
    lines: list[str] = []
    for n in data.get("notices", []):
        lines.append(f"Hinweis: {n}")
    if not notes:
        lines.append(f"Nichts Passendes gefunden zu „{data['title']}“.")
        lines.append("Bitte nicht aus Allgemeinwissen antworten, als stünde es in den Notizen.")
        return "\n".join(lines)
    shown = notes[offset:offset + count]
    head = f"{len(shown)} {'Notiz' if len(shown) == 1 else 'Notizen'} zu „{data['title']}“"
    if offset:
        head += f" (weiter ab Nr. {offset + 1})"
    if data.get("fallback"):
        head += f" – {data['fallback']}"
    if data.get("keyword_only"):
        head += " (nur Stichwortsuche)"
    lines += [head, ""]
    for i, n in enumerate(shown, start=offset + 1):
        lines.append(f"{i}. {n['path']} ({fmt_int(n['tokens'])} Tokens)")
        for j, h in enumerate(n["hits"]):
            s, e = _neighbors(layout, n["path"], h["start"], h["end"], params.get("neighbors", 0))
            printed = h.get("printed", "") if (s, e) == (h["start"], h["end"]) else ""
            lines.append(f"   › {h['label']}, {format_range(n['unit'], s, e)}{printed} ({label(h['strength'])})")
            if i == offset + 1 and j == 0:
                lines.append(f"   „{_snippet(h['snippet_src'], data.get('terms', []))}“")
        lines.append("")
    rest = len(notes) - (offset + len(shown))
    if rest > 0:
        lines.append(f"[--weiter: {rest} weitere {'Notiz' if rest == 1 else 'Notizen'}]")
    else:
        while lines and not lines[-1]:
            lines.pop()
    best = shown[0]
    h0 = best["hits"][0]
    anchor = f"#{h0['heading'].split(' > ')[-1]}" if h0["heading"] else f":{h0['start']}-{h0['end']}"
    lines.append(f'Lesen: plug-n-rag lesen "{best["path"]}{anchor}" (nur passende Abschnitte, nicht ganze Dateien)')
    return "\n".join(lines)


def _render_cached(layout: Layout, cached: dict, params: dict) -> str:
    offset = cached.get("first", 0) + cached.get("page", 0) * cached.get("page_size", 3)
    if offset >= len(cached["notes"]):
        return "Keine weiteren Treffer."
    count = cached.get("page_size", 3)
    cached["page"] = cached.get("page", 0) + 1
    atomic_write_json(layout.cache_dir / "last_search.json", cached, indent=None)
    out = _render(layout, cached, offset, count, params)
    _log_search(layout, cached, cached["page"], count, out, offset=offset)
    return out


def _log_search(layout: Layout, data: dict, page: int, count: int, out: str, offset: int = 0) -> None:
    shown = data["notes"][offset:offset + count]
    tuning.log_event(layout, {
        "cmd": "suche",
        "purpose": data.get("purpose"),
        "page": page,
        "n": len(shown) + offset,
        "more": max(0, len(data["notes"]) - offset - len(shown)),
        "results": [[n["path"], i] for i, n in enumerate(data["notes"][: offset + len(shown) + 10], start=1)],
        "tokens": estimate_tokens(out),
        "full_tokens": sum(n["tokens"] for n in shown),
        "filtered": bool(data.get("fallback")),
    })


def _pending_notice(layout: Layout) -> str | None:
    errors_or_pending = read_json(layout.cache_dir / "pending.json", {}) or {}
    n = len(errors_or_pending.get("pending", []))
    if n:
        return f"{n} Dateien sind noch nicht semantisch indexiert (Stichwortsuche deckt sie ab)."
    return None
