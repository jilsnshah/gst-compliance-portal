"""Round-trips a file through whichever storage backend is configured.

    .venv/bin/python check_storage.py

Reads backend/.env, so it proves the exact configuration the API will use.
"""

from __future__ import annotations

import sys
import uuid

from app.core.config import settings
from app.storage import build_key, get_storage

KEY = build_key(0, "CHECK", "0000-00", "SELFTEST", 1, f"probe-{uuid.uuid4().hex[:8]}.txt")
PAYLOAD = b"storage round-trip probe"


def main() -> int:
    print(f"backend        : {settings.storage_backend}")
    if settings.storage_backend == "firebase":
        print(f"bucket         : {settings.firebase_bucket}")
        print(f"credentials    : {settings.firebase_credentials_file or 'GOOGLE_APPLICATION_CREDENTIALS'}")
    else:
        print(f"root           : {settings.storage_root}")

    try:
        storage = get_storage()
    except Exception as exc:
        print(f"\nFAILED to construct the backend: {exc}")
        return 1

    try:
        storage.put(KEY, PAYLOAD, "text/plain")
        print(f"\nwrote          : {KEY}")

        got = storage.read(KEY)
        assert got == PAYLOAD, f"read back {got!r}, expected {PAYLOAD!r}"
        print("read back      : matches")

        assert storage.exists(KEY), "exists() said no straight after writing"
        print("exists         : yes")

        url = storage.signed_url(KEY, 300)
        print(f"signed url     : {url[:80]}{'…' if len(url) > 80 else ''}")
    except Exception as exc:
        print(f"\nFAILED: {type(exc).__name__}: {exc}")
        return 1
    finally:
        delete = getattr(storage, "delete", None)
        if delete:
            try:
                delete(KEY)
                print("cleaned up     : yes")
            except Exception:
                print(f"cleaned up     : no -- remove {KEY} by hand")

    print("\nStorage is working.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
