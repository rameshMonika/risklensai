#!/bin/sh
set -e

# Fully stateless, no DB, no migration step -- just start the server.
exec uv run uvicorn agent_service.main:app --host 0.0.0.0 --port 8100
