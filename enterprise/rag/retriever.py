from __future__ import annotations

import re

from .embedder import Embedder
from .schemas import RetrievalResult
from .vector_store import VectorStore

_WORD_RE = re.compile(r"[\w\u4e00-\u9fff]+")


class Retriever:
    def __init__(self, vector_store: VectorStore, embedder: Embedder, top_k: int = 10, rerank_top_k: int = 5):
        self.vector_store = vector_store
        self.embedder = embedder
        self.top_k = top_k
        self.rerank_top_k = rerank_top_k

    async def retrieve(
        self,
        query: str,
        filter_metadata: dict | None = None,
        top_k: int | None = None,
    ) -> list[RetrievalResult]:
        query_embedding = await self.embedder.embed_query(query)
        candidates = self.vector_store.query(
            query_embedding=query_embedding,
            top_k=top_k or self.top_k,
            filter_metadata=filter_metadata,
        )
        reranked = self._rerank(query, candidates)
        return reranked[: self.rerank_top_k]

    def _rerank(self, query: str, candidates: list[RetrievalResult]) -> list[RetrievalResult]:
        query_terms = set(self._tokenize(query))
        reranked: list[RetrievalResult] = []
        for candidate in candidates:
            chunk_terms = set(self._tokenize(candidate.chunk.content))
            overlap = len(query_terms & chunk_terms)
            density = overlap / max(len(query_terms), 1)
            rerank_score = round(candidate.similarity_score * 0.7 + density * 0.3, 4)
            candidate.rerank_score = rerank_score
            reranked.append(candidate)
        reranked.sort(
            key=lambda item: (item.rerank_score if item.rerank_score is not None else item.similarity_score),
            reverse=True,
        )
        return reranked

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return [match.group(0).lower() for match in _WORD_RE.finditer(text)]
