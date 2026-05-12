"""Workflow helper functions.

Port of clawrecipes/src/lib/workflows/workflow-utils.ts. Includes:
  - shape coercion helpers (``as_record`` / ``as_array`` / ``as_string``)
  - ``normalize_workflow`` — accepts both canonical and ClawKitchen UI schema
  - ``expand_file_includes`` — safe ``{{file:relative/path}}`` inlining
  - ``pick_next_runnable_node_index`` — DAG scheduler
  - run-log read/write helpers
"""

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from hermes_recipes.workflows.io import read_text_file
from hermes_recipes.workflows.outbound_sanitize import sanitize_outbound_post_text


# ---- shape coercion --------------------------------------------------------


def is_record(value: Any) -> bool:
    return isinstance(value, dict)


def as_record(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_string(value: Any, fallback: str = "") -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return fallback
    return str(value)


def as_array(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


# ---- workflow normalization ------------------------------------------------


def normalize_workflow(raw: Any) -> dict[str, Any]:
    """Accept both canonical and ClawKitchen-UI workflow schemas; emit canonical.

    Mirrors the TS version: nodes may use either ``{kind, assignedTo, action}``
    or ``{type, config}`` and we fold the latter into the former in place.
    """
    workflow = as_record(raw)
    wid = as_string(workflow.get("id")).strip()
    if not wid:
        raise ValueError("Workflow missing required field: id")

    meta = as_record(workflow.get("meta"))
    approval_binding_id = as_string(meta.get("approvalBindingId")).strip()

    nodes: list[dict[str, Any]] = []
    for raw_node in as_array(workflow.get("nodes")):
        n = as_record(raw_node)
        config = as_record(n.get("config"))

        kind = as_string(n.get("kind") or n.get("type")).strip()

        assigned_to_rec = as_record(n.get("assignedTo"))
        agent_id = as_string(
            assigned_to_rec.get("agentId") or config.get("agentId")
        ).strip()
        assigned_to: Optional[dict[str, str]] = (
            {"agentId": agent_id} if agent_id else None
        )

        action: dict[str, Any] = dict(as_record(n.get("action")))
        if config.get("promptTemplate") is not None:
            action["promptTemplate"] = as_string(config["promptTemplate"])
        if config.get("promptTemplatePath") is not None:
            action["promptTemplatePath"] = as_string(config["promptTemplatePath"])
        if config.get("model") is not None:
            action["model"] = as_string(config["model"])
        if config.get("provider") is not None:
            action["provider"] = as_string(config["provider"])
        if config.get("tool") is not None:
            action["tool"] = as_string(config["tool"])
        if is_record(config.get("args")):
            action["args"] = config["args"]
        if config.get("approvalBindingId") is not None:
            action["approvalBindingId"] = as_string(config["approvalBindingId"])

        if (
            kind == "human_approval"
            and not as_string(action.get("approvalBindingId")).strip()
            and approval_binding_id
        ):
            action["approvalBindingId"] = approval_binding_id

        normalized_node: dict[str, Any] = {
            **n,
            "id": as_string(n.get("id")).strip(),
            "kind": kind,
            "action": action,
            "config": config,
        }
        if assigned_to is not None:
            normalized_node["assignedTo"] = assigned_to
        else:
            normalized_node.pop("assignedTo", None)
        nodes.append(normalized_node)

    raw_edges = workflow.get("edges")
    edges: Optional[list[dict[str, Any]]] = None
    if isinstance(raw_edges, list):
        edges = []
        for raw_edge in raw_edges:
            e = as_record(raw_edge)
            edges.append(
                {
                    **e,
                    "from": as_string(e.get("from")).strip(),
                    "to": as_string(e.get("to")).strip(),
                    "on": as_string(e.get("on")).strip() or "success",
                }
            )

    out = {**workflow, "id": wid, "nodes": nodes}
    if edges is not None:
        out["edges"] = edges
    return out


# ---- timestamp helpers -----------------------------------------------------


def iso_compact(ts: Optional[datetime] = None) -> str:
    """URL-safe lowercase ISO-ish timestamp used in ``runId``."""
    ts = ts or datetime.now(timezone.utc)
    raw = ts.isoformat()
    return re.sub(r"[:.]", "-", raw.lower())


def _now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


# ---- lane helpers ----------------------------------------------------------


def assert_lane(lane: str) -> None:
    if lane not in ("backlog", "in-progress", "testing", "done"):
        raise ValueError(f"Invalid lane: {lane}")


def lane_to_status(lane: str) -> str:
    if lane == "backlog":
        return "queued"
    if lane == "in-progress":
        return "in-progress"
    if lane == "testing":
        return "testing"
    return "done"


# ---- ticket numbering ------------------------------------------------------


def list_ticket_numbers(team_dir: Path | str) -> list[int]:
    base = Path(team_dir) / "work"
    nums: list[int] = []
    for lane in ("backlog", "in-progress", "testing", "done"):
        d = base / lane
        if not d.exists():
            continue
        for entry in d.iterdir():
            m = re.match(r"^(\d{4})-", entry.name)
            if m:
                nums.append(int(m.group(1)))
    return nums


def next_ticket_number(team_dir: Path | str) -> str:
    nums = list_ticket_numbers(team_dir)
    return f"{(max(nums) if nums else 0) + 1:04d}"


# ---- template replacement --------------------------------------------------


def template_replace(value: Any, variables: dict[str, str]) -> str:
    out = as_string(value)
    for key, val in variables.items():
        out = out.replace(f"{{{{{key}}}}}", val)
    return out


FILE_INCLUDE_MAX_BYTES_DEFAULT = 256 * 1024


def expand_file_includes(
    value: Any,
    team_dir: Path | str,
    *,
    max_bytes: int = FILE_INCLUDE_MAX_BYTES_DEFAULT,
) -> str:
    """Inline ``{{file:relative/path}}`` markers from files under team_dir.

    Safety: rejects absolute paths, paths containing ``..``, and paths that
    escape ``team_dir`` even via symlink. Rejected markers leave a short
    ``[[file-include …]]`` note in place so the LLM has visible context.
    """
    text = as_string(value)
    pattern = re.compile(r"\{\{\s*file:([^}]+?)\s*\}\}")
    matches = list(pattern.finditer(text))
    if not matches:
        return text

    team_dir_resolved = Path(team_dir).resolve()
    try:
        team_dir_resolved = team_dir_resolved.resolve(strict=False)
    except OSError:
        pass

    resolved_cache: dict[str, str] = {}
    for match in matches:
        raw_path = match.group(1).strip()
        if raw_path in resolved_cache:
            continue
        if (
            not raw_path
            or os.path.isabs(raw_path)
            or ".." in raw_path.split("/")
        ):
            resolved_cache[raw_path] = (
                f'[[file-include rejected: unsafe path "{raw_path}"]]'
            )
            continue

        candidate = (team_dir_resolved / raw_path).resolve(strict=False)
        if candidate != team_dir_resolved and team_dir_resolved not in candidate.parents:
            resolved_cache[raw_path] = (
                f'[[file-include rejected: outside team workspace "{raw_path}"]]'
            )
            continue

        try:
            real = candidate.resolve(strict=True)
            if (
                real != team_dir_resolved
                and team_dir_resolved not in real.parents
            ):
                resolved_cache[raw_path] = (
                    f'[[file-include rejected: symlink escapes team workspace "{raw_path}"]]'
                )
                continue
            stat = real.stat()
            if not real.is_file():
                resolved_cache[raw_path] = (
                    f'[[file-include rejected: not a regular file "{raw_path}"]]'
                )
                continue
            if stat.st_size > max_bytes:
                resolved_cache[raw_path] = (
                    f'[[file-include rejected: "{raw_path}" size {stat.st_size}B exceeds {max_bytes}B cap]]'
                )
                continue
            resolved_cache[raw_path] = real.read_text(encoding="utf-8")
        except FileNotFoundError as e:
            resolved_cache[raw_path] = f'[[file-include failed: "{raw_path}" — {e}]]'
        except OSError as e:
            resolved_cache[raw_path] = f'[[file-include failed: "{raw_path}" — {e}]]'

    def _replace(m: re.Match[str]) -> str:
        return resolved_cache.get(m.group(1).strip(), "")

    return pattern.sub(_replace, text)


def sanitize_draft_only_text(text: str) -> str:
    return sanitize_outbound_post_text(text)


# ---- ticket lane moves -----------------------------------------------------


def move_run_ticket(
    *, team_dir: Path | str, ticket_path: Path | str, to_lane: str
) -> dict[str, Path]:
    """Rename a ticket file into ``work/<to_lane>/`` and update its Status."""
    team = Path(team_dir)
    src = Path(ticket_path)
    to_dir = team / "work" / to_lane
    to_dir.mkdir(parents=True, exist_ok=True)
    dest = to_dir / src.name
    if src.resolve() != dest.resolve():
        src.rename(dest)
    try:
        md = dest.read_text(encoding="utf-8")
        next_md = re.sub(
            r"^Status: .*$",
            f"Status: {lane_to_status(to_lane)}",
            md,
            count=1,
            flags=re.MULTILINE,
        )
        if next_md != md:
            dest.write_text(next_md, encoding="utf-8")
    except OSError:
        pass
    return {"ticket_path": dest}


# ---- node state derivation -------------------------------------------------


def load_node_states_from_run(
    run: dict[str, Any], *, workflow: Optional[dict[str, Any]] = None
) -> dict[str, dict[str, str]]:
    """Rebuild node states from explicit ``run.nodeStates`` + the event stream.

    Revision semantics: when ``run.status == "needs_revision"``, node states
    from ``run.nextNodeIndex`` onward are intentionally cleared so the worker
    re-runs them.
    """
    out: dict[str, dict[str, str]] = {}
    cur = run.get("nodeStates") if isinstance(run.get("nodeStates"), dict) else {}
    for node_id, st in cur.items():
        if isinstance(st, dict) and st.get("status") in ("success", "error", "waiting"):
            out[str(node_id)] = {"status": st["status"], "ts": st.get("ts", "")}

    for ev_raw in as_array(run.get("events")):
        ev = as_record(ev_raw)
        node_id = as_string(ev.get("nodeId")).strip()
        if not node_id:
            continue
        ts = as_string(ev.get("ts")) or _now_iso()
        type_ = as_string(ev.get("type")).strip()
        if type_ == "node.completed":
            out[node_id] = {"status": "success", "ts": ts}
        elif type_ == "node.error":
            out[node_id] = {"status": "error", "ts": ts}
        elif type_ == "node.awaiting_approval":
            out[node_id] = {"status": "waiting", "ts": ts}
        elif type_ == "node.approved":
            out[node_id] = {"status": "success", "ts": ts}

    if (
        run.get("status") == "needs_revision"
        and isinstance(run.get("nextNodeIndex"), int)
        and workflow is not None
    ):
        nodes = workflow.get("nodes") or []
        for i in range(max(0, run["nextNodeIndex"]), len(nodes)):
            node_id = as_string(as_record(nodes[i]).get("id")).strip()
            out.pop(node_id, None)
    return out


def pick_next_runnable_node_index(
    *, workflow: dict[str, Any], run: dict[str, Any]
) -> Optional[int]:
    nodes = workflow.get("nodes") or []
    if not nodes:
        return None

    edges = workflow.get("edges") or []
    if not isinstance(edges, list) or not edges:
        start = run.get("nextNodeIndex") if isinstance(run.get("nextNodeIndex"), int) else 0
        node_states = as_record(run.get("nodeStates"))
        for i in range(max(0, start), len(nodes)):
            node = as_record(nodes[i])
            node_id = as_string(node.get("id")).strip()
            if not node_id:
                continue
            st = as_record(node_states.get(node_id)).get("status")
            if st in ("success", "error", "waiting"):
                continue
            return i
        return None

    node_states = load_node_states_from_run(run, workflow=workflow)

    if run.get("status") == "needs_revision" and isinstance(run.get("nextNodeIndex"), int):
        for i in range(max(0, run["nextNodeIndex"]), len(nodes)):
            nid = as_string(as_record(nodes[i]).get("id")).strip()
            node_states.pop(nid, None)

    incoming: dict[str, list[dict[str, Any]]] = {}
    for edge in edges:
        e = as_record(edge)
        to = as_string(e.get("to")).strip()
        if not to:
            continue
        incoming.setdefault(to, []).append(e)

    def edge_satisfied(edge: dict[str, Any]) -> bool:
        from_id = as_string(edge.get("from")).strip()
        from_status = as_record(node_states.get(from_id)).get("status")
        on = as_string(edge.get("on")) or "success"
        if not from_status:
            return False
        if on == "always":
            return from_status in ("success", "error")
        if on == "error":
            return from_status == "error"
        return from_status == "success"

    def node_ready(node: dict[str, Any]) -> bool:
        node_id = as_string(node.get("id")).strip()
        if not node_id:
            return False
        st = as_record(node_states.get(node_id)).get("status")
        if st in ("success", "error", "waiting"):
            return False
        input_from = as_record(node.get("input")).get("from")
        if isinstance(input_from, list) and input_from:
            return all(
                as_record(node_states.get(as_string(dep))).get("status") == "success"
                for dep in input_from
            )
        edges_in = incoming.get(node_id) or []
        if not edges_in:
            return True
        return any(edge_satisfied(e) for e in edges_in)

    for i, node in enumerate(nodes):
        if node_ready(as_record(node)):
            return i
    return None


# ---- run-log read/write ----------------------------------------------------


def run_file_path_for(runs_dir: Path | str, run_id: str) -> Path:
    return Path(runs_dir) / run_id / "run.json"


def load_run_file(
    team_dir: Path | str, runs_dir: Path | str, run_id: str
) -> dict[str, Any]:
    run_path = run_file_path_for(runs_dir, run_id)
    if not run_path.exists():
        rel = run_path.relative_to(Path(team_dir)) if str(run_path).startswith(str(team_dir)) else run_path
        raise FileNotFoundError(f"Run file not found: {rel}")
    return {"path": run_path, "run": json.loads(read_text_file(run_path))}


def _write_run_log(run_log_path: Path | str, fn: Callable[[dict[str, Any]], dict[str, Any]]) -> None:
    path = Path(run_log_path)
    cur = json.loads(read_text_file(path))
    next_log = fn(cur)
    next_log = {**next_log, "updatedAt": _now_iso()}
    path.write_text(json.dumps(next_log, indent=2), encoding="utf-8")


def append_run_log(run_log_path: Path | str, fn: Callable[[dict[str, Any]], dict[str, Any]]) -> None:
    _write_run_log(run_log_path, fn)


def write_run_file(run_path: Path | str, fn: Callable[[dict[str, Any]], dict[str, Any]]) -> None:
    _write_run_log(run_path, fn)


def node_label(node: dict[str, Any]) -> str:
    kind = as_string(node.get("kind"))
    node_id = as_string(node.get("id"))
    name = as_string(node.get("name"))
    suffix = f" ({name})" if name else ""
    return f"{kind}:{node_id}{suffix}"
