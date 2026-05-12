"""Mirrors clawrecipes/tests/take.test.ts + handoff.test.ts."""

from pathlib import Path

import pytest

from hermes_recipes.ticket_workflow import (
    handoff_ticket,
    patch_ticket_fields,
    take_ticket,
)


def _seed_team_dir(base: Path) -> Path:
    (base / "work" / "backlog").mkdir(parents=True)
    # intentionally omit work/in-progress and work/assignments to simulate
    # older workspaces (matches the TS test fixture).
    (base / "work" / "done").mkdir(parents=True)
    return base


def test_take_moves_ticket_and_creates_missing_lane(tmp_path, capsys):
    team = _seed_team_dir(tmp_path)
    src = team / "work" / "backlog" / "0007-sample.md"
    src.write_text("# 0007-sample\n\n## Context\nTest\n", encoding="utf-8")

    res = take_ticket(team_dir=team, ticket="0007", owner="devops")
    err = capsys.readouterr().err
    assert "migration: created work/in-progress/" in err
    assert "work/in-progress" in str(res["dest_path"])

    next_md = res["dest_path"].read_text(encoding="utf-8")
    assert "Owner: devops" in next_md
    assert "Status: in-progress" in next_md
    assert "Assignment:" not in next_md


def test_take_raises_when_ticket_missing(tmp_path):
    _seed_team_dir(tmp_path)
    with pytest.raises(FileNotFoundError, match="Ticket not found"):
        take_ticket(team_dir=tmp_path, ticket="9999", owner="dev")


def test_take_refuses_done_ticket(tmp_path):
    team = _seed_team_dir(tmp_path)
    done_ticket = team / "work" / "done" / "0001-complete.md"
    done_ticket.write_text("# 0001-complete\n\nStatus: done\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Cannot take a done ticket"):
        take_ticket(team_dir=team, ticket="0001", owner="dev")


def test_take_idempotent_when_already_in_progress(tmp_path, capsys):
    team = _seed_team_dir(tmp_path)
    in_progress = team / "work" / "in-progress"
    in_progress.mkdir()
    ticket = in_progress / "0002-sample.md"
    ticket.write_text("# 0002-sample\n\n## Context\n", encoding="utf-8")

    # Legacy stub must remain untouched.
    legacy = team / "work" / "assignments"
    legacy.mkdir()
    legacy_file = legacy / "0002-assigned-dev.md"
    legacy_file.write_text("ORIGINAL", encoding="utf-8")

    res = take_ticket(team_dir=team, ticket="0002", owner="dev")
    capsys.readouterr()
    assert res["moved"] is False
    assert legacy_file.read_text(encoding="utf-8") == "ORIGINAL"


def test_handoff_moves_to_testing_and_idempotent(tmp_path, capsys):
    team = tmp_path
    (team / "work" / "in-progress").mkdir(parents=True)
    (team / "work" / "done").mkdir(parents=True)
    src = team / "work" / "in-progress" / "0001-sample.md"
    src.write_text(
        "# 0001-sample\n\nOwner: dev\nStatus: in-progress\n\n## Context\nTest\n",
        encoding="utf-8",
    )

    first = handoff_ticket(team_dir=team, ticket="0001", tester="test")
    err = capsys.readouterr().err
    assert "migration: created work/testing/" in err
    assert first["moved"] is True
    assert "work/testing" in str(first["dest_path"])

    next_md = first["dest_path"].read_text(encoding="utf-8")
    assert "Owner: test" in next_md
    assert "Status: testing" in next_md
    assert "Assignment:" not in next_md

    second = handoff_ticket(team_dir=team, ticket="0001", tester="test")
    assert second["moved"] is False


def test_handoff_raises_when_ticket_missing(tmp_path):
    (tmp_path / "work" / "in-progress").mkdir(parents=True)
    with pytest.raises(FileNotFoundError, match="Ticket not found"):
        handoff_ticket(team_dir=tmp_path, ticket="9999", tester="test")


def test_patch_ticket_fields_adds_when_absent():
    md = "# 0001-sample\n\n## Context\nTest\n"
    out = patch_ticket_fields(md, owner_safe="dev", status="in-progress")
    assert "Owner: dev" in out
    assert "Status: in-progress" in out


def test_patch_ticket_fields_replaces_when_present():
    md = "# 0001-sample\n\nOwner: prev\nStatus: queued\n"
    out = patch_ticket_fields(md, owner_safe="qa", status="testing")
    assert "Owner: qa" in out
    assert "Status: testing" in out
    assert "Owner: prev" not in out
    assert "Status: queued" not in out


def test_normalize_owner_sanitizes_unsafe_chars(tmp_path):
    team = _seed_team_dir(tmp_path)
    src = team / "work" / "backlog" / "0010-sample.md"
    src.write_text("# 0010-sample\n", encoding="utf-8")
    res = take_ticket(team_dir=team, ticket="0010", owner="QA $$$")
    md = res["dest_path"].read_text(encoding="utf-8")
    assert "Owner: qa" in md
