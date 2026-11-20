import asyncio

import pytest

from plug_n_rag.sync import sync

mcp = pytest.importorskip("mcp")


def _text(res):
    if isinstance(res, tuple):
        res = res[0]
    content = getattr(res, "content", res)
    return content[0].text


def test_mcp_tools_return_cli_text(layout, fake, monkeypatch):
    sync(layout, embedder=fake)
    monkeypatch.setenv("PLUG_N_RAG_ROOT", str(layout.root))
    from plug_n_rag.mcp_server import build_server

    server = build_server()
    tools = {t.name for t in asyncio.run(server.list_tools())}
    assert tools == {"karte", "suche", "gliederung", "lesen", "verwandt", "status"}
    assert "## Ablauf" in _text(asyncio.run(server.call_tool("gliederung", {"notiz": "NPS"})))
    assert _text(asyncio.run(server.call_tool("karte", {"kurz": True}))).startswith("Vault:")


def test_mcp_not_set_up(tmp_path, monkeypatch):
    monkeypatch.setenv("PLUG_N_RAG_ROOT", str(tmp_path))
    from plug_n_rag.mcp_server import build_server

    assert "/plug-n-rag:setup" in _text(asyncio.run(build_server().call_tool("status", {})))
