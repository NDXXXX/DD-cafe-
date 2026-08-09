from qdrant_client import QdrantClient

from app.config import Settings
from app.rag.reranker import FusedScoreReranker, LocalCrossEncoderReranker
from app.rag.store import FastEmbedDenseEncoder, QdrantRagIndex


def create_rag_index(settings: Settings) -> QdrantRagIndex:
    if settings.qdrant_url == ":memory:":
        client = QdrantClient(":memory:")
    else:
        client = QdrantClient(url=settings.qdrant_url, trust_env=False)
    use_local_reranker = settings.rag_reranker_enabled and settings.qdrant_url != ":memory:"
    reranker = (
        LocalCrossEncoderReranker(settings.rag_reranker_model)
        if use_local_reranker
        else FusedScoreReranker()
    )
    if use_local_reranker and settings.rag_reranker_prewarm:
        reranker.prewarm()
    return QdrantRagIndex(
        client=client,
        collection_name=settings.qdrant_collection,
        dense_encoder=FastEmbedDenseEncoder(settings.rag_dense_model),
        reranker=reranker,
    )
