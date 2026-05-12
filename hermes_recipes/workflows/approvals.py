"""Approval-record lifecycle: approve / reject / poll / resume.

Port of clawrecipes/src/lib/workflows/workflow-approvals.ts. The TS module
imports the queue's ``enqueueTask`` directly; here we keep ``approvals`` free
of the queue dependency by accepting an ``enqueue_task`` callback. Phase 4b
wires the real implementation; tests inject a fake.
"""

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from hermes_recipes.workflows.io import read_json_file, read_text_file
from hermes_recipes.workflows.utils import (
    append_run_log,
    as_record,
    as_string,
    load_run_file,
    normalize_workflow,
    pick_next_runnable_node_index,
    write_run_file,
)


EnqueueTaskFn = Callable[[Path, str, dict[str, Any]], None]


def _now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def approval_path_for(team_dir: Path | str, run_id: str) -> Path:
    return (
        Path(team_dir)
        / "shared-context"
        / "workflow-runs"
        / run_id
        / "approvals"
        / "approval.json"
    )


@dataclass(frozen=True)
class ApproveResult:
    run_id: str
    status: str
    approval_file: Path


def approve_workflow_run(
    *,
    team_dir: Path | str,
    run_id: str,
    approved: bool,
    note: Optional[str] = None,
) -> ApproveResult:
    """Patch an approval record to ``approved`` or ``rejected``."""
    approval_file = approval_path_for(team_dir, run_id)
    if not approval_file.exists():
        rel = approval_file.relative_to(Path(team_dir)) if str(approval_file).startswith(str(team_dir)) else approval_file
        raise FileNotFoundError(f"Approval file not found for runId={run_id}: {rel}")
    cur = json.loads(read_text_file(approval_file))
    next_record = {
        **cur,
        "status": "approved" if approved else "rejected",
        "decidedAt": _now_iso(),
    }
    if note:
        next_record["note"] = str(note)
    approval_file.write_text(json.dumps(next_record, indent=2), encoding="utf-8")
    return ApproveResult(run_id=run_id, status=next_record["status"], approval_file=approval_file)


def _find_revise_idx(workflow: dict[str, Any], approval_idx: int) -> int:
    nodes = workflow.get("nodes") or []
    # 1) explicit node id "draft_assets" prior to approval
    for idx, node in enumerate(nodes):
        if idx < approval_idx and as_string(as_record(node).get("id")) == "draft_assets":
            return idx
    # 2) closest prior llm node
    for i in range(approval_idx - 1, -1, -1):
        if as_string(as_record(nodes[i]).get("kind")) == "llm":
            return i
    return 0


def resume_workflow_run(
    *,
    team_dir: Path | str,
    team_id: str,
    run_id: str,
    enqueue_task: EnqueueTaskFn,
) -> dict[str, Any]:
    """Re-enter a paused run after the approval record was patched.

    The caller supplies ``enqueue_task(team_dir, agent_id, packet)`` — the
    workflow-queue implementation lives in Phase 4b.
    """
    base = Path(team_dir)
    shared = base / "shared-context"
    runs_dir = shared / "workflow-runs"
    workflows_dir = shared / "workflows"

    loaded = load_run_file(base, runs_dir, run_id)
    run_log_path = loaded["path"]
    run_log = loaded["run"]

    if run_log.get("status") in ("completed", "rejected"):
        return {
            "ok": True,
            "run_id": run_id,
            "status": run_log["status"],
            "message": "No-op; run already finished.",
        }
    if run_log.get("status") not in ("awaiting_approval", "running"):
        raise ValueError(f"Run is not awaiting approval (status={run_log.get('status')}).")

    workflow_file = as_string(as_record(run_log.get("workflow")).get("file"))
    workflow_path = workflows_dir / workflow_file
    workflow = normalize_workflow(json.loads(read_text_file(workflow_path)))

    approval_file = approval_path_for(team_dir, run_id)
    if not approval_file.exists():
        rel = approval_file.relative_to(base)
        raise FileNotFoundError(f"Missing approval file: {rel}")
    approval = json.loads(read_text_file(approval_file))
    if approval.get("status") == "pending":
        rel = approval_file.relative_to(base)
        raise ValueError(f"Approval still pending. Update {rel} first.")

    ticket_path = base / as_string(as_record(run_log.get("ticket")).get("file"))

    nodes = workflow.get("nodes") or []
    approval_node_id = as_string(approval.get("nodeId"))
    approval_idx = next(
        (
            i
            for i, node in enumerate(nodes)
            if as_string(as_record(node).get("kind")) == "human_approval"
            and as_string(as_record(node).get("id")) == approval_node_id
        ),
        -1,
    )
    if approval_idx < 0:
        raise ValueError(f"Approval node not found in workflow: nodeId={approval_node_id}")

    if approval.get("status") == "rejected":
        return _handle_rejected(
            team_dir=base,
            team_id=team_id,
            run_id=run_id,
            run_log_path=run_log_path,
            workflow=workflow,
            approval=approval,
            approval_idx=approval_idx,
            ticket_path=ticket_path,
            enqueue_task=enqueue_task,
        )

    return _handle_approved(
        team_dir=base,
        team_id=team_id,
        run_id=run_id,
        runs_dir=runs_dir,
        run_log_path=run_log_path,
        workflow=workflow,
        approval=approval,
        ticket_path=ticket_path,
        enqueue_task=enqueue_task,
    )


