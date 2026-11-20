"""Thin MCP wrapper around the core (stdio). No logic of its own: every tool calls the
same functions as the CLI and returns the same text.

Start: ``plug-n-rag mcp`` (installs the optional ``mcp`` extra on first use).
The vault is the working directory, ``PLUG_N_RAG_ROOT`` or ``CLAUDE_PROJECT_DIR``.
"""

from __future__ import annotations

import os
from pathlib import Path

from . import i18n
from .cli import not_set_up
from .config import find_layout
from .i18n import tr


def _layout():
    start = os.environ.get("PLUG_N_RAG_ROOT") or os.environ.get("CLAUDE_PROJECT_DIR")
    layout = find_layout(Path(start) if start else None)
    i18n.use_layout(layout if layout is not None and layout.configured else None)
    if layout is None or not layout.configured:
        return None
    return layout


def _run(fn):
    layout = _layout()
    if layout is None:
        return not_set_up()
    try:
        return fn(layout)
    except Exception as exc:  # noqa: BLE001 - report instead of crashing the server
        return tr(f"Fehler in plug-n-rag: {exc}", f"Error in plug-n-rag: {exc}")


def build_server():
    try:  # mcp >= 2
        from mcp.server.mcpserver import MCPServer as Server
    except ImportError:  # mcp 1.x
        from mcp.server.fastmcp import FastMCP as Server

    server = Server("plug-n-rag")

    @server.tool()
    def karte(kurz: bool = False) -> str:
        """Overview of the vault (Überblick): folders, counts, description, topics, frequent tags."""
        from .mapview import karte as _k

        return _run(lambda L: _k(L, short=kurz))

    @server.tool()
    def suche(frage: str = "", zweck: str = "frage", ordner: str | None = None, tag: str | None = None,
              seit: str | None = None, weiter: bool = False) -> str:
        """Find relevant notes (Notizen finden). zweck (purpose): frage|question, recherche|research,
        erstellen|create. weiter=True returns the next page of the last search. Result: paths,
        sections with lines, relevance in words. Works for German and English questions."""
        from .search import search as _s

        return _run(lambda L: _s(L, frage or None, purpose={"question": "frage", "research": "recherche", "create": "erstellen"}.get(zweck, zweck), folder=ordner, tag=tag, since=seit, more=weiter))

    @server.tool()
    def gliederung(notiz: str) -> str:
        """Headings of a note (Gliederung) with lines and token size."""
        from .navigate import outline

        return _run(lambda L: outline(L, notiz))

    @server.tool()
    def lesen(ziel: str) -> str:
        """Read a section (lesen): 'path#Heading', 'path:45-80' (lines/pages) or just 'path'."""
        from .navigate import read

        return _run(lambda L: read(L, ziel))

    @server.tool()
    def verwandt(notiz: str) -> str:
        """Links and backlinks first, then notes with similar content (verwandt)."""
        from .navigate import related

        return _run(lambda L: related(L, notiz))

    @server.tool()
    def status() -> str:
        """Freshness, model, errors, learned values, estimated savings."""
        from .status import status as _st

        return _run(lambda L: _st(L, check_remote=False))

    return server


def main() -> None:
    build_server().run()
