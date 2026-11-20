"""Two languages, German and English, side by side in the code: ``tr("Deutsch", "English")``.

Which one is used, first match wins:
1. the environment variable ``PLUG_N_RAG_LANG`` (``de`` or ``en``),
2. ``language`` in the folder's configuration (set during setup),
3. for a configuration written before 0.9 without that key: German (all of them were German),
4. otherwise the system language (``LC_ALL``, ``LC_MESSAGES``, ``LANG``): German if it starts
   with ``de``, else English.

Claude itself always answers in the language the person writes in; this only decides the
fixed texts of plug-n-rag's tools (search results, status, setup, messages).
"""

from __future__ import annotations

import os

SUPPORTED = ("de", "en")
_current: str | None = None


def _norm(value: object) -> str | None:
    v = str(value or "").strip().lower()
    if v.startswith("de") or v in ("deutsch", "german"):
        return "de"
    if v.startswith("en") or v in ("englisch", "english"):
        return "en"
    return None


def system_language() -> str:
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        lang = _norm(os.environ.get(var))
        if lang:
            return lang
    return "en"


def from_config(config: dict | None, *, configured: bool) -> str:
    """The language a folder's configuration asks for (see the module docstring)."""
    env = _norm(os.environ.get("PLUG_N_RAG_LANG"))
    if env:
        return env
    if config:
        lang = _norm(config.get("language") or config.get("sprache"))
        if lang:
            return lang
    return "de" if configured else system_language()


def set_language(lang: str | None) -> None:
    global _current
    _current = _norm(lang) if lang else None


def language() -> str:
    if _current:
        return _current
    return _norm(os.environ.get("PLUG_N_RAG_LANG")) or system_language()


def is_en() -> bool:
    return language() == "en"


def tr(de: str, en: str) -> str:
    """The text in the current language."""
    return en if is_en() else de


def use_layout(layout) -> None:
    """Switch to the language of a vault or collection (or of the system for none)."""
    if layout is None:
        set_language(from_config(None, configured=False))
    else:
        set_language(from_config(layout.config, configured=layout.configured))
