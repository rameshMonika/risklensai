FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1

COPY --from=ghcr.io/astral-sh/uv:0.9.7 /uv /uvx /bin/

# libgomp1: PyTorch's CPU wheel (pulled in transitively by sentence-transformers,
# for the semantic router's local HuggingFaceEncoder) dynamically links against
# libgomp for OpenMP, which python:3.12-slim doesn't ship by default -- without
# this, importing torch fails at runtime, not build time.
#
# ca-certificates: router.py calls truststore.inject_into_ssl() at import time,
# which switches Python's TLS verification from its bundled certifi bundle to
# the OS trust store -- python:3.12-slim doesn't install this package by
# default, so that OS store is empty. HuggingFaceEncoder's model download (also
# at import time, same module) then has no way to verify any HTTPS connection,
# hanging/failing silently before uvicorn ever gets to log a single line.
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 ca-certificates \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies first, isolated in their own layer.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# The mcp_servers/ directory MUST sit alongside src/ at the project root, same
# as in local dev -- mcp_manager.py resolves it relative to its own installed
# location (Path(__file__).resolve().parents[3] / "mcp_servers"), not as a
# packaged resource, so this layout is load-bearing, not cosmetic.
COPY src ./src
COPY mcp_servers ./mcp_servers
COPY entrypoint.sh ./entrypoint.sh
RUN chmod +x entrypoint.sh && uv sync --frozen --no-dev

# Pre-fetch the router's HuggingFaceEncoder model at BUILD time so it's baked
# into the image. Otherwise every container start downloads it from the HF Hub
# at import time -- on Azure Container Apps that download runs over the custom
# VNet subnet (no NAT gateway) and reliably exceeds the startup-probe window,
# leaving the revision stuck in ActivationFailed with the app never logging a
# line. HF_HOME points inside /app so the next `chown` makes it writable to
# appuser; HF_HUB_OFFLINE/TRANSFORMERS_OFFLINE then guarantee no network at
# runtime -- a cache miss becomes a loud error instead of a silent hang.
ENV HF_HOME=/app/.cache/huggingface
RUN uv run python -c "from semantic_router.encoders import HuggingFaceEncoder; HuggingFaceEncoder(score_threshold=0.0)"
ENV HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

RUN useradd --create-home --uid 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8100

ENTRYPOINT ["./entrypoint.sh"]
