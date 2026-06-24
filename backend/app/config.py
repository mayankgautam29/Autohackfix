from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    cors_origins: str = (
        "https://autohackfix.vercel.app,"
        "http://localhost:3000,http://127.0.0.1:3000"
    )
    app_env: str = "development"
    root_path: str = ""
    cache_ttl_seconds: int = 3600
    rate_limit_requests: int = 10
    rate_limit_window_seconds: int = 3600


def get_settings() -> Settings:
    return Settings()
