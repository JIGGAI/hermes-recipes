"""JSON.stringify with deterministic key ordering and circular handling.

Port of clawrecipes/src/lib/stable-stringify.ts. Used for generating stable
hashes/signatures of objects (cron-spec hashing, binding deduplication).
"""

import json
from typing import Any


def stable_stringify(value: Any) -> str:
    seen: set[int] = set()

    def _sort(v: Any) -> Any:
        if isinstance(v, dict):
            if id(v) in seen:
                return "[Circular]"
            seen.add(id(v))
            return {k: _sort(v[k]) for k in sorted(v.keys())}
        if isinstance(v, list):
            if id(v) in seen:
                return "[Circular]"
            seen.add(id(v))
            return [_sort(item) for item in v]
        return v

    return json.dumps(_sort(value), separators=(",", ":"), ensure_ascii=False)
