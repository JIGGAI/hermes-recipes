"""Concurrent runner tick — claim up to N queued runs and enqueue their next nodes.

Port of clawrecipes/src/lib/workflows/workflow-tick.ts. Reuses the
``_advance_run`` helper from ``runner.py`` so the per-run logic stays in one
place.
"""

import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from hermes_recipes.workflows.io import read_text_file
from hermes_recipes.workflows.runner import _advance_run, _load_run_candidates, _sort_candidates
from hermes_recipes.workflows.utils import normalize_workflow, write_run_file


def _now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _try_claim(run_path: Path, *, lease_seconds: float, runner_id_base: str) -> Optional[dict[str, Any]]:
    raw = read_text_file(run_path)
    cur = json.loads(raw)
    if cur.get("status") != "queued":
        return None
    exp_iso = cur.get("claimExpiresAt")
    exp = (
        datetime.fromisoformat(exp_iso.replace("Z", "+00:00")).timestamp()
        if isinstance(exp_iso, str)
        else 0
    ) if exp_iso else 0
    if cur.get("claimedBy") and exp > datetime.now(timezone.utc).timestamp():
        return None

    claim_expires = datetime.now(timezone.utc).timestamp() + lease_seconds
    claim_expires_iso = (
        datetime.fromtimestamp(claim_expires, tz=timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )
    claimed_by = f"{runner_id_base}:{secrets.token_hex(3)}"
    next_log = {
        **cur,
        "updatedAt": _now_iso(),
        "status": "running",
        "claimedBy": claimed_by,
        "claimExpiresAt": claim_expires_iso,
        "events": [
            *(cur.get("events") or []),
            {
                "ts": _now_iso(),
                "type": "run.claimed",
                "claimedBy": claimed_by,
                "claimExpiresAt": claim_expires_iso,
            },
        ],
    }
    run_path.write_text(json.dumps(next_log, indent=2), encoding="utf-8")
    return next_log


def run_workflow_runner_tick(
    *,
    team_dir: Path | str,
    team_id: str,
    concurrency: int = 1,
    lease_seconds: float = 300.0,
) -> dict[str, Any]:
    team_dir_path = Path(team_dir)
    shared = team_dir_path / "shared-context"
    runs_dir = shared / "workflow-runs"
    workflows_dir = shared / "workflows"

    if not runs_dir.exists():
        return {
            "ok": True,
            "team_id": team_id,
            "claimed": 0,
            "message": "No workflow-runs directory present.",
        }

    candidates = _load_run_candidates(runs_dir)
    if not candidates:
        return {
            "ok": True,
            "team_id": team_id,
            "claimed": 0,
            "message": "No queued runs available.",
        }
    _sort_candidates(candidates)

    runner_id_base = f"workflow-runner:{os.getpid()}"
    cap = max(1, int(concurrency))
    claimed: list[dict[str, Any]] = []
    for c in candidates:
        if len(claimed) >= cap:
            break
        result = _try_claim(c["file"], lease_seconds=lease_seconds, runner_id_base=runner_id_base)
        if result is not None:
            claimed.append({"file": c["file"], "run": result})

    if not claimed:
        return {
            "ok": True,
            "team_id": team_id,
            "claimed": 0,
            "message": "No queued runs available (raced on claim).",
        }

    results: list[dict[str, Any]] = []
    for c in claimed:
        workflow_path = workflows_dir / c["run"]["workflow"]["file"]
        workflow = normalize_workflow(json.loads(read_text_file(workflow_path)))
        try:
            results.append(
                _advance_run(
                    team_dir=team_dir_path,
                    team_id=team_id,
                    runs_dir=runs_dir,
                    run_path=c["file"],
                    run_id_value=c["run"]["runId"],
                    workflow=workflow,
                )
            )
        except Exception as e:
            def _mark_error(cur: dict[str, Any], err=e) -> dict[str, Any]:
                return {
                    **cur,
                    "status": "error",
                    "claimedBy": None,
                    "claimExpiresAt": None,
                    "events": [
                        *(cur.get("events") or []),
                        {"ts": _now_iso(), "type": "run.error", "message": str(err)},
                    ],
                }

            write_run_file(c["file"], _mark_error)
            results.append({"run_id": c["run"]["runId"], "status": "error", "error": str(e)})

    return {"ok": True, "team_id": team_id, "claimed": len(claimed), "results": results}
