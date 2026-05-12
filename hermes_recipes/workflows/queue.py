"""Per-agent file-first task queue with claim/lease locking.

Port of clawrecipes/src/lib/workflows/workflow-queue.ts. Tasks are appended to
``shared-context/workflow-queues/<agentId>.jsonl``; a per-agent cursor lives
at ``<agentId>.state.json``. Claims sit under
``shared-context/workflow-queues/claims/<agentId>.<taskId>.json`` and can be
stolen once their lease expires.
"""

import json
import os
import secrets
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


def _now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _parse_iso(value: Any) -> Optional[float]:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _queue_dir(team_dir: Path | str) -> Path:
    return Path(team_dir) / "shared-context" / "workflow-queues"


def _claims_dir(team_dir: Path | str) -> Path:
    return _queue_dir(team_dir) / "claims"


def _claim_path_for(team_dir: Path | str, agent_id: str, task_id: str) -> Path:
    return _claims_dir(team_dir) / f"{agent_id}.{task_id}.json"


def queue_path_for(team_dir: Path | str, agent_id: str) -> Path:
    return _queue_dir(team_dir) / f"{agent_id}.jsonl"


def _state_path_for(team_dir: Path | str, agent_id: str) -> Path:
    return _queue_dir(team_dir) / f"{agent_id}.state.json"


def _load_claim(team_dir: Path | str, agent_id: str, task_id: str) -> Optional[dict[str, Any]]:
    p = _claim_path_for(team_dir, agent_id, task_id)
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _is_expired_claim(claim: Optional[dict[str, Any]], fallback_lease: Optional[float]) -> bool:
    if not claim:
        return False
    lease = claim.get("leaseSeconds") if isinstance(claim.get("leaseSeconds"), (int, float)) else fallback_lease
    claimed_at = _parse_iso(claim.get("claimedAt"))
    if lease is None or claimed_at is None:
        return False
    return datetime.now(timezone.utc).timestamp() - claimed_at > lease


def release_task_claim(team_dir: Path | str, agent_id: str, task_id: str) -> None:
    try:
        _claim_path_for(team_dir, agent_id, task_id).unlink()
    except FileNotFoundError:
        pass
    except OSError:
        pass


@dataclass(frozen=True)
class QueueTask:
    id: str
    ts: str
    teamId: str
    runId: str
    nodeId: str
    kind: str  # "execute_node"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "ts": self.ts,
            "teamId": self.teamId,
            "runId": self.runId,
            "nodeId": self.nodeId,
            "kind": self.kind,
        }


@dataclass(frozen=True)
class DequeuedTask:
    task: QueueTask
    start_offset_bytes: int
    end_offset_bytes: int


def _load_state(team_dir: Path | str, agent_id: str) -> dict[str, Any]:
    p = _state_path_for(team_dir, agent_id)
    if not p.exists():
        return {"offsetBytes": 0, "updatedAt": _now_iso()}
    try:
        parsed = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(parsed, dict) or not isinstance(parsed.get("offsetBytes"), int):
            raise ValueError("invalid state")
        return parsed
    except (OSError, ValueError, json.JSONDecodeError):
        return {"offsetBytes": 0, "updatedAt": _now_iso()}


def _write_state(team_dir: Path | str, agent_id: str, state: dict[str, Any]) -> None:
    _queue_dir(team_dir).mkdir(parents=True, exist_ok=True)
    _state_path_for(team_dir, agent_id).write_text(
        json.dumps(state, indent=2), encoding="utf-8"
    )


def enqueue_task(team_dir: Path | str, agent_id: str, task: dict[str, Any]) -> dict[str, Any]:
    _queue_dir(team_dir).mkdir(parents=True, exist_ok=True)
    entry = {
        "id": secrets.token_hex(8),
        "ts": _now_iso(),
        **task,
    }
    qpath = queue_path_for(team_dir, agent_id)

    # If cursor is past EOF (file was rotated), reset cursor first.
    state = _load_state(team_dir, agent_id)
    file_size = qpath.stat().st_size if qpath.exists() else 0
    if state["offsetBytes"] > 0 and state["offsetBytes"] >= file_size:
        _write_state(team_dir, agent_id, {"offsetBytes": 0, "updatedAt": _now_iso()})

    with qpath.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")
    return {"ok": True, "path": qpath, "task": entry}


def has_pending_task_for(
    team_dir: Path | str,
    agent_id: str,
    *,
    run_id: str,
    node_id: str,
) -> bool:
    qpath = queue_path_for(team_dir, agent_id)
    if not qpath.exists():
        return False
    state = _load_state(team_dir, agent_id)
    raw = qpath.read_bytes()
    tail = raw[state["offsetBytes"] :].decode("utf-8", errors="ignore")
    for line in tail.split("\n"):
        if not line.strip():
            continue
        try:
            t = json.loads(line)
        except json.JSONDecodeError:
            continue
        if t.get("runId") == run_id and t.get("nodeId") == node_id:
            return True
    return False


