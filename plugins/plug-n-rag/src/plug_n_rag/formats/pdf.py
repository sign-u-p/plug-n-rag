"""PDF files with a text layer (via pypdf). Positions are pages.

Extracted text is cached by file hash under ``<cache>/extract/`` and never written into the
user's folder. Scanned pages without a text layer are reported, not guessed.
"""

from __future__ import annotations

import collections
import io
import logging
import re
import warnings
from pathlib import Path

from ..util import atomic_write_json, estimate_tokens, read_json
from .base import Block, Document, ExtractionError, NeedsTranscription, OutlineItem, Section
from ..i18n import tr

EXTRACT_VERSION = "pdf-v2"  # v2: printed page numbers
MIN_PAGE_CHARS = 25  # below this a page counts as "no text layer" (likely scanned)


def quiet_pypdf() -> None:
    """pypdf logs one warning per font it cannot fully decode (e.g. "fontTools is required…").
    With large collections that is tens of kilobytes of noise in the agent's context."""
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    warnings.filterwarnings("ignore", module="pypdf")


quiet_pypdf()

PAGE_NO_RE = re.compile(r"^\s*[-–—]?\s*(?:S\.|Seite|Page)?\s*(\d{1,4})\s*[-–—]?\s*$", re.IGNORECASE)


def printed_page_labels(reader, pages: list[str]) -> list[str] | None:
    """Printed page numbers, if they differ from the PDF page index.

    1. The PDF's own page labels (/PageLabels), e.g. roman numbers in the front matter.
    2. Otherwise: a bare number in the first or last line of the page text, if most such
       numbers agree on one offset (PDF page 1 = book page 11).
    """
    n = len(pages)
    try:
        root = reader.trailer["/Root"]
        if "/PageLabels" in root:
            labels = list(reader.page_labels)
            if len(labels) == n and any(lab != str(i + 1) for i, lab in enumerate(labels)):
                return [str(lab) for lab in labels]
    except Exception:  # noqa: BLE001 - labels are optional
        pass
    offsets: collections.Counter = collections.Counter()
    found = 0
    for i, text in enumerate(pages):
        lines = [ln for ln in text.splitlines() if ln.strip()]
        if not lines:
            continue
        for cand in (lines[0], lines[-1]):
            m = PAGE_NO_RE.match(cand)
            if m:
                offsets[int(m.group(1)) - (i + 1)] += 1
                found += 1
                break
    if not offsets:
        return None
    offset, count = offsets.most_common(1)[0]
    if offset == 0 or count < 3 or count < 0.3 * n:
        return None
    return [str(i + 1 + offset) if i + 1 + offset > 0 else "" for i in range(n)]


def _clean(text: str) -> str:
    text = text.replace("\x00", "")
    text = re.sub(r"-\n(?=[a-zäöüß])", "", text)  # join hyphenated line breaks
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _walk_outline(reader, items, level: int, out: list) -> None:
    for item in items:
        if isinstance(item, list):
            _walk_outline(reader, item, level + 1, out)
            continue
        try:
            page = reader.get_destination_page_number(item) + 1
            title = str(item.title).strip()
        except Exception:  # noqa: BLE001 - broken outlines are common
            continue
        if title:
            out.append((title, level, page))


def extract_pdf(data: bytes) -> dict:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover
        raise ExtractionError(tr("pypdf ist nicht installiert", "pypdf is not installed")) from exc
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception as exc:  # noqa: BLE001
                raise ExtractionError(tr("PDF ist verschlüsselt", "PDF is encrypted")) from exc
        pages = []
        for page in reader.pages:
            try:
                pages.append(_clean(page.extract_text() or ""))
            except Exception:  # noqa: BLE001
                pages.append("")
        outline: list = []
        try:
            _walk_outline(reader, reader.outline, 1, outline)
        except Exception:  # noqa: BLE001
            outline = []
        meta = {}
        try:
            info = reader.metadata or {}
            if info.get("/Title"):
                meta["title"] = str(info.get("/Title")).strip()
            if info.get("/Author"):
                meta["author"] = str(info.get("/Author")).strip()
        except Exception:  # noqa: BLE001
            pass
    except ExtractionError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ExtractionError(tr(f"PDF konnte nicht gelesen werden: {exc}", f"PDF could not be read: {exc}")) from exc
    try:
        labels = printed_page_labels(reader, pages)
    except Exception:  # noqa: BLE001
        labels = None
    return {"version": EXTRACT_VERSION, "pages": pages, "outline": outline, "meta": meta, "labels": labels}


