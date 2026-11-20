"""Ingestion (``aufnehmen``): turn PDFs into text, page by page, through a cascade.

1. text layer (pypdf) – free and exact
2. local OCR (Tesseract with the German and/or English language pack, whichever is installed) for pages without text
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
from .i18n import is_en, tr
from .util import fmt_int, atomic_write_json, atomic_write_text, read_json, sha256_bytes

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
        reasons.append(tr(f"Python-Paket fehlt ({exc.name or exc})", f"Python package missing ({exc.name or exc})"))
    except Exception as exc:  # noqa: BLE001 - report and try poppler
        reasons.append(f"pypdfium2: {exc}")
    if shutil.which("pdftoppm"):
        stem = out_png.with_suffix("")
        r = subprocess.run(["pdftoppm", "-f", str(page), "-l", str(page), "-r", str(dpi), "-png",
                            "-singlefile", str(pdf), str(stem)], capture_output=True, timeout=120)
        if r.returncode == 0 and out_png.exists():
            return
        reasons.append(tr("pdftoppm schlug fehl", "pdftoppm failed"))
    else:
        reasons.append(tr("pdftoppm nicht installiert", "pdftoppm not installed"))
    raise RenderError("; ".join(reasons))


OCR_LANGS = ("deu", "eng")
_installed_langs: list[str] | None = None


def tesseract_langs() -> list[str]:
    """Language packs Tesseract has installed (asked once per process)."""
    global _installed_langs
    if _installed_langs is None:
        try:
            r = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True, timeout=30)
            out = (r.stdout or "") + "\n" + (r.stderr or "")  # older versions print the list to stderr
            _installed_langs = [ln.strip() for ln in out.splitlines()
                                if ln.strip() and " " not in ln.strip() and not ln.strip().endswith(":")]
        except (OSError, subprocess.SubprocessError):
            _installed_langs = []
    return _installed_langs


def ocr_languages() -> str | None:
    """The `-l` value: German and English as far as installed, the folder's language first.

    None means: neither pack is there, Tesseract uses its default.
    """
    have = set(tesseract_langs())
    order = ("eng", "deu") if is_en() else ("deu", "eng")
    usable = [lang for lang in order if lang in have]
    return "+".join(usable) or None


def missing_ocr_languages() -> list[str]:
    if not tesseract_available():
        return []
    have = set(tesseract_langs())
    return [lang for lang in OCR_LANGS if lang not in have]


def ocr_page(png: Path) -> tuple[str, float]:
    """Run Tesseract with the installed German/English packs. Returns (text, mean confidence 0-100)."""
    cmd = ["tesseract", str(png), "stdout"]
    langs = ocr_languages()
    if langs:
        cmd += ["-l", langs]
    r = subprocess.run(cmd + ["tsv"], capture_output=True, text=True, timeout=300)
    if r.returncode != 0 and langs:  # a broken pack: fall back to Tesseract's default
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


PLACES = {"vault": ("neben_original", "ordner"), "collection": ("ordner", "intern")}
PLACE_FROM_EN = {"beside": "neben_original", "folder": "ordner", "internal": "intern"}
PLACE_EN = {v: k for k, v in PLACE_FROM_EN.items()}


def place_text(key: str) -> str:
    return {
        "neben_original": tr("neben dem Original-PDF", "next to the original PDF"),
        "ordner": tr("in einem eigenen Ordner (Standard „Abschriften/“, gleiche Unterordner wie die PDFs)",
                     "in a folder of their own (default “Abschriften/”, same subfolders as the PDFs)"),
        "intern": tr("nur intern für die Suche, keine zusätzlichen Dateien",
                     "only internally for search, no additional files"),
    }[key]


def transcript_place(layout: Layout) -> str | None:
    """Configured place for transcripts, or None if nobody has decided yet."""
    ort = (layout.config.get("abschriften") or {}).get("ort")
    valid = PLACES["collection" if layout.mode == "collection" else "vault"]
    return ort if ort in valid else None


def place_question(layout: Layout) -> str:
    opts = PLACES["collection" if layout.mode == "collection" else "vault"]
    lines = [tr("FRAGE AN NUTZER:IN (einmalig, wird gemerkt): Wohin sollen Abschriften von PDFs?",
                "QUESTION FOR THE USER (asked once, remembered): Where should transcripts of PDFs go?")]
    for key in opts:
        text = place_text(key)
        if layout.mode == "collection" and key == "ordner":
            text = tr("als lesbare Markdown-Dateien in .plug-n-rag/abschriften/ (wandern mit dem Index mit)",
                      "as readable Markdown files in .plug-n-rag/abschriften/ (they travel with the index)")
        lines.append(f"  {tr(key, PLACE_EN[key])}: {text}")
    lines.append(tr("Danach denselben Befehl mit `--ablage <wahl>` ausführen.",
                    "Then run the same command with `--place <choice>`."))
    return "\n".join(lines)


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
            texts.append(tr("[nicht erkannt]", "[not recognised]"))
            missing.append(i)
    kind = "haiku" if "haiku" in methods else "sonnet" if "sonnet" in methods else (
        "lokal" if methods & {"ocr", "lokal-unsicher"} else "text")
    if "sonnet" in methods and "haiku" in methods:
        kind = "haiku+sonnet"
    place = transcript_place(layout)
    header = [
        "---",
        f"{tr('quelle', 'source')}: \"{rel}\"",
        f"{tr('datei_hash', 'file_hash')}: \"{file_hash}\"",
        f"{tr('transkription', 'transcription')}: {kind}",
        f"{tr('aufgenommen', 'ingested')}: {_dt.date.today().isoformat()}",
        "---",
        f"# {pdf.stem}",
        "",
    ]
    body = list(header)
    for i, t in enumerate(texts, start=1):
        body += [f"<!-- {tr('Seite', 'Page')} {i} -->", t, ""]
    if layout.mode == "collection":
        # the index always uses the page texts (exact page citations) ...
        extract = load_extract(data, file_hash, layout.cache_dir)
        extract["pages"] = [t if t not in ("[nicht erkannt]", "[not recognised]") else "" for t in texts]
        extract["version"] = EXTRACT_VERSION
        extract["transcription"] = kind
        atomic_write_json(layout.cache_dir / "extract" / (file_hash.replace("sha256:", "") + ".json"), extract,
                          indent=None)
        if place == "ordner":
            # ... and, if wanted, a readable copy that travels with the folder
            target = layout.transcripts_dir / (rel + ".md")
            atomic_write_text(target, "\n".join(body))
            shown = (target.relative_to(layout.root).as_posix() if layout.location == "inside" else str(target))
            where = tr(f"als lesbare Abschrift {shown} (die Sammlung selbst bleibt unverändert)",
                       f"as a readable transcript {shown} (the collection itself stays unchanged)")
        else:
            where = tr("nur intern im lokalen Cache (die Sammlung bleibt unverändert)",
                       "only internally in the local cache (the collection stays unchanged)")
    else:
        if place == "ordner":
            folder = str(layout.config.get("abschriften", {}).get("ordner") or "Abschriften").strip("/")
            target = layout.root / folder / Path(rel).with_suffix(".md")
        else:
            target = pdf.with_suffix(".md")
            if target.exists():
                target = pdf.with_name(pdf.stem + " (Transkription).md")
        if target.exists():
            return tr(f"{target.relative_to(layout.root).as_posix()} existiert bereits, nichts überschrieben.",
                      f"{target.relative_to(layout.root).as_posix()} already exists, nothing overwritten.")
        target.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(target, "\n".join(body))
        where = tr(f"als neue Notiz {target.relative_to(layout.root).as_posix()}",
                   f"as a new note {target.relative_to(layout.root).as_posix()}")
    msg = tr(f"{rel}: {n} Seiten abgelegt {where} (Transkription: {kind}).",
             f"{rel}: {n} pages saved {where} (transcription: {kind}).")
    if missing:
        msg += tr(f" Nicht erkannt: Seiten {', '.join(map(str, missing))}.",
                  f" Not recognised: pages {', '.join(map(str, missing))}.")
    return msg


def ingest(layout: Layout, files: list[Path], *, transcribe: str = "fragen", write_pages: bool = False) -> str:
    """transcribe: 'fragen' (ask first), 'lokal' (never send pages), 'erlaubt' (consent given)."""
    if transcript_place(layout) is None:
        return place_question(layout)
    out = []
    for f in files:
        f = f if f.is_absolute() else (Path.cwd() / f)
        if not f.exists():
            out.append(tr(f"{f}: Datei nicht gefunden.", f"{f}: file not found."))
            continue
        if f.suffix.lower() != ".pdf":
            out.append(tr(f"{f.name}: Nur PDF wird in Version 1 aufgenommen. Markdown und Text werden direkt indexiert.",
                          f"{f.name}: Only PDFs are ingested in version 1. Markdown and text are indexed directly."))
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
        line = tr(f"{rel}: {state['page_count']} Seiten · Textebene {counts.get('text', 0)} · "
                  f"lokal erkannt {counts.get('ocr', 0)} · offen {len(pending)}",
                  f"{rel}: {state['page_count']} pages · text layer {counts.get('text', 0)} · "
                  f"recognised locally {counts.get('ocr', 0)} · open {len(pending)}")
        if not tesseract_available() and pending:
            line += tr(" (lokale Texterkennung nicht installiert: Tesseract mit den Sprachpaketen deu und eng)",
                       " (local text recognition not installed: Tesseract with language packs eng/deu)")
        elif pending and (missing := missing_ocr_languages()):
            names = ", ".join(missing)
            line += tr(f" (Sprachpaket für die Texterkennung fehlt: {names}; erkannt wird mit den vorhandenen)",
                       f" (language pack for text recognition missing: {names}; the installed ones are used)")
        out.append(line)
        if not pending:
            out.append(finalize(layout, f, rel))
            continue
        if transcribe == "lokal":
            out.append(finalize(layout, f, rel, accept_ocr=True))
            continue
        if transcribe == "fragen":
            est = fmt_int(len(pending) * 2500)
            out.append(tr(f"FRAGE AN NUTZER:IN: {len(pending)} Seiten sind eingescannt oder schlecht lesbar. "
                          "Soll Claude sie vollständig lesen und abschreiben? Dann gehen diese Seiten an Anthropic "
                          f"(geschätzt {est} Tokens mit Haiku). Alternativ erkenne ich den Text "
                          "nur lokal, das ist aber ungenauer.",
                          f"QUESTION FOR THE USER: {len(pending)} pages are scanned or hard to read. "
                          "Should Claude read and transcribe them completely? Then these pages go to Anthropic "
                          f"(about {est} tokens with Haiku). Alternatively the text is recognised "
                          "locally only, which is less accurate."))
            out.append(tr(f"Danach: `plug-n-rag aufnehmen \"{rel}\" --transkription erlaubt` oder `--transkription lokal`.",
                          f"Then: `plug-n-rag ingest \"{rel}\" --transcription allowed` or `--transcription local`."))
            continue
        batches, failed, reason = prepare_images(layout, f, state)
        if failed:
            out.append(tr(f"FEHLER: Für {len(failed)} Seiten konnten keine Seitenbilder erzeugt werden ({reason}). "
                          "Ohne Bilder ist kein Abschreiben möglich. Lösung: plug-n-rag über den Starter neu aufrufen "
                          "(er installiert pypdfium2 und Pillow) oder Poppler (pdftoppm) installieren.",
                          f"ERROR: No page images could be created for {len(failed)} pages ({reason}). "
                          "Without images no transcription is possible. Fix: call plug-n-rag through its launcher "
                          "(it installs pypdfium2 and Pillow) or install Poppler (pdftoppm)."))
            if not batches:
                continue
        plan = {"source": rel, "stage": state["stage"], "pages_dir": str(Path(state["stage"]) / "pages"),
                "batches": batches}
        out.append(tr("TRANSKRIPTION: Bitte den Subagenten `transkription` je Bündel aufrufen. Plan:",
                      "TRANSCRIPTION: Please call the subagent `transkription` for each batch. Plan:"))
        out.append(json.dumps(plan, ensure_ascii=False))
        out.append(tr(f"Danach: `plug-n-rag aufnehmen \"{rel}\" --abschliessen haiku` (oder sonnet).",
                      f"Then: `plug-n-rag ingest \"{rel}\" --finish haiku` (or sonnet)."))
    return "\n".join(out)


def complete(layout: Layout, files: list[Path], method: str) -> str:
    out = []
    for f in files:
        f = f if f.is_absolute() else (Path.cwd() / f)
        rel = f.resolve().relative_to(layout.root.resolve()).as_posix() if f.resolve().is_relative_to(
            layout.root.resolve()) else f.name
        stage = _stage_dir(layout, sha256_bytes(f.read_bytes()))
        n = record_transcription(layout, stage, method)
        out.append(tr(f"{rel}: {n} transkribierte Seiten übernommen.", f"{rel}: {n} transcribed pages taken over."))
        out.append(finalize(layout, f, rel))
    return "\n".join(out)
