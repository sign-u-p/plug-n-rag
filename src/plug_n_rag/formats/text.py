"""Plain text files. Positions are lines, one section, blocks are paragraphs."""

from __future__ import annotations

from pathlib import Path

from ..util import estimate_tokens
from .base import Block, Document, Section


def parse_text(source: str, text: str) -> Document:
    lines = text.splitlines()
    blocks: list[Block] = []
    cur: list[tuple[int, str]] = []
    for i, raw in enumerate(lines, start=1):
        if not raw.strip():
            if cur:
                blocks.append(Block(cur[0][0], cur[-1][0], "\n".join(t for _, t in cur).strip()))
                cur = []
            continue
        cur.append((i, raw))
    if cur:
        blocks.append(Block(cur[0][0], cur[-1][0], "\n".join(t for _, t in cur).strip()))
    sections = [Section("", 0, "", blocks[0].start, len(lines), blocks)] if blocks else []
    stem = Path(source).stem
    return Document(
        source=source,
        format="text",
        unit="lines",
        title=stem,
        explicit_title="",
        sections=sections,
        outline=[],
        total_units=len(lines),
        tokens=estimate_tokens(text),
    )
