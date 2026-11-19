"""Format-neutral document model.

Every supported file format is parsed into a :class:`Document`. Positions are expressed in
the format's natural *unit* (``lines`` for Markdown and text, ``pages`` for PDF, later
``paragraphs`` for DOCX). Nothing downstream (chunking, index, database, search) depends
on a concrete format.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Block:
    """A paragraph-like unit of text with its position range (inclusive)."""

    start: int
    end: int
    text: str


@dataclass
class Section:
    heading: str  # "" for text before the first heading
    level: int  # 0 for the preamble
    heading_path: str  # "Grundlagen > Modulation"
    start: int  # position of the heading itself (or first block)
    end: int  # last position of the section's own text (excluding sub-sections)
    blocks: list[Block] = field(default_factory=list)


@dataclass
class OutlineItem:
    heading: str
    level: int
    start: int
    end: int  # end of the whole subtree
    tokens: int = 0


@dataclass
class Document:
    source: str  # path relative to root, posix
    format: str  # markdown | text | pdf
    unit: str  # lines | pages | paragraphs
    title: str  # display title (explicit title or file stem)
    explicit_title: str  # frontmatter title / H1 / document metadata title, else ""
    sections: list[Section]
    outline: list[OutlineItem]
    tags: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    private: bool = False
    meta: dict = field(default_factory=dict)  # author, type, frontmatter extras
    total_units: int = 0
    tokens: int = 0

    @property
    def stem(self) -> str:
        return Path(self.source).stem


class ExtractionError(RuntimeError):
    """Raised when a file cannot be turned into text (e.g. a scanned PDF without text layer)."""


UNIT_LABEL = {"lines": ("Z.", "Zeile", "Zeilen"), "pages": ("S.", "Seite", "Seiten"),
              "paragraphs": ("Abs.", "Absatz", "Absätze")}


def format_range(unit: str, start: int, end: int) -> str:
    """'Z. 45–80', 'S. 3', 'S. 3–5'."""
    short = UNIT_LABEL.get(unit, ("Z.",))[0]
    if start == end:
        return f"{short} {start}"
    return f"{short} {start}–{end}"
