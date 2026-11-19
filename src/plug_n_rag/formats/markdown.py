"""Markdown / Obsidian notes: frontmatter, headings, tags, wikilinks. Positions are lines.

Parsing ideas (heading paths, tags, wikilinks, title fallback) follow git-rag
(https://github.com/dogfoodlab-io/git-rag, MIT License, Copyright (c) 2026 Dogfood Lab).
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from ..util import estimate_tokens
from .base import Block, Document, OutlineItem, Section

HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$")
FENCE_RE = re.compile(r"^[ \t]*(```|~~~)")
WIKILINK_RE = re.compile(r"!?\[\[([^\]\|#]*)(#[^\]\|]*)?(\|[^\]]*)?\]\]")
MDLINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+?\.md)(#[^)]*)?\)")
TAG_RE = re.compile(r"(?<![\w/:&#\[])#([^\W\d][\w\-/]*|\d+[^\W\d][\w\-/]*)")
TRUTHY = {"true", "ja", "yes", "1", "wahr", "on"}


def split_frontmatter(lines: list[str]) -> tuple[dict, int]:
    """Return (frontmatter dict, number of lines it occupies including delimiters)."""
    if not lines or lines[0].strip() != "---":
        return {}, 0
    for i in range(1, min(len(lines), 400)):
        if lines[i].strip() in ("---", "..."):
            raw = "\n".join(lines[1:i])
            try:
                data = yaml.safe_load(raw) or {}
            except yaml.YAMLError:
                data = {}
            if not isinstance(data, dict):
                data = {}
            return data, i + 1
    return {}, 0


def _as_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [v for v in re.split(r"[,\s]+", value) if v]
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value if v is not None and str(v).strip()]
    return [str(value)]


def is_private(fm: dict) -> bool:
    for key in ("privat", "private"):
        if key in fm:
            v = fm[key]
            if isinstance(v, bool):
                return v
            if str(v).strip().lower() in TRUTHY:
                return True
    return False


def parse_markdown(source: str, text: str) -> Document:
    lines = text.splitlines()
    fm, fm_len = split_frontmatter(lines)
    stem = Path(source).stem

    # Pass 1: mark headings (outside code fences) and collect tags / links.
    headings: list[tuple[int, int, str]] = []  # (line_no, level, text)
    in_fence = False
    fence_marker = ""
    tags: list[str] = []
    links: list[str] = []
    for idx in range(fm_len, len(lines)):
        line = lines[idx]
        m_f = FENCE_RE.match(line)
        if m_f:
            marker = m_f.group(1)
            if not in_fence:
                in_fence, fence_marker = True, marker
            elif marker == fence_marker:
                in_fence = False
            continue
        if in_fence:
            continue
        m = HEADING_RE.match(line)
        if m:
            headings.append((idx + 1, len(m.group(1)), m.group(2).strip()))
            continue
        for t in TAG_RE.findall(line):
            tags.append(t.rstrip("/"))
        for m_l in WIKILINK_RE.finditer(line):
            target = m_l.group(1).strip()
            if target:
                links.append(Path(target).stem if target.endswith(".md") else target)
        for m_l in MDLINK_RE.finditer(line):
            links.append(Path(m_l.group(1)).stem)

    for t in _as_list(fm.get("tags")) + _as_list(fm.get("tag")):
        tags.append(t.lstrip("#"))
    tags = sorted({t.lower() for t in tags if t})
    seen: set[str] = set()
    uniq_links = []
    for link in links:
        key = link.lower()
        if key not in seen:
            seen.add(key)
            uniq_links.append(link)

    explicit_title = ""
    if isinstance(fm.get("title"), str) and fm["title"].strip():
        explicit_title = fm["title"].strip()
    elif isinstance(fm.get("titel"), str) and fm["titel"].strip():
        explicit_title = fm["titel"].strip()
    else:
        for _, level, htext in headings:
            if level == 1:
                explicit_title = htext
                break

    # Pass 2: sections with blocks. Section boundaries are heading lines.
    first_body = fm_len + 1
    total = len(lines)
    bounds = [h[0] for h in headings] + [total + 1]
    sections: list[Section] = []
    stack: list[tuple[int, str]] = []

    def blocks_for(start: int, end: int) -> list[Block]:
        out: list[Block] = []
        cur: list[tuple[int, str]] = []
        in_code = False
        for ln in range(start, end + 1):
            raw = lines[ln - 1]
            if FENCE_RE.match(raw):
                in_code = not in_code
                cur.append((ln, raw))
                continue
            if not in_code and not raw.strip():
                if cur:
                    out.append(Block(cur[0][0], cur[-1][0], "\n".join(t for _, t in cur).strip()))
                    cur = []
                continue
            cur.append((ln, raw))
        if cur:
            out.append(Block(cur[0][0], cur[-1][0], "\n".join(t for _, t in cur).strip()))
        return [b for b in out if b.text]

    pre_end = (headings[0][0] - 1) if headings else total
    if pre_end >= first_body:
        blocks = blocks_for(first_body, pre_end)
        if blocks:
            sections.append(Section("", 0, "", blocks[0].start, pre_end, blocks))

    for i, (ln, level, htext) in enumerate(headings):
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, htext))
        path = " > ".join(h for _, h in stack)
        end = bounds[i + 1] - 1
        sections.append(Section(htext, level, path, ln, end, blocks_for(ln + 1, end)))

    # Outline: each heading spans until the next heading of the same or higher level.
    outline: list[OutlineItem] = []
    for i, (ln, level, htext) in enumerate(headings):
        end = total
        for ln2, level2, _ in headings[i + 1:]:
            if level2 <= level:
                end = ln2 - 1
                break
        while end > ln and not lines[end - 1].strip():
            end -= 1
        seg = "\n".join(lines[ln - 1:end])
        outline.append(OutlineItem(htext, level, ln, end, estimate_tokens(seg)))

    meta = {}
    for key in ("type", "typ", "author", "autor", "date", "datum", "quelle", "source"):
        if key in fm and fm[key] is not None:
            meta[key] = str(fm[key])

    return Document(
        source=source,
        format="markdown",
        unit="lines",
        title=explicit_title or stem,
        explicit_title=explicit_title,
        sections=sections,
        outline=outline,
        tags=tags,
        links=uniq_links,
        private=is_private(fm),
        meta=meta,
        total_units=total,
        tokens=estimate_tokens(text),
    )
