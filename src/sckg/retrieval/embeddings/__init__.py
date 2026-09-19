"""Lazy local sentence-transformers embeddings (no hosted inference)."""
from __future__ import annotations

from functools import lru_cache
from typing import Any


class SentenceTransformerEmbeddingProvider:
    def __init__(
        self,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        *,
        local_files_only: bool = False,
    ) -> None:
        self.model_name = model_name
        self.local_files_only = local_files_only
        self._model: Any = None
        self._cached_embed = lru_cache(maxsize=4096)(self._encode)

    def _encode(self, text: str) -> tuple[float, ...]:
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(
                    self.model_name, device="cpu", local_files_only=self.local_files_only,
                    trust_remote_code=False,
                )
            except (ImportError, OSError) as exc:
                raise RuntimeError(
                    "Cannot load local embedding model. Install sckg[embeddings] and cache the "
                    "model, or select embedding_provider: hashing / --use-hash-sim."
                ) from exc
        vector = self._model.encode(text, normalize_embeddings=True, show_progress_bar=False)
        return tuple(float(value) for value in vector)

    def embed(self, text: str) -> list[float]:
        return list(self._cached_embed(text))
