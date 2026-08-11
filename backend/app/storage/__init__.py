from __future__ import annotations

from functools import lru_cache

from app.core.config import settings
from app.storage.base import StorageBackend, build_key
from app.storage.local import LocalStorage

__all__ = ["StorageBackend", "build_key", "get_storage"]


@lru_cache(maxsize=1)
def get_storage() -> StorageBackend:
    if settings.storage_backend == "local":
        return LocalStorage(settings.storage_root)
    # A cloud backend plugs in here: implement StorageBackend and return it.
    # Nothing outside this package changes -- the app only ever handles the
    # opaque storage_key strings that build_key() produces.
    raise ValueError(f"unknown storage backend: {settings.storage_backend}")
