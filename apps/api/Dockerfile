# syntax=docker/dockerfile:1

# Build context is the repo root (`docker build -f apps/api/Dockerfile .`),
# so that `seed.py`'s PROJECT_ROOT=parents[3] resolves to `/app`.
FROM python:3.12-slim

# uv for fast, reproducible dependency installs
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# 1) Manifest first, so dependency layers cache across source edits
COPY apps/api/pyproject.toml apps/api/uv.lock apps/api/alembic.ini apps/api/

# 2) Install runtime deps into apps/api/.venv (skip dev group + the project itself)
RUN cd apps/api && uv sync --frozen --no-dev --no-install-project

# 3) Source + migrations + seed data (data/seed is read via PROJECT_ROOT)
COPY apps/api/app apps/api/app
COPY apps/api/migrations apps/api/migrations
COPY data/seed data/seed

WORKDIR /app/apps/api
ENV PATH="/app/apps/api/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
