"""Voyage provider: against a local fake API always, against the real API only with VOYAGE_API_KEY."""

import hashlib
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import numpy as np
import pytest

from plug_n_rag.embed import EmbeddingUnavailable, get_embedder, model_id_for
from plug_n_rag.search import search
from plug_n_rag.sync import sync

from .conftest import copy_vault, make_layout


class FakeVoyage(BaseHTTPRequestHandler):
    calls: list = []

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeVoyage.calls.append({"auth": self.headers.get("Authorization"), **body})
        if self.headers.get("Authorization") != "Bearer test-key":
            self.send_response(401)
            self.end_headers()
            return
        dims = body.get("output_dimension", 1024)
        data = []
        for i, text in enumerate(body["input"]):
            seed = int(hashlib.md5(text.encode()).hexdigest()[:8], 16)
            v = np.random.default_rng(seed).normal(size=dims)
            data.append({"index": i, "embedding": (v / np.linalg.norm(v)).tolist()})
        out = json.dumps({"data": data, "usage": {"total_tokens": 7 * len(data)}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)


@pytest.fixture
def fake_api(monkeypatch):
    srv = HTTPServer(("127.0.0.1", 0), FakeVoyage)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    monkeypatch.setenv("PLUG_N_RAG_VOYAGE_URL", f"http://127.0.0.1:{srv.server_port}/v1/embeddings")
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    FakeVoyage.calls = []
    yield FakeVoyage
    srv.shutdown()


def test_voyage_against_fake_api(tmp_path, fake_api, monkeypatch):
    monkeypatch.setenv("VOYAGE_API_KEY", "test-key")
    root = copy_vault(tmp_path)
    layout = make_layout(root, provider="voyage")
    assert model_id_for(layout.config) == "voyage:voyage-3.5-lite@d1024"
    r = sync(layout)
    assert r.embedded_chunks > 0 and not r.embed_error
    call = fake_api.calls[0]
    assert call["model"] == "voyage-3.5-lite" and call["input_type"] == "document"
    assert call["output_dimension"] == 1024
    out = search(layout, "Dachsanierung")
    assert "besprechungen/2026-10-hausversammlung.md" in out
    assert fake_api.calls[-1]["input_type"] == "query"
    # the key never ends up in any file of the vault
    for p in root.rglob("*"):
        if p.is_file():
            assert b"test-key" not in p.read_bytes()


def test_voyage_without_key_falls_back(tmp_path, fake_api, monkeypatch):
    monkeypatch.delenv("VOYAGE_API_KEY", raising=False)
    root = copy_vault(tmp_path)
    layout = make_layout(root, provider="voyage")
    r = sync(layout)
    assert r.embed_error and "API-Key" in r.embed_error
    assert "besprechungen/2026-10-hausversammlung.md" in search(layout, "Dachsanierung")


def test_voyage_rejected_key(fake_api, monkeypatch):
    monkeypatch.setenv("VOYAGE_API_KEY", "wrong")
    emb = get_embedder({"embedding": {"provider": "voyage", "model": "voyage-3.5-lite"}})
    with pytest.raises(EmbeddingUnavailable, match="401"):
        emb.embed(["x"], "query")


@pytest.mark.voyage
@pytest.mark.skipif(not os.environ.get("VOYAGE_API_KEY"), reason="VOYAGE_API_KEY nicht gesetzt")
def test_voyage_real_api(tmp_path, monkeypatch):
    monkeypatch.delenv("PLUG_N_RAG_VOYAGE_URL", raising=False)
    root = copy_vault(tmp_path)
    layout = make_layout(root, provider="voyage")
    r = sync(layout)
    assert not r.embed_error
    out = search(layout, "Unter dem Dach ist es morgens zu kalt")
    assert "besprechungen/2026-10-hausversammlung.md" in out
