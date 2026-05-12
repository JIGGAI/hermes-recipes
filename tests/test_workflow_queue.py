"""Mirrors clawrecipes/tests/workflow-queue.test.ts."""

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from hermes_recipes.workflows.queue import (
    cleanup_queues,
    compact_queue,
    dequeue_next_task,
    enqueue_task,
    has_pending_task_for,
    queue_path_for,
    read_next_tasks,
    release_task_claim,
)


def _enqueue(team_dir: Path, agent_id: str, run_id: str, node_id: str = "n1") -> dict:
    return enqueue_task(
        team_dir,
        agent_id,
        {
            "teamId": "t1",
            "runId": run_id,
            "nodeId": node_id,
            "kind": "execute_node",
        },
    )


def test_dequeue_returns_tasks_in_order_and_advances_cursor(tmp_path):
    _enqueue(tmp_path, "agent-a", "r1")
    _enqueue(tmp_path, "agent-a", "r2", node_id="n2")

    dq1 = dequeue_next_task(tmp_path, "agent-a", worker_id="w1")
    assert dq1["task"].task.runId == "r1"
    release_task_claim(tmp_path, "agent-a", dq1["task"].task.id)

    dq2 = dequeue_next_task(tmp_path, "agent-a", worker_id="w1")
    assert dq2["task"].task.runId == "r2"
    release_task_claim(tmp_path, "agent-a", dq2["task"].task.id)

    dq3 = dequeue_next_task(tmp_path, "agent-a", worker_id="w1")
    assert dq3["task"] is None


def test_dequeue_skips_claim_by_other_worker_unexpired(tmp_path):
    enq = _enqueue(tmp_path, "agent-a", "r1")
    claims_dir = tmp_path / "shared-context" / "workflow-queues" / "claims"
    claims_dir.mkdir(parents=True)
    (claims_dir / f"agent-a.{enq['task']['id']}.json").write_text(
        json.dumps(
            {
                "taskId": enq["task"]["id"],
                "agentId": "agent-a",
                "workerId": "worker-a",
                "claimedAt": datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z"),
                "leaseSeconds": 3600,
            }
        ),
        encoding="utf-8",
    )

    dq = dequeue_next_task(tmp_path, "agent-a", worker_id="worker-b", lease_seconds=1)
    assert dq["task"] is None
    assert "r1" in queue_path_for(tmp_path, "agent-a").read_text(encoding="utf-8")


def test_dequeue_steals_expired_claim(tmp_path):
    enq = _enqueue(tmp_path, "agent-a", "r1")
    claims_dir = tmp_path / "shared-context" / "workflow-queues" / "claims"
    claims_dir.mkdir(parents=True)
    old_iso = (
        (datetime.now(timezone.utc) - timedelta(seconds=10))
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )
    (claims_dir / f"agent-a.{enq['task']['id']}.json").write_text(
        json.dumps(
            {
                "taskId": enq["task"]["id"],
                "agentId": "agent-a",
                "workerId": "worker-a",
                "claimedAt": old_iso,
                "leaseSeconds": 1,
            }
        ),
        encoding="utf-8",
    )

    dq = dequeue_next_task(tmp_path, "agent-a", worker_id="worker-b", lease_seconds=1)
    assert dq["task"].task.runId == "r1"
    claim = json.loads(
        (claims_dir / f"agent-a.{enq['task']['id']}.json").read_text(encoding="utf-8")
    )
    assert claim["workerId"] == "worker-b"


