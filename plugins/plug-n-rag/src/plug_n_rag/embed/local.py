"""Local embeddings with ONNX Runtime. No service besides Hugging Face (one-time download).

The model files are downloaded once, pinned to an exact Hugging Face commit, into the user
cache (or ``PLUG_N_RAG_MODEL_DIR``). Weight updates can therefore never happen unnoticed.
"""

from __future__ import annotations

import os
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np

from ..util import user_cache_dir
from . import EmbeddingUnavailable, normalize
from ..i18n import tr

LOCAL_MODELS: dict[str, dict] = {
    "intfloat/multilingual-e5-small": {
        "revision": "614241f622f53c4eeff9890bdc4f31cfecc418b3",
        "dims": 384,
        "onnx": "onnx/model.onnx",
        "tokenizer": "onnx/tokenizer.json",
        "query_prefix": "query: ",
        "document_prefix": "passage: ",
        "max_length": 512,
        "size_mb": 470,
        # e5 similarities are compressed into a high band; calibrated on the test vault.
        "min_similarity": 0.83,
        "strong_similarity": 0.87,
    },
}

HF_BASE = os.environ.get("PLUG_N_RAG_HF_ENDPOINT", "https://huggingface.co")


def model_dir(name: str, revision: str) -> Path:
    base = os.environ.get("PLUG_N_RAG_MODEL_DIR")
    root = Path(base) if base else user_cache_dir() / "models"
    return root / name.replace("/", "--") / revision


def _download(url: str, dest: Path, quiet: bool) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "plug-n-rag"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp, open(tmp, "wb") as fh:
            total = int(resp.headers.get("Content-Length") or 0)
            done = 0
            last = -1
            while True:
                buf = resp.read(1 << 20)
                if not buf:
                    break
                fh.write(buf)
                done += len(buf)
                if not quiet and total:
                    pct = done * 100 // total
                    if pct // 10 != last:
                        last = pct // 10
                        print(tr(f"  Modell-Download: {pct} % von {total // 1_000_000} MB",
                                 f"  Model download: {pct} % of {total // 1_000_000} MB"), file=sys.stderr)
        os.replace(tmp, dest)
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise EmbeddingUnavailable(tr(
            f"Modell konnte nicht von Hugging Face geladen werden ({exc}). "
            "In Cloud-Sitzungen muss huggingface.co in der Netzwerkfreigabe stehen. "
            "Bis dahin funktioniert nur die Stichwortsuche.",
            f"The model could not be downloaded from Hugging Face ({exc}). "
            "In cloud sessions, huggingface.co must be in the network allowlist. "
            "Until then, only keyword search works.",
        )) from exc


def ensure_model_files(name: str, revision: str, spec: dict, quiet: bool = True) -> Path:
    d = model_dir(name, revision)
    for key in ("tokenizer", "onnx"):
        rel = spec[key]
        dest = d / rel
        if dest.exists() and dest.stat().st_size > 0:
            continue
        # Optional: a copy shipped next to the vault (e.g. .plug-n-rag/models/...).
        local_copy = os.environ.get("PLUG_N_RAG_MODEL_COPY")
        if local_copy and (Path(local_copy) / rel).exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(Path(local_copy) / rel, dest)
            continue
        url = f"{HF_BASE}/{name}/resolve/{revision}/{rel}"
        _download(url, dest, quiet)
    return d


def is_model_cached(name: str, revision: str | None = None) -> bool:
    spec = LOCAL_MODELS.get(name)
    if not spec:
        return False
    d = model_dir(name, revision or spec["revision"])
    return all((d / spec[k]).exists() for k in ("tokenizer", "onnx"))


class LocalEmbedder:
    _cache: dict[tuple[str, str], tuple] = {}

    def __init__(self, name: str, revision: str | None = None, quiet: bool | None = None):
        spec = LOCAL_MODELS.get(name)
        if spec is None:
            raise EmbeddingUnavailable(tr(
                f"Lokales Modell '{name}' ist nicht bekannt. Bekannt: {', '.join(LOCAL_MODELS)}",
                f"Unknown local model '{name}'. Known: {', '.join(LOCAL_MODELS)}",
            ))
        self.name = name
        self.spec = spec
        self.revision = revision or spec["revision"]
        self.dims = spec["dims"]
        self.model_id = f"local:{name}@{self.revision}"
        self.min_similarity = spec["min_similarity"]
        self.strong_similarity = spec["strong_similarity"]
        self._quiet = (not sys.stderr.isatty()) if quiet is None else quiet
        self._session = None
        self._tokenizer = None

    def _load(self):
        key = (self.name, self.revision)
        if key in LocalEmbedder._cache:
            self._tokenizer, self._session, self._inputs = LocalEmbedder._cache[key]
            return
        try:
            import onnxruntime as ort
            from tokenizers import Tokenizer
        except ImportError as exc:  # pragma: no cover
            raise EmbeddingUnavailable(tr(f"onnxruntime/tokenizers fehlen: {exc}",
                                          f"onnxruntime/tokenizers missing: {exc}")) from exc
        d = ensure_model_files(self.name, self.revision, self.spec, quiet=self._quiet)
        tok = Tokenizer.from_file(str(d / self.spec["tokenizer"]))
        tok.enable_truncation(max_length=self.spec["max_length"])
        tok.enable_padding(pad_id=tok.token_to_id("<pad>") or 1, pad_token="<pad>")
        opts = ort.SessionOptions()
        opts.log_severity_level = 3
        try:
            sess = ort.InferenceSession(str(d / self.spec["onnx"]), opts, providers=["CPUExecutionProvider"])
        except Exception as exc:  # noqa: BLE001 - corrupt download etc.
            raise EmbeddingUnavailable(tr(f"Modell konnte nicht geladen werden: {exc}",
                                          f"Model could not be loaded: {exc}")) from exc
        inputs = {i.name for i in sess.get_inputs()}
        LocalEmbedder._cache[key] = (tok, sess, inputs)
        self._tokenizer, self._session, self._inputs = tok, sess, inputs

    def embed(self, texts: list[str], kind: str = "document", batch_size: int = 16) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dims), dtype=np.float32)
        if self._session is None:
            self._load()
        prefix = self.spec["query_prefix"] if kind == "query" else self.spec["document_prefix"]
        order = sorted(range(len(texts)), key=lambda i: len(texts[i]))
        out = np.zeros((len(texts), self.dims), dtype=np.float32)
        for b in range(0, len(order), batch_size):
            idx = order[b:b + batch_size]
            enc = self._tokenizer.encode_batch([prefix + texts[i] for i in idx])
            ids = np.array([e.ids for e in enc], dtype=np.int64)
            mask = np.array([e.attention_mask for e in enc], dtype=np.int64)
            feed = {"input_ids": ids, "attention_mask": mask}
            if "token_type_ids" in self._inputs:
                feed["token_type_ids"] = np.zeros_like(ids)
            hidden = self._session.run(None, feed)[0]
            m = mask[:, :, None].astype(np.float32)
            pooled = (hidden * m).sum(axis=1) / np.clip(m.sum(axis=1), 1e-9, None)
            out[idx] = pooled
        return normalize(out)
