from __future__ import annotations

from abc import ABC, abstractmethod
from typing import BinaryIO


class StorageBackend(ABC):
    """Swap point for cloud storage. The rest of the app only ever sees a
    storage_key string, so moving off local disk -- to S3, R2, Supabase or
    anything else -- touches nothing outside this package."""

    @abstractmethod
    def put(self, key: str, data: bytes, content_type: str = "") -> str:
        """Persist bytes at key. Returns the canonical storage key."""

    @abstractmethod
    def open(self, key: str) -> BinaryIO:
        """Open a readable stream for key."""

    @abstractmethod
    def read(self, key: str) -> bytes:
        ...

    @abstractmethod
    def exists(self, key: str) -> bool:
        ...

    @abstractmethod
    def signed_url(self, key: str, expires_seconds: int = 3600) -> str:
        """Direct-access URL. The local backend returns an API download path."""


def build_key(
    client_id: int,
    gstin: str,
    period_code: str,
    doc_type: str,
    version_no: int,
    filename: str,
) -> str:
    safe_name = filename.replace("/", "_").replace("\\", "_").strip()
    return f"clients/{client_id}/{gstin}/{period_code}/{doc_type}/v{version_no}_{safe_name}"
