from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field


@dataclass
class ChunkConfig:
    chunk_size: int = 512
    chunk_overlap: int = 64
    separator: str = "\n\n"
    secondary_separators: list[str] = field(default_factory=lambda: ["\n", "。", ". "])


@dataclass
class DocumentChunk:
    chunk_id: str
    content: str
    metadata: dict[str, Any]
    token_count: int


@dataclass
class RetrievalResult:
    chunk: DocumentChunk
    similarity_score: float
    rerank_score: float | None = None


@dataclass
class RAGContext:
    augmented_text: str
    sources: list[dict[str, Any]]
    total_chunks_retrieved: int
    total_chunks_used: int


class RAGQueryRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)
    filter_metadata: dict[str, Any] | None = None
    max_context_tokens: int = Field(default=1500, ge=128, le=8000)


class RAGQueryResponse(BaseModel):
    augmented_text: str
    sources: list[dict[str, Any]]
    total_chunks_retrieved: int
    total_chunks_used: int


class DocumentListItem(BaseModel):
    source_file: str
    chunk_count: int
    metadata: dict[str, Any] = Field(default_factory=dict)


class UploadDocumentResponse(BaseModel):
    source_file: str
    chunks_added: int


class DeleteDocumentResponse(BaseModel):
    source_file: str
    deleted_chunks: int


class RAGStatsResponse(BaseModel):
    total_documents: int
    total_chunks: int
    sources: list[str]
