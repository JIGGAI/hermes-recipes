"""Covers hermes_recipes/workflows/approvals.py."""

import json
from pathlib import Path

import pytest

from hermes_recipes.workflows.approvals import (
    approval_path_for,
    approve_workflow_run,
    poll_workflow_approvals,
    resume_workflow_run,
)


def _seed_run(
    team_dir: Path,
    *,
    run_id: str,
    workflow: dict,
    run: dict,
    approval: dict,
) -> dict[str, Path]:
    shared = team_dir / "shared-context"
    workflows_dir = shared / "workflows"
    workflows_dir.mkdir(parents=True, exist_ok=True)
    workflow_file = "marketing.workflow.json"
    (workflows_dir / workflow_file).write_text(
        json.dumps(workflow), encoding="utf-8"
    )

    runs_dir = shared / "workflow-runs" / run_id
    runs_dir.mkdir(parents=True, exist_ok=True)
    (runs_dir / "run.json").write_text(json.dumps(run), encoding="utf-8")

    approvals_dir = runs_dir / "approvals"
    approvals_dir.mkdir()
    (approvals_dir / "approval.json").write_text(
        json.dumps(approval), encoding="utf-8"
    )

    # Ticket file referenced by the run
    ticket_path = team_dir / run["ticket"]["file"]
    ticket_path.parent.mkdir(parents=True, exist_ok=True)
    ticket_path.write_text(
        "# Ticket\nStatus: in-progress\nOwner: dev\n", encoding="utf-8"
    )
    return {"runs_dir": runs_dir, "approval_path": approvals_dir / "approval.json"}


def test_approval_path_for_uses_canonical_layout(tmp_path):
    p = approval_path_for(tmp_path, "run-abc")
    assert p == (
        tmp_path
        / "shared-context"
        / "workflow-runs"
        / "run-abc"
        / "approvals"
        / "approval.json"
    )


def test_approve_workflow_run_patches_status(tmp_path):
    approval = approval_path_for(tmp_path, "run-1")
    approval.parent.mkdir(parents=True)
    approval.write_text(
        json.dumps({"runId": "run-1", "status": "pending", "nodeId": "n1"}),
        encoding="utf-8",
    )
    res = approve_workflow_run(team_dir=tmp_path, run_id="run-1", approved=True)
    assert res.status == "approved"
    data = json.loads(approval.read_text(encoding="utf-8"))
    assert data["status"] == "approved"
    assert "decidedAt" in data


def test_approve_workflow_run_rejects_with_note(tmp_path):
    approval = approval_path_for(tmp_path, "run-1")
    approval.parent.mkdir(parents=True)
    approval.write_text(
        json.dumps({"runId": "run-1", "status": "pending", "nodeId": "n1"}),
        encoding="utf-8",
    )
    res = approve_workflow_run(
        team_dir=tmp_path,
        run_id="run-1",
        approved=False,
        note="Tighten the hook",
    )
    data = json.loads(approval.read_text(encoding="utf-8"))
    assert res.status == "rejected"
    assert data["note"] == "Tighten the hook"


def test_approve_workflow_run_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError, match="Approval file not found"):
        approve_workflow_run(team_dir=tmp_path, run_id="missing", approved=True)


def test_resume_workflow_run_approved_path_enqueues_next_node(tmp_path):
    workflow = {
        "id": "wf",
        "nodes": [
            {"id": "draft_assets", "kind": "llm", "assignedTo": {"agentId": "lead"}},
            {"id": "approve", "kind": "human_approval"},
            {"id": "post", "kind": "tool", "assignedTo": {"agentId": "dev"}, "action": {"tool": "publish"}},
        ],
        "edges": [
            {"from": "draft_assets", "to": "approve"},
            {"from": "approve", "to": "post"},
        ],
    }
    run = {
        "runId": "run-x",
        "teamId": "team-a",
        "workflow": {"file": "marketing.workflow.json"},
        "ticket": {"file": "work/in-progress/0001-x.md"},
        "status": "awaiting_approval",
        "events": [
            {"ts": "t0", "type": "node.completed", "nodeId": "draft_assets"},
            {"ts": "t1", "type": "node.awaiting_approval", "nodeId": "approve"},
        ],
        "nodeStates": {
            "draft_assets": {"status": "success", "ts": "t0"},
            "approve": {"status": "waiting", "ts": "t1"},
        },
    }
    approval = {"runId": "run-x", "status": "approved", "nodeId": "approve"}
    _seed_run(tmp_path, run_id="run-x", workflow=workflow, run=run, approval=approval)

    enqueued: list[tuple] = []
    res = resume_workflow_run(
        team_dir=tmp_path,
        team_id="team-a",
        run_id="run-x",
        enqueue_task=lambda d, a, p: enqueued.append((d, a, p)),
    )
    assert res["status"] == "waiting_workers"
    assert len(enqueued) == 1
    _, agent_id, packet = enqueued[0]
    assert agent_id == "dev"
    assert packet["nodeId"] == "post"


