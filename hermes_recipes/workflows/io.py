"""Tiny async-free wrappers around file reads.

Port of clawrecipes/src/lib/workflows/workflow-runner-io.ts. The TS version
isolates reads into its own module because heuristic scanners flag
filesystem + network/process patterns when they sit in the same file. We
keep that boundary for parity.
"""

import json
from pathlib import Path
from typing import Any, Optional


def read_text_file(p: Path | str) -> str:
    return Path(p).read_text(encoding="utf-8")


def read_json_file(p: Path | str) -> Any:
    return json.loads(read_text_file(p))


def maybe_read_text_file(p: Path | str) -> Optional[str]:
    try:
        return read_text_file(p)
    except OSError:
        return None
