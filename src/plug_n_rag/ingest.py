"""Ingestion (``aufnehmen``): turn PDFs into text, page by page, through a cascade.

1. text layer (pypdf) – free and exact
2. local OCR (Tesseract with German language pack, if installed) for pages without text
3. quality check: OCR confidence and share of real words
4. pages that fail → subagent ``transkription`` (Haiku), only with consent
5. escalation to Sonnet is decided by the main agent

The CLI does stages 1–3, renders page images for stage 4 into the local cache and later
assembles the result. Vault mode: a new Markdown note next to the original (existing notes
are never changed). Collection mode: only the extract cache, never inside the folder.
"""

from __future__ import annotations

import datetime as _dt
import json
import re
import shutil
import subprocess
from pathlib import Path

from .config import Layout
from .formats.pdf import EXTRACT_VERSION, MIN_PAGE_CHARS, load_extract
from .util import atomic_write_json, atomic_write_text, read_json, sha256_bytes

WORD_RE = re.compile(r"\S+")
REAL_WORD_RE = re.compile(r"^[A-Za-zÄÖÜäöüßÀ-ÿ][A-Za-zÄÖÜäöüßÀ-ÿ\-]+[.,;:!?)]?$")
MIN_CONFIDENCE = 70.0
MIN_WORD_SHARE = 0.6
BATCH_PAGES = 20


def word_share(text: str) -> float:
    words = WORD_RE.findall(text)
    if not words:
        return 0.0
    return sum(1 for w in words if REAL_WORD_RE.match(w.strip("„“\"'(")) or w.isdigit()) / len(words)


def tesseract_available() -> bool:
    return shutil.which("tesseract") is not None


class RenderError(RuntimeError):
    pass


def _render_page(pdf: Path, page: int, out_png: Path, dpi: int = 200) -> None:
    """Render one page to PNG. Raises RenderError with a readable reason if nothing works."""
    out_png.parent.mkdir(parents=True, exist_ok=True)
    reasons = []
    try:
        import pypdfium2 as pdfium

        doc = pdfium.PdfDocument(str(pdf))
        try:
            img = doc[page - 1].render(scale=dpi / 72).to_pil()
            img.save(out_png)
        finally:
            doc.close()
        return
    except ImportError as exc:
        reasons.append(f"Python-Paket fehlt ({exc.name or exc})")
    except Exception as exc:  # noqa: BLE001 - report and try poppler
        reasons.append(f"pypdfium2: {exc}")
    if shutil.which("pdftoppm"):
        stem = out_png.with_suffix("")
        r = subprocess.run(["pdftoppm", "-f", str(page), "-l", str(page), "-r", str(dpi), "-png",
                            "-singlefile", str(pdf), str(stem)], capture_output=True, timeout=120)
        if r.returncode == 0 and out_png.exists():
            return
        reasons.append("pdftoppm schlug fehl")
    else:
        reasons.append("pdftoppm nicht installiert")
    raise RenderError("; ".join(reasons))


