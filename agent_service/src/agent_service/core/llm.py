"""Shared Groq LLM client + helpers, ported from notebook cells 2 and 4.

invoke_with_retry retries once on empty model output, then falls back to an
explicit message -- Groq's openai/gpt-oss-20b occasionally returns an empty
.content on an otherwise-successful call (an intermittent reliability quirk),
which would otherwise pass straight through as a blank final answer with no
indication anything had gone wrong.
"""

from langchain_groq import ChatGroq

from agent_service.core.config import settings

llm = ChatGroq(model=settings.model_id, temperature=0, api_key=settings.groq_api_key)


def content_to_text(content) -> str:
    """Normalizes a LangChain message .content into plain text: providers
    sometimes return a list of content blocks instead of a bare string."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or ""))
        return " ".join(parts)
    return str(content)


def invoke_with_retry(messages: list, fallback: str, max_attempts: int = 2) -> str:
    for _ in range(max_attempts):
        response = llm.invoke(messages)
        text = content_to_text(response.content).strip()
        if text:
            return text
    return fallback
