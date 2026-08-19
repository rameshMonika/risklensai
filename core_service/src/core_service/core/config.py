from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 14

    internal_service_api_key: str
    agent_service_url: str = "http://localhost:8100"

    cors_origins: list[str] = ["http://localhost:5173"]


settings = Settings()
