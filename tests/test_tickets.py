"""Covers hermes_recipes/tickets.py — list/move/assign/dispatch handlers."""

from pathlib import Path

import pytest

from hermes_recipes.tickets import (
    assign_ticket,
    dispatch_request,
    list_tickets,
    move_ticket,
    patch_ticket_owner,
    patch_ticket_status,
)


def _seed_team_dir(base: Path) -> Path:
    for lane in ("backlog", "in-progress", "testing", "done"):
        (base / "work" / lane).mkdir(parents=True)
    return base


def test_list_tickets_groups_by_lane(tmp_path):
    team = _seed_team_dir(tmp_path)
    (team / "work" / "backlog" / "0001-a.md").write_text("# 0001-a\n", encoding="utf-8")
    (team / "work" / "in-progress" / "0002-b.md").write_text("# 0002-b\n", encoding="utf-8")
    (team / "work" / "done" / "0003-c.md").write_text("# 0003-c\n", encoding="utf-8")

    out = list_tickets(team)
    assert len(out["backlog"]) == 1
    assert len(out["in_progress"]) == 1
    assert len(out["done"]) == 1
    assert len(out["tickets"]) == 3
    assert out["backlog"][0].id == "0001-a"
    assert out["in_progress"][0].number == 2


def test_move_ticket_dry_run_does_not_write(tmp_path):
    team = _seed_team_dir(tmp_path)
    src = team / "work" / "backlog" / "0007-foo.md"
    src.write_text("# 0007-foo\n\nStatus: queued\n", encoding="utf-8")

    result = move_ticket(team_dir=team, ticket="0007", to="in-progress", dry_run=True)
    assert result["ok"] is True
    assert src.exists()  # not moved
    assert "Status: queued" in src.read_text(encoding="utf-8")


def test_move_ticket_updates_status_and_moves_file(tmp_path):
    team = _seed_team_dir(tmp_path)
    src = team / "work" / "backlog" / "0007-foo.md"
    src.write_text("# 0007-foo\n\nStatus: queued\n", encoding="utf-8")

    result = move_ticket(team_dir=team, ticket="0007", to="testing")
    assert result["ok"] is True
    dest = team / "work" / "testing" / "0007-foo.md"
    assert dest.exists()
    md = dest.read_text(encoding="utf-8")
    assert "Status: testing" in md
    assert "Status: queued" not in md


def test_move_ticket_to_done_with_completed_stamps_timestamp(tmp_path):
    team = _seed_team_dir(tmp_path)
    src = team / "work" / "testing" / "0008-baz.md"
    src.write_text("# 0008-baz\n\nStatus: testing\n", encoding="utf-8")

    move_ticket(team_dir=team, ticket="0008", to="done", completed=True)
    dest = team / "work" / "done" / "0008-baz.md"
    md = dest.read_text(encoding="utf-8")
    assert "Status: done" in md
    assert "Completed: " in md


def test_move_ticket_rejects_invalid_stage(tmp_path):
    _seed_team_dir(tmp_path)
    with pytest.raises(ValueError, match="to must be one of"):
        move_ticket(team_dir=tmp_path, ticket="0001", to="wherever")  # type: ignore[arg-type]


def test_assign_ticket_dry_run(tmp_path):
    team = _seed_team_dir(tmp_path)
    src = team / "work" / "backlog" / "0007-foo.md"
    src.write_text("# 0007-foo\n", encoding="utf-8")
    result = assign_ticket(team_dir=team, ticket="0007", owner="lead", dry_run=True)
    assert result["ok"] is True
    assert "Owner:" not in src.read_text(encoding="utf-8")


def test_assign_ticket_updates_owner(tmp_path):
    team = _seed_team_dir(tmp_path)
    src = team / "work" / "backlog" / "0007-foo.md"
    src.write_text("# 0007-foo\n", encoding="utf-8")
    assign_ticket(team_dir=team, ticket="0007", owner="devops")
    assert "Owner: devops" in src.read_text(encoding="utf-8")


def test_assign_ticket_rejects_invalid_owner(tmp_path):
    _seed_team_dir(tmp_path)
    with pytest.raises(ValueError, match="owner must be one of"):
        assign_ticket(team_dir=tmp_path, ticket="0007", owner="ceo")


def test_dispatch_dry_run_returns_plan(tmp_path):
    team = _seed_team_dir(tmp_path)
    result = dispatch_request(
        team_dir=team,
        team_id="dev-team",
        request_text="Add a route",
        owner="dev",
        dry_run=True,
    )
    assert result["ok"] is True
    assert len(result["plan"]["files"]) == 2


def test_dispatch_writes_inbox_and_backlog_ticket(tmp_path):
    team = _seed_team_dir(tmp_path)
    result = dispatch_request(
        team_dir=team,
        team_id="dev-team",
        request_text="Add a new clinic-team recipe",
        owner="lead",
    )
    assert result["ok"] is True
    assert result["nudge_queued"] is False  # no hook provided
    assert any("inbox" in p for p in result["wrote"])
    assert any("backlog" in p for p in result["wrote"])
    backlog_files = sorted((team / "work" / "backlog").iterdir())
    assert len(backlog_files) == 1
    ticket_md = backlog_files[0].read_text(encoding="utf-8")
    assert "Owner: lead" in ticket_md
    assert "Status: queued" in ticket_md
    assert "Add a new clinic-team recipe" in ticket_md


def test_dispatch_increments_ticket_number(tmp_path):
    team = _seed_team_dir(tmp_path)
    dispatch_request(team_dir=team, team_id="dev-team", request_text="first request")
    dispatch_request(team_dir=team, team_id="dev-team", request_text="second request")
    backlog_files = sorted((team / "work" / "backlog").iterdir())
    assert len(backlog_files) == 2
    assert backlog_files[0].name.startswith("0001-")
    assert backlog_files[1].name.startswith("0002-")


def test_dispatch_rejects_empty_request(tmp_path):
    team = _seed_team_dir(tmp_path)
    with pytest.raises(ValueError, match="Request cannot be empty"):
        dispatch_request(team_dir=team, team_id="dev-team", request_text="  ")


def test_dispatch_calls_optional_nudge_and_manifest_hooks(tmp_path):
    team = _seed_team_dir(tmp_path)
    nudge_calls: list[tuple] = []
    manifest_calls: list[None] = []

    dispatch_request(
        team_dir=team,
        team_id="dev-team",
        request_text="hook test",
        on_nudge=lambda body, meta: nudge_calls.append((body, meta)),
        on_manifest_regen=lambda: manifest_calls.append(None),
    )
    assert len(nudge_calls) == 1
    assert "agent:dev-team-lead:main" in nudge_calls[0][1]["session_key"]
    assert manifest_calls == [None]


def test_patch_owner_and_status_helpers():
    md = "# 0001-foo\n\nOwner: prev\nStatus: queued\n"
    assert "Owner: lead" in patch_ticket_owner(md, "lead")
    assert "Status: testing" in patch_ticket_status(md, "testing")
