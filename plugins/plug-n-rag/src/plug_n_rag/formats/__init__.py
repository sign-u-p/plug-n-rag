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


def load_document(abs_path: Path, rel: str, fmt: str, cache_dir: Path | None,
                  transcripts_dir: Path | None = None) -> tuple[Document, str]:
    """Parse a file. Returns (document, file_hash). Raises ExtractionError on failure."""
    data = abs_path.read_bytes()
    file_hash = sha256_bytes(data)
    return parse_bytes(data, rel, fmt, file_hash, cache_dir, transcripts_dir), file_hash


def parse_bytes(data: bytes, rel: str, fmt: str, file_hash: str, cache_dir: Path | None,
                transcripts_dir: Path | None = None) -> Document:
    if fmt == "markdown":
        return parse_markdown(rel, decode_text(data))
    if fmt == "text":
        return parse_text(rel, decode_text(data))
    if fmt == "pdf":
        return parse_pdf(rel, pdf_extract(data, rel, file_hash, cache_dir, transcripts_dir))
    raise ExtractionError(f"Unbekanntes Format: {fmt}")


def pdf_extract(data: bytes, rel: str, file_hash: str, cache_dir: Path | None,
                transcripts_dir: Path | None) -> dict:
    """The PDF's text, page by page. For scans, a saved transcript (``.plug-n-rag/abschriften/``)
    restores the text, so a lost cache or a colleague's copy needs no new transcription."""
    extract = load_extract(data, file_hash, cache_dir)
    if transcripts_dir is not None and not any(len(p) >= 25 for p in extract.get("pages", [])):
        pages = read_transcript(transcripts_dir / (rel + ".md"), file_hash)
        if pages:
            extract = {**extract, "pages": pages, "transcription": "abschrift"}
            if cache_dir is not None:
                from ..util import atomic_write_json

                atomic_write_json(cache_dir / "extract" / (file_hash.replace("sha256:", "") + ".json"),
                                  extract, indent=None)
    return extract


def read_transcript(path: Path, file_hash: str) -> list[str] | None:
    """Pages of a transcript file written by ``aufnehmen`` if it belongs to this exact file."""
    import re

    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    m = re.search(r"^datei_hash:\s*\"?([^\"\n]+)\"?\s*$", text, re.MULTILINE)
    if not m or m.group(1).strip() != file_hash:
        return None
    parts = re.split(r"^<!-- Seite (\d+) -->\s*$", text, flags=re.MULTILINE)
    pages: dict[int, str] = {}
    for i in range(1, len(parts) - 1, 2):
        body = parts[i + 1].strip()
        pages[int(parts[i])] = "" if body == "[nicht erkannt]" else body
    if not pages:
        return None
    return [pages.get(n, "") for n in range(1, max(pages) + 1)]


def read_units(abs_path: Path, fmt: str, start: int, end: int, cache_dir: Path | None,
               transcripts_dir: Path | None = None, rel: str = "") -> str:
    """Return the raw text of a position range (lines or pages), for reading sections."""
    data = abs_path.read_bytes()
    if fmt in ("markdown", "text"):
        lines = decode_text(data).splitlines()
        return "\n".join(lines[start - 1:end])
    if fmt == "pdf":
        extract = pdf_extract(data, rel or abs_path.name, sha256_bytes(data), cache_dir,
                              transcripts_dir if rel else None)
        pages = extract.get("pages", [])
        parts = []
        for p in range(start, min(end, len(pages)) + 1):
            parts.append(f"<!-- Seite {p} -->\n{pages[p - 1]}")
        return "\n\n".join(parts)
    raise ExtractionError(f"Unbekanntes Format: {fmt}")
