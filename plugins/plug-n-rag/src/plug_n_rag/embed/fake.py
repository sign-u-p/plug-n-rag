"""Deterministic fake embedder for tests: hashed word and character-trigram features.

It has a crude notion of similarity (shared words and word parts), runs instantly and
needs no network. Never use it for real vaults.
"""

from __future__ import annotations

import hashlib
import re

import numpy as np

from . import normalize

WORD_RE = re.compile(r"\w+", re.UNICODE)


class FakeEmbedder:
    def __init__(self, dims: int = 384):
        self.dims = dims
        self.model_id = "fake:fake-384@1"
        self.min_similarity = 0.25
        self.strong_similarity = 0.5
        self.calls = 0
        self.texts_embedded = 0

    def _vec(self, text: str) -> np.ndarray:
        v = np.zeros(self.dims, dtype=np.float32)
        for w in WORD_RE.findall(text.lower()):
            feats = [w] + [w[i:i + 4] for i in range(max(1, len(w) - 3))]
            for f in feats:
                h = int.from_bytes(hashlib.blake2b(f.encode(), digest_size=4).digest(), "little")
                v[h % self.dims] += 1.0 if f == w else 0.5
        return v

    def embed(self, texts: list[str], kind: str = "document") -> np.ndarray:
        self.calls += 1
        self.texts_embedded += len(texts)
        if not texts:
            return np.zeros((0, self.dims), dtype=np.float32)
        return normalize(np.stack([self._vec(t) for t in texts]))
