from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    app_name: str = "GST Compliance Platform"

    # Dev-stage only. Swap for a real secret + Firebase Auth in Stage 2.
    secret_key: str = "dev-secret-not-for-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 12

    database_url: str = "sqlite:///" + str(BASE_DIR / "gst_platform.db")

    # storage backend: "local" now, "firebase" later
    storage_backend: str = "local"
    storage_root: Path = BASE_DIR / "storage"

    # auth provider: "local" now, "firebase" later
    auth_provider: str = "local"

    cors_origins: list = ["http://localhost:5173", "http://127.0.0.1:5173"]

    class Config:
        env_file = ".env"


settings = Settings()
