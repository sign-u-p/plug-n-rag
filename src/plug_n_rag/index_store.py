"""Versioned index files: one JSON file per source file, mirroring its path.

``Themen/Sensorik.md`` -> ``<index>/Themen/Sensorik.md.json``. Index files never contain the
note text, only positions, hashes and vectors (float16, little endian, base64).
Mirrored paths and the hydrate idea come from git-semantic
(https://github.com/ccherrad/git-semantic, MIT OR Apache-2.0).
"""

from __future__ import annotations

import base64
import datetime as _dt
import json
from pathlib import Path
from typing import Iterator

import numpy as np

from .chunk import CHUNKING_VERSION, EMBED_TEXT_VERSION, Chunk
from .formats import EXTRACT_VERSIONS
from .formats.base import Document
from .util import atomic_write_json, read_json

SCHEMA = 1
META_NAME = "_meta.json"


def encode_vec(vec: np.ndarray) -> str:
    return base64.b64encode(np.asarray(vec, dtype="<f2").tobytes()).decode("ascii")


def decode_vec(s: str) -> np.ndarray:
    return np.frombuffer(base64.b64decode(s), dtype="<f2").astype(np.float32)


def index_path(index_dir: Path, source: str) -> Path:
    return index_dir / (source + ".json")


def source_of(index_dir: Path, path: Path) -> str:
    rel = path.relative_to(index_dir).as_posix()
    return rel[:-5] if rel.endswith(".json") else rel


def iter_index_files(index_dir: Path) -> Iterator[Path]:
    if not index_dir.is_dir():
        return
    for p in index_dir.rglob("*.json"):
        if p.name == META_NAME and p.parent == index_dir:
            continue
        if p.name.startswith(".tmp-"):
            continue
        yield p


def read_index(path: Path) -> dict | None:
    """Read an index file. Broken files (e.g. merge conflict markers) count as missing."""
    data = read_json(path)
    if not isinstance(data, dict) or data.get("schema") != SCHEMA or "source" not in data:
        return None
    return data


def build_index_record(doc: Document, file_hash: str, model: str, chunks: list[Chunk],
                       vecs: dict[str, str]) -> dict:
    unit = doc.unit
    return {
        "schema": SCHEMA,
        "source": doc.source,
        "format": doc.format,
        "extract": EXTRACT_VERSIONS.get(doc.format, ""),
        "file_hash": file_hash,
        "model": model,
        "title": doc.title,
        "tags": doc.tags,
        "links": doc.links,
        "private": False,
        "tokens": doc.tokens,
        "unit": unit,
        "outline": [
            {"heading": o.heading, "level": o.level, unit: [o.start, o.end], "tokens": o.tokens}
            for o in doc.outline
        ],
        "chunks": [
            {
                "hash": c.hash,
                "heading_path": c.heading_path,
                unit: [c.start, c.end],
                "tokens": c.tokens,
                "vec": vecs[c.hash],
            }
            for c in chunks
            if c.hash in vecs
        ],
    }


def write_index(index_dir: Path, record: dict) -> None:
    atomic_write_json(index_path(index_dir, record["source"]), record)


def delete_index(index_dir: Path, source: str) -> bool:
    p = index_path(index_dir, source)
    try:
        p.unlink()
    except FileNotFoundError:
        return False
    # remove empty parent folders inside the index dir
    parent = p.parent
    while parent != index_dir and parent.is_dir():
        try:
            parent.rmdir()
        except OSError:
            break
        parent = parent.parent
    return True


def read_meta(index_dir: Path) -> dict | None:
    data = read_json(index_dir / META_NAME)
    return data if isinstance(data, dict) else None


def make_meta(model: str, dims: int, created: str | None = None) -> dict:
    return {
        "schema": SCHEMA,
        "model": model,
        "dims": dims,
        "chunking": CHUNKING_VERSION,
        "embed_text": EMBED_TEXT_VERSION,
        "extract": dict(EXTRACT_VERSIONS),
        "created": created or _dt.date.today().isoformat(),
    }


def write_meta(index_dir: Path, meta: dict) -> None:
    atomic_write_json(index_dir / META_NAME, meta, indent=1)


def record_is_current(rec: dict | None, file_hash: str, meta: dict, fmt: str) -> bool:
    if not rec:
        return False
    return (
        rec.get("file_hash") == file_hash
        and rec.get("model") == meta.get("model")
        and rec.get("extract", EXTRACT_VERSIONS.get(fmt)) == EXTRACT_VERSIONS.get(fmt)
    )


def dumps_compact(rec: dict) -> str:
    return json.dumps(rec, ensure_ascii=False)
