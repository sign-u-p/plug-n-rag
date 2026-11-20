"""Silent inventory for the guided setup (no AI involved): what is there, what will it cost?"""

from __future__ import annotations

import collections
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from . import gitops
from .config import CONFIG_NAME, STATE_DIR_NAME, find_layout
from .scan import detect_template_folders
from .i18n import tr
from .util import estimate_tokens, fmt_int

PRIVATE_HINT_RE = re.compile(r"(tagebuch|journal|privat|private|personal|diary|persönlich)", re.I)
CLOUD_HINT_RE = re.compile(r"(iCloud|Mobile Documents|OneDrive|Dropbox|Google ?Drive|CloudStorage)", re.I)
WIKILINK_RE = re.compile(r"\[\[[^\]]+\]\]")
SECONDS_PER_CHUNK_LOCAL = 0.03  # measured on a 4-core cloud CPU with multilingual-e5-small
TOKENS_PER_CHUNK = 350


def _pdf_info(path: Path) -> tuple[int, bool, int]:
    """(pages, has text layer, estimated tokens). Samples up to 6 pages spread over the file."""
    try:
        from pypdf import PdfReader

        from .formats.pdf import quiet_pypdf

        quiet_pypdf()
        r = PdfReader(str(path))
        n = len(r.pages)
        if n == 0:
            return 0, False, 0
        idx = sorted({min(n - 1, round(i * (n - 1) / 5)) for i in range(6)}) if n > 6 else list(range(n))
        texts = [(r.pages[i].extract_text() or "").strip() for i in idx]
        with_text = [t for t in texts if len(t) >= 25]
        has_text = len(with_text) * 2 >= len(texts)
        avg_chars = sum(len(t) for t in texts) / len(texts)
        return n, has_text, int(estimate_tokens("x" * int(avg_chars)) * n)
    except Exception:  # noqa: BLE001
        return 0, False, 0


