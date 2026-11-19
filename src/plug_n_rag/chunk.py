"""Split a Document into chunks for embedding and full-text search.

Rules (SPEC "Chunking"):
* split at headings; ``heading_path`` such as ``Grundlagen > Modulation``
* sections longer than ~512 tokens are split at paragraphs with ~15 % overlap
* documents without text get a stub chunk made of title and headings
* embedding input: ``<file name> > <title> > <heading_path>`` + blank line + text

The chunk hash covers the *explicit* title, the heading path and the chunk text, but not the
file name or folder. Renaming or moving a note therefore reuses every vector.
Breadcrumb, stub chunk and hash recipe follow git-rag (MIT, Copyright (c) 2026 Dogfood Lab).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .formats.base import Block, Document
from .util import estimate_tokens, sha256_text

CHUNKING_VERSION = "v1"
EMBED_TEXT_VERSION = "v1"
TARGET_TOKENS = 512
OVERLAP_RATIO = 0.15


@dataclass
class Chunk:
    hash: str
    heading_path: str
    start: int
    end: int
    tokens: int
    text: str
    embed_text: str
    stub: bool = False


def chunk_hash(title: str, heading_path: str, text: str) -> str:
    return sha256_text(f"{title}\n{heading_path}\n{text}")


def breadcrumb(stem: str, title: str, heading_path: str) -> str:
    parts = [stem]
    if title and title != stem:
        parts.append(title)
    if heading_path:
        parts.append(heading_path)
    return " > ".join(parts)


_SENT_RE = re.compile(r"(?<=[.!?…])\s+")


def _split_big_block(block: Block, limit: int) -> list[Block]:
    """Split a single oversized block at line, then sentence boundaries."""
    lines = block.text.split("\n")
    if block.end > block.start and len(lines) == block.end - block.start + 1:
        units = [(block.start + i, ln) for i, ln in enumerate(lines)]
    else:
        units = [(block.start, s) for s in _SENT_RE.split(block.text) if s.strip()]
        if len(units) <= 1:
            text = block.text
            size = limit * 4
            units = [(block.start, text[i:i + size]) for i in range(0, len(text), size)]
    out: list[Block] = []
    cur: list[tuple[int, str]] = []
    cur_tok = 0
    for pos, txt in units:
        t = estimate_tokens(txt)
        if cur and cur_tok + t > limit:
            out.append(Block(cur[0][0], max(cur[-1][0], cur[0][0]), _join(cur, block)))
            cur, cur_tok = [], 0
        cur.append((pos, txt))
        cur_tok += t
    if cur:
        out.append(Block(cur[0][0], max(cur[-1][0], cur[0][0]), _join(cur, block)))
    if block.start == block.end:  # page-based: all parts keep the same position
        for b in out:
            b.start = b.end = block.start
    return out


def _join(parts: list[tuple[int, str]], block: Block) -> str:
    sep = "\n" if block.end > block.start else " "
    return sep.join(t for _, t in parts).strip()


def _group_blocks(blocks: list[Block], limit: int) -> list[list[Block]]:
    expanded: list[Block] = []
    for b in blocks:
        if estimate_tokens(b.text) > limit:
            expanded.extend(_split_big_block(b, limit))
        else:
            expanded.append(b)
    groups: list[list[Block]] = []
    cur: list[Block] = []
    cur_tok = 0
    overlap_budget = int(limit * OVERLAP_RATIO)
    for b in expanded:
        t = estimate_tokens(b.text)
        if cur and cur_tok + t > limit:
            groups.append(cur)
            tail = cur[-1]
            if estimate_tokens(tail.text) <= overlap_budget:
                cur, cur_tok = [tail], estimate_tokens(tail.text)
            else:
                cur, cur_tok = [], 0
        cur.append(b)
        cur_tok += t
    if cur:
        groups.append(cur)
    return groups


def chunk_document(doc: Document, limit: int = TARGET_TOKENS) -> list[Chunk]:
    title = doc.explicit_title
    chunks: list[Chunk] = []
    sep = "\n\n"
    for section in doc.sections:
        if not section.blocks:
            continue
        for gi, group in enumerate(_group_blocks(section.blocks, limit)):
            text = sep.join(b.text for b in group)
            crumb = breadcrumb(doc.stem, doc.title, section.heading_path)
            chunks.append(
                Chunk(
                    hash=chunk_hash(title, section.heading_path, text),
                    heading_path=section.heading_path,
                    start=section.start if gi == 0 else group[0].start,
                    end=group[-1].end,
                    tokens=estimate_tokens(text),
                    text=text,
                    embed_text=f"{crumb}\n\n{text}",
                )
            )
    if not chunks:
        heads = " > ".join(o.heading for o in doc.outline)
        text = heads or doc.title
        crumb = breadcrumb(doc.stem, doc.title, "")
        chunks.append(
            Chunk(
                hash=chunk_hash(title, "", text),
                heading_path="",
                start=1,
                end=max(1, doc.total_units),
                tokens=estimate_tokens(text),
                text=text,
                embed_text=f"{crumb}\n\n{text}",
                stub=True,
            )
        )
    return chunks

