FROM python:3.12-slim

# uv binary, not pip -- matches how this project is developed locally
# (core_service/pyproject.toml + uv.lock), so `uv sync --frozen` here
# installs exactly what the lockfile pins, no resolution drift.
COPY --from=ghcr.io/astral-sh/uv:0.9.7 /uv /uvx /bin/

WORKDIR /app

# Dependencies first, isolated in their own layer -- source changes below
# don't invalidate this (slowest) layer on rebuild.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Now the actual source, alembic config, and entrypoint.
COPY src ./src
COPY alembic.ini ./alembic.ini
COPY migrations ./migrations
COPY entrypoint.sh ./entrypoint.sh
RUN chmod +x entrypoint.sh && uv sync --frozen --no-dev

# Runs as non-root.
RUN useradd --create-home --uid 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]
