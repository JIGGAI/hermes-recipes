"""Filesystem helpers — direct Python equivalents of clawrecipes/src/lib/fs-utils.ts.

Most of the TS file is unnecessary in Python (pathlib covers it), but the
``write_file_safely`` createOnly mode is recipe-domain behavior and gets a
dedicated helper.
"""

from pathlib import Path
from typing import Literal


WriteMode = Literal["createOnly", "overwrite"]


def ensure_dir(p: Path | str) -> None:
    Path(p).mkdir(parents=True, exist_ok=True)


def write_file_safely(p: Path | str, content: str, mode: WriteMode) -> dict:
    """Write *content* to *p*.

    Returns ``{"wrote": True, "reason": "ok"}`` on write or
    ``{"wrote": False, "reason": "exists"}`` when *mode* is ``"createOnly"``
    and the file already exists.
    """
    path = Path(p)
    if mode == "createOnly" and path.exists():
        return {"wrote": False, "reason": "exists"}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return {"wrote": True, "reason": "ok"}
