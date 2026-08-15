# Database migrations

Alembic revisions for the PostgreSQL schema, in dependency order:

- `7255765012cd` — initial schema (menu, knowledge, carts, orders, idempotency).
- `4d773da3c52e` — correct the demo Americano spec.
- `9a874d18a4d2` — durable cart-mutation idempotency.
- `f36d52ad71c8` — knowledge chunks and SHA-256 index state.
- `b7e2f4a9c1d3` — customer session tokens (see `app/sessions`).

Run `make db-upgrade` (or `cd apps/api && uv run alembic upgrade head`) to apply them. The app also creates the schema on startup via `auto_create_schema`, but migrations remain the source of truth for upgrades.