def _coerce_task(line: str) -> Optional[QueueTask]:
    try:
        t = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(t, dict):
        return None
    required = ("id", "runId", "nodeId")
    if not all(isinstance(t.get(k), str) and t.get(k) for k in required):
        return None
    return QueueTask(
        id=t["id"],
        ts=t.get("ts", ""),
        teamId=t.get("teamId", ""),
        runId=t["runId"],
        nodeId=t["nodeId"],
        kind=t.get("kind", "execute_node"),
    )


def _try_claim_task(
    *,
    team_dir: Path | str,
    agent_id: str,
    worker_id: str,
    lease_seconds: Optional[float],
    task: QueueTask,
    start_offset_bytes: int,
    end_offset_bytes: int,
    advance_state: bool,
) -> Optional[dict[str, Any]]:
    _claims_dir(team_dir).mkdir(parents=True, exist_ok=True)
    claim_path = _claim_path_for(team_dir, agent_id, task.id)

    def _write_claim(overwrite: bool) -> None:
        record = {
            "taskId": task.id,
            "agentId": agent_id,
            "workerId": worker_id,
            "claimedAt": _now_iso(),
            "leaseSeconds": lease_seconds,
        }
        flag = "w" if overwrite else "x"
        with open(claim_path, flag, encoding="utf-8") as fh:
            json.dump(record, fh, indent=2)

    try:
        _write_claim(overwrite=False)
    except FileExistsError:
        existing = _load_claim(team_dir, agent_id, task.id)
        if str((existing or {}).get("workerId") or "") != worker_id:
            if not _is_expired_claim(existing, lease_seconds):
                if advance_state:
                    _write_state(
                        team_dir, agent_id, {"offsetBytes": end_offset_bytes, "updatedAt": _now_iso()}
                    )
                return None
            _write_claim(overwrite=True)
    if advance_state:
        _write_state(
            team_dir, agent_id, {"offsetBytes": end_offset_bytes, "updatedAt": _now_iso()}
        )
    return {
        "ok": True,
        "task": DequeuedTask(
            task=task,
            start_offset_bytes=start_offset_bytes,
            end_offset_bytes=end_offset_bytes,
        ),
    }


def dequeue_next_task(
    team_dir: Path | str,
    agent_id: str,
    *,
    worker_id: Optional[str] = None,
    lease_seconds: Optional[float] = None,
) -> dict[str, Any]:
    qpath = queue_path_for(team_dir, agent_id)
    if not qpath.exists():
        return {"ok": True, "task": None, "message": "Queue file not present."}

    state = _load_state(team_dir, agent_id)
    worker = worker_id or f"worker:{os.getpid()}"
    raw_bytes = qpath.read_bytes()
    size = len(raw_bytes)

    if state["offsetBytes"] > size:
        state = {"offsetBytes": 0, "updatedAt": _now_iso()}
        _write_state(team_dir, agent_id, state)

    if state["offsetBytes"] < size:
        chunk = raw_bytes[state["offsetBytes"] :].decode("utf-8", errors="replace")
        lines = chunk.split("\n")
        full_lines = lines[:-1]
        cursor = state["offsetBytes"]
        for line in full_lines:
            line_bytes = len((line + "\n").encode("utf-8"))
            start_off = cursor
            end_off = cursor + line_bytes
            cursor = end_off
            if not line.strip():
                _write_state(team_dir, agent_id, {"offsetBytes": cursor, "updatedAt": _now_iso()})
                continue
            task = _coerce_task(line)
            if task is None:
                _write_state(team_dir, agent_id, {"offsetBytes": cursor, "updatedAt": _now_iso()})
                continue
            claimed = _try_claim_task(
                team_dir=team_dir,
                agent_id=agent_id,
                worker_id=worker,
                lease_seconds=lease_seconds,
                task=task,
                start_offset_bytes=start_off,
                end_offset_bytes=end_off,
                advance_state=True,
            )
            if claimed:
                return claimed

    # Recovery scan — revisit tasks behind the cursor with expired claims.
    cursor = 0
    full_raw = raw_bytes.decode("utf-8", errors="replace")
    for line in full_raw.split("\n"):
        line_bytes = len((line + "\n").encode("utf-8"))
        start_off = cursor
        end_off = cursor + line_bytes
        cursor = end_off
        if not line.strip():
            continue
        task = _coerce_task(line)
        if task is None:
            continue
        existing = _load_claim(team_dir, agent_id, task.id)
        if not existing:
            continue
        if (
            str(existing.get("workerId") or "") != worker
            and not _is_expired_claim(existing, lease_seconds)
        ):
            continue
        claimed = _try_claim_task(
            team_dir=team_dir,
            agent_id=agent_id,
            worker_id=worker,
            lease_seconds=lease_seconds,
            task=task,
            start_offset_bytes=start_off,
            end_offset_bytes=end_off,
            advance_state=False,
        )
        if claimed:
            return claimed

    return {"ok": True, "task": None, "message": "No new or recoverable tasks."}


