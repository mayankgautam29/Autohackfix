from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    # development | production — used for middleware / headers
    app_env: str = "development"
    # When behind a reverse proxy with a path prefix, set e.g. /api (no trailing slash)
    root_path: str = ""


def get_settings() -> Settings:
    return Settings()
