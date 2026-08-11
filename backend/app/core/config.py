from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    app_name: str = "GST Compliance Platform"

    # Dev-stage only. Swap for a real secret + Firebase Auth in Stage 2.
    secret_key: str = "dev-secret-not-for-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 12

    database_url: str = "sqlite:///" + str(BASE_DIR / "gst_platform.db")

    # storage backend: "local" for now; a cloud backend plugs into app/storage
    storage_backend: str = "local"
    storage_root: Path = BASE_DIR / "storage"

    # auth provider: "local" now, "firebase" later
    auth_provider: str = "local"

    # Comma-separated. Add the deployed frontend origin here, e.g.
    # CORS_ORIGINS=http://localhost:5173,https://my-app.vercel.app
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    # Optional regex, handy for Vercel preview deployments:
    # CORS_ORIGIN_REGEX=https://.*\.vercel\.app
    cors_origin_regex: Optional[str] = None

    @property
    def cors_origin_list(self) -> list:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    class Config:
        env_file = ".env"


settings = Settings()
