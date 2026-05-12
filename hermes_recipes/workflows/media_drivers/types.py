"""Driver interface + duration parsing.

Port of clawrecipes/src/lib/workflows/media-drivers/types.ts.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Optional, Protocol


MediaType = Literal["image", "video", "audio"]
DEFAULT_DURATION_SECONDS = 15


def parse_duration(config: Optional[dict[str, Any]]) -> str:
    """Coerce ``config['duration']`` (e.g. ``"5s"``, ``"10"``, ``15``) to seconds."""
    raw = (config or {}).get("duration")
    if raw is None:
        return str(DEFAULT_DURATION_SECONDS)
    s = str(raw).rstrip("sS").strip()
    try:
        n = int(s)
    except ValueError:
        return str(DEFAULT_DURATION_SECONDS)
    if n <= 0:
        return str(DEFAULT_DURATION_SECONDS)
    return str(n)


@dataclass(frozen=True)
class DurationConstraints:
    min_seconds: int
    max_seconds: int
    default_seconds: int
    step_seconds: Optional[int] = None


@dataclass(frozen=True)
class MediaDriverInvokeOpts:
    prompt: str
    output_dir: Path
    timeout: float
    config: dict[str, Any] = field(default_factory=dict)
    env: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class MediaDriverResult:
    file_path: Path
    metadata: dict[str, Any] = field(default_factory=dict)


class MediaDriver(Protocol):
    """Static interface a driver class must satisfy."""

    slug: str
    media_type: MediaType
    display_name: str
    required_env_vars: tuple[str, ...]
    duration_constraints: Optional[DurationConstraints]

    def invoke(self, opts: MediaDriverInvokeOpts) -> MediaDriverResult: ...
