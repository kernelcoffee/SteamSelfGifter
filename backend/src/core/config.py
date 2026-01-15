import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal


def get_data_dir() -> str:
    """Get data directory - /config in Docker, ./data locally"""
    if os.path.exists("/config"):
        return "/config"
    return "./data"


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # Application
    app_name: str = "SteamSelfGifter"
    version: str = "2.0.0"
    environment: Literal["development", "production"] = "development"
    debug: bool = True

    # Database
    database_url: str = f"sqlite+aiosqlite:///{get_data_dir()}/steamselfgifter.db"

    # API
    api_v1_prefix: str = "/api/v1"
    allowed_origins: list[str] = ["http://localhost:3000", "http://localhost:8000", "http://localhost:8080"]

    # Logging
    log_level: str = "INFO"
    log_file: str = f"{get_data_dir()}/app.log"

    # Scheduler
    scheduler_timezone: str = "UTC"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


settings = Settings()
