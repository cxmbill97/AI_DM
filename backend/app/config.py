"""Application settings loaded from environment / .env file."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    minimax_api_key: str = ""
    # TODO: add any additional config fields (e.g. log level, CORS origins)


settings = Settings()
