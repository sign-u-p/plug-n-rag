"""Voyage AI embeddings (optional provider, needs explicit consent and VOYAGE_API_KEY).

The key is read from the environment variable ``VOYAGE_API_KEY`` or from the file
``<user config>/voyage_api_key`` outside the repository. It is never written anywhere.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

import numpy as np

from ..util import user_config_dir
from . import EmbeddingUnavailable, normalize
from ..i18n import tr

API_URL = "https://api.voyageai.com/v1/embeddings"
DEFAULT_DIMS = 1024


def voyage_dims(emb_cfg: dict) -> int:
    return int(emb_cfg.get("dims") or DEFAULT_DIMS)


def api_key() -> str | None:
    key = os.environ.get("VOYAGE_API_KEY")
    if key:
        return key.strip()
    path = user_config_dir() / "voyage_api_key"
    try:
        key = path.read_text(encoding="utf-8").strip()
        if key:
            return key
    except OSError:
        pass
    if os.environ.get("CLAUDE_CODE_REMOTE") == "true":
        # Cloud session: the key is stored as a network secret and the agent proxy replaces
        # this placeholder in the Authorization header. The real key never enters the session.
        return "proxy-injected"
    return None


class VoyageEmbedder:
    def __init__(self, emb_cfg: dict):
        self.name = emb_cfg.get("model", "voyage-3.5-lite")
        self.dims = voyage_dims(emb_cfg)
        self.model_id = f"voyage:{self.name}@d{self.dims}"
        self.min_similarity = float(emb_cfg.get("min_similarity", 0.35))
        self.strong_similarity = float(emb_cfg.get("strong_similarity", 0.55))
        self.tokens_used = 0

    def _post(self, payload: dict, key: str) -> dict:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            os.environ.get("PLUG_N_RAG_VOYAGE_URL", API_URL),
            data=data,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        )
        delay = 2.0
        for attempt in range(5):
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                if exc.code in (429, 500, 502, 503, 504) and attempt < 4:
                    time.sleep(delay)
                    delay *= 2
                    continue
                if exc.code in (401, 403):
                    raise EmbeddingUnavailable(tr("Voyage lehnt den API-Key ab (401/403).",
                                                  "Voyage rejects the API key (401/403).")) from exc
                raise EmbeddingUnavailable(tr(f"Voyage-Fehler {exc.code}", f"Voyage error {exc.code}")) from exc
            except (urllib.error.URLError, OSError, TimeoutError) as exc:
                if attempt < 2:
                    time.sleep(delay)
                    continue
                raise EmbeddingUnavailable(tr(
                    f"Voyage nicht erreichbar ({exc}). In Cloud-Sitzungen muss api.voyageai.com "
                    "freigegeben sein.",
                    f"Voyage not reachable ({exc}). In cloud sessions, api.voyageai.com must be allowed.",
                )) from exc
        raise EmbeddingUnavailable(tr("Voyage nicht erreichbar", "Voyage not reachable"))

    def embed(self, texts: list[str], kind: str = "document", batch_size: int = 64) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dims), dtype=np.float32)
        key = api_key()
        if not key:
            raise EmbeddingUnavailable(tr("Kein Voyage-API-Key gefunden (VOYAGE_API_KEY).",
                                          "No Voyage API key found (VOYAGE_API_KEY)."))
        out = []
        for b in range(0, len(texts), batch_size):
            payload = {
                "input": texts[b:b + batch_size],
                "model": self.name,
                "input_type": "query" if kind == "query" else "document",
                "output_dimension": self.dims,
                "truncation": True,
            }
            resp = self._post(payload, key)
            self.tokens_used += int(resp.get("usage", {}).get("total_tokens", 0))
            rows = sorted(resp["data"], key=lambda r: r["index"])
            out.extend(r["embedding"] for r in rows)
        return normalize(np.array(out, dtype=np.float32))