def read_next_tasks(
    team_dir: Path | str,
    agent_id: str,
    *,
    limit: int = 10,
) -> dict[str, Any]:
    """Peek-style read. Does NOT advance the queue cursor."""
    qpath = queue_path_for(team_dir, agent_id)
    if not qpath.exists():
        return {"ok": True, "tasks": [], "consumed": 0, "message": "Queue file not present."}

    state = _load_state(team_dir, agent_id)
    raw_bytes = qpath.read_bytes()
    size = len(raw_bytes)
    if state["offsetBytes"] > size:
        state = {"offsetBytes": 0, "updatedAt": _now_iso()}
        _write_state(team_dir, agent_id, state)
    if state["offsetBytes"] >= size:
        return {"ok": True, "tasks": [], "consumed": 0, "message": "No new tasks."}

    to_read = min(size - state["offsetBytes"], 256 * 1024)
    chunk = raw_bytes[state["offsetBytes"] : state["offsetBytes"] + to_read].decode(
        "utf-8", errors="replace"
    )
    lines = chunk.split("\n")
    full_lines = lines[:-1]
    tasks: list[QueueTask] = []
    for line in full_lines:
        if not line.strip():
            continue
        task = _coerce_task(line)
        if task is not None:
            tasks.append(task)
        if len(tasks) >= max(1, int(limit)):
            break

    return {
        "ok": True,
        "tasks": tasks,
        "consumed": len(tasks),
        "offsetBytes": state["offsetBytes"],
    }


def compact_queue(
    team_dir: Path | str,
    agent_id: str,
    *,
    min_waste_bytes: int = 4096,
) -> dict[str, Any]:
    qpath = queue_path_for(team_dir, agent_id)
    if not qpath.exists():
        return {"ok": True, "compacted": False, "reason": "no queue file"}
    state = _load_state(team_dir, agent_id)
    if state["offsetBytes"] < min_waste_bytes:
        return {"ok": True, "compacted": False, "reason": "below threshold"}

    raw = qpath.read_bytes()
    remaining = raw[state["offsetBytes"] :]
    tmp = qpath.with_name(qpath.name + ".compact.tmp")
    tmp.write_bytes(remaining)
    tmp.replace(qpath)
    _write_state(team_dir, agent_id, {"offsetBytes": 0, "updatedAt": _now_iso()})

    claims_root = _claims_dir(team_dir)
    if claims_root.exists():
        prefix = f"{agent_id}."
        for child in claims_root.iterdir():
            if not (child.name.startswith(prefix) and child.name.endswith(".json")):
                continue
            try:
                claim = json.loads(child.read_text(encoding="utf-8"))
                if _is_expired_claim(claim, 120):
                    child.unlink()
            except (OSError, json.JSONDecodeError):
                continue

    return {
        "ok": True,
        "compacted": True,
        "removed_bytes": state["offsetBytes"],
        "remaining_bytes": len(remaining),
    }


_TERMINAL_STATUSES = frozenset({"completed", "error", "canceled", "done", "failed"})


def cleanup_queues(team_dir: Path | str) -> dict[str, Any]:
    qdir = _queue_dir(team_dir)
    runs_dir = Path(team_dir) / "shared-context" / "workflow-runs"
    if not qdir.exists():
        return {"ok": True, "queues_processed": 0, "tasks_removed": 0, "tasks_kept": 0}

    files = sorted(p for p in qdir.iterdir() if p.suffix == ".jsonl")
    total_removed = 0
    total_kept = 0
    for qpath in files:
        try:
            raw = qpath.read_text(encoding="utf-8")
        except OSError:
            continue
        lines = [l for l in raw.split("\n") if l.strip()]
        if not lines:
            continue
        kept: list[str] = []
        for line in lines:
            try:
                task = json.loads(line)
            except json.JSONDecodeError:
                total_removed += 1
                continue
            run_path = runs_dir / task["runId"] / "run.json"
            remove = False
            try:
                run = json.loads(run_path.read_text(encoding="utf-8"))
                if run.get("status") in _TERMINAL_STATUSES:
                    remove = True
            except (OSError, json.JSONDecodeError):
                remove = True
            if remove:
                total_removed += 1
            else:
                kept.append(line)
                total_kept += 1
        if len(kept) != len(lines):
            qpath.write_text(("\n".join(kept) + "\n") if kept else "", encoding="utf-8")
            agent_id = qpath.stem
            _write_state(team_dir, agent_id, {"offsetBytes": 0, "updatedAt": _now_iso()})

    return {
        "ok": True,
        "queues_processed": len(files),
        "tasks_removed": total_removed,
        "tasks_kept": total_kept,
    }
