"""Phase 6a coverage — argparse wiring + plugin registration + handlers."""

import argparse
import io
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from hermes_recipes import register
from hermes_recipes._cli import recipes_command, register_cli


def _seed_team(base: Path, team_id: str) -> Path:
    team_dir = base.parent / f"workspace-{team_id}"
    for lane in ("backlog", "in-progress", "testing", "done"):
        (team_dir / "work" / lane).mkdir(parents=True)
    return team_dir


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hermes recipes")
    register_cli(parser)
    return parser


# ── plugin registration ─────────────────────────────────────────────────────


def test_register_calls_ctx_register_cli_command():
    ctx = MagicMock()
    register(ctx)
    ctx.register_cli_command.assert_called_once()
    kwargs = ctx.register_cli_command.call_args.kwargs
    assert kwargs["name"] == "recipes"
    assert callable(kwargs["setup_fn"])
    assert callable(kwargs["handler_fn"])
    assert kwargs["handler_fn"] is recipes_command


def test_register_cli_builds_expected_actions():
    parser = _build_parser()
    args = parser.parse_args(["tickets", "--team-id", "x"])
    assert args.recipes_action == "tickets"
    args = parser.parse_args(
        ["dispatch", "--team-id", "x", "--request", "do thing", "--owner", "lead"]
    )
    assert args.recipes_action == "dispatch"
    args = parser.parse_args(
        ["move-ticket", "--team-id", "x", "--ticket", "0001", "--to", "testing"]
    )
    assert args.recipes_action == "move-ticket"


def test_recipes_command_with_no_action_returns_2(capsys):
    parser = _build_parser()
    args = parser.parse_args([])
    code = recipes_command(args)
    out = capsys.readouterr().out
    assert code == 2
    assert "Usage: hermes recipes" in out


# ── ticket lifecycle end-to-end ─────────────────────────────────────────────


def test_dispatch_then_tickets_then_take_then_handoff_then_complete(tmp_path, capsys):
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    parser = _build_parser()

    # 1. dispatch — creates backlog ticket + inbox entry
    args = parser.parse_args(
        [
            "--workspace-root",
            str(workspace_root),
            "dispatch",
            "--team-id",
            "dev-team",
            "--request",
            "Add a new clinic-team recipe",
            "--owner",
            "lead",
        ]
    )
    assert recipes_command(args) == 0
    dispatch_out = json.loads(capsys.readouterr().out)
    assert dispatch_out["ok"] is True
    assert len(dispatch_out["wrote"]) == 2

    team_dir = Path(dispatch_out["team_dir"])
    backlog_files = list((team_dir / "work" / "backlog").iterdir())
    assert len(backlog_files) == 1
    ticket_filename = backlog_files[0].stem  # "0001-..."
    ticket_num = ticket_filename.split("-", 1)[0]
    assert ticket_num == "0001"

    # 2. tickets --json — see backlog populated
    args = parser.parse_args(
        ["--workspace-root", str(workspace_root), "tickets", "--team-id", "dev-team", "--json"]
    )
    assert recipes_command(args) == 0
    listing = json.loads(capsys.readouterr().out)
    assert len(listing["backlog"]) == 1
    assert listing["backlog"][0]["number"] == 1

    # 3. take — moves ticket to in-progress, sets Owner: dev
    args = parser.parse_args(
        [
            "--workspace-root",
            str(workspace_root),
            "take",
            "--team-id",
            "dev-team",
            "--ticket",
            ticket_num,
            "--owner",
            "dev",
        ]
    )
    assert recipes_command(args) == 0
    take_out = json.loads(capsys.readouterr().out)
    assert "work/in-progress" in take_out["dest_path"]
    assert take_out["moved"] is True
    in_progress_files = list((team_dir / "work" / "in-progress").iterdir())
    assert len(in_progress_files) == 1
    assert "Owner: dev" in in_progress_files[0].read_text(encoding="utf-8")

    # 4. handoff — moves to testing, sets Owner: test
    args = parser.parse_args(
        [
            "--workspace-root",
            str(workspace_root),
            "handoff",
            "--team-id",
            "dev-team",
            "--ticket",
            ticket_num,
        ]
    )
    assert recipes_command(args) == 0
    capsys.readouterr()  # discard
    testing_files = list((team_dir / "work" / "testing").iterdir())
    assert len(testing_files) == 1
    assert "Owner: test" in testing_files[0].read_text(encoding="utf-8")

    # 5. complete — moves to done with Completed: stamp
    args = parser.parse_args(
        [
            "--workspace-root",
            str(workspace_root),
            "complete",
            "--team-id",
            "dev-team",
            "--ticket",
            ticket_num,
        ]
    )
    assert recipes_command(args) == 0
    capsys.readouterr()
    done_files = list((team_dir / "work" / "done").iterdir())
    assert len(done_files) == 1
    md = done_files[0].read_text(encoding="utf-8")
    assert "Status: done" in md
    assert "Completed:" in md


