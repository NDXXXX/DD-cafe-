.PHONY: infra-up infra-down db-upgrade api web test-api lint-api eval eval-rag eval-rag-reranker eval-ragas test-web build-web verify

infra-up:
	docker compose -f infra/compose.yaml up -d

infra-down:
	docker compose -f infra/compose.yaml down

db-upgrade:
	cd apps/api && uv run alembic upgrade head

api:
	cd apps/api && uv run uvicorn app.main:app --reload

web:
	corepack pnpm --dir apps/web dev

test-api:
	cd apps/api && uv run pytest

lint-api:
	cd apps/api && uv run ruff check .

eval:
	cd apps/api && uv run python -m app.harness.run

eval-rag:
	cd apps/api && uv run python -m app.harness.run_rag

eval-rag-reranker:
	cd apps/api && uv run python -m app.harness.run_rag --local-reranker

eval-ragas:
	cd apps/api && uv run python -m app.harness.run_rag --local-reranker --ragas

test-web:
	corepack pnpm --dir apps/web test

build-web:
	corepack pnpm --dir apps/web build

verify: test-api lint-api eval eval-rag test-web build-web
	docker compose -f infra/compose.yaml config --quiet
