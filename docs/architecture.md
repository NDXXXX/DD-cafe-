# Architecture

## Shape

The system is a modular monolith in a monorepo. The web application calls one FastAPI service. PostgreSQL is the authoritative business store, Redis holds LangGraph checkpoints and short-lived coordination state, and Qdrant is a rebuildable retrieval index.

## Agent flow

```text
input
-> LangGraph supervisor (rules first, model fallback)
-> recommendation | ordering | recommend_then_order | clarify
-> deterministic verification
-> final response
```

The recommendation agent is read-only and may use the live menu, restaurant RAG, and web search. The constrained order agent interprets language but cannot write directly. Deterministic order services validate and execute commands in PostgreSQL transactions.

## Order safety

- Ambiguous writes are rejected or clarified.
- Prices, availability, totals, and order state come from PostgreSQL.
- Redis persists short-lived LangGraph checkpoints; PostgreSQL provides durable idempotency for every cart mutation and order submission.
- Success events are emitted only after commit and database read-back.
- Submitted orders are immutable.
- Later additions create addendum orders.
- Cancellations create pending requests.

## Retrieval

Knowledge documents, SHA-256 index state, and stable chunks live in PostgreSQL. Qdrant stores Chinese dense embeddings. Retrieval combines dense candidates with jieba-tokenized BM25, applies RRF using stable chunk IDs, and runs `BAAI/bge-reranker-base` locally. Context-dependent questions are rewritten from recent history, while failures fall back to the original query. Low-confidence evidence is removed before generation. The Qdrant collection is rebuildable from PostgreSQL.

The RAG harness records the exact contexts used by the same Agent run. Deterministic gates cover Hit@K, reciprocal rank, no-evidence behavior, latency, and zero order mutation. Optional DeepSeek-backed RAGAS evaluation covers Faithfulness, Answer Relevancy, Context Precision, and Context Recall.

## Streaming

FastAPI exposes SSE events for message text, retrieval progress, tool progress, cart changes, order changes, completion, and errors.
