from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import math
from typing import Any

from .schemas import DocumentChunk, RetrievalResult


@dataclass
class StoredChunk:
    chunk: DocumentChunk
    embedding: list[float]


class VectorStore:
    def __init__(self, persist_directory: str = "./data/chroma_db", collection_name: str = "finrpa_docs"):
        self.persist_directory = persist_directory
        self.collection_name = collection_name
        self._items: list[StoredChunk] = []

    def add_chunks(self, chunks: list[DocumentChunk], embeddings: list[list[float]]) -> int:
        for chunk, embedding in zip(chunks, embeddings, strict=False):
            self._items.append(StoredChunk(chunk=chunk, embedding=embedding))
        return min(len(chunks), len(embeddings))

    def query(
        self,
        query_embedding: list[float],
        top_k: int = 10,
        filter_metadata: dict[str, Any] | None = None,
    ) -> list[RetrievalResult]:
        candidates: list[RetrievalResult] = []
        for item in self._items:
            if filter_metadata and not self._metadata_matches(item.chunk.metadata, filter_metadata):
                continue
            score = self._cosine_similarity(query_embedding, item.embedding)
            candidates.append(RetrievalResult(chunk=item.chunk, similarity_score=score))
        candidates.sort(key=lambda result: result.similarity_score, reverse=True)
        return candidates[:top_k]

    def delete_by_source(self, source_file: str) -> int:
        before = len(self._items)
        self._items = [item for item in self._items if item.chunk.metadata.get("source_file") != source_file]
        return before - len(self._items)

    def list_documents(self) -> list[dict[str, Any]]:
        grouped: dict[str, list[DocumentChunk]] = defaultdict(list)
        for item in self._items:
            grouped[item.chunk.metadata.get("source_file", "unknown")].append(item.chunk)

        documents: list[dict[str, Any]] = []
        for source_file, chunks in grouped.items():
            first_metadata = dict(chunks[0].metadata) if chunks else {}
            documents.append(
                {
                    "source_file": source_file,
                    "chunk_count": len(chunks),
                    "metadata": first_metadata,
                }
            )
        documents.sort(key=lambda doc: doc["source_file"])
        return documents

    def stats(self) -> dict[str, Any]:
        sources = sorted(
            {item.chunk.metadata.get("source_file", "unknown") for item in self._items}
        )
        return {
            "total_documents": len(sources),
            "total_chunks": len(self._items),
            "sources": sources,
        }

    @staticmethod
    def _metadata_matches(metadata: dict[str, Any], filters: dict[str, Any]) -> bool:
        for key, expected in filters.items():
            if metadata.get(key) != expected:
                return False
        return True

    @staticmethod
    def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
        if not vec_a or not vec_b or len(vec_a) != len(vec_b):
            return 0.0
        dot = sum(a * b for a, b in zip(vec_a, vec_b, strict=False))
        norm_a = math.sqrt(sum(a * a for a in vec_a)) or 1.0
        norm_b = math.sqrt(sum(b * b for b in vec_b)) or 1.0
        return dot / (norm_a * norm_b)
