#!/bin/sh
set -e

# Creates/updates the schema on whatever Postgres DATABASE_URL points at --
# a no-op if it's already at head (e.g. local dev, already stamped), the
# thing that actually bootstraps a brand-new empty Azure Postgres on first
# deploy, and applies any future migration on redeploy.
uv run alembic upgrade head

exec uv run uvicorn core_service.main:app --host 0.0.0.0 --port 8000
