from __future__ import annotations

import uuid
from typing import Any

from .schemas import ChunkConfig, DocumentChunk


def _estimate_tokens(text: str) -> int:
    stripped = text.strip()
    if not stripped:
        return 0
    return max(1, len(stripped) // 4)


def _normalize_text(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.replace("\r\n", "\n").split("\n")).strip()


def _split_by_separator(text: str, separator: str) -> list[str]:
    if not separator or separator not in text:
        return [text]
    return [segment.strip() for segment in text.split(separator) if segment.strip()]


def _fallback_fixed_chunks(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    safe_size = max(chunk_size, 1)
    safe_overlap = min(max(chunk_overlap, 0), safe_size - 1) if safe_size > 1 else 0
    step = max(1, safe_size - safe_overlap)
    pieces: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + safe_size * 4)
        piece = text[start:end].strip()
        if piece:
            pieces.append(piece)
        if end >= len(text):
            break
        start += step * 4
    return pieces


def split_document(text: str, config: ChunkConfig, metadata: dict[str, Any]) -> list[DocumentChunk]:
    normalized = _normalize_text(text)
    if not normalized:
        return []

    candidate_segments = [normalized]
    for separator in [config.separator, *config.secondary_separators]:
        next_segments: list[str] = []
        changed = False
        for segment in candidate_segments:
            if _estimate_tokens(segment) <= config.chunk_size:
                next_segments.append(segment)
                continue
            split_segments = _split_by_separator(segment, separator)
            if len(split_segments) > 1:
                changed = True
                next_segments.extend(split_segments)
            else:
                next_segments.append(segment)
        candidate_segments = next_segments
        if changed and all(_estimate_tokens(seg) <= config.chunk_size for seg in candidate_segments):
            break

    final_segments: list[str] = []
    for segment in candidate_segments:
        if _estimate_tokens(segment) <= config.chunk_size:
            final_segments.append(segment)
        else:
            final_segments.extend(_fallback_fixed_chunks(segment, config.chunk_size, config.chunk_overlap))

    chunks: list[DocumentChunk] = []
    previous_tail = ""
    overlap_chars = max(0, config.chunk_overlap * 4)

    for segment in final_segments:
        merged = f"{previous_tail}{segment}".strip() if previous_tail else segment.strip()
        if not merged:
            continue
        token_count = _estimate_tokens(merged)
        chunk_metadata = dict(metadata)
        chunk_metadata["sequence"] = len(chunks)
        chunks.append(
            DocumentChunk(
                chunk_id=f"chunk_{uuid.uuid4().hex[:12]}",
                content=merged,
                metadata=chunk_metadata,
                token_count=token_count,
            )
        )
        previous_tail = merged[-overlap_chars:] if overlap_chars else ""

    return chunks
