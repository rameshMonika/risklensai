"""Shared LLM client + helpers, ported from notebook cells 2 and 4.

The provider is chosen by settings.llm_provider: "groq" (default, local dev,
gpt-oss-20b) or "azure" (Azure AI Foundry, prod, gpt-oss-120b). Both serve the
same OpenAI gpt-oss family and return the same LangChain message shape, so the
rest of the pipeline (nodes, guardrail, router) is provider-agnostic.

invoke_with_retry retries once on empty model output, then falls back to an
explicit message -- gpt-oss occasionally returns an empty .content on an
otherwise-successful call (an intermittent reliability quirk), which would
otherwise pass straight through as a blank final answer with no indication
anything had gone wrong.
"""

from agent_service.core.config import settings

if settings.llm_provider == "azure":
    from langchain_openai import AzureChatOpenAI

    llm = AzureChatOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        azure_deployment=settings.azure_openai_deployment,
        api_version=settings.azure_openai_api_version,
        temperature=0,
    )
else:
    from langchain_groq import ChatGroq

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
