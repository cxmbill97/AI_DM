"""Application settings loaded from environment / .env file."""

from __future__ import annotations

import logging
import secrets

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    minimax_api_key: str = ""
    jwt_secret: str = secrets.token_hex(32)   # override via JWT_SECRET env var — ephemeral default logs out all users on restart
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/auth/google/callback"
    google_mobile_redirect_uri: str = "http://localhost:8000/auth/google/mobile/callback"
    frontend_url: str = "http://localhost:5173"
    apple_bundle_id: str = ""


settings = Settings()

if not settings.jwt_secret or settings.jwt_secret == "":
    logger.warning(
        "JWT_SECRET env var is not set — using a random secret that resets on every restart. "
        "All user tokens will be invalidated on each process restart. "
        "Set JWT_SECRET in your .env file for persistent sessions."
    )
