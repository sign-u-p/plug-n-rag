"""Moving between layouts without recomputing anything (``plug-n-rag umziehen``).

* old layout (≤ 0.5): ``plug-n-rag.yml`` in the root and volatile data in ``.plug-n-rag/cache``
  (or, for central collections, below the user *cache* directory)
* current layout: shareable data in one ``.plug-n-rag/`` folder (inside) or in the user *data*
  directory (central); volatile data always in the user cache

Old caches are never just deleted: extracted texts and transcripts in them may have cost
money (Haiku/Sonnet), so they are copied into the new cache first.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from .config import (CONFIG_NAME, STATE_DIR_NAME, Layout, external_state_dir, find_layout, load_config,
                     register_external, unregister_external)
from .i18n import tr
from .util import user_cache_dir

OLD_GITIGNORE_MARK = "Lokaler Cache von plug-n-rag"
KEEP_FROM_OLD_CACHE = ("extract", "ingest", "tuning.json", "log.jsonl")


def old_cache_dir(layout: Layout) -> Path:
    return layout.state_dir / "cache"


def carry_over_old_cache(layout: Layout) -> bool:
    """Copy expensive parts of an old cache (extracts, transcripts, learning) into the new one.

    Idempotent and cheap when there is nothing to do. Returns True if something was copied.
    """
    old = old_cache_dir(layout)
    if not old.is_dir() or old.resolve() == layout.cache_dir.resolve():
        return False
    marker = layout.cache_dir / ".alter-cache-uebernommen"
    if marker.exists():
        return False
    layout.cache_dir.mkdir(parents=True, exist_ok=True)
    copied = False
    for name in KEEP_FROM_OLD_CACHE:
        src = old / name
        dst = layout.cache_dir / name
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
            copied = True
        elif src.is_file() and not dst.exists():
            shutil.copy2(src, dst)
            copied = True
    marker.write_text("1", encoding="utf-8")
    return copied


def _move_tree_contents(src: Path, dst: Path, skip: tuple[str, ...] = ()) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        if item.name in skip:
            continue
        target = dst / item.name
        if target.exists():
            if item.is_dir():
                shutil.copytree(item, target, dirs_exist_ok=True)
                shutil.rmtree(item)
            else:
                item.unlink()  # identical content was already moved earlier
            continue
        shutil.move(str(item), str(target))


def move(layout: Layout, target: str | None = None) -> list[str]:
    """Bring a layout up to date and optionally move it: target 'ordner' | 'zentral' | None."""
    steps: list[str] = []
    carry_over_old_cache(layout)
    root = layout.root
    target = {"folder": "ordner", "central": "zentral"}.get(target or "", target)
    want = target or ("ordner" if layout.location == "inside" else "zentral")

    if want == "ordner":
        dest = root / STATE_DIR_NAME
        if layout.location == "external":
            _move_tree_contents(layout.state_dir, dest, skip=("cache",))
            unregister_external(root)
            steps.append(tr(f"Index und Konfiguration von {layout.state_dir} nach {dest} verschoben.",
                            f"Index and configuration moved from {layout.state_dir} to {dest}."))
        legacy_cfg = root / CONFIG_NAME
        if legacy_cfg.exists():
            dest.mkdir(parents=True, exist_ok=True)
            if not (dest / CONFIG_NAME).exists():
                shutil.move(str(legacy_cfg), str(dest / CONFIG_NAME))
                steps.append(tr("plug-n-rag.yml in den Ordner .plug-n-rag/ verschoben.",
                                "plug-n-rag.yml moved into the folder .plug-n-rag/."))
        old = dest / "cache"
        if old.is_dir():
            shutil.rmtree(old)
            steps.append(tr("Alten Cache aus .plug-n-rag/cache entfernt (Inhalte vorher übernommen).",
                            "Old cache removed from .plug-n-rag/cache (its contents were carried over first)."))
        gi = dest / ".gitignore"
        try:
            if gi.exists() and OLD_GITIGNORE_MARK in gi.read_text(encoding="utf-8"):
                gi.unlink()
        except OSError:
            pass
        _set_location(dest / CONFIG_NAME, "inside")
    else:  # zentral
        dest = external_state_dir(root)
        if layout.location == "inside":
            src = root / STATE_DIR_NAME
            if (root / CONFIG_NAME).exists():
                dest.mkdir(parents=True, exist_ok=True)
                shutil.move(str(root / CONFIG_NAME), str(dest / CONFIG_NAME))
            if src.is_dir():
                _move_tree_contents(src, dest, skip=("cache", ".gitignore"))
                shutil.rmtree(src, ignore_errors=True)
            steps.append(tr(f"Index und Konfiguration aus dem Ordner nach {dest} verschoben; "
                            "im Ordner liegt nichts mehr von plug-n-rag.",
                            f"Index and configuration moved out of the folder to {dest}; "
                            "nothing of plug-n-rag is left in the folder."))
        elif layout.state_dir.resolve() != dest.resolve():
            # old central location below the user cache → durable data directory
            _move_tree_contents(layout.state_dir, dest, skip=("cache",))
            old = layout.state_dir / "cache"
            if old.is_dir():
                shutil.rmtree(old)
            try:
                layout.state_dir.rmdir()
            except OSError:
                pass
            steps.append(tr(f"Zentralen Index aus dem Cache-Ordner nach {dest} verschoben "
                            "(dort löschen Aufräumprogramme nichts).",
                            f"Central index moved from the cache folder to {dest} "
                            "(clean-up tools do not delete anything there)."))
        register_external(root, dest)
        _set_location(dest / CONFIG_NAME, "external")
    if not steps:
        steps.append(tr("Alles ist bereits im aktuellen Aufbau, nichts zu tun.",
                        "Everything already uses the current layout, nothing to do."))
    return steps


def _set_location(cfg_path: Path, location: str) -> None:
    from .config import save_config

    if not cfg_path.exists():
        return
    cfg = load_config(cfg_path)
    if cfg.get("index_location") != location:
        cfg["index_location"] = location
        save_config(cfg_path, cfg)


def needs_update(layout: Layout) -> bool:
    if layout.legacy or (layout.state_dir / "cache").is_dir():
        return True
    if layout.location == "external":
        try:
            layout.state_dir.resolve().relative_to(user_cache_dir().resolve())
            return True
        except ValueError:
            return False
    return False


def reload(root: Path) -> Layout | None:
    return find_layout(root)
