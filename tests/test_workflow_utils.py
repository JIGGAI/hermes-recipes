"""Covers hermes_recipes/workflows/utils.py."""

import json
from pathlib import Path

import pytest

from hermes_recipes.workflows.utils import (
    as_array,
    as_record,
    as_string,
    assert_lane,
    expand_file_includes,
    iso_compact,
    lane_to_status,
    list_ticket_numbers,
    load_node_states_from_run,
    move_run_ticket,
    next_ticket_number,
    node_label,
    normalize_workflow,
    pick_next_runnable_node_index,
    template_replace,
)


def test_as_record_and_array_and_string():
    assert as_record({"x": 1}) == {"x": 1}
    assert as_record([1, 2]) == {}
    assert as_array([1, 2]) == [1, 2]
    assert as_array({}) == []
    assert as_string(None) == ""
    assert as_string(42) == "42"
    assert as_string("hi") == "hi"
    assert as_string(None, "fallback") == "fallback"


def test_normalize_workflow_canonical_pass_through():
    raw = {
        "id": "wf-1",
        "nodes": [
            {"id": "a", "kind": "llm", "assignedTo": {"agentId": "lead"}, "action": {}},
            {"id": "b", "kind": "tool", "assignedTo": {"agentId": "dev"}, "action": {"tool": "search"}},
        ],
        "edges": [{"from": "a", "to": "b"}],
    }
    out = normalize_workflow(raw)
    assert out["id"] == "wf-1"
    assert out["nodes"][0]["kind"] == "llm"
    assert out["edges"][0]["on"] == "success"


def test_normalize_workflow_folds_clawkitchen_ui_schema():
    raw = {
        "id": "wf-2",
        "nodes": [
            {
                "id": "draft",
                "type": "llm",
                "config": {
                    "agentId": "team-lead",
                    "promptTemplate": "Write a hook",
                    "model": "claude-sonnet-4",
                },
            }
        ],
    }
    out = normalize_workflow(raw)
    node = out["nodes"][0]
    assert node["kind"] == "llm"
    assert node["assignedTo"] == {"agentId": "team-lead"}
    assert node["action"]["promptTemplate"] == "Write a hook"
    assert node["action"]["model"] == "claude-sonnet-4"


def test_normalize_workflow_human_approval_inherits_meta_binding():
    raw = {
        "id": "wf-3",
        "meta": {"approvalBindingId": "telegram:home"},
        "nodes": [{"id": "ok", "kind": "human_approval", "assignedTo": {"agentId": "lead"}}],
    }
    out = normalize_workflow(raw)
    assert out["nodes"][0]["action"]["approvalBindingId"] == "telegram:home"


def test_normalize_workflow_rejects_missing_id():
    with pytest.raises(ValueError, match="missing required field: id"):
        normalize_workflow({"nodes": []})


def test_iso_compact_is_url_safe():
    out = iso_compact()
    assert ":" not in out
    assert "." not in out
    assert out == out.lower()


def test_assert_lane_accepts_known_and_rejects_unknown():
    for lane in ("backlog", "in-progress", "testing", "done"):
        assert_lane(lane)
    with pytest.raises(ValueError, match="Invalid lane"):
        assert_lane("staging")


def test_lane_to_status_mappings():
    assert lane_to_status("backlog") == "queued"
    assert lane_to_status("in-progress") == "in-progress"
    assert lane_to_status("testing") == "testing"
    assert lane_to_status("done") == "done"


def test_template_replace_substitutes_braces():
    assert (
        template_replace("hello {{name}} from {{team}}", {"name": "Ada", "team": "ops"})
        == "hello Ada from ops"
    )


def test_list_and_next_ticket_number(tmp_path):
    base = tmp_path / "work"
    (base / "backlog").mkdir(parents=True)
    (base / "in-progress").mkdir(parents=True)
    (base / "backlog" / "0003-x.md").write_text("", encoding="utf-8")
    (base / "in-progress" / "0007-y.md").write_text("", encoding="utf-8")
    nums = list_ticket_numbers(tmp_path)
    assert sorted(nums) == [3, 7]
    assert next_ticket_number(tmp_path) == "0008"
    # No tickets case
    empty = tmp_path / "empty-team"
    empty.mkdir()
    assert next_ticket_number(empty) == "0001"


