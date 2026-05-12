"""Cron mapping state + spec hashing.

Port of clawrecipes/src/lib/cron-utils.ts. ``CronMappingState`` is the per-team
or per-agent state file that maps each declared cronJob id to the installed
cron-system id plus a spec hash, so re-scaffolding can detect drift and
disable orphans.
"""

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Optional

from hermes_recipes.stable_stringify import stable_stringify


@dataclass(frozen=True)
class CronMappingEntry:
    installed_cron_id: str
    spec_hash: str
    updated_at_ms: int
    orphaned: bool = False


def load_cron_mapping_state(state_path: Path | str) -> dict[str, CronMappingEntry]:
    """Load a ``cron-jobs.json`` mapping file or return an empty mapping."""
    p = Path(state_path)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict) or data.get("version") != 1:
        return {}
    entries = data.get("entries")
    if not isinstance(entries, dict):
        return {}
    out: dict[str, CronMappingEntry] = {}
    for key, raw in entries.items():
        if not isinstance(raw, dict):
            continue
        cron_id = raw.get("installedCronId")
        spec_hash = raw.get("specHash")
        updated_at = raw.get("updatedAtMs")
        if not isinstance(cron_id, str) or not isinstance(spec_hash, str):
            continue
        out[str(key)] = CronMappingEntry(
            installed_cron_id=cron_id,
            spec_hash=spec_hash,
            updated_at_ms=int(updated_at) if isinstance(updated_at, int) else 0,
            orphaned=bool(raw.get("orphaned") or False),
        )
    return out


def save_cron_mapping_state(state_path: Path | str, entries: dict[str, CronMappingEntry]) -> None:
    p = Path(state_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "entries": {
            key: {
                "installedCronId": e.installed_cron_id,
                "specHash": e.spec_hash,
                "updatedAtMs": e.updated_at_ms,
                "orphaned": e.orphaned,
            }
            for key, e in entries.items()
        },
    }
    p.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


ScopeKind = Literal["team", "agent"]


@dataclass(frozen=True)
class CronScope:
    kind: ScopeKind
    recipe_id: str
    state_dir: Path
    team_id: Optional[str] = None
    agent_id: Optional[str] = None

    def template_vars(self) -> dict[str, str]:
        out: dict[str, str] = {"recipeId": self.recipe_id}
        if self.kind == "team" and self.team_id is not None:
            out["teamId"] = self.team_id
        elif self.kind == "agent" and self.agent_id is not None:
            out["agentId"] = self.agent_id
        return out


def cron_key(scope: CronScope, cron_job_id: str) -> str:
    if scope.kind == "team":
        if scope.team_id is None:
            raise ValueError("team scope requires team_id")
        return f"team:{scope.team_id}:recipe:{scope.recipe_id}:cron:{cron_job_id}"
    if scope.agent_id is None:
        raise ValueError("agent scope requires agent_id")
    return f"agent:{scope.agent_id}:recipe:{scope.recipe_id}:cron:{cron_job_id}"


def hash_spec(spec: Any) -> str:
    """Stable SHA-256 of a JSON-serializable value."""
    return hashlib.sha256(stable_stringify(spec).encode("utf-8")).hexdigest()


def parse_tool_text_json(text: str | None, label: str) -> Any:
    """Parse JSON emitted by a tool, raising with a labelled message on failure."""
    trimmed = (text or "").strip()
    if not trimmed:
        return None
    try:
        return json.loads(trimmed)
    except json.JSONDecodeError as e:
        err = ValueError(f"Failed parsing JSON from tool text ({label})")
        err.__cause__ = e
        raise err