def _estimate(tokens: int, files: int, pdf_tokens: int, extra_chunks: int = 0) -> dict:
    chunks = max(1, tokens // TOKENS_PER_CHUNK + files) + extra_chunks
    total = tokens + pdf_tokens
    seconds = total / TOKENS_PER_CHUNK * SECONDS_PER_CHUNK_LOCAL * 3 + 15
    return {"tokens": total, "chunks": chunks, "local_seconds": round(seconds),
            "voyage_tokens": total + chunks * 15}


def inventory(root: Path) -> dict:
    root = root.resolve()
    md = 0
    txt_files = 0
    txt_tokens = 0
    md_bytes = 0
    md_tokens = 0
    with_fm = 0
    links = 0
    folders: collections.Counter = collections.Counter()
    other: collections.Counter = collections.Counter()
    pdfs = []
    big = []
    private_candidates = set()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d != "node_modules"]
        rel_dir = Path(dirpath).relative_to(root).as_posix()
        top = "" if rel_dir == "." else rel_dir.split("/")[0]
        for d in dirnames:
            if PRIVATE_HINT_RE.search(d):
                private_candidates.add((Path(rel_dir) / d).as_posix().lstrip("./") if rel_dir != "." else d)
        for name in filenames:
            if name.startswith("."):
                continue
            p = Path(dirpath) / name
            try:
                size = p.stat().st_size
            except OSError:
                continue
            rel = p.relative_to(root).as_posix()
            if size > 100 * 1024 * 1024:
                big.append((rel, size))
            ext = p.suffix.lower()
            if ext in (".md", ".markdown"):
                md += 1
                md_bytes += size
                folders[top or "(Hauptordner)"] += 1
                try:
                    text = p.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                md_tokens += estimate_tokens(text)
                if text.startswith("---"):
                    with_fm += 1
                links += len(WIKILINK_RE.findall(text))
            else:
                other[ext or "(ohne Endung)"] += 1
                if ext == ".pdf":
                    pages, has_text, tok = _pdf_info(p)
                    pdfs.append({"path": rel, "pages": pages, "text_layer": has_text,
                                 "tokens": tok if has_text else 0})
                elif ext in (".txt", ".text"):
                    txt_files += 1
                    txt_tokens += max(1, size // 4)
    is_git = gitops.is_repo(root)
    url = gitops.remote_url(root) if is_git else None
    gh = shutil.which("gh") is not None
    gh_auth = False
    if gh:
        try:
            gh_auth = subprocess.run(["gh", "auth", "status"], capture_output=True, timeout=10).returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            gh_auth = False
    layout = find_layout(root)
    pdf_tokens = sum(p["tokens"] for p in pdfs)
    pdf_pages = sum(p["pages"] for p in pdfs if p["text_layer"])
    vault_est = _estimate(md_tokens, md, 0)
    # PDF chunks never cross a page: at least one per page, more for long pages
    pdf_chunks = pdf_pages * max(1, -(-int(pdf_tokens / max(1, pdf_pages)) // 450)) if pdf_pages else 0
    coll_est = _estimate(md_tokens + txt_tokens, md + txt_files, pdf_tokens, extra_chunks=pdf_chunks)
    return {
        "root": str(root),
        "is_vault": (root / ".obsidian").is_dir(),
        "configured": bool(layout and layout.configured and layout.root == root),
        "config_exists": (root / STATE_DIR_NAME / CONFIG_NAME).exists() or (root / CONFIG_NAME).exists(),
        "index_exists": (root / STATE_DIR_NAME / "index").is_dir(),
        "markdown_files": md,
        "markdown_mb": round(md_bytes / 1e6, 2),
        "tokens": md_tokens,
        "frontmatter_share": round(with_fm / md, 2) if md else 0,
        "wikilinks_per_note": round(links / md, 1) if md else 0,
        "folders": folders.most_common(),
        "other_files": other.most_common(),
        "pdfs": pdfs,
        "scanned_pdfs": [p for p in pdfs if not p["text_layer"]],
        "big_files": big,
        "template_folders": detect_template_folders(root),
        "private_candidates": sorted(private_candidates),
        "cloud_sync_folder": bool(CLOUD_HINT_RE.search(str(root))),
        "git": {"repo": is_git, "remote": url, "github": gitops.github_slug(url),
                "visibility": gitops.repo_visibility(root) if url else None,
                "gh_installed": gh, "gh_logged_in": gh_auth},
        "text_files": txt_files,
        "text_tokens": txt_tokens,
        "pdf_tokens": pdf_tokens,
        "estimate": vault_est if (root / ".obsidian").is_dir() else coll_est,
        "estimate_vault": vault_est,
        "estimate_collection": coll_est,
    }


def render(inv: dict) -> str:
    yes, no = tr("ja", "yes"), tr("nein", "no")
    lines = [tr(f"Bestandsaufnahme von {inv['root']}", f"Inventory of {inv['root']}")]
    lines.append(tr(f"Obsidian-Vault: {yes if inv['is_vault'] else no} · bereits eingerichtet: "
                    f"{yes if inv['configured'] else no}",
                    f"Obsidian vault: {yes if inv['is_vault'] else no} · already set up: "
                    f"{yes if inv['configured'] else no}"))
    lines.append(tr(f"Markdown-Notizen: {fmt_int(inv['markdown_files'])} ({inv['markdown_mb']} MB, "
                    f"ca. {fmt_int(inv['tokens'])} Tokens)",
                    f"Markdown notes: {fmt_int(inv['markdown_files'])} ({inv['markdown_mb']} MB, "
                    f"about {fmt_int(inv['tokens'])} tokens)"))
    if inv["markdown_files"]:
        lines.append(tr(f"Frontmatter in {round(inv['frontmatter_share'] * 100)} % der Notizen, "
                        f"{inv['wikilinks_per_note']} Wikilinks pro Notiz",
                        f"Frontmatter in {round(inv['frontmatter_share'] * 100)} % of the notes, "
                        f"{inv['wikilinks_per_note']} wikilinks per note"))
    if inv["folders"]:
        lines.append(tr("Ordner: ", "Folders: ") + ", ".join(f"{f} ({n})" for f, n in inv["folders"][:12]))
    if inv["other_files"]:
        lines.append(tr("Andere Dateien: ", "Other files: ") + ", ".join(f"{e} ({n})" for e, n in inv["other_files"][:10]))
    if inv["pdfs"]:
        scans = inv["scanned_pdfs"]
        pages = sum(p["pages"] for p in scans)
        text_pages = sum(p["pages"] for p in inv["pdfs"] if p["text_layer"])
        lines.append(tr(f"PDFs: {len(inv['pdfs'])}, davon {len(scans)} ohne Textebene (eingescannt, {pages} Seiten); "
                        f"mit Textebene {fmt_int(text_pages)} Seiten, ca. {fmt_int(inv['pdf_tokens'])} Tokens",
                        f"PDFs: {len(inv['pdfs'])}, {len(scans)} of them without text layer (scanned, {pages} pages); "
                        f"with text layer {fmt_int(text_pages)} pages, about {fmt_int(inv['pdf_tokens'])} tokens"))
    if inv["template_folders"]:
        lines.append(tr("Vorlagen-Ordner (Vorschlag: ausschließen): ", "Template folders (suggestion: exclude): ")
                     + ", ".join(inv["template_folders"]))
    if inv["private_candidates"]:
        lines.append(tr("Möglicherweise private Ordner (bitte nachfragen): ", "Possibly private folders (please ask): ")
                     + ", ".join(inv["private_candidates"]))
    if inv["big_files"]:
        lines.append(tr("Dateien über 100 MB (GitHub lehnt sie ab): ", "Files over 100 MB (GitHub rejects them): ")
                     + ", ".join(p for p, _ in inv["big_files"][:5]))
    if inv["cloud_sync_folder"]:
        lines.append(tr("Hinweis: Der Ordner liegt in einem Cloud-Sync-Ordner (iCloud/OneDrive/Dropbox). "
                        "Git und Cloud-Sync zusammen führen oft zu Konflikten.",
                        "Note: The folder is inside a cloud sync folder (iCloud/OneDrive/Dropbox). "
                        "Git and cloud sync together often cause conflicts."))
    g = inv["git"]
    if not g["repo"]:
        lines.append(tr("Git: noch kein Repo", "Git: no repo yet"))
    else:
        vis = {"private": tr("privat", "private"), "public": tr("ÖFFENTLICH", "PUBLIC"),
               "internal": tr("intern", "internal")}.get(g["visibility"] or "", tr("unbekannt", "unknown"))
        lines.append(tr(f"Git: Repo vorhanden, GitHub: {g['github'] or 'nein'}", f"Git: repo present, GitHub: {g['github'] or 'no'}")
                     + (tr(f", Sichtbarkeit {vis}", f", visibility {vis}") if g["remote"] else ""))
    gh_state = (tr(", angemeldet", ", signed in") if g["gh_logged_in"]
                else (tr(", nicht angemeldet", ", not signed in") if g["gh_installed"] else ""))
    lines.append(tr("GitHub-CLI: ", "GitHub CLI: ") + (tr("installiert", "installed") if g["gh_installed"] else tr("fehlt", "missing")) + gh_state)

    def est(label: str, e: dict) -> str:
        minutes = max(1, round(e["local_seconds"] / 60))
        return tr(f"{label}: ca. {fmt_int(e['tokens'])} Tokens, {fmt_int(e['chunks'])} Abschnitte · lokal ca. "
                  f"{minutes} Min. (plus einmalig ca. 470 MB Modell-Download) · "
                  f"Voyage ca. {fmt_int(e['voyage_tokens'])} Tokens",
                  f"{label}: about {fmt_int(e['tokens'])} tokens, {fmt_int(e['chunks'])} sections · locally about "
                  f"{minutes} min (plus a one-time model download of about 470 MB) · "
                  f"Voyage about {fmt_int(e['voyage_tokens'])} tokens")

    if inv["text_files"] or inv["pdf_tokens"]:
        lines.append(est(tr("Schätzung Vault-Modus (nur Markdown)", "Estimate vault mode (Markdown only)"),
                         inv["estimate_vault"]))
        lines.append(est(tr("Schätzung Sammlungs-Modus (Markdown, Text, PDF mit Textebene)",
                            "Estimate collection mode (Markdown, text, PDF with text layer)"), inv["estimate_collection"]))
    else:
        lines.append(est(tr("Schätzung", "Estimate"), inv["estimate"]))
    return "\n".join(lines)


def as_json(inv: dict) -> str:
    return json.dumps(inv, ensure_ascii=False, indent=1)