def test_expand_file_includes_inlines_content(tmp_path):
    target = tmp_path / "notes" / "context.md"
    target.parent.mkdir(parents=True)
    target.write_text("HELLO BODY", encoding="utf-8")
    out = expand_file_includes("Before {{file:notes/context.md}} After", tmp_path)
    assert "HELLO BODY" in out


def test_expand_file_includes_rejects_unsafe_path(tmp_path):
    out = expand_file_includes("{{file:/etc/passwd}}", tmp_path)
    assert "unsafe path" in out


def test_expand_file_includes_rejects_escape(tmp_path):
    out = expand_file_includes("{{file:../escape}}", tmp_path)
    # Either rejected as unsafe or as outside-workspace — both prevent exfiltration.
    assert "rejected" in out


def test_expand_file_includes_rejects_oversize(tmp_path):
    target = tmp_path / "huge.txt"
    target.write_text("x" * 100, encoding="utf-8")
    out = expand_file_includes("{{file:huge.txt}}", tmp_path, max_bytes=10)
    assert "exceeds 10B cap" in out


def test_load_node_states_from_run_uses_explicit_then_events():
    run = {
        "nodeStates": {"a": {"status": "success", "ts": "t0"}},
        "events": [
            {"ts": "t1", "type": "node.completed", "nodeId": "b"},
            {"ts": "t2", "type": "node.awaiting_approval", "nodeId": "c"},
            {"ts": "t3", "type": "node.error", "nodeId": "d"},
            {"ts": "t4", "type": "node.approved", "nodeId": "e"},
        ],
    }
    out = load_node_states_from_run(run)
    assert out["a"]["status"] == "success"
    assert out["b"]["status"] == "success"
    assert out["c"]["status"] == "waiting"
    assert out["d"]["status"] == "error"
    assert out["e"]["status"] == "success"


def test_load_node_states_revision_clears_from_next_idx():
    run = {
        "status": "needs_revision",
        "nextNodeIndex": 1,
        "events": [
            {"ts": "t1", "type": "node.completed", "nodeId": "a"},
            {"ts": "t2", "type": "node.completed", "nodeId": "b"},
        ],
    }
    workflow = {"nodes": [{"id": "a"}, {"id": "b"}, {"id": "c"}]}
    out = load_node_states_from_run(run, workflow=workflow)
    assert "a" in out
    assert "b" not in out
    assert "c" not in out


def test_pick_next_runnable_sequential_fallback():
    workflow = {
        "nodes": [{"id": "a", "kind": "llm"}, {"id": "b", "kind": "llm"}, {"id": "c", "kind": "llm"}]
    }
    run = {"nodeStates": {"a": {"status": "success", "ts": "t"}}}
    assert pick_next_runnable_node_index(workflow=workflow, run=run) == 1


def test_pick_next_runnable_with_edges_respects_dependencies():
    workflow = {
        "nodes": [{"id": "a"}, {"id": "b"}, {"id": "c"}],
        "edges": [{"from": "a", "to": "b"}, {"from": "b", "to": "c"}],
    }
    run = {"events": [{"ts": "t", "type": "node.completed", "nodeId": "a"}]}
    assert pick_next_runnable_node_index(workflow=workflow, run=run) == 1


def test_pick_next_runnable_returns_none_when_done():
    workflow = {
        "nodes": [{"id": "a"}, {"id": "b"}],
        "edges": [{"from": "a", "to": "b"}],
    }
    run = {
        "events": [
            {"ts": "t", "type": "node.completed", "nodeId": "a"},
            {"ts": "t", "type": "node.completed", "nodeId": "b"},
        ]
    }
    assert pick_next_runnable_node_index(workflow=workflow, run=run) is None


def test_move_run_ticket_renames_and_updates_status(tmp_path):
    src = tmp_path / "work" / "in-progress" / "0001-foo.md"
    src.parent.mkdir(parents=True)
    src.write_text("# 0001-foo\nStatus: in-progress\n", encoding="utf-8")
    res = move_run_ticket(team_dir=tmp_path, ticket_path=src, to_lane="testing")
    dest = res["ticket_path"]
    assert dest.parent.name == "testing"
    assert "Status: testing" in dest.read_text(encoding="utf-8")


def test_node_label_format():
    assert node_label({"kind": "llm", "id": "a"}) == "llm:a"
    assert node_label({"kind": "tool", "id": "b", "name": "Search"}) == "tool:b (Search)"