def test_dispatch_dry_run_does_not_write_files(tmp_path, capsys):
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    parser = _build_parser()
    args = parser.parse_args(
        [
            "--workspace-root",
            str(workspace_root),
            "dispatch",
            "--team-id",
            "dev-team",
            "--request",
            "noop",
            "--dry-run",
        ]
    )
    assert recipes_command(args) == 0
    team_dir = workspace_root.parent / "workspace-dev-team"
    # tickets lanes get auto-created by resolve_team_context, but no ticket file written
    assert not any((team_dir / "work" / "backlog").iterdir())
    assert not (team_dir / "inbox").exists()


def test_assign_updates_owner_header(tmp_path, capsys):
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    parser = _build_parser()
    # Pre-populate a ticket so assign has something to patch.
    parser.parse_args  # silence unused
    args = parser.parse_args(
        [
            "--workspace-root",
            str(workspace_root),
            "dispatch",
            "--team-id",
            "dev-team",
            "--request",
            "Build a thing",
            "--owner",
            "dev",
        ]
    )
    recipes_command(args)
    capsys.readouterr()

    args = parser.parse_args(
        [
            "--workspace-root",
            str(workspace_root),
            "assign",
            "--team-id",
            "dev-team",
            "--ticket",
            "0001",
            "--owner",
            "devops",
        ]
    )
    assert recipes_command(args) == 0
    team_dir = workspace_root.parent / "workspace-dev-team"
    ticket = list((team_dir / "work" / "backlog").iterdir())[0]
    assert "Owner: devops" in ticket.read_text(encoding="utf-8")


def test_move_ticket_dry_run_does_not_move(tmp_path, capsys):
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    parser = _build_parser()
    args = parser.parse_args(
        [
            "--workspace-root",
            str(workspace_root),
            "dispatch",
            "--team-id",
            "dev-team",
            "--request",
            "Build a thing",
        ]
    )
    recipes_command(args)
    capsys.readouterr()

    args = parser.parse_args(
        [
            "--workspace-root",
            str(workspace_root),
            "move-ticket",
            "--team-id",
            "dev-team",
            "--ticket",
            "0001",
            "--to",
            "testing",
            "--dry-run",
        ]
    )
    assert recipes_command(args) == 0
    capsys.readouterr()
    team_dir = workspace_root.parent / "workspace-dev-team"
    assert len(list((team_dir / "work" / "backlog").iterdir())) == 1
    assert not list((team_dir / "work" / "testing").iterdir())


def test_tickets_handles_missing_team_workspace_gracefully(tmp_path):
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    parser = _build_parser()
    args = parser.parse_args(
        ["--workspace-root", str(workspace_root), "tickets", "--team-id", "ghost-team", "--json"]
    )
    # resolve_team_context creates the lane dirs; tickets list will be empty.
    assert recipes_command(args) == 0


def test_handler_returns_1_on_missing_ticket(tmp_path, capsys):
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    parser = _build_parser()
    args = parser.parse_args(
        [
            "--workspace-root",
            str(workspace_root),
            "take",
            "--team-id",
            "dev-team",
            "--ticket",
            "9999",
            "--owner",
            "dev",
        ]
    )
    assert recipes_command(args) == 1
    out = capsys.readouterr().out
    assert "Ticket not found" in out