def _handle_rejected(
    *,
    team_dir: Path,
    team_id: str,
    run_id: str,
    run_log_path: Path,
    workflow: dict[str, Any],
    approval: dict[str, Any],
    approval_idx: int,
    ticket_path: Path,
    enqueue_task: EnqueueTaskFn,
) -> dict[str, Any]:
    approval_note = as_string(approval.get("note")).strip()
    revise_idx = _find_revise_idx(workflow, approval_idx)
    nodes = workflow.get("nodes") or []
    revise_node = as_record(nodes[revise_idx])
    revise_agent_id = as_string(as_record(revise_node.get("assignedTo")).get("agentId")).strip()
    if not revise_agent_id:
        raise ValueError(f"Revision node {revise_node.get('id')} missing assignedTo.agentId")

    now = _now_iso()

    def _patch(cur: dict[str, Any]) -> dict[str, Any]:
        node_states = {
            **as_record(cur.get("nodeStates")),
            approval["nodeId"]: {"status": "error", "ts": now, "message": "rejected"},
        }
        for i in range(revise_idx, len(nodes)):
            nid = as_string(as_record(nodes[i]).get("id")).strip()
            node_states.pop(nid, None)
        new_event = {
            "ts": now,
            "type": "run.revision_requested",
            "nodeId": approval["nodeId"],
            "reviseNodeId": revise_node.get("id"),
            "reviseAgentId": revise_agent_id,
        }
        if approval_note:
            new_event["note"] = approval_note
        return {
            **cur,
            "updatedAt": now,
            "status": "needs_revision",
            "nextNodeIndex": revise_idx,
            "nodeStates": node_states,
            "events": [*(cur.get("events") or []), new_event],
        }

    write_run_file(run_log_path, _patch)

    # Best-effort lock cleanup so the revision can actually re-run.
    lock_dir = Path(run_log_path).parent / "locks"
    if lock_dir.exists():
        for i in range(revise_idx, len(nodes)):
            nid = as_string(as_record(nodes[i]).get("id")).strip()
            if not nid:
                continue
            lock_file = lock_dir / f"{nid}.lock"
            try:
                lock_file.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                pass

    packet: dict[str, Any] = {
        "teamId": team_id,
        "runId": run_id,
        "nodeId": revise_node.get("id"),
        "kind": "execute_node",
    }
    if approval_note:
        packet["packet"] = {"revisionNote": approval_note}
    enqueue_task(team_dir, revise_agent_id, packet)

    return {
        "ok": True,
        "run_id": run_id,
        "status": "needs_revision",
        "ticket_path": ticket_path,
        "run_log_path": run_log_path,
    }


