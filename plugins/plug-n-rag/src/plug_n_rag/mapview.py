"""The map (karte): folders, counts, descriptions, focus topics, frequent tags.

Focus topics are found by clustering the note vectors of each folder and naming each
cluster with frequent tags and heading words. The result is cached until the database
changes. The idea of a map before searching comes from git-semantic.
"""

from __future__ import annotations

import collections
import datetime as _dt
import json
import re

import numpy as np

from .config import Layout
from .db import open_db
from .search import STOPWORDS
from .i18n import tr
from .util import atomic_write_json, fmt_int, plural, read_json

WORD_RE = re.compile(r"[^\W\d_]{4,}", re.UNICODE)


def _kmeans(x: np.ndarray, k: int, iters: int = 20) -> np.ndarray:
    # deterministic init: farthest-point seeding from the first vector
    centers = [x[0]]
    for _ in range(1, k):
        d = np.min(np.stack([1 - x @ c for c in centers]), axis=0)
        centers.append(x[int(np.argmax(d))])
    c = np.stack(centers)
    labels = np.zeros(len(x), dtype=int)
    for _ in range(iters):
        labels = np.argmax(x @ c.T, axis=1)
        for j in range(k):
            m = x[labels == j]
            if len(m):
                v = m.mean(axis=0)
                c[j] = v / (np.linalg.norm(v) or 1)
    return labels


def _terms(rows) -> list[str]:
    cnt: collections.Counter = collections.Counter()
    for r in rows:
        for t in (r["tags"] or "").split():
            cnt[t] += 3
        for it in json.loads(r["outline"] or "[]"):
            for w in WORD_RE.findall(it["heading"]):
                if w.lower() not in STOPWORDS:
                    cnt[w] += 1
        for w in WORD_RE.findall(r["title"] or ""):
            if w.lower() not in STOPWORDS:
                cnt[w] += 1
    return [w for w, _ in cnt.most_common(3)]


def _folder_desc(cfg: dict, folder: str) -> str:
    folders = cfg.get("folders") or {}
    for key in (folder, folder + "/", "/" + folder, "/" + folder + "/"):
        if key in folders and folders[key]:
            return str(folders[key])
    return ""


def compute_map(layout: Layout) -> dict:
    conn, _ = open_db(layout)
    try:
        sig = conn.execute("SELECT value FROM meta WHERE key='hydrated'").fetchone()
        sig = sig[0] if sig else ""
        cached = read_json(layout.cache_dir / "map.json", {}) or {}
        if cached.get("sig") == sig and cached.get("cfg") == json.dumps(layout.config.get("folders"), sort_keys=True):
            return cached
        rows = conn.execute("SELECT path, folder, title, tags, outline, mtime, vec, tokens FROM notes").fetchall()
    finally:
        conn.close()
    by_folder: dict[str, list] = collections.defaultdict(list)
    for r in rows:
        by_folder[r["folder"] or tr("(Hauptordner)", "(top level)")].append(r)
    folders = []
    for folder in sorted(by_folder):
        items = by_folder[folder]
        with_vec = [r for r in items if r["vec"] is not None]
        topics: list[str] = []
        if len(with_vec) >= 4:
            x = np.stack([np.frombuffer(r["vec"], dtype=np.float32) for r in with_vec])
            k = min(3, max(1, len(with_vec) // 3))
            labels = _kmeans(x, k)
            for j in range(k):
                members = [with_vec[i] for i in range(len(with_vec)) if labels[i] == j]
                names = _terms(members)[:2]
                if names:
                    topics.append(" / ".join(names))
        else:
            topics = _terms(items)[:3]
        mt = [r["mtime"] for r in items if r["mtime"]]
        span = ""
        if mt:
            a = _dt.date.fromtimestamp(min(mt))
            b = _dt.date.fromtimestamp(max(mt))
            span = f"{a:%m/%Y}" if (a.year, a.month) == (b.year, b.month) else f"{a:%m/%Y}–{b:%m/%Y}"
        folders.append({
            "folder": folder, "count": len(items), "tokens": sum(r["tokens"] or 0 for r in items),
            "desc": _folder_desc(layout.config, folder), "topics": list(dict.fromkeys(topics)), "span": span,
        })
    tags: collections.Counter = collections.Counter()
    for r in rows:
        tags.update((r["tags"] or "").split())
    data = {"sig": sig, "cfg": json.dumps(layout.config.get("folders"), sort_keys=True),
            "notes": len(rows), "folders": folders, "tags": tags.most_common(12)}
    atomic_write_json(layout.cache_dir / "map.json", data, indent=None)
    return data


def karte(layout: Layout, short: bool = False) -> str:
    data = compute_map(layout)
    kind = "Vault" if layout.mode == "vault" else tr("Sammlung", "Collection")
    names = [f["folder"] for f in data["folders"]]
    n = data["notes"]
    if short:
        shown = ", ".join(names[:6]) + (" …" if len(names) > 6 else "")
        k = len(names)
        return tr(f"{kind}: {fmt_int(n)} {'Datei' if n == 1 else 'Dateien'} in "
                  f"{k} {'Bereich' if k == 1 else 'Bereichen'} ({shown}). "
                  "`plug-n-rag karte` für Details, `plug-n-rag suche \"…\" --zweck frage` zum Suchen.",
                  f"{kind}: {fmt_int(n)} {'file' if n == 1 else 'files'} in "
                  f"{k} {'area' if k == 1 else 'areas'} ({shown}). "
                  "`plug-n-rag map` for details, `plug-n-rag search \"…\" --purpose question` to search.")
    lines = [tr(f"{kind} {layout.root.name}: {fmt_int(n)} Dateien", f"{kind} {layout.root.name}: {plural(n, 'file', 'files')}"), ""]
    for f in data["folders"]:
        line = tr(f"{f['folder']}/ · {f['count']} Dateien · {fmt_int(f['tokens'])} Tokens",
                  f"{f['folder']}/ · {plural(f['count'], 'file', 'files')} · {fmt_int(f['tokens'])} tokens")
        if f["span"]:
            line += f" · {f['span']}"
        lines.append(line)
        if f["desc"]:
            lines.append(f"  {f['desc']}")
        if f["topics"]:
            lines.append(tr("  Schwerpunkte: ", "  Main topics: ") + "; ".join(f["topics"]))
    if data["tags"]:
        lines += ["", tr("Häufige Tags: ", "Frequent tags: ") + ", ".join(f"#{t} ({c})" for t, c in data["tags"])]
    return "\n".join(lines)
