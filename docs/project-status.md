# Project status

## Completed

- Product and architecture discussion.
- Project working agreement.
- React mobile menu, chat drawer, cart, and post-order experience.
- FastAPI catalog, cart, order, cancellation, knowledge, and SSE chat APIs.
- PostgreSQL models and Alembic initial migration.
- Structured order intent, exact explicit-spec preservation, durable cart/order idempotency, database read-back, immutable submitted orders, and addendum orders.
- LangGraph supervisor with typed shared state, explicit recommendation-to-order handoff, layered short-term memory, read-only recommendation agent, constrained order agent, and independent verification events.
- Redis-backed LangGraph checkpoints with an in-memory test substitute.
- PostgreSQL knowledge documents/chunks with SHA-256 incremental indexing and retry status.
- Qdrant dense retrieval plus Chinese BM25, RRF, local BGE cross-encoder reranking, query rewrite, evidence filtering, and knowledge CRUD/reindexing.
- Optional real-time web search and optional DeepSeek streaming model.
- Deterministic no-key demo model and labelled demo menu/restaurant data.
- Agent safety harness, deterministic RAG harness, and optional four-metric RAGAS evaluator.
- Passing API tests and Ruff, web test and production build, harness cases, migrations, and Compose validation.
- Manual mobile-browser verification of menu add, quantity change, submit, addendum, RAG question, chat add, and backdrop close.

## Current milestone

Replace demo menu and restaurant knowledge with verified restaurant data, then connect a DeepSeek API key and evaluate model answers.

## Deliberately deferred from V1

- Payment and kitchen/POS integration.
- Staff handling UI for pending cancellation requests.
- QR generation, user accounts, multi-store tenancy, and long-term customer profiles.
- Kubernetes, Kafka, GraphQL, Redux, and microservice extraction until scale or team boundaries justify them.
