from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

CONTEXT_PRONOUNS = ("它", "这个", "那个", "该", "其", "这款", "那款", "上面的")


class QueryRewriteModel(Protocol):
    async def rewrite_query(
        self,
        query: str,
        history: Sequence[tuple[str, str]],
    ) -> str: ...


@dataclass(frozen=True)
class RewriteResult:
    query: str
    applied: bool
    degraded: bool


def needs_rewrite(query: str, history: Sequence[tuple[str, str]]) -> bool:
    return bool(history) and any(pronoun in query for pronoun in CONTEXT_PRONOUNS)


async def rewrite_query(
    model: QueryRewriteModel,
    query: str,
    history: Sequence[tuple[str, str]],
) -> RewriteResult:
    if not needs_rewrite(query, history):
        return RewriteResult(query=query, applied=False, degraded=False)
    try:
        rewritten = (await model.rewrite_query(query, history[-4:])).strip()
    except Exception:  # noqa: BLE001 - model providers expose different transport errors
        return RewriteResult(query=query, applied=False, degraded=True)
    if not rewritten or len(rewritten) > 200:
        return RewriteResult(query=query, applied=False, degraded=True)
    return RewriteResult(query=rewritten, applied=rewritten != query, degraded=False)
