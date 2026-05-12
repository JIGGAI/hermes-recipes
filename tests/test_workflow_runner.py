"""Covers hermes_recipes/workflows/runner.py."""

import json
from pathlib import Path

import pytest

from hermes_recipes.workflows.queue import queue_path_for
from hermes_recipes.workflows.runner import (
    enqueue_workflow_run,
    run_workflow_runner_once,
)
from hermes_recipes.workflows.tick import run_workflow_runner_tick


def _seed_workflow(
    team_dir: Path, workflow_name: str = "marketing.workflow.json"
) -> Path:
    workflows_dir = team_dir / "shared-context" / "workflows"
    workflows_dir.mkdir(parents=True)
    workflow = {
        "id": "marketing-cadence-v1",
        "name": "Marketing cadence",
        "nodes": [
            {"id": "start", "kind": "start"},
            {
                "id": "draft",
                "kind": "llm",
                "assignedTo": {"agentId": "team-lead"},
                "action": {},
            },
            {
                "id": "post",
                "kind": "tool",
                "assignedTo": {"agentId": "team-dev"},
                "action": {"tool": "publish"},
            },
            {"id": "end", "kind": "end"},
        ],
        "edges": [
            {"from": "start", "to": "draft"},
            {"from": "draft", "to": "post"},
            {"from": "post", "to": "end"},
        ],
    }
    path = workflows_dir / workflow_name
    path.write_text(json.dumps(workflow), encoding="utf-8")
    return path


def test_enqueue_workflow_run_writes_ticket_and_run_log(tmp_path):
    _seed_workflow(tmp_path)
    result = enqueue_workflow_run(
        team_dir=tmp_path,
        team_id="dev-team",
        workflow_file="marketing.workflow.json",
    )
    assert result["status"] == "queued"
    assert result["run_log_path"].exists()
    run = json.loads(result["run_log_path"].read_text(encoding="utf-8"))
    assert run["status"] == "queued"
    assert run["events"][0]["type"] == "run.enqueued"
    assert result["ticket_path"].exists()
    md = result["ticket_path"].read_text(encoding="utf-8")
    assert "Workflow run: Marketing cadence" in md


def test_enqueue_workflow_run_rejects_empty_workflow(tmp_path):
    workflows_dir = tmp_path / "shared-context" / "workflows"
    workflows_dir.mkdir(parents=True)
    (workflows_dir / "empty.workflow.json").write_text(
        json.dumps({"id": "empty", "nodes": []}), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="no nodes"):
        enqueue_workflow_run(
            team_dir=tmp_path, team_id="dev-team", workflow_file="empty.workflow.json"
        )


def test_runner_once_claims_and_enqueues_first_executable_node(tmp_path):
    _seed_workflow(tmp_path)
    enqueue_workflow_run(
        team_dir=tmp_path, team_id="dev-team", workflow_file="marketing.workflow.json"
    )

    result = run_workflow_runner_once(team_dir=tmp_path, team_id="dev-team")
    assert result["claimed"] == 1
    assert result["status"] == "waiting_workers"

    # Queue file for team-lead should now contain a single execute_node task.
    qpath = queue_path_for(tmp_path, "team-lead")
    lines = [
        json.loads(l)
        for l in qpath.read_text(encoding="utf-8").splitlines()
        if l.strip()
    ]
    assert len(lines) == 1
    assert lines[0]["nodeId"] == "draft"
    assert lines[0]["runId"] == result["run_id"]


def test_runner_once_returns_zero_when_no_queue(tmp_path):
    result = run_workflow_runner_once(team_dir=tmp_path, team_id="dev-team")
    assert result["claimed"] == 0
    assert "No workflow-runs" in result["message"]


def test_runner_tick_claims_up_to_concurrency(tmp_path):
    _seed_workflow(tmp_path)
    for _ in range(3):
        enqueue_workflow_run(
            team_dir=tmp_path,
            team_id="dev-team",
            workflow_file="marketing.workflow.json",
        )

    result = run_workflow_runner_tick(
        team_dir=tmp_path, team_id="dev-team", concurrency=2
    )
    assert result["claimed"] == 2
    assert len(result["results"]) == 2
    for r in result["results"]:
        assert r["status"] == "waiting_workers"


def test_runner_filters_to_specific_run_id(tmp_path):
    _seed_workflow(tmp_path)
    first = enqueue_workflow_run(
        team_dir=tmp_path, team_id="dev-team", workflow_file="marketing.workflow.json"
    )
    enqueue_workflow_run(
        team_dir=tmp_path, team_id="dev-team", workflow_file="marketing.workflow.json"
    )
    result = run_workflow_runner_once(
        team_dir=tmp_path, team_id="dev-team", run_id=first["run_id"]
    )
    assert result["run_id"] == first["run_id"]
