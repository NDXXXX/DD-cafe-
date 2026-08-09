from collections.abc import Sequence
from typing import Protocol

from fastembed.rerank.cross_encoder import TextCrossEncoder


class Reranker(Protocol):
    def rerank(self, query: str, documents: Sequence[str]) -> list[float]: ...


class LocalCrossEncoderReranker:
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self._model: TextCrossEncoder | None = None

    @property
    def model(self) -> TextCrossEncoder:
        if self._model is None:
            self._model = TextCrossEncoder(
                model_name=self.model_name,
                lazy_load=True,
            )
        return self._model

    def prewarm(self) -> None:
        self.rerank("咖啡", ["咖啡"])

    def rerank(self, query: str, documents: Sequence[str]) -> list[float]:
        return [float(score) for score in self.model.rerank(query, documents)]


class FusedScoreReranker:
    def rerank(self, query: str, documents: Sequence[str]) -> list[float]:
        del query
        return [0.0] * len(documents)
