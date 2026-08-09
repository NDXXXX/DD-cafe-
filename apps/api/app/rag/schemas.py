from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class KnowledgeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=160)
    content: str = Field(min_length=1, max_length=8000)
    source_type: str = Field(min_length=1, max_length=80)


class KnowledgeUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=160)
    content: str | None = Field(default=None, min_length=1, max_length=8000)
    source_type: str | None = Field(default=None, min_length=1, max_length=80)

    @model_validator(mode="after")
    def require_change(self) -> "KnowledgeUpdate":
        if self.title is None and self.content is None and self.source_type is None:
            raise ValueError("至少提供一个需要更新的字段")
        return self


class KnowledgeView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    content: str
    source_type: str
    version: int
    content_sha256: str
    index_status: str
    index_error: str | None
    indexed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class IndexedChunk(BaseModel):
    chunk_id: str
    document_id: str
    chunk_index: int
    title: str
    content: str
    source_type: str


class RetrievedDocument(BaseModel):
    chunk_id: str
    document_id: str
    title: str
    source_type: str
    evidence: str
    retrieval_score: float
    rerank_score: float


class RagResult(BaseModel):
    original_query: str
    rewritten_query: str
    evidence: list[RetrievedDocument]
    timings_ms: dict[str, float]
    degraded_steps: list[str]
    no_evidence: bool
