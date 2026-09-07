from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # "groq" (default, local dev) or "azure" (Azure AI Foundry, prod). Both
    # serve the same OpenAI gpt-oss family; only the LangChain client differs
    # (see core/llm.py). Everything downstream is provider-agnostic.
    llm_provider: str = "groq"

    # Groq (used when llm_provider == "groq")
    groq_api_key: str | None = None
    model_id: str = "openai/gpt-oss-20b"  # Groq-hosted, supports tool/structured-output calling

    # Azure AI Foundry (required when llm_provider == "azure")
    azure_openai_endpoint: str | None = None
    azure_openai_api_key: str | None = None
    azure_openai_deployment: str = "gpt-oss-120b"
    azure_openai_api_version: str = "2024-10-21"

    tavily_api_key: str
    alpha_vantage_api_key: str | None = None

    internal_service_api_key: str

    # LangSmith tracing. LangGraph/LangChain auto-instrument when these are in
    # os.environ (see core/observability.py, which bridges them from here since
    # pydantic-settings does not export .env values to the environment).
    langsmith_tracing: bool = False
    langsmith_api_key: str | None = None
    langsmith_project: str = "risklens-agent"
    langsmith_endpoint: str = "https://api.smith.langchain.com"


settings = Settings()
