from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from enterprise.auth.dependencies import require_admin, require_any_operator
from enterprise.auth.schemas import UserContext

from .chunker import split_document
from .document_loader import load_document_bytes
from .embedder import Embedder, EmbeddingProvider
from .rag_chain import RAGChain
from .retriever import Retriever
from .schemas import (
    ChunkConfig,
    DeleteDocumentResponse,
    DocumentListItem,
    RAGQueryRequest,
    RAGQueryResponse,
    RAGStatsResponse,
    UploadDocumentResponse,
)
from .vector_store import VectorStore

router = APIRouter(prefix="/enterprise/rag", tags=["rag"])

_vector_store = VectorStore()
_embedder = Embedder(provider=EmbeddingProvider.HASH)
_retriever = Retriever(_vector_store, _embedder)
_rag_chain = RAGChain(_retriever)
_chunk_config = ChunkConfig()


def get_rag_chain() -> RAGChain:
    return _rag_chain


@router.post("/documents/upload", response_model=UploadDocumentResponse)
async def upload_document(
    file: UploadFile = File(...),
    user: UserContext = Depends(require_admin),
) -> UploadDocumentResponse:
    try:
        raw_bytes = await file.read()
        text = load_document_bytes(file.filename or "document.txt", raw_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    metadata = {
        "source_file": file.filename or "document.txt",
        "uploaded_by": user.user_id,
        "organization_id": user.org_id,
        "type": "knowledge",
    }
    chunks = split_document(text, _chunk_config, metadata)
    embeddings = await _embedder.embed_texts([chunk.content for chunk in chunks])
    added = _vector_store.add_chunks(chunks, embeddings)
    return UploadDocumentResponse(source_file=metadata["source_file"], chunks_added=added)


@router.get("/documents", response_model=list[DocumentListItem])
async def list_documents(
    user: UserContext = Depends(require_any_operator),
) -> list[DocumentListItem]:
    return [DocumentListItem(**item) for item in _vector_store.list_documents()]


@router.delete("/documents/{source_file}", response_model=DeleteDocumentResponse)
async def delete_document(
    source_file: str,
    user: UserContext = Depends(require_admin),
) -> DeleteDocumentResponse:
    deleted = _vector_store.delete_by_source(source_file)
    return DeleteDocumentResponse(source_file=source_file, deleted_chunks=deleted)


@router.post("/query", response_model=RAGQueryResponse)
async def query_documents(
    request: RAGQueryRequest,
    user: UserContext = Depends(require_any_operator),
) -> RAGQueryResponse:
    context = await _rag_chain.build_augmented_context(
        query=request.query,
        filter_metadata=request.filter_metadata,
        max_context_tokens=request.max_context_tokens,
        top_k=request.top_k,
    )
    return RAGQueryResponse(**context.__dict__)


@router.get("/stats", response_model=RAGStatsResponse)
async def rag_stats(
    user: UserContext = Depends(require_any_operator),
) -> RAGStatsResponse:
    return RAGStatsResponse(**_vector_store.stats())
