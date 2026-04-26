from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    # Comma-separated browser origins only (no trailing slashes). UptimeRobot and similar
    # hit GET /health from servers — they do not use CORS; do not list monitor domains here.
    cors_origins: str = (
        "https://autohackfix.vercel.app,"
        "http://localhost:3000,http://127.0.0.1:3000"
    )
    app_env: str = "development"
    root_path: str = ""


def get_settings() -> Settings:
    return Settings()
