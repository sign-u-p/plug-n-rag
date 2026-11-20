"""Small shared helpers: hashing, token estimates, atomic writes, locking, formatting."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


def sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def estimate_tokens(text: str) -> int:
    """Rough token estimate (about 4 characters per token, slightly fewer for German).

    Deliberately simple and model independent. It is only used for size hints and
    savings estimates, never for hard limits that must be exact.
    """
    if not text:
        return 0
    return max(1, round(len(text) / 3.8))


def atomic_write_text(path: Path, text: str) -> None:
    """Write via a temporary file in the same directory, then rename (atomic on POSIX/NTFS)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", suffix=path.suffix, dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def atomic_write_json(path: Path, data: Any, *, indent: int | None = 1) -> None:
    atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=indent) + "\n")


def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


class LockBusy(RuntimeError):
    pass


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":  # os.kill(pid, 0) would send CTRL_C_EVENT on Windows; rely on lock age
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


@contextmanager
def file_lock(path: Path, *, wait: float = 0.0, stale_after: float = 1800.0) -> Iterator[None]:
    """Portable exclusive lock using O_EXCL. Stale locks (dead pid or too old) are broken.

    ``wait`` is how many seconds to retry before raising LockBusy.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + wait
    while True:
        try:
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w") as fh:
                fh.write(json.dumps({"pid": os.getpid(), "t": time.time()}))
            break
        except FileExistsError:
            info = read_json(path, {}) or {}
            age = time.time() - float(info.get("t", 0))
            if age > stale_after or not _pid_alive(int(info.get("pid", 0))):
                try:
                    path.unlink()
                except OSError:
                    pass
                continue
            if time.monotonic() >= deadline:
                raise LockBusy(str(path))
            time.sleep(0.2)
    try:
        yield
    finally:
        try:
            path.unlink()
        except OSError:
            pass


def fmt_int(n: int) -> str:
    """Thousands separator of the current language: 2400 -> '2.400' (de) or '2,400' (en)."""
    from .i18n import is_en

    return f"{n:,}" if is_en() else f"{n:,}".replace(",", ".")


def plural(n: int, one: str, many: str) -> str:
    return f"{fmt_int(n)} {one if n == 1 else many}"


def user_cache_dir() -> Path:
    base = os.environ.get("XDG_CACHE_HOME")
    if base:
        return Path(base) / "plug-n-rag"
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "plug-n-rag"
    return Path.home() / ".cache" / "plug-n-rag"


def user_data_dir() -> Path:
    """Durable per-user data (central indexes). Unlike the cache, cleaners must not delete it."""
    base = os.environ.get("XDG_DATA_HOME")
    if base:
        return Path(base) / "plug-n-rag"
    if os.name == "nt" and os.environ.get("APPDATA"):
        return Path(os.environ["APPDATA"]) / "plug-n-rag" / "data"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "plug-n-rag"
    return Path.home() / ".local" / "share" / "plug-n-rag"


def user_config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME")
    if base:
        return Path(base) / "plug-n-rag"
    if os.name == "nt" and os.environ.get("APPDATA"):
        return Path(os.environ["APPDATA"]) / "plug-n-rag"
    return Path.home() / ".config" / "plug-n-rag"
