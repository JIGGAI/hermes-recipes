"""Hermes-flavored counterpart of clawrecipes/tests/workspace.test.ts."""

from pathlib import Path

from hermes_recipes.workspace import (
    ensure_ticket_stage_dirs,
    resolve_team_context,
    resolve_team_dir,
    resolve_workspace_root,
)


def test_workspace_root_prefers_explicit():
    assert resolve_workspace_root(explicit="/home/me/ws", env={}) == Path("/home/me/ws")


def test_workspace_root_falls_back_to_env(tmp_path):
    env = {"HERMES_RECIPES_WORKSPACE": str(tmp_path / "ws")}
    assert resolve_workspace_root(env=env) == tmp_path / "ws"


def test_workspace_root_defaults_to_hermes_home(tmp_path):
    out = resolve_workspace_root(env={}, hermes_home=tmp_path / ".hermes")
    assert out == tmp_path / ".hermes" / "recipes" / "workspace"


def test_team_dir_relative_to_workspace_parent(tmp_path):
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    team_dir = resolve_team_dir("my-team", workspace_root=workspace_root, env={})
    assert team_dir == (tmp_path / "workspace-my-team").resolve()


def test_team_dir_resolves_when_workspace_is_under_role(tmp_path):
    nested = tmp_path / "workspace-my-team" / "roles" / "lead"
    nested.mkdir(parents=True)
    team_dir = resolve_team_dir("my-team", workspace_root=nested, env={})
    assert team_dir == tmp_path / "workspace-my-team"


def test_ensure_ticket_stage_dirs_creates_all_lanes(tmp_path):
    ensure_ticket_stage_dirs(tmp_path)
    for lane in ("backlog", "in-progress", "testing", "done", "assignments"):
        assert (tmp_path / "work" / lane).is_dir()


def test_resolve_team_context_returns_paths_and_creates_lanes(tmp_path):
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    ctx = resolve_team_context("test-team", workspace_root=workspace_root, env={})
    assert ctx["team_dir"] == (tmp_path / "workspace-test-team").resolve()
    assert (ctx["team_dir"] / "work" / "backlog").is_dir()
