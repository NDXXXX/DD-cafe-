import hashlib

from app.db.models import KnowledgeChunkModel, KnowledgeDocumentModel
from app.rag.schemas import IndexedChunk

CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
BOUNDARIES = ("\n\n", "\n", "。", "！", "？", "；", "，")


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def split_chinese_text(
    content: str,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> list[str]:
    normalized = content.strip()
    if not normalized:
        return []
    if chunk_size < 1 or overlap < 0 or overlap >= chunk_size:
        raise ValueError("分块参数无效")

    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(start + chunk_size, len(normalized))
        if end < len(normalized):
            lower_bound = start + chunk_size // 2
            boundary = max(normalized.rfind(mark, lower_bound, end) for mark in BOUNDARIES)
            if boundary >= lower_bound:
                end = boundary + 1
        chunk = normalized[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(normalized):
            break
        start = max(end - overlap, start + 1)
    return chunks


def build_chunk_models(document: KnowledgeDocumentModel) -> list[KnowledgeChunkModel]:
    models: list[KnowledgeChunkModel] = []
    for index, content in enumerate(split_chinese_text(document.content)):
        content_hash = sha256_text(content)
        chunk_id = sha256_text(f"{document.id}:{index}:{content_hash}")
        models.append(
            KnowledgeChunkModel(
                id=chunk_id,
                document_id=document.id,
                chunk_index=index,
                content=content,
                content_sha256=content_hash,
            )
        )
    return models


def as_indexed_chunk(
    document: KnowledgeDocumentModel,
    chunk: KnowledgeChunkModel,
) -> IndexedChunk:
    return IndexedChunk(
        chunk_id=chunk.id,
        document_id=document.id,
        chunk_index=chunk.chunk_index,
        title=document.title,
        content=chunk.content,
        source_type=document.source_type,
    )
