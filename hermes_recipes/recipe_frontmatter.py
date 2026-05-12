"""Recipe frontmatter parsing and cron-job normalization.

Port of clawrecipes/src/lib/recipe-frontmatter.ts.
"""

from dataclasses import dataclass
from typing import Any, Literal, Optional

import yaml

DeliveryMode = Literal["none", "announce"]


@dataclass(frozen=True)
class CronJobSpec:
    id: str
    schedule: str
    message: str
    name: Optional[str] = None
    description: Optional[str] = None
    timezone: Optional[str] = None
    channel: Optional[str] = None
    to: Optional[str] = None
    agent_id: Optional[str] = None
    enabled_by_default: bool = False
    delivery: Optional[DeliveryMode] = None
    timeout_seconds: Optional[int] = None


# Recipe frontmatter is a free-form dict (recipes can add custom keys); the
# typed surface here matches what the rest of the package actually reads.
RecipeFrontmatter = dict[str, Any]


def parse_frontmatter(md: str) -> tuple[RecipeFrontmatter, str]:
    """Parse YAML frontmatter and body from a recipe markdown string.

    Raises ValueError if the frontmatter is missing or has no `id` field.
    """
    if not md.startswith("---\n"):
        raise ValueError("Recipe markdown must start with YAML frontmatter (---)")
    end = md.find("\n---\n", 4)
    if end == -1:
        raise ValueError("Recipe frontmatter not terminated (---)")
    yaml_text = md[4:end]
    body = md[end + 5 :]
    frontmatter = yaml.safe_load(yaml_text)
    if not isinstance(frontmatter, dict):
        raise ValueError("Recipe frontmatter must be a YAML mapping")
    if not frontmatter.get("id"):
        raise ValueError("Recipe frontmatter must include id")
    return frontmatter, body


def _coerce_optional_str(value: Any) -> Optional[str]:
    return str(value) if value is not None else None


def _validate_cron_input(raw: Any) -> tuple[str, str, str]:
    if not isinstance(raw, dict):
        raise ValueError("cronJobs entries must be objects")
    job_id = str(raw.get("id") or "").strip()
    if not job_id:
        raise ValueError("cronJobs[].id is required")
    schedule = str(raw.get("schedule") or "").strip()
    message = str(
        raw.get("message") or raw.get("task") or raw.get("prompt") or ""
    ).strip()
    if not schedule:
        raise ValueError(f"cronJobs[{job_id}].schedule is required")
    if not message:
        raise ValueError(f"cronJobs[{job_id}].message is required")
    return job_id, schedule, message


def _build_cron_spec(raw: dict[str, Any], job_id: str, schedule: str, message: str) -> CronJobSpec:
    delivery_raw = raw.get("delivery")
    delivery: Optional[DeliveryMode] = (
        delivery_raw if delivery_raw in ("none", "announce") else None
    )
    timeout_raw = raw.get("timeoutSeconds")
    timeout = (
        int(timeout_raw)
        if isinstance(timeout_raw, (int, float)) and timeout_raw > 0
        else None
    )
    return CronJobSpec(
        id=job_id,
        schedule=schedule,
        message=message,
        name=_coerce_optional_str(raw.get("name")),
        description=_coerce_optional_str(raw.get("description")),
        timezone=_coerce_optional_str(raw.get("timezone")),
        channel=_coerce_optional_str(raw.get("channel")),
        to=_coerce_optional_str(raw.get("to")),
        agent_id=_coerce_optional_str(raw.get("agentId")),
        enabled_by_default=bool(raw.get("enabledByDefault") or False),
        delivery=delivery,
        timeout_seconds=timeout,
    )


def normalize_cron_jobs(frontmatter: dict[str, Any]) -> list[CronJobSpec]:
    """Normalize and validate the `cronJobs` array from a recipe frontmatter.

    Accepts the legacy `task` and `prompt` keys as fallbacks for `message`.
    Raises ValueError on duplicate ids, missing required fields, or a non-list
    `cronJobs` value.
    """
    raw = frontmatter.get("cronJobs")
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("frontmatter.cronJobs must be an array")

    seen: set[str] = set()
    out: list[CronJobSpec] = []
    for entry in raw:
        job_id, schedule, message = _validate_cron_input(entry)
        if job_id in seen:
            raise ValueError(f"Duplicate cronJobs[].id: {job_id}")
        seen.add(job_id)
        out.append(_build_cron_spec(entry, job_id, schedule, message))
    return out
