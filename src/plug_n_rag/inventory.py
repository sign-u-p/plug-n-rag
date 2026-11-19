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
from .util import estimate_tokens, fmt_int

PRIVATE_HINT_RE = re.compile(r"(tagebuch|journal|privat|private|personal|diary|persönlich)", re.I)
CLOUD_HINT_RE = re.compile(r"(iCloud|Mobile Documents|OneDrive|Dropbox|Google ?Drive|CloudStorage)", re.I)
WIKILINK_RE = re.compile(r"\[\[[^\]]+\]\]")
SECONDS_PER_CHUNK_LOCAL = 0.03  # measured on a 4-core cloud CPU with multilingual-e5-small
TOKENS_PER_CHUNK = 350


def _pdf_info(path: Path) -> tuple[int, bool]:
    try:
        from pypdf import PdfReader

        r = PdfReader(str(path))
        n = len(r.pages)
        sample = [r.pages[i] for i in range(min(n, 3))]
        text = "".join((p.extract_text() or "") for p in sample)
        return n, len(text.strip()) > 40 * max(1, len(sample))
    except Exception:  # noqa: BLE001
        return 0, False


def inventory(root: Path) -> dict:
    root = root.resolve()
    md = 0
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
                    pages, has_text = _pdf_info(p)
                    pdfs.append({"path": rel, "pages": pages, "text_layer": has_text})
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
    chunks = max(1, md_tokens // TOKENS_PER_CHUNK + md)
    return {
        "root": str(root),
        "is_vault": (root / ".obsidian").is_dir(),
        "configured": bool(layout and layout.configured and layout.root == root),
        "config_exists": (root / CONFIG_NAME).exists(),
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
        "estimate": {"chunks": chunks, "local_seconds": round(chunks * SECONDS_PER_CHUNK_LOCAL + 15),
                     "voyage_tokens": md_tokens + chunks * 15},
    }


def render(inv: dict) -> str:
    lines = [f"Bestandsaufnahme von {inv['root']}"]
    lines.append(f"Obsidian-Vault: {'ja' if inv['is_vault'] else 'nein'} · bereits eingerichtet: "
                 f"{'ja' if inv['configured'] else 'nein'}")
    lines.append(f"Markdown-Notizen: {fmt_int(inv['markdown_files'])} ({inv['markdown_mb']} MB, "
                 f"ca. {fmt_int(inv['tokens'])} Tokens)")
    if inv["markdown_files"]:
        lines.append(f"Frontmatter in {round(inv['frontmatter_share'] * 100)} % der Notizen, "
                     f"{inv['wikilinks_per_note']} Wikilinks pro Notiz")
    if inv["folders"]:
        lines.append("Ordner: " + ", ".join(f"{f} ({n})" for f, n in inv["folders"][:12]))
    if inv["other_files"]:
        lines.append("Andere Dateien: " + ", ".join(f"{e} ({n})" for e, n in inv["other_files"][:10]))
    if inv["pdfs"]:
        scans = inv["scanned_pdfs"]
        pages = sum(p["pages"] for p in scans)
        lines.append(f"PDFs: {len(inv['pdfs'])}, davon {len(scans)} ohne Textebene (eingescannt, {pages} Seiten)")
    if inv["template_folders"]:
        lines.append("Vorlagen-Ordner (Vorschlag: ausschließen): " + ", ".join(inv["template_folders"]))
    if inv["private_candidates"]:
        lines.append("Möglicherweise private Ordner (bitte nachfragen): " + ", ".join(inv["private_candidates"]))
    if inv["big_files"]:
        lines.append("Dateien über 100 MB (GitHub lehnt sie ab): " + ", ".join(p for p, _ in inv["big_files"][:5]))
    if inv["cloud_sync_folder"]:
        lines.append("Hinweis: Der Ordner liegt in einem Cloud-Sync-Ordner (iCloud/OneDrive/Dropbox). "
                     "Git und Cloud-Sync zusammen führen oft zu Konflikten.")
    g = inv["git"]
    if not g["repo"]:
        lines.append("Git: noch kein Repo")
    else:
        vis = {"private": "privat", "public": "ÖFFENTLICH", "internal": "intern"}.get(g["visibility"] or "", "unbekannt")
        lines.append(f"Git: Repo vorhanden, GitHub: {g['github'] or 'nein'}" + (f", Sichtbarkeit {vis}" if g["remote"] else ""))
    lines.append(f"GitHub-CLI: {'installiert' if g['gh_installed'] else 'fehlt'}"
                 + (", angemeldet" if g["gh_logged_in"] else (", nicht angemeldet" if g["gh_installed"] else "")))
    e = inv["estimate"]
    lines.append(f"Schätzung: ca. {fmt_int(e['chunks'])} Abschnitte · lokal ca. {max(1, e['local_seconds'] // 60)} Min. "
                 f"(plus einmalig ca. 470 MB Modell-Download) · Voyage ca. {fmt_int(e['voyage_tokens'])} Tokens")
    return "\n".join(lines)


def as_json(inv: dict) -> str:
    return json.dumps(inv, ensure_ascii=False, indent=1)
