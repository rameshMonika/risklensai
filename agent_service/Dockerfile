FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.9.7 /uv /uvx /bin/

# libgomp1: PyTorch's CPU wheel (pulled in transitively by sentence-transformers,
# for the semantic router's local HuggingFaceEncoder) dynamically links against
# libgomp for OpenMP, which python:3.12-slim doesn't ship by default -- without
# this, importing torch fails at runtime, not build time.
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
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

RUN useradd --create-home --uid 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8100

ENTRYPOINT ["./entrypoint.sh"]
