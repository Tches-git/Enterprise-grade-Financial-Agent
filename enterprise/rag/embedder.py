from __future__ import annotations

import hashlib
import math
from enum import Enum


class EmbeddingProvider(str, Enum):
    OPENAI = "openai"
    LOCAL_BGE = "local_bge"
    HASH = "hash"


class Embedder:
    def __init__(self, provider: EmbeddingProvider = EmbeddingProvider.HASH, dimensions: int = 64):
        self.provider = provider
        self.dimensions = dimensions

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text, is_query=False) for text in texts]

    async def embed_query(self, query: str) -> list[float]:
        return self._embed(query, is_query=True)

    def _embed(self, text: str, *, is_query: bool) -> list[float]:
        prefix = "query:" if is_query and self.provider == EmbeddingProvider.LOCAL_BGE else "doc:"
        normalized = f"{prefix}{text.strip().lower()}"
        if not normalized:
            return [0.0] * self.dimensions

        vector = [0.0] * self.dimensions
        for token in normalized.split():
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            for i in range(self.dimensions):
                vector[i] += digest[i % len(digest)] / 255.0

        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]
