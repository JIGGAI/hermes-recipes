"""Strip internal-only disclaimer lines before outbound publishing.

Port of clawrecipes/src/lib/workflows/outbound-sanitize.ts. Conservative by
design: only well-known phrases get dropped so the actual post body stays
intact.
"""

import re

_DROP_PATTERNS = (
    re.compile(r"\bdraft\s*only\b", re.IGNORECASE),
    re.compile(r"\bdo\s+not\s+post\b", re.IGNORECASE),
    re.compile(r"\bdo\s+not\s+publish\b", re.IGNORECASE),
    re.compile(r"\bnot\s+for\s+posting\b", re.IGNORECASE),
    re.compile(r"\binternal\s+only\b", re.IGNORECASE),
    re.compile(r"\bneeds\s+approval\b", re.IGNORECASE),
    re.compile(r"\bapproval\s+required\b", re.IGNORECASE),
)
_MULTI_BLANK_RE = re.compile(r"\n{3,}")


def sanitize_outbound_post_text(value: str | None) -> str:
    raw = "" if value is None else str(value)
    if not raw.strip():
        return ""

    def should_drop(line: str) -> bool:
        stripped = line.strip()
        if not stripped:
            return False
        return any(p.search(stripped) for p in _DROP_PATTERNS)

    lines = re.split(r"\r?\n", raw)
    kept = [line for line in lines if not should_drop(line)]
    return _MULTI_BLANK_RE.sub("\n\n", "\n".join(kept)).strip()
