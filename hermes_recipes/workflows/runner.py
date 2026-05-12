"""Workflow run lifecycle: enqueue + scheduler tick.

Port of clawrecipes/src/lib/workflows/workflow-runner.ts. The pull-based
scheduler functions (``enqueue_workflow_run`` + ``run_workflow_runner_once``)
are platform-neutral; ``run_workflow_once`` (which executes nodes inline) is
deferred to Phase 4c with the node executor.
"""

import json
import os
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from hermes_recipes.workflows.io import read_text_file
from hermes_recipes.workflows.queue import enqueue_task
from hermes_recipes.workflows.utils import (
    append_run_log,
    as_record,
    as_string,
    assert_lane,
    iso_compact,
    lane_to_status,
    load_run_file,
    next_ticket_number,
    normalize_workflow,
    pick_next_runnable_node_index,
    write_run_file,
)


def _now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", value, flags=re.IGNORECASE).lower()


def enqueue_workflow_run(
    *,
    team_dir: Path | str,
    team_id: str,
    workflow_file: str,
    trigger: Optional[dict[str, Any]] = None,
    trigger_input: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Create the run.json + initial ticket + run dir for a workflow.

    Does NOT call any LLM/tool — purely a file-first enqueue.
    """
    team_dir_path = Path(team_dir)
    shared = team_dir_path / "shared-context"
    workflows_dir = shared / "workflows"
    runs_dir = shared / "workflow-runs"

    workflow_path = workflows_dir / workflow_file
    workflow = normalize_workflow(json.loads(read_text_file(workflow_path)))
    if not (workflow.get("nodes") or []):
        raise ValueError("Workflow has no nodes")

    # Determine initial lane from first node that declares a lane in its config.
    first_lane = "backlog"
    for node in workflow["nodes"]:
        cfg = as_record(node.get("config"))
        if "lane" in cfg:
            first_lane = as_string(cfg["lane"]) or "backlog"
            break
    assert_lane(first_lane)
    initial_lane = first_lane

    run_id = f"{iso_compact()}-{secrets.token_hex(4)}"
    runs_dir.mkdir(parents=True, exist_ok=True)
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "node-outputs").mkdir(exist_ok=True)
    (run_dir / "artifacts").mkdir(exist_ok=True)
    (run_dir / "approvals").mkdir(exist_ok=True)

    run_log_path = run_dir / "run.json"
    ticket_num = next_ticket_number(team_dir_path)
    workflow_id_for_slug = (
        workflow.get("id")
        or Path(workflow_file).stem
    )
    slug = f"workflow-run-{_slug(str(workflow_id_for_slug))}"
    ticket_file = f"{ticket_num}-{slug}.md"

    lane_dir = team_dir_path / "work" / initial_lane
    lane_dir.mkdir(parents=True, exist_ok=True)
    ticket_path = lane_dir / ticket_file

    trigger = trigger or {"kind": "manual"}
    workflow_name = workflow.get("name") or workflow.get("id") or workflow_file
    header = f"# {ticket_num} — Workflow run: {workflow_name}\n\n"
    md_lines = [
        header,
        "Owner: lead",
        f"Status: {lane_to_status(initial_lane)}",
        "\n## Run",
        f"- workflow: {workflow_path.relative_to(team_dir_path)}",
        f"- run dir: {run_log_path.parent.relative_to(team_dir_path)}",
        f"- run file: {run_log_path.relative_to(team_dir_path)}",
        f"- trigger: {trigger.get('kind', 'manual')}"
        + (f" @ {trigger['at']}" if trigger.get("at") else ""),
        f"- runId: {run_id}",
        "\n## Notes",
        "- Created by: hermes recipes workflows run (enqueue-only)",
        "",
    ]
    md = "\n".join(md_lines)

    created_at = _now_iso()
    initial_log: dict[str, Any] = {
        "runId": run_id,
        "createdAt": created_at,
        "updatedAt": created_at,
        "teamId": team_id,
        "workflow": {
            "file": workflow_file,
            "id": workflow.get("id"),
            "name": workflow.get("name"),
        },
        "ticket": {
            "file": str(ticket_path.relative_to(team_dir_path)),
            "number": ticket_num,
            "lane": initial_lane,
        },
        "trigger": trigger,
        "status": "queued",
        "priority": 0,
        "claimedBy": None,
        "claimExpiresAt": None,
        "nextNodeIndex": 0,
        "events": [{"ts": created_at, "type": "run.enqueued", "lane": initial_lane}],
        "nodeResults": [],
    }
    if trigger_input:
        initial_log["triggerInput"] = trigger_input

    ticket_path.write_text(md, encoding="utf-8")
    run_log_path.write_text(json.dumps(initial_log, indent=2), encoding="utf-8")

    return {
        "ok": True,
        "team_id": team_id,
        "team_dir": team_dir_path,
        "workflow_path": workflow_path,
        "run_id": run_id,
        "run_log_path": run_log_path,
        "ticket_path": ticket_path,
        "lane": initial_lane,
        "status": "queued",
    }


def _load_run_candidates(runs_dir: Path) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc).timestamp()
    candidates: list[dict[str, Any]] = []
    if not runs_dir.exists():
        return candidates
    for entry in sorted(runs_dir.iterdir()):
        if not entry.is_dir():
            continue
        run_path = entry / "run.json"
        if not run_path.exists():
            continue
        try:
            run = json.loads(read_text_file(run_path))
        except (OSError, json.JSONDecodeError):
            continue
        if run.get("status") != "queued":
            continue
        exp_iso = run.get("claimExpiresAt")
        exp = (
            datetime.fromisoformat(exp_iso.replace("Z", "+00:00")).timestamp()
            if isinstance(exp_iso, str)
            else 0
        ) if exp_iso else 0
        if run.get("claimedBy") and exp > now:
            continue
        candidates.append({"file": run_path, "run": run})
    return candidates


def _sort_candidates(candidates: list[dict[str, Any]]) -> None:
    def key(c: dict[str, Any]) -> tuple[int, str]:
        pri = c["run"].get("priority") if isinstance(c["run"].get("priority"), int) else 0
        return (-pri, str(c["run"].get("createdAt") or ""))

    candidates.sort(key=key)


def run_workflow_runner_once(
    *,
    team_dir: Path | str,
    team_id: str,
    lease_seconds: float = 60.0,
    run_id: Optional[str] = None,
) -> dict[str, Any]:
    """Claim at most one queued run and enqueue its next runnable node.

    Pure scheduler: never invokes an LLM or tool. The worker module (Phase 4c)
    handles the actual node execution off the per-agent queue.
    """
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
    if run_id is not None:
        candidates = [c for c in candidates if c["file"].parent.name == run_id]
    if not candidates:
        return {
            "ok": True,
            "team_id": team_id,
            "claimed": 0,
            "message": "No queued runs available.",
        }
    _sort_candidates(candidates)
    chosen = candidates[0]

    claim_expires = (
        datetime.now(timezone.utc)
        .timestamp()
        + max(1.0, lease_seconds)
    )
    claim_expires_iso = datetime.fromtimestamp(claim_expires, tz=timezone.utc).isoformat(
        timespec="microseconds"
    ).replace("+00:00", "Z")
    runner_id = f"workflow-runner:{os.getpid()}"

    def _mark_claimed(cur: dict[str, Any]) -> dict[str, Any]:
        events = list(cur.get("events") or [])
        events.append(
            {
                "ts": _now_iso(),
                "type": "run.claimed",
                "claimedBy": runner_id,
                "claimExpiresAt": claim_expires_iso,
            }
        )
        return {
            **cur,
            "status": "running",
            "claimedBy": runner_id,
            "claimExpiresAt": claim_expires_iso,
            "events": events,
        }

    write_run_file(chosen["file"], _mark_claimed)

    workflow_file = as_string(as_record(chosen["run"]["workflow"]).get("file"))
    workflow_path = workflows_dir / workflow_file
    workflow = normalize_workflow(json.loads(read_text_file(workflow_path)))

    try:
        return _advance_run(
            team_dir=team_dir_path,
            team_id=team_id,
            runs_dir=runs_dir,
            run_path=chosen["file"],
            run_id_value=chosen["run"]["runId"],
            workflow=workflow,
        )
    except Exception as e:
        def _mark_error(cur: dict[str, Any]) -> dict[str, Any]:
            return {
                **cur,
                "status": "error",
                "claimedBy": None,
                "claimExpiresAt": None,
                "events": [
                    *(cur.get("events") or []),
                    {"ts": _now_iso(), "type": "run.error", "message": str(e)},
                ],
            }

        write_run_file(chosen["file"], _mark_error)
        raise


def _advance_run(
    *,
    team_dir: Path,
    team_id: str,
    runs_dir: Path,
    run_path: Path,
    run_id_value: str,
    workflow: dict[str, Any],
) -> dict[str, Any]:
    """Pick + enqueue the next runnable node, skipping start/end noops.

    Shared by ``run_workflow_runner_once`` and ``run_workflow_runner_tick``.
    """
    nodes = workflow.get("nodes") or []
    run_cur = load_run_file(team_dir, runs_dir, run_id_value)["run"]
    idx = pick_next_runnable_node_index(workflow=workflow, run=run_cur)

    while idx is not None:
        node = as_record(nodes[idx])
        kind = as_string(node.get("kind"))
        if kind not in ("start", "end"):
            break
        ts = _now_iso()

        def _skip_noop(cur: dict[str, Any], i=idx, n=node, k=kind, t=ts) -> dict[str, Any]:
            return {
                **cur,
                "nextNodeIndex": i + 1,
                "nodeStates": {
                    **as_record(cur.get("nodeStates")),
                    n.get("id"): {"status": "success", "ts": t},
                },
                "events": [
                    *(cur.get("events") or []),
                    {"ts": t, "type": "node.completed", "nodeId": n.get("id"), "kind": k, "noop": True},
                ],
                "nodeResults": [
                    *(cur.get("nodeResults") or []),
                    {"nodeId": n.get("id"), "kind": k, "noop": True},
                ],
            }

        append_run_log(run_path, _skip_noop)
        run_cur = load_run_file(team_dir, runs_dir, run_id_value)["run"]
        idx = pick_next_runnable_node_index(workflow=workflow, run=run_cur)

    if idx is None:
        def _complete(cur: dict[str, Any]) -> dict[str, Any]:
            return {
                **cur,
                "status": "completed",
                "claimedBy": None,
                "claimExpiresAt": None,
                "events": [*(cur.get("events") or []), {"ts": _now_iso(), "type": "run.completed"}],
            }

        write_run_file(run_path, _complete)
        return {
            "ok": True,
            "team_id": team_id,
            "claimed": 1,
            "run_id": run_id_value,
            "status": "completed",
        }

    node = as_record(nodes[idx])
    assigned_agent_id = as_string(as_record(node.get("assignedTo")).get("agentId")).strip()
    if not assigned_agent_id:
        raise ValueError(
            f"Node {node.get('id')} missing assignedTo.agentId (required for pull-based execution)"
        )

    enqueue_task(
        team_dir,
        assigned_agent_id,
        {
            "teamId": team_id,
            "runId": run_id_value,
            "nodeId": node.get("id"),
            "kind": "execute_node",
        },
    )

    def _waiting(cur: dict[str, Any]) -> dict[str, Any]:
        return {
            **cur,
            "status": "waiting_workers",
            "claimedBy": None,
            "claimExpiresAt": None,
            "nextNodeIndex": idx,
            "events": [
                *(cur.get("events") or []),
                {
                    "ts": _now_iso(),
                    "type": "node.enqueued",
                    "nodeId": node.get("id"),
                    "agentId": assigned_agent_id,
                },
            ],
        }

    write_run_file(run_path, _waiting)
    return {
        "ok": True,
        "team_id": team_id,
        "claimed": 1,
        "run_id": run_id_value,
        "status": "waiting_workers",
    }