def test_resume_workflow_run_rejected_path_loops_back(tmp_path):
    workflow = {
        "id": "wf",
        "nodes": [
            {"id": "draft_assets", "kind": "llm", "assignedTo": {"agentId": "lead"}},
            {"id": "approve", "kind": "human_approval"},
            {"id": "post", "kind": "tool", "assignedTo": {"agentId": "dev"}},
        ],
        "edges": [
            {"from": "draft_assets", "to": "approve"},
            {"from": "approve", "to": "post"},
        ],
    }
    run = {
        "runId": "run-y",
        "teamId": "team-a",
        "workflow": {"file": "marketing.workflow.json"},
        "ticket": {"file": "work/in-progress/0001-y.md"},
        "status": "awaiting_approval",
        "events": [{"ts": "t0", "type": "node.completed", "nodeId": "draft_assets"}],
        "nodeStates": {"draft_assets": {"status": "success", "ts": "t0"}},
    }
    approval = {
        "runId": "run-y",
        "status": "rejected",
        "nodeId": "approve",
        "note": "Try again",
    }
    _seed_run(tmp_path, run_id="run-y", workflow=workflow, run=run, approval=approval)

    enqueued: list[tuple] = []
    res = resume_workflow_run(
        team_dir=tmp_path,
        team_id="team-a",
        run_id="run-y",
        enqueue_task=lambda d, a, p: enqueued.append((d, a, p)),
    )
    assert res["status"] == "needs_revision"
    assert len(enqueued) == 1
    _, agent_id, packet = enqueued[0]
    assert agent_id == "lead"
    assert packet["nodeId"] == "draft_assets"
    assert packet["packet"] == {"revisionNote": "Try again"}


def test_poll_workflow_approvals_skips_pending_and_resumes_decided(tmp_path):
    workflow = {
        "id": "wf",
        "nodes": [
            {"id": "approve", "kind": "human_approval"},
            {"id": "post", "kind": "tool", "assignedTo": {"agentId": "dev"}},
        ],
    }
    run_pending = {
        "runId": "run-a",
        "teamId": "team-a",
        "workflow": {"file": "marketing.workflow.json"},
        "ticket": {"file": "work/in-progress/0001-a.md"},
        "status": "awaiting_approval",
        "events": [],
        "nodeStates": {},
    }
    run_decided = {
        "runId": "run-b",
        "teamId": "team-a",
        "workflow": {"file": "marketing.workflow.json"},
        "ticket": {"file": "work/in-progress/0001-b.md"},
        "status": "awaiting_approval",
        "events": [],
        "nodeStates": {},
    }
    _seed_run(
        tmp_path,
        run_id="run-a",
        workflow=workflow,
        run=run_pending,
        approval={"runId": "run-a", "status": "pending", "nodeId": "approve"},
    )
    _seed_run(
        tmp_path,
        run_id="run-b",
        workflow=workflow,
        run=run_decided,
        approval={"runId": "run-b", "status": "approved", "nodeId": "approve"},
    )

    enqueued: list[tuple] = []
    res = poll_workflow_approvals(
        team_dir=tmp_path,
        team_id="team-a",
        enqueue_task=lambda d, a, p: enqueued.append((d, a, p)),
    )
    assert res["polled"] == 2
    assert res["resumed"] == 1
    assert res["skipped"] == 1
    assert len(enqueued) == 1


def test_poll_workflow_approvals_returns_empty_when_no_runs(tmp_path):
    res = poll_workflow_approvals(
        team_dir=tmp_path, team_id="team-x", enqueue_task=lambda *_: None
    )
    assert res["polled"] == 0
    assert "No workflow-runs directory" in res["message"]