def load_extract(data: bytes, file_hash: str, cache_dir: Path | None) -> dict:
    if cache_dir is not None:
        cpath = cache_dir / "extract" / (file_hash.replace("sha256:", "") + ".json")
        cached = read_json(cpath)
        if cached and cached.get("version") == EXTRACT_VERSION:
            return cached
    result = extract_pdf(data)
    if cache_dir is not None and cached and cached.get("transcription") and cached.get("pages"):
        # A newer extractor must never throw away paid transcriptions: keep their page texts.
        result["pages"] = cached["pages"]
        result["transcription"] = cached["transcription"]
    if cache_dir is not None:
        atomic_write_json(cpath, result, indent=None)
    return result


def parse_pdf(source: str, extract: dict) -> Document:
    pages: list[str] = extract.get("pages", [])
    n = len(pages)
    empty = [i + 1 for i, p in enumerate(pages) if len(p) < MIN_PAGE_CHARS]
    if n == 0 or len(empty) == n:
        raise NeedsTranscription(
            tr(f"wartet auf Aufnahme: keine Textebene ({n} Seiten, eingescannt), /plug-n-rag:aufnehmen",
               f"waiting for ingestion: no text layer ({n} pages, scanned), /plug-n-rag:ingest")
        )
    meta = dict(extract.get("meta", {}))
    if extract.get("labels"):
        meta["page_labels"] = extract["labels"]
    if empty:
        meta["pages_without_text"] = empty
    outline_raw = sorted(extract.get("outline", []), key=lambda t: (t[2], t[1]))

    def page_blocks(first: int, last: int) -> list[Block]:
        out = []
        for p in range(first, last + 1):
            txt = pages[p - 1]
            if len(txt) >= MIN_PAGE_CHARS:
                out.append(Block(p, p, txt))
        return out

    sections: list[Section] = []
    outline: list[OutlineItem] = []
    if outline_raw:
        stack: list[tuple[int, str]] = []
        first_page = outline_raw[0][2]
        if first_page > 1:
            blocks = page_blocks(1, first_page - 1)
            if blocks:
                sections.append(Section("", 0, "", 1, first_page - 1, blocks))
        for i, (title, level, page) in enumerate(outline_raw):
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, title))
            nxt = outline_raw[i + 1][2] if i + 1 < len(outline_raw) else n + 1
            last = max(page, nxt - 1) if nxt > page else page
            # Only the first entry starting on a page owns the page text.
            owns = i == 0 or outline_raw[i - 1][2] != page
            blocks = page_blocks(page, min(last, n)) if owns else []
            sections.append(Section(title, level, " > ".join(t for _, t in stack), page, min(last, n), blocks))
            sub_end = n
            for t2, l2, p2 in outline_raw[i + 1:]:
                if l2 <= level:
                    sub_end = max(page, p2 - 1)
                    break
            text = "\n\n".join(pages[page - 1:sub_end])
            outline.append(OutlineItem(title, level, page, sub_end, estimate_tokens(text)))
    else:
        sections.append(Section("", 0, "", 1, n, page_blocks(1, n)))

    explicit = meta.get("title", "")
    return Document(
        source=source,
        format="pdf",
        unit="pages",
        title=explicit or Path(source).stem,
        explicit_title=explicit,
        sections=sections,
        outline=outline,
        meta=meta,
        total_units=n,
        tokens=estimate_tokens("\n\n".join(pages)),
    )
