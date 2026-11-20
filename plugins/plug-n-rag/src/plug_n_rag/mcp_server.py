"""Thin MCP wrapper around the core (stdio). No logic of its own: every tool calls the
same functions as the CLI and returns the same text.

Start: ``plug-n-rag mcp`` (installs the optional ``mcp`` extra on first use).
The vault is the working directory, ``PLUG_N_RAG_ROOT`` or ``CLAUDE_PROJECT_DIR``.
"""

from __future__ import annotations

import os
from pathlib import Path

from .cli import NOT_SET_UP
from .config import find_layout


def _layout():
    start = os.environ.get("PLUG_N_RAG_ROOT") or os.environ.get("CLAUDE_PROJECT_DIR")
    layout = find_layout(Path(start) if start else None)
    if layout is None or not layout.configured:
        return None
    return layout


def _run(fn):
    layout = _layout()
    if layout is None:
        return NOT_SET_UP
    try:
        return fn(layout)
    except Exception as exc:  # noqa: BLE001 - report instead of crashing the server
        return f"Fehler in plug-n-rag: {exc}"


def build_server():
    try:  # mcp >= 2
        from mcp.server.mcpserver import MCPServer as Server
    except ImportError:  # mcp 1.x
        from mcp.server.fastmcp import FastMCP as Server

    server = Server("plug-n-rag")

    @server.tool()
    def karte(kurz: bool = False) -> str:
        """Überblick über die Vault: Ordner, Anzahl, Beschreibung, Schwerpunkte, häufige Tags."""
        from .mapview import karte as _k

        return _run(lambda L: _k(L, short=kurz))

    @server.tool()
    def suche(frage: str = "", zweck: str = "frage", ordner: str | None = None, tag: str | None = None,
              seit: str | None = None, weiter: bool = False) -> str:
        """Relevante Notizen finden. zweck: frage | recherche | erstellen. weiter=True liefert die
        nächste Seite der letzten Suche. Ergebnis: Pfade, Abschnitte mit Zeilen, Relevanz in Worten."""
        from .search import search as _s

        return _run(lambda L: _s(L, frage or None, purpose=zweck, folder=ordner, tag=tag, since=seit, more=weiter))

    @server.tool()
    def gliederung(notiz: str) -> str:
        """Überschriften einer Notiz mit Zeilen und Token-Größe."""
        from .navigate import outline

        return _run(lambda L: outline(L, notiz))

    @server.tool()
    def lesen(ziel: str) -> str:
        """Einen Abschnitt lesen: 'pfad#Überschrift', 'pfad:45-80' (Zeilen/Seiten) oder nur 'pfad'."""
        from .navigate import read

        return _run(lambda L: read(L, ziel))

    @server.tool()
    def verwandt(notiz: str) -> str:
        """Links und Backlinks zuerst, dann inhaltlich ähnliche Notizen."""
        from .navigate import related

        return _run(lambda L: related(L, notiz))

    @server.tool()
    def status() -> str:
        """Aktualität, Modell, Fehler, gelernte Werte, geschätzte Ersparnis."""
        from .status import status as _st

        return _run(lambda L: _st(L, check_remote=False))

    return server


def main() -> None:
    build_server().run()
