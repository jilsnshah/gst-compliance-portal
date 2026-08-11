from __future__ import annotations

import re
import unicodedata
import zipfile
from io import BytesIO
from typing import Optional, Tuple


class RejectedUpload(Exception):
    """The file is not something we are willing to store or hand back out.
    Carries a message meant for whoever is uploading."""


MAX_FILENAME = 120

# Extension -> the content type we will serve it back as. The browser is never
# told anything the bytes do not support, and nothing executable is on the list.
ALLOWED = {
    "pdf": "application/pdf",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
    "heic": "image/heic",
    "heif": "image/heif",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "xlsm": "application/vnd.ms-excel.sheet.macroEnabled.12",
    "xls": "application/vnd.ms-excel",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "csv": "text/csv",
    "txt": "text/plain",
}

# SVG and HTML are deliberately absent: both can carry script, and anything we
# serve from our own origin could then run with the user's session.
BLOCKED_HINT = (
    "Attach a PDF, image (png, jpg, gif, webp, heic), spreadsheet "
    "(xlsx, xls, csv) or a text file."
)


def _ext(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def safe_filename(filename: str) -> str:
    """Strip anything that could escape a directory or confuse a download
    header, while keeping the name recognisable to the person who sent it."""
    name = unicodedata.normalize("NFKD", filename or "")
    name = name.replace("\\", "/").rsplit("/", 1)[-1]          # drop any path
    name = "".join(c for c in name if c.isprintable() and c not in '"\r\n\t')
    name = re.sub(r"\s+", " ", name).strip(" .")
    name = re.sub(r"[^A-Za-z0-9._ ()\-]", "_", name)
    if not name:
        raise RejectedUpload("That file has no usable name.")
    if len(name) > MAX_FILENAME:
        ext = _ext(name)
        keep = MAX_FILENAME - len(ext) - 1
        name = f"{name[:keep]}.{ext}" if ext else name[:MAX_FILENAME]
    return name


def _zip_kind(data: bytes) -> Optional[str]:
    try:
        names = zipfile.ZipFile(BytesIO(data)).namelist()
    except Exception:
        return None
    if any(n.startswith("xl/") for n in names):
        return "xlsx"
    if any(n.startswith("word/") for n in names):
        return "docx"
    return None


def _looks_textual(data: bytes) -> bool:
    head = data[:4096]
    if b"\x00" in head:
        return False
    try:
        text = head.decode("utf-8-sig")
    except UnicodeDecodeError:
        return False
    # A "csv" that is really a web page is a stored-XSS attempt waiting for
    # somewhere that renders it.
    return not text.lstrip()[:200].lower().startswith(("<!doctype", "<html", "<?xml", "<svg"))


def sniff(data: bytes) -> Optional[str]:
    """What the bytes actually are, ignoring the name and the declared type."""
    if data[:5] == b"%PDF-":
        return "pdf"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data[4:8] == b"ftyp" and data[8:12].lower() in (b"heic", b"heix", b"mif1", b"heim"):
        return "heic"
    if data[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        return "xls"
    if data[:4] == b"PK\x03\x04":
        return _zip_kind(data)
    if _looks_textual(data):
        return "text"
    return None


# Which sniffed kinds each extension is allowed to be.
CONSISTENT = {
    "pdf": {"pdf"},
    "png": {"png"},
    "jpg": {"jpg"},
    "jpeg": {"jpg"},
    "gif": {"gif"},
    "webp": {"webp"},
    "heic": {"heic"},
    "heif": {"heic"},
    "xlsx": {"xlsx"},
    "xlsm": {"xlsx"},
    "xls": {"xls"},
    "docx": {"docx"},
    "csv": {"text"},
    "txt": {"text"},
}


def validate(filename: str, data: bytes) -> Tuple[str, str]:
    """Returns (safe filename, content type to store and serve).

    The extension must be on the allowlist *and* the bytes must actually be
    that kind of file -- neither the name nor the browser-supplied content type
    is trusted, since both are chosen by whoever is uploading.
    """
    if not data:
        raise RejectedUpload("That file is empty.")

    name = safe_filename(filename)
    ext = _ext(name)
    if ext not in ALLOWED:
        raise RejectedUpload(
            f"{'.' + ext if ext else 'That file type'} is not allowed. {BLOCKED_HINT}"
        )

    kind = sniff(data)
    if kind is None:
        raise RejectedUpload(
            f"This does not look like a real {ext.upper()} file. {BLOCKED_HINT}"
        )
    if kind not in CONSISTENT[ext]:
        raise RejectedUpload(
            f"This is named .{ext} but its contents are a {kind.upper()} file. "
            "Rename it correctly or upload the right file."
        )
    return name, ALLOWED[ext]
