from __future__ import annotations

import re
from typing import Annotated

from pydantic import AfterValidator

# Deliberately permissive. Pydantic's EmailStr refuses special-use TLDs such as
# .local and .internal, which is exactly what an office LAN uses for its own
# addresses -- an account created as partner@nhs.local could then never log in.
# This catches typos without deciding which domains are allowed to exist.
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _check(value: str) -> str:
    value = (value or "").strip()
    if not _EMAIL.match(value):
        raise ValueError("not a valid email address")
    return value


Email = Annotated[str, AfterValidator(_check)]