def _handle_approved(
    *,
    team_dir: Path,
    team_id: str,
    run_id: str,
    runs_dir: Path,
    run_log_path: Path,
    workflow: dict[str, Any],
    approval: dict[str, Any],
    ticket_path: Path,
    enqueue_task: EnqueueTaskFn,
) -> dict[str, Any]:
    approved_ts = _now_iso()

    def _mark_approved(cur: dict[str, Any]) -> dict[str, Any]:
        events = cur.get("events") or []
        already_recorded = any(
            as_string(as_record(ev).get("type")) == "node.approved"
            and as_string(as_record(ev).get("nodeId")) == as_string(approval["nodeId"])
            for ev in events
        )
        next_events = (
            events
            if already_recorded
            else [*events, {"ts": approved_ts, "type": "node.approved", "nodeId": approval["nodeId"]}]
        )
        return {
            **cur,
            "status": "running",
            "nodeStates": {
                **as_record(cur.get("nodeStates")),
                approval["nodeId"]: {"status": "success", "ts": approved_ts},
            },
            "events": next_events,
        }

    append_run_log(run_log_path, _mark_approved)

    nodes = workflow.get("nodes") or []
    updated = load_run_file(team_dir, runs_dir, run_id)["run"]
    enqueue_idx = pick_next_runnable_node_index(workflow=workflow, run=updated)

    # Auto-skip start/end markers.
    while enqueue_idx is not None:
        node = as_record(nodes[enqueue_idx])
        kind = as_string(node.get("kind"))
        if kind not in ("start", "end"):
            break
        ts = _now_iso()

        def _skip_noop(cur: dict[str, Any], idx=enqueue_idx, n=node, k=kind, t=ts) -> dict[str, Any]:
            return {
                **cur,
                "nextNodeIndex": idx + 1,
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

        append_run_log(run_log_path, _skip_noop)
        updated = load_run_file(team_dir, runs_dir, run_id)["run"]
        enqueue_idx = pick_next_runnable_node_index(workflow=workflow, run=updated)

    if enqueue_idx is None:
        now = _now_iso()

        def _complete(cur: dict[str, Any]) -> dict[str, Any]:
            return {
                **cur,
                "updatedAt": now,
                "status": "completed",
                "events": [*(cur.get("events") or []), {"ts": now, "type": "run.completed"}],
            }

        write_run_file(run_log_path, _complete)
        return {
            "ok": True,
            "run_id": run_id,
            "status": "completed",
            "ticket_path": ticket_path,
            "run_log_path": run_log_path,
        }

    next_node = as_record(nodes[enqueue_idx])
    next_kind = as_string(next_node.get("kind"))
    next_agent_id = as_string(as_record(next_node.get("assignedTo")).get("agentId")).strip()
    if not next_agent_id:
        raise ValueError(
            f"Next runnable node {next_node.get('id')} ({next_kind}) missing "
            "assignedTo.agentId (required for pull-based execution)"
        )

    enqueue_task(
        team_dir,
        next_agent_id,
        {
            "teamId": team_id,
            "runId": run_id,
            "nodeId": next_node.get("id"),
            "kind": "execute_node",
        },
    )

    def _mark_waiting(cur: dict[str, Any]) -> dict[str, Any]:
        return {
            **cur,
            "updatedAt": _now_iso(),
            "status": "waiting_workers",
            "nextNodeIndex": enqueue_idx,
            "events": [
                *(cur.get("events") or []),
                {
                    "ts": _now_iso(),
                    "type": "node.enqueued",
                    "nodeId": next_node.get("id"),
                    "agentId": next_agent_id,
                },
            ],
        }

    write_run_file(run_log_path, _mark_waiting)

    return {
        "ok": True,
        "run_id": run_id,
        "status": "waiting_workers",
        "ticket_path": ticket_path,
        "run_log_path": run_log_path,
    }


def poll_workflow_approvals(
    *,
    team_dir: Path | str,
    team_id: str,
    enqueue_task: EnqueueTaskFn,
    limit: Optional[int] = None,
) -> dict[str, Any]:
    base = Path(team_dir)
    runs_dir = base / "shared-context" / "workflow-runs"
    if not runs_dir.exists():
        return {
            "ok": True,
            "team_id": team_id,
            "polled": 0,
            "resumed": 0,
            "skipped": 0,
            "message": "No workflow-runs directory present.",
        }

    approval_paths: list[Path] = []
    for entry in sorted(runs_dir.iterdir()):
        p = entry / "approvals" / "approval.json"
        if p.exists():
            approval_paths.append(p)
    if limit is not None and limit > 0:
        approval_paths = approval_paths[:limit]
    if not approval_paths:
        return {
            "ok": True,
            "team_id": team_id,
            "polled": 0,
            "resumed": 0,
            "skipped": 0,
            "message": "No approval records present.",
        }

    resumed = 0
    skipped = 0
    results: list[dict[str, Any]] = []
    for approval_path in approval_paths:
        try:
            approval = read_json_file(approval_path)
        except (OSError, json.JSONDecodeError) as e:
            skipped += 1
            results.append(
                {
                    "run_id": approval_path.parent.parent.name,
                    "status": "unknown",
                    "action": "error",
                    "message": f"Failed to parse: {e}",
                }
            )
            continue

        if approval.get("status") == "pending":
            skipped += 1
            results.append(
                {"run_id": approval["runId"], "status": approval["status"], "action": "skipped"}
            )
            continue
        if approval.get("resumedAt"):
            skipped += 1
            results.append(
                {
                    "run_id": approval["runId"],
                    "status": approval["status"],
                    "action": "skipped",
                    "message": "Already resumed.",
                }
            )
            continue

        try:
            res = resume_workflow_run(
                team_dir=base,
                team_id=team_id,
                run_id=approval["runId"],
                enqueue_task=enqueue_task,
            )
            resumed += 1
            results.append(
                {
                    "run_id": approval["runId"],
                    "status": approval["status"],
                    "action": "resumed",
                    "message": f"resume status={res.get('status', 'ok')}",
                }
            )
            next_record = {
                **approval,
                "resumedAt": _now_iso(),
                "resumedStatus": str(res.get("status", "ok")),
            }
            approval_path.write_text(json.dumps(next_record, indent=2), encoding="utf-8")
        except Exception as e:
            results.append(
                {
                    "run_id": approval["runId"],
                    "status": approval["status"],
                    "action": "error",
                    "message": str(e),
                }
            )
            next_record = {
                **approval,
                "resumedAt": _now_iso(),
                "resumedStatus": "error",
                "resumeError": str(e),
            }
            approval_path.write_text(json.dumps(next_record, indent=2), encoding="utf-8")

    return {
        "ok": True,
        "team_id": team_id,
        "polled": len(approval_paths),
        "resumed": resumed,
        "skipped": skipped,
        "results": results,
    }
