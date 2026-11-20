"""Embedding providers behind one interface: ``embed(texts, kind) -> np.ndarray``.

``kind`` is ``"document"`` or ``"query"`` (some models need different prefixes).
All providers return L2-normalised float32 vectors.
"""

from __future__ import annotations

from typing import Protocol

import numpy as np


class EmbeddingUnavailable(RuntimeError):
    """The provider cannot be used right now (no network, no key, model download failed)."""


class Embedder(Protocol):
    model_id: str
    dims: int
    min_similarity: float  # below this a purely semantic hit counts as irrelevant
    strong_similarity: float  # above this a semantic hit counts as "sehr passend"

    def embed(self, texts: list[str], kind: str) -> np.ndarray: ...


def normalize(mat: np.ndarray) -> np.ndarray:
    mat = np.asarray(mat, dtype=np.float32)
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return mat / norms


def model_id_for(config: dict) -> str:
    """Model identifier (provider, name, revision) the configuration asks for, without loading it."""
    emb = config.get("embedding", {})
    provider = emb.get("provider", "local")
    name = emb.get("model", "")
    if provider == "local":
        from .local import LOCAL_MODELS

        spec = LOCAL_MODELS.get(name)
        rev = emb.get("revision") or (spec["revision"] if spec else "unknown")
        return f"local:{name}@{rev}"
    if provider == "voyage":
        from .voyage import voyage_dims

        return f"voyage:{name}@d{voyage_dims(emb)}"
    if provider == "fake":
        return f"fake:{name or 'fake-384'}@1"
    return f"{provider}:{name}"


def dims_for(config: dict) -> int:
    emb = config.get("embedding", {})
    provider = emb.get("provider", "local")
    if provider == "local":
        from .local import LOCAL_MODELS

        spec = LOCAL_MODELS.get(emb.get("model", ""))
        return int(emb.get("dims") or (spec["dims"] if spec else 384))
    if provider == "voyage":
        from .voyage import voyage_dims

        return voyage_dims(emb)
    return 384


def get_embedder(config: dict) -> Embedder:
    emb = config.get("embedding", {})
    provider = emb.get("provider", "local")
    if provider == "local":
        from .local import LocalEmbedder

        return LocalEmbedder(emb.get("model", "intfloat/multilingual-e5-small"), emb.get("revision"))
    if provider == "voyage":
        from .voyage import VoyageEmbedder

        return VoyageEmbedder(emb)
    if provider == "fake":
        from .fake import FakeEmbedder

        return FakeEmbedder()
    from ..i18n import tr

    raise EmbeddingUnavailable(tr(f"Unbekannter Embedding-Provider: {provider}", f"Unknown embedding provider: {provider}"))
