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

## Authentication

Two mechanisms, both fail-closed:

- **Customer writes.** The web client calls `POST /api/sessions` on load to mint a random opaque token bound to its `session_id`. The token is stored in `localStorage` and sent as `X-Session-Token`; the server verifies it with `secrets.compare_digest`. Cart, order, cancellation, chat, and image-upload endpoints all require it. `serve_image` stays open because `<img>` tags cannot send headers.
- **Knowledge management.** Create/update/delete/reindex require an `X-Admin-Key`. When no admin key is configured, these endpoints return 403 rather than falling open.

See ADR-001 for the threat model and the rejected alternatives.

## Multimodal check-in card

An image in the chat follows a separate pipeline: the web client resizes and compresses the upload, the API streams the image to a QwenVL vision model for understanding and a QwenVL reply, and DashScope image generation/edit produces a shareable check-in card. Generated images are saved under the upload directory and served back through the same image endpoint. The frontend renders the card in a dedicated component (`CheckInCard`).

## Deployment

`apps/api/Dockerfile` and `apps/web/Dockerfile` (multi-stage, nginx serving the SPA and proxying `/api/` to the API) are wired into `infra/compose.yaml` alongside PostgreSQL, Redis, and Qdrant. The web image is built with an empty `VITE_API_BASE_URL` so requests stay same-origin. `.github/workflows/ci.yml` runs API lint + tests and web test + build on push and pull requests. If Redis is unavailable the checkpointer falls back to an in-memory saver so the API still boots.

## Streaming

FastAPI exposes SSE events for message text, retrieval progress, tool progress, cart changes, order changes, check-in card progress, completion, and errors.
