"""Format registry: maps file extensions to parsers and knows how to read positions back."""

from __future__ import annotations

from pathlib import Path

from ..util import sha256_bytes
from .base import Document, ExtractionError, format_range  # noqa: F401
from .markdown import parse_markdown
from .pdf import EXTRACT_VERSION as PDF_EXTRACT_VERSION
from .pdf import load_extract, parse_pdf
from .text import parse_text

EXTENSIONS = {
    ".md": "markdown",
    ".markdown": "markdown",
    ".txt": "text",
    ".text": "text",
    ".pdf": "pdf",
}

# Bumping one of these versions marks documents of that format as outdated.
EXTRACT_VERSIONS = {"markdown": "md-v1", "text": "txt-v1", "pdf": PDF_EXTRACT_VERSION}


def format_for(path: str | Path, enabled: list[str]) -> str | None:
    fmt = EXTENSIONS.get(Path(path).suffix.lower())
    return fmt if fmt in enabled else None


def decode_text(data: bytes) -> str:
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def load_document(abs_path: Path, rel: str, fmt: str, cache_dir: Path | None) -> tuple[Document, str]:
    """Parse a file. Returns (document, file_hash). Raises ExtractionError on failure."""
    data = abs_path.read_bytes()
    file_hash = sha256_bytes(data)
    return parse_bytes(data, rel, fmt, file_hash, cache_dir), file_hash


def parse_bytes(data: bytes, rel: str, fmt: str, file_hash: str, cache_dir: Path | None) -> Document:
    if fmt == "markdown":
        return parse_markdown(rel, decode_text(data))
    if fmt == "text":
        return parse_text(rel, decode_text(data))
    if fmt == "pdf":
        return parse_pdf(rel, load_extract(data, file_hash, cache_dir))
    raise ExtractionError(f"Unbekanntes Format: {fmt}")


def read_units(abs_path: Path, fmt: str, start: int, end: int, cache_dir: Path | None) -> str:
    """Return the raw text of a position range (lines or pages), for reading sections."""
    data = abs_path.read_bytes()
    if fmt in ("markdown", "text"):
        lines = decode_text(data).splitlines()
        return "\n".join(lines[start - 1:end])
    if fmt == "pdf":
        extract = load_extract(data, sha256_bytes(data), cache_dir)
        pages = extract.get("pages", [])
        parts = []
        for p in range(start, min(end, len(pages)) + 1):
            parts.append(f"<!-- Seite {p} -->\n{pages[p - 1]}")
        return "\n\n".join(parts)
    raise ExtractionError(f"Unbekanntes Format: {fmt}")
