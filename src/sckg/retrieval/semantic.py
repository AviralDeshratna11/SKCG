from __future__ import annotations

import math
import hashlib
from collections import Counter
from typing import Protocol

from sckg.ir.models import Symbol
from sckg.retrieval.lexical import Candidate, tokenize


class EmbeddingProvider(Protocol):
    def embed(self, text: str) -> list[float]: ...


class HashingEmbeddingProvider:
    def __init__(self, dimensions: int = 256) -> None:
        if dimensions < 1:
            raise ValueError("embedding dimensions must be positive")
        self.dimensions = dimensions

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in tokenize(text):
            bucket = int.from_bytes(hashlib.blake2b(token.encode(), digest_size=8).digest(), "big")
            vector[bucket % self.dimensions] += 1.0
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]


def cosine(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    norm = math.sqrt(sum(a * a for a in left) * sum(b * b for b in right))
    return max(-1.0, min(1.0, dot / norm)) if norm else 0.0


def make_embedding_provider(
    name: str = "sentence-transformers",
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
    local_files_only: bool = False,
) -> EmbeddingProvider:
    if name == "hashing":
        return HashingEmbeddingProvider()
    if name == "sentence-transformers":
        from sckg.retrieval.embeddings import SentenceTransformerEmbeddingProvider
        return SentenceTransformerEmbeddingProvider(model_name, local_files_only=local_files_only)
    raise ValueError(f"Unknown embedding provider: {name}")


class SemanticRetriever:
    def __init__(self, provider: EmbeddingProvider | None = None) -> None:
        self.provider = provider or make_embedding_provider()

    def score(self, query: str, symbols: list[Symbol], limit: int = 20) -> list[Candidate]:
        if not symbols:
            return []
        query_vec = self.provider.embed(query)
        candidates: list[Candidate] = []
        for symbol in symbols:
            text = " ".join(
                [symbol.name, symbol.qualified_name, symbol.file_path, symbol.signature or "",
                 symbol.source_text or ""]
            )
            score = cosine(query_vec, self.provider.embed(text))
            if score > 0:
                candidates.append(Candidate(symbol, score, "semantic embedding similarity"))
        return sorted(candidates, key=lambda candidate: candidate.score, reverse=True)[:limit]


def bag_of_words(text: str) -> Counter[str]:
    return Counter(tokenize(text))
