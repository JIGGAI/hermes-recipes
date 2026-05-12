"""Mirrors lane behavior from clawrecipes/src/lib/lanes.ts."""

from pathlib import Path

import pytest

from hermes_recipes.lanes import RecipesCliError, ensure_lane_dir, ticket_stage_dir


def test_ticket_stage_dir_for_each_stage(tmp_path):
    for stage in ("backlog", "in-progress", "testing", "done"):
        assert ticket_stage_dir(tmp_path, stage) == tmp_path / "work" / stage


def test_ticket_stage_dir_for_assignments(tmp_path):
    assert ticket_stage_dir(tmp_path, "assignments") == tmp_path / "work" / "assignments"


def test_ensure_lane_dir_creates_dir_and_reports_created(tmp_path, capsys):
    result = ensure_lane_dir(team_dir=tmp_path, lane="backlog")
    assert result["created"] is True
    assert (tmp_path / "work" / "backlog").is_dir()
    err = capsys.readouterr().err
    assert "created work/backlog/" in err


def test_ensure_lane_dir_quiet_suppresses_log(tmp_path, capsys):
    ensure_lane_dir(team_dir=tmp_path, lane="testing", quiet=True)
    err = capsys.readouterr().err
    assert err == ""


def test_ensure_lane_dir_idempotent(tmp_path):
    (tmp_path / "work" / "done").mkdir(parents=True)
    result = ensure_lane_dir(team_dir=tmp_path, lane="done", quiet=True)
    assert result["created"] is False


def test_recipes_cli_error_carries_metadata():
    with pytest.raises(RecipesCliError) as excinfo:
        raise RecipesCliError(
            message="boom",
            code="LANE_DIR_CREATE_FAILED",
            command="recipes tickets",
            missing_path="/x/y/work/backlog",
            suggested_fix="mkdir -p work/backlog",
        )
    e = excinfo.value
    assert e.code == "LANE_DIR_CREATE_FAILED"
    assert e.command == "recipes tickets"
    assert e.missing_path == "/x/y/work/backlog"
    assert e.suggested_fix == "mkdir -p work/backlog"
