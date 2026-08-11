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

    # storage backend: "local" (disk) or "firebase" (Cloud Storage bucket)
    storage_backend: str = "local"
    storage_root: Path = BASE_DIR / "storage"

    # Firebase Storage. The bucket is the one shown in the Firebase console
    # under Storage, e.g. "my-project.appspot.com" or "my-project.firebasestorage.app".
    # Leave the credentials file unset to fall back to GOOGLE_APPLICATION_CREDENTIALS.
    firebase_bucket: Optional[str] = None
    firebase_credentials_file: Optional[str] = None
    # Hand out short-lived signed URLs instead of streaming file bytes through
    # the API. Only takes effect on the firebase backend.
    use_signed_urls: bool = False
    signed_url_ttl_seconds: int = 900

    # auth provider: "local" now, "firebase" later
    auth_provider: str = "local"

    cors_origins: list = ["http://localhost:5173", "http://127.0.0.1:5173"]

    class Config:
        env_file = ".env"


settings = Settings()
