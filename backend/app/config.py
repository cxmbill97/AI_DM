"""Application settings loaded from environment / .env file."""

from __future__ import annotations

import secrets

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    minimax_api_key: str = ""
    jwt_secret: str = secrets.token_hex(32)   # override via JWT_SECRET env var
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/auth/google/callback"


settings = Settings()
