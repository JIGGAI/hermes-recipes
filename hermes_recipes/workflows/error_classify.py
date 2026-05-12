"""Classify workflow errors so the worker can decide retry vs. user-error.

Port of clawrecipes/src/lib/workflows/workflow-error-classify.ts. The TS
version interrogates ``ToolsInvokeError`` for an HTTP status; here we accept
any exception with an ``http_status`` (or ``httpStatus``) attribute so the
classifier remains decoupled from the tool-invocation client.
"""

import re
from typing import Any, Literal

ErrorCategory = Literal["funding", "rate-limit", "auth", "timeout", "unknown"]

_FUNDING_PATTERNS = (
    re.compile(r"insufficient.*(credits?|funds?|balance)", re.IGNORECASE),
    re.compile(r"billing", re.IGNORECASE),
    re.compile(r"payment\s+required", re.IGNORECASE),
    re.compile(r"quota\s+exceeded", re.IGNORECASE),
    re.compile(r"out\s+of\s+credits", re.IGNORECASE),
    re.compile(r"budget\s+(exceeded|limit)", re.IGNORECASE),
    re.compile(r"no\s+(active\s+)?subscription", re.IGNORECASE),
    re.compile(r"plan\s+(limit|exceeded)", re.IGNORECASE),
)
_RATE_LIMIT_PATTERNS = (
    re.compile(r"rate\s+limit", re.IGNORECASE),
    re.compile(r"too\s+many\s+requests", re.IGNORECASE),
    re.compile(r"throttl", re.IGNORECASE),
)
_AUTH_PATTERNS = (
    re.compile(r"unauthorized", re.IGNORECASE),
    re.compile(r"invalid.*api.?key", re.IGNORECASE),
    re.compile(r"forbidden", re.IGNORECASE),
    re.compile(r"authentication\s+failed", re.IGNORECASE),
    re.compile(r"access\s+denied", re.IGNORECASE),
)
_TIMED_OUT_RE = re.compile(r"timed?\s*out", re.IGNORECASE)


def _http_status_from(error: Any) -> int:
    for attr in ("http_status", "httpStatus", "status"):
        value = getattr(error, attr, None)
        if isinstance(value, int):
            return value
    return 0


def _classify_by_http_status(status: int) -> ErrorCategory | None:
    if status == 402:
        return "funding"
    if status == 429:
        return "rate-limit"
    if status in (401, 403):
        return "auth"
    if status in (408, 504):
        return "timeout"
    return None


def _classify_by_message(message: str, error: Any) -> ErrorCategory | None:
    if any(p.search(message) for p in _FUNDING_PATTERNS):
        return "funding"
    if any(p.search(message) for p in _RATE_LIMIT_PATTERNS):
        return "rate-limit"
    if any(p.search(message) for p in _AUTH_PATTERNS):
        return "auth"
    # Standard Python timeout / cancellation surfaces.
    if isinstance(error, TimeoutError):
        return "timeout"
    if error.__class__.__name__ in ("AbortError", "CancelledError"):
        return "timeout"
    if _TIMED_OUT_RE.search(message):
        return "timeout"
    return None


def classify_error(error: Any) -> ErrorCategory:
    http_status = _http_status_from(error)
    message = str(error) if not isinstance(error, str) else error
    return (
        _classify_by_http_status(http_status)
        or _classify_by_message(message, error)
        or "unknown"
    )


_CATEGORY_LABELS: dict[ErrorCategory, str] = {
    "funding": "Funding issue — the model provider may be out of credits or require payment",
    "rate-limit": "Rate limit — the model provider is throttling requests",
    "auth": "Authentication failure — the API key may be invalid or expired",
    "timeout": "Timeout — the request took too long to complete",
    "unknown": "Unknown error",
}


def error_category_label(category: ErrorCategory) -> str:
    return _CATEGORY_LABELS.get(category, _CATEGORY_LABELS["unknown"])