def test_dequeue_recovers_expired_claim_behind_cursor(tmp_path):
    enq = _enqueue(tmp_path, "agent-a", "r1")
    dq1 = dequeue_next_task(tmp_path, "agent-a", worker_id="worker-a", lease_seconds=1)
    assert dq1["task"].task.id == enq["task"]["id"]

    claims_dir = tmp_path / "shared-context" / "workflow-queues" / "claims"
    claim_path = claims_dir / f"agent-a.{enq['task']['id']}.json"
    old_iso = (
        (datetime.now(timezone.utc) - timedelta(seconds=10))
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )
    claim_path.write_text(
        json.dumps(
            {
                "taskId": enq["task"]["id"],
                "agentId": "agent-a",
                "workerId": "worker-a",
                "claimedAt": old_iso,
                "leaseSeconds": 1,
            }
        ),
        encoding="utf-8",
    )

    dq2 = dequeue_next_task(tmp_path, "agent-a", worker_id="worker-b", lease_seconds=1)
    assert dq2["task"].task.id == enq["task"]["id"]


def test_has_pending_task_for_finds_match_past_cursor(tmp_path):
    _enqueue(tmp_path, "agent-a", "r1")
    _enqueue(tmp_path, "agent-a", "r2", node_id="n2")
    assert has_pending_task_for(tmp_path, "agent-a", run_id="r1", node_id="n1")
    assert has_pending_task_for(tmp_path, "agent-a", run_id="r2", node_id="n2")
    assert not has_pending_task_for(tmp_path, "agent-a", run_id="rX", node_id="nX")
    assert not has_pending_task_for(tmp_path, "agent-a", run_id="r1", node_id="n2")


def test_has_pending_task_for_ignores_consumed_tasks(tmp_path):
    _enqueue(tmp_path, "agent-a", "r1")
    dq = dequeue_next_task(tmp_path, "agent-a", worker_id="w1")
    release_task_claim(tmp_path, "agent-a", dq["task"].task.id)
    assert not has_pending_task_for(tmp_path, "agent-a", run_id="r1", node_id="n1")


def test_has_pending_task_for_when_queue_missing(tmp_path):
    assert not has_pending_task_for(tmp_path, "missing-agent", run_id="r", node_id="n")


def test_release_task_claim_prevents_recovery(tmp_path):
    enq = _enqueue(tmp_path, "agent-a", "r1")
    dq1 = dequeue_next_task(tmp_path, "agent-a", worker_id="worker-a", lease_seconds=1)
    assert dq1["task"].task.id == enq["task"]["id"]
    release_task_claim(tmp_path, "agent-a", enq["task"]["id"])

    dq2 = dequeue_next_task(tmp_path, "agent-a", worker_id="worker-b", lease_seconds=1)
    assert dq2["task"] is None


def test_read_next_tasks_peeks_without_advancing_cursor(tmp_path):
    _enqueue(tmp_path, "agent-a", "r1")
    _enqueue(tmp_path, "agent-a", "r2", node_id="n2")
    peek = read_next_tasks(tmp_path, "agent-a", limit=10)
    assert peek["consumed"] == 2
    # cursor must still be 0; the very next dequeue should still claim r1
    dq = dequeue_next_task(tmp_path, "agent-a", worker_id="w1")
    assert dq["task"].task.runId == "r1"


def test_cleanup_queues_drops_tasks_for_terminal_runs(tmp_path):
    _enqueue(tmp_path, "agent-a", "r-done", node_id="n1")
    _enqueue(tmp_path, "agent-a", "r-active", node_id="n2")

    runs_dir = tmp_path / "shared-context" / "workflow-runs"
    (runs_dir / "r-done").mkdir(parents=True)
    (runs_dir / "r-done" / "run.json").write_text(
        json.dumps({"runId": "r-done", "status": "completed"}), encoding="utf-8"
    )
    (runs_dir / "r-active").mkdir(parents=True)
    (runs_dir / "r-active" / "run.json").write_text(
        json.dumps({"runId": "r-active", "status": "queued"}), encoding="utf-8"
    )

    result = cleanup_queues(tmp_path)
    assert result["queues_processed"] == 1
    assert result["tasks_removed"] == 1
    assert result["tasks_kept"] == 1


def test_compact_queue_no_op_when_cursor_unchanged(tmp_path):
    _enqueue(tmp_path, "agent-a", "r1")
    result = compact_queue(tmp_path, "agent-a")
    assert result["compacted"] is False
    assert result["reason"] == "below threshold"