def ocr_page(png: Path) -> tuple[str, float]:
    """Run Tesseract (German + English). Returns (text, mean confidence 0-100)."""
    r = subprocess.run(["tesseract", str(png), "stdout", "-l", "deu+eng", "tsv"],
                       capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        r = subprocess.run(["tesseract", str(png), "stdout", "tsv"], capture_output=True, text=True, timeout=300)
    words, confs, lines = [], [], {}
    for row in r.stdout.splitlines()[1:]:
        cols = row.split("\t")
        if len(cols) < 12 or not cols[11].strip():
            continue
        try:
            conf = float(cols[10])
        except ValueError:
            continue
        if conf < 0:
            continue
        key = (cols[2], cols[3], cols[4])
        lines.setdefault(key, []).append(cols[11])
        words.append(cols[11])
        confs.append(conf)
    text = "\n".join(" ".join(v) for v in lines.values())
    return text, (sum(confs) / len(confs) if confs else 0.0)


def _stage_dir(layout: Layout, file_hash: str) -> Path:
    return layout.cache_dir / "ingest" / file_hash.replace("sha256:", "")[:16]


def analyse(layout: Layout, pdf: Path, rel: str, *, use_ocr: bool = True) -> dict:
    data = pdf.read_bytes()
    file_hash = sha256_bytes(data)
    stage = _stage_dir(layout, file_hash)
    state = read_json(stage / "state.json") or {"source": rel, "file_hash": file_hash, "pages": {}}
    extract = load_extract(data, file_hash, layout.cache_dir)
    pages = extract.get("pages", [])
    state["page_count"] = len(pages)
    for i, text in enumerate(pages, start=1):
        key = str(i)
        if state["pages"].get(key, {}).get("method") in ("text", "ocr", "haiku", "sonnet"):
            continue
        if len(text) >= MIN_PAGE_CHARS and word_share(text) >= MIN_WORD_SHARE:
            atomic_write_text(stage / "pages" / f"{i:04d}.md", text)
            state["pages"][key] = {"method": "text"}
            continue
        entry = {"method": "pending"}
        if use_ocr and tesseract_available():
            png = stage / "img" / f"{i:04d}.png"
            try:
                if not png.exists():
                    _render_page(pdf, i, png)
            except RenderError:
                png = None
            if png is not None:
                ocr_text, conf = ocr_page(png)
                share = word_share(ocr_text)
                entry.update({"ocr_confidence": round(conf, 1), "word_share": round(share, 2)})
                atomic_write_text(stage / "ocr" / f"{i:04d}.md", ocr_text)
                if conf >= MIN_CONFIDENCE and share >= MIN_WORD_SHARE and len(ocr_text) >= MIN_PAGE_CHARS:
                    atomic_write_text(stage / "pages" / f"{i:04d}.md", ocr_text)
                    entry["method"] = "ocr"
        state["pages"][key] = entry
    atomic_write_json(stage / "state.json", state)
    state["stage"] = str(stage)
    return state


def prepare_images(layout: Layout, pdf: Path, state: dict) -> tuple[list[list[str]], list[int], str]:
    """Render page images for pending pages and group them in batches for the subagent.

    Returns (batches, pages without image, reason).
    """
    stage = Path(state["stage"])
    paths, failed, reason = [], [], ""
    for key, entry in sorted(state["pages"].items(), key=lambda kv: int(kv[0])):
        if entry.get("method") != "pending":
            continue
        png = stage / "img" / f"{int(key):04d}.png"
        try:
            if not png.exists():
                _render_page(pdf, int(key), png)
            paths.append(str(png))
        except RenderError as exc:
            failed.append(int(key))
            reason = str(exc)
    return [paths[i:i + BATCH_PAGES] for i in range(0, len(paths), BATCH_PAGES)], failed, reason


def record_transcription(layout: Layout, stage: Path, method: str) -> int:
    """Mark pages whose transcription file exists (written by the subagent) as done."""
    state = read_json(stage / "state.json") or {}
    n = 0
    for key, entry in state.get("pages", {}).items():
        if entry.get("method") == "pending" and (stage / "pages" / f"{int(key):04d}.md").exists():
            entry["method"] = method
            n += 1
    atomic_write_json(stage / "state.json", state)
    return n


def finalize(layout: Layout, pdf: Path, rel: str, *, accept_ocr: bool = False) -> str:
    data = pdf.read_bytes()
    file_hash = sha256_bytes(data)
    stage = _stage_dir(layout, file_hash)
    state = read_json(stage / "state.json") or {}
    pages = state.get("pages", {})
    n = state.get("page_count", len(pages))
    texts, methods, missing = [], set(), []
    for i in range(1, n + 1):
        entry = pages.get(str(i), {})
        p = stage / "pages" / f"{i:04d}.md"
        if not p.exists() and accept_ocr and (stage / "ocr" / f"{i:04d}.md").exists():
            p = stage / "ocr" / f"{i:04d}.md"
            entry = {**entry, "method": "lokal-unsicher"}
        if p.exists():
            texts.append(p.read_text(encoding="utf-8").strip())
            methods.add(entry.get("method", "text"))
        else:
            texts.append("[nicht erkannt]")
            missing.append(i)
    kind = "haiku" if "haiku" in methods else "sonnet" if "sonnet" in methods else (
        "lokal" if methods & {"ocr", "lokal-unsicher"} else "text")
    if "sonnet" in methods and "haiku" in methods:
        kind = "haiku+sonnet"
    if layout.mode == "collection":
        extract = load_extract(data, file_hash, layout.cache_dir)
        extract["pages"] = [t if t != "[nicht erkannt]" else "" for t in texts]
        extract["version"] = EXTRACT_VERSION
        extract["transcription"] = kind
        atomic_write_json(layout.cache_dir / "extract" / (file_hash.replace("sha256:", "") + ".json"), extract,
                          indent=None)
        where = "im lokalen Cache (die Sammlung bleibt unverändert)"
        target_rel = rel
    else:
        target = pdf.with_suffix(".md")
        if target.exists():
            target = pdf.with_name(pdf.stem + " (Transkription).md")
        if target.exists():
            return f"{target.name} existiert bereits, nichts überschrieben."
        body = [
            "---",
            f"quelle: \"{rel}\"",
            f"transkription: {kind}",
            f"aufgenommen: {_dt.date.today().isoformat()}",
            "---",
            f"# {pdf.stem}",
            "",
        ]
        for i, t in enumerate(texts, start=1):
            body += [f"<!-- Seite {i} -->", t, ""]
        atomic_write_text(target, "\n".join(body))
        target_rel = target.relative_to(layout.root).as_posix()
        where = f"als neue Notiz {target_rel}"
    msg = f"{rel}: {n} Seiten abgelegt {where} (Transkription: {kind})."
    if missing:
        msg += f" Nicht erkannt: Seiten {', '.join(map(str, missing))}."
    return msg


def ingest(layout: Layout, files: list[Path], *, transcribe: str = "fragen", write_pages: bool = False) -> str:
    """transcribe: 'fragen' (ask first), 'lokal' (never send pages), 'erlaubt' (consent given)."""
    out = []
    for f in files:
        f = f if f.is_absolute() else (Path.cwd() / f)
        if not f.exists():
            out.append(f"{f}: Datei nicht gefunden.")
            continue
        if f.suffix.lower() != ".pdf":
            out.append(f"{f.name}: Nur PDF wird in Version 1 aufgenommen. Markdown und Text werden direkt indexiert.")
            continue
        try:
            rel = f.resolve().relative_to(layout.root.resolve()).as_posix()
        except ValueError:
            rel = f.name
        state = analyse(layout, f, rel)
        pages = state["pages"]
        counts: dict[str, int] = {}
        for e in pages.values():
            counts[e["method"]] = counts.get(e["method"], 0) + 1
        pending = sorted(int(k) for k, e in pages.items() if e["method"] == "pending")
        line = (f"{rel}: {state['page_count']} Seiten · Textebene {counts.get('text', 0)} · "
                f"lokal erkannt {counts.get('ocr', 0)} · offen {len(pending)}")
        if not tesseract_available() and pending:
            line += " (lokale Texterkennung nicht installiert: Tesseract mit Sprachpaket deu)"
        out.append(line)
        if not pending:
            out.append(finalize(layout, f, rel))
            continue
        if transcribe == "lokal":
            out.append(finalize(layout, f, rel, accept_ocr=True))
            continue
        if transcribe == "fragen":
            out.append(f"FRAGE AN NUTZER:IN: {len(pending)} Seiten sind eingescannt oder schlecht lesbar. "
                       "Soll Claude sie vollständig lesen und abschreiben? Dann gehen diese Seiten an Anthropic "
                       f"(geschätzt {len(pending) * 2500:,} Tokens mit Haiku). Alternativ erkenne ich den Text "
                       "nur lokal, das ist aber ungenauer.".replace(",", "."))
            out.append(f"Danach: `plug-n-rag aufnehmen \"{rel}\" --transkription erlaubt` oder `--transkription lokal`.")
            continue
        batches, failed, reason = prepare_images(layout, f, state)
        if failed:
            out.append(f"FEHLER: Für {len(failed)} Seiten konnten keine Seitenbilder erzeugt werden ({reason}). "
                       "Ohne Bilder ist kein Abschreiben möglich. Lösung: plug-n-rag über den Starter neu aufrufen "
                       "(er installiert pypdfium2 und Pillow) oder Poppler (pdftoppm) installieren.")
            if not batches:
                continue
        plan = {"source": rel, "stage": state["stage"], "pages_dir": str(Path(state["stage"]) / "pages"),
                "batches": batches}
        out.append("TRANSKRIPTION: Bitte den Subagenten `transkription` je Bündel aufrufen. Plan:")
        out.append(json.dumps(plan, ensure_ascii=False))
        out.append(f"Danach: `plug-n-rag aufnehmen \"{rel}\" --abschliessen haiku` (oder sonnet).")
    return "\n".join(out)


def complete(layout: Layout, files: list[Path], method: str) -> str:
    out = []
    for f in files:
        f = f if f.is_absolute() else (Path.cwd() / f)
        rel = f.resolve().relative_to(layout.root.resolve()).as_posix() if f.resolve().is_relative_to(
            layout.root.resolve()) else f.name
        stage = _stage_dir(layout, sha256_bytes(f.read_bytes()))
        n = record_transcription(layout, stage, method)
        out.append(f"{rel}: {n} transkribierte Seiten übernommen.")
        out.append(finalize(layout, f, rel))
    return "\n".join(out)
