from __future__ import annotations

from pathlib import Path
from typing import BinaryIO

from app.storage.base import StorageBackend


class LocalStorage(StorageBackend):
    """Dev-stage backend. Writes under settings.storage_root, mirroring the key
    hierarchy so files are inspectable on disk."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        root = self.root.resolve()
        if root not in path.parents and path != root:
            raise ValueError("storage key escapes storage root")
        return path

    def put(self, key: str, data: bytes, content_type: str = "") -> str:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    def open(self, key: str) -> BinaryIO:
        return open(self._path(key), "rb")

    def read(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def signed_url(self, key: str, expires_seconds: int = 3600) -> str:
        # No real signing in dev -- downloads go through the authorised API route.
        return f"/api/documents/versions/by-key/{key}"
