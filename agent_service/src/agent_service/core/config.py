from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    groq_api_key: str
    tavily_api_key: str
    alpha_vantage_api_key: str | None = None

    internal_service_api_key: str

    model_id: str = "openai/gpt-oss-20b"  # Groq-hosted, supports tool/structured-output calling


settings = Settings()
