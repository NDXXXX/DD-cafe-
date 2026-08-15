# Architecture decision records

Add one short record here when a decision has meaningful alternatives or migration consequences. Each record states context, decision, alternatives, and consequences.

Do not create an ADR for routine implementation details.

## ADR-001 · Customer writes use a server-issued session token

- **Context.** Cart, order, cancellation, and chat/image writes are keyed by a `session_id` that a browser chooses freely. Without authentication, anyone who learns a session id can read or mutate another guest's cart.
- **Decision.** On app load the web client calls `POST /api/sessions`, which get-or-creates a row in the `sessions` table and returns a cryptographically random opaque token (`secrets.token_urlsafe`). The client stores it in `localStorage` and sends it as `X-Session-Token`; the server compares it with `secrets.compare_digest`. Knowledge-base writes (CRUD/reindex) require a separate `X-Admin-Key`, which fails closed (403) when no key is configured.
- **Alternatives.** A full OAuth2/JWT identity system was rejected as out of scope for a demo; a static bearer key would not separate customers from staff. Token issuance remains unauthenticated (anyone can mint a token for their own session), which is acceptable because the threat model is cross-session tampering, not account impersonation.
- **Consequences.** Writes now require a token, so the frontend must create a session before its first request. Read endpoints such as `GET /api/cart` also verify the token to avoid information disclosure. `serve_image` stays unauthenticated because `<img>` tags cannot carry headers.

## ADR-002 · Deterministic order boundary

- **Context.** A language model that writes directly to the cart can hallucinate prices, items, or specifications, and can be prompted into unintended mutations.
- **Decision.** The model only *proposes* intent and menu-item ids. A deterministic `ConstrainedOrderAgent` validates the item exists, the temperature/sweetness/quantity are legal, and the user's words match the menu; a deterministic `OrderService` then executes the command in a PostgreSQL transaction and reads the result back before emitting a success event. Prices, availability, totals, and order state are read from the database, never from model text.
- **Alternatives.** Function-calling with model-side argument construction was rejected because it still lets the model pick invalid values; guardrails-only prompting was rejected as unverifiable.
- **Consequences.** The model cannot mutate state directly. Every write path goes through idempotent, verifiable domain services, which makes the ordering behavior testable and the Agent harness (see `app/harness`) able to assert "no order mutation" deterministically.
