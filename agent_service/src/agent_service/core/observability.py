"""LangSmith tracing setup for the LangGraph pipeline.

LangGraph and LangChain auto-instrument every node, LLM call and tool call
when the LANGSMITH_* variables are present in `os.environ`. pydantic-settings
reads `.env` into the Settings object but does NOT export those values to the
process environment, so a bare `uv run uvicorn` (which only has `.env`) would
otherwise trace nothing. This module bridges the gap: it copies the settings
into `os.environ` so the LangSmith SDK picks them up. In Docker / Azure the
vars are already real environment variables and the setdefault calls are
harmless no-ops.

Call `configure_tracing()` once at startup, before the first graph invoke.
"""

import os

from agent_service.core.config import settings


def configure_tracing() -> None:
    if not settings.langsmith_tracing or not settings.langsmith_api_key:
        return
    os.environ.setdefault("LANGSMITH_TRACING", "true")
    os.environ.setdefault("LANGSMITH_API_KEY", settings.langsmith_api_key)
    os.environ.setdefault("LANGSMITH_PROJECT", settings.langsmith_project)
    os.environ.setdefault("LANGSMITH_ENDPOINT", settings.langsmith_endpoint)
