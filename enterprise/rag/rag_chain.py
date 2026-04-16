from __future__ import annotations

from .retriever import Retriever
from .schemas import RAGContext


class RAGChain:
    def __init__(self, retriever: Retriever):
        self.retriever = retriever

    async def build_augmented_context(
        self,
        query: str,
        filter_metadata: dict | None = None,
        max_context_tokens: int = 2000,
        top_k: int | None = None,
    ) -> RAGContext:
        results = await self.retriever.retrieve(query, filter_metadata=filter_metadata, top_k=top_k)

        used_chunks = []
        sources = []
        token_budget = 0
        for result in results:
            if token_budget + result.chunk.token_count > max_context_tokens and used_chunks:
                break
            used_chunks.append(result.chunk.content)
            token_budget += result.chunk.token_count
            sources.append(
                {
                    "file": result.chunk.metadata.get("source_file", "unknown"),
                    "chunk_id": result.chunk.chunk_id,
                    "score": result.rerank_score if result.rerank_score is not None else result.similarity_score,
                    "metadata": result.chunk.metadata,
                }
            )

        return RAGContext(
            augmented_text="\n\n".join(used_chunks),
            sources=sources,
            total_chunks_retrieved=len(results),
            total_chunks_used=len(used_chunks),
        )
