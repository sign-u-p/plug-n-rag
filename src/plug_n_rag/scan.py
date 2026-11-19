"""List the source files of a vault or collection, applying excludes and private folders."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .config import Layout
from .formats import format_for

MAX_FILE_BYTES = 100 * 1024 * 1024


@lru_cache(maxsize=256)
def _glob_regex(pattern: str) -> re.Pattern:
    pat = pattern.strip().lstrip("/")
    if pat.endswith("/"):
        pat += "**"
    anchored = "/" in pat.rstrip("*")
    out = ""
    i = 0
    while i < len(pat):
        if pat.startswith("**/", i):
            out += "(?:.*/)?"
            i += 3
        elif pat.startswith("**", i):
            out += ".*"
            i += 2
        elif pat[i] == "*":
            out += "[^/]*"
            i += 1
        elif pat[i] == "?":
            out += "[^/]"
            i += 1
        else:
            out += re.escape(pat[i])
            i += 1
    if not anchored:
        out = "(?:.*/)?" + out
    return re.compile("^" + out + "(?:/.*)?$", re.IGNORECASE)


def matches_any(rel: str, patterns: list[str]) -> bool:
    return any(_glob_regex(p).match(rel) for p in patterns if p and p.strip())


@dataclass
class SourceFile:
    rel: str
    abs: Path
    fmt: str
    mtime: float
    size: int


@dataclass
class ScanResult:
    files: list[SourceFile]
    private_paths: set[str]  # matched private_folders (never parsed or indexed)
    too_large: list[str]
    excluded_count: int


def scan(layout: Layout) -> ScanResult:
    cfg = layout.config
    root = layout.root
    formats = cfg.get("formats", ["markdown"])
    exclude = list(cfg.get("exclude", []))
    private = list(cfg.get("private_folders", []))
    state_dir = layout.state_dir.resolve()
    files: list[SourceFile] = []
    priv: set[str] = set()
    big: list[str] = []
    excluded = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dpath = Path(dirpath)
        rel_dir = dpath.relative_to(root).as_posix()
        rel_dir = "" if rel_dir == "." else rel_dir
        keep = []
        for d in dirnames:
            rel = f"{rel_dir}/{d}" if rel_dir else d
            full = (dpath / d)
            if d.startswith(".") or full.resolve() == state_dir:
                continue
            if matches_any(rel + "/", exclude) and matches_any(rel + "/x", exclude):
                excluded += 1
                continue
            keep.append(d)
        dirnames[:] = sorted(keep)
        for name in sorted(filenames):
            if name.startswith("."):
                continue
            rel = f"{rel_dir}/{name}" if rel_dir else name
            fmt = format_for(name, formats)
            if fmt is None:
                continue
            if matches_any(rel, exclude):
                excluded += 1
                continue
            if matches_any(rel, private):
                priv.add(rel)
                continue
            full = dpath / name
            try:
                st = full.stat()
            except OSError:
                continue
            if st.st_size > MAX_FILE_BYTES:
                big.append(rel)
                continue
            files.append(SourceFile(rel, full, fmt, st.st_mtime, st.st_size))
    return ScanResult(files, priv, big, excluded)


def detect_template_folders(root: Path) -> list[str]:
    """Template folders configured in Obsidian core templates or the Templater plugin."""
    import json

    found = []
    for cfg_path, key in (
        (root / ".obsidian" / "templates.json", "folder"),
        (root / ".obsidian" / "plugins" / "templater-obsidian" / "data.json", "templates_folder"),
    ):
        try:
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        folder = str(data.get(key) or "").strip().strip("/")
        if folder and folder not in found:
            found.append(folder)
    return found
