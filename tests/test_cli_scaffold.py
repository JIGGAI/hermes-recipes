"""End-to-end CLI coverage for Phase 6b scaffold + workflow commands."""

import argparse
import json
from pathlib import Path
from typing import Any

import pytest

from hermes_recipes._cli import CLI_HOOKS, recipes_command, register_cli
from hermes_recipes.integrations.hermes_cron import InMemoryCronApi
from hermes_recipes.integrations.hermes_profiles import InMemoryProfileProvisioner


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hermes recipes")
    register_cli(parser)
    return parser


@pytest.fixture
def fake_hooks():
    """Replace the live Hermes integration hooks with in-memory fakes."""
    provisioner = InMemoryProfileProvisioner()
    cron_api = InMemoryCronApi()
    original = dict(CLI_HOOKS)
    CLI_HOOKS["profile_provisioner"] = lambda: provisioner
    CLI_HOOKS["cron_api"] = lambda: cron_api
    yield {"provisioner": provisioner, "cron_api": cron_api}
    CLI_HOOKS.clear()
    CLI_HOOKS.update(original)


def _write_recipe(recipes_dir: Path, recipe_id: str, frontmatter: dict, body: str = "") -> Path:
    import yaml

    recipes_dir.mkdir(parents=True, exist_ok=True)
    target = recipes_dir / f"{recipe_id}.md"
    target.write_text(f"---\n{yaml.safe_dump(frontmatter, sort_keys=False)}---\n{body}", encoding="utf-8")
    return target


# ── scaffold (single agent) ─────────────────────────────────────────────────


def test_scaffold_writes_files_and_provisions_profile(tmp_path, capsys, fake_hooks):
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    recipes_dir = tmp_path / "recipes"
    _write_recipe(
        recipes_dir,
        "writer",
        {
            "id": "writer",
            "kind": "agent",
            "name": "Writer",
            "templates": {
                "soul": "# SOUL — {{agentName}}\nid={{agentId}}\n",
            },
            "files": [{"path": "SOUL.md", "template": "soul"}],
        },
    )
    parser = _build_parser()
    args = parser.parse_args(
        [
            "--workspace-root",
            str(workspace_root),
            "--recipes-dir",
            str(recipes_dir),
            "scaffold",
            "--recipe-id",
            "writer",
            "--agent-id",
            "writer-1",
            "--name",
            "Writer One",
            "--provision-profile",
        ]
    )
    assert recipes_command(args) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["agent_id"] == "writer-1"
    assert payload["profile"]["created"] is True
    files_dir = workspace_root.parent / "workspace-writer-1"
    soul = (files_dir / "SOUL.md").read_text(encoding="utf-8")
    assert "id=writer-1" in soul
    assert "Writer One" in soul
    assert fake_hooks["provisioner"].created == {"writer-1"}


def test_scaffold_does_not_provision_without_flag(tmp_path, capsys, fake_hooks):
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    recipes_dir = tmp_path / "recipes"
    _write_recipe(
        recipes_dir,
        "writer",
        {"id": "writer", "kind": "agent", "templates": {}, "files": []},
    )
    parser = _build_parser()
    args = parser.parse_args(
        [
            "--workspace-root",
            str(workspace_root),
            "--recipes-dir",
            str(recipes_dir),
            "scaffold",
            "--recipe-id",
            "writer",
            "--agent-id",
            "writer-2",
        ]
    )
    assert recipes_command(args) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["profile"] is None
    assert fake_hooks["provisioner"].created == set()


def test_scaffold_returns_error_when_recipe_missing(tmp_path, capsys, fake_hooks):
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    parser = _build_parser()
    args = parser.parse_args(
        [
            "--workspace-root",
            str(workspace_root),
            "scaffold",
            "--recipe-id",
            "missing-recipe",
            "--agent-id",
            "x",
        ]
    )
    assert recipes_command(args) == 1
    err_out = capsys.readouterr().out
    assert "Recipe not found" in err_out


# ── scaffold-team ───────────────────────────────────────────────────────────


def test_scaffold_team_lays_out_per_role_dirs_and_provisions_profiles(
    tmp_path, capsys, fake_hooks
):
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    recipes_dir = tmp_path / "recipes"
    _write_recipe(
        recipes_dir,
        "dev-team-recipe",
        {
            "id": "dev-team-recipe",
            "kind": "team",
            "name": "Dev Team",
            "agents": [
                {"role": "lead"},
                {"role": "dev"},
                {"role": "test"},
            ],
            "templates": {
                "lead.soul": "# SOUL — {{agentName}} ({{role}})\n",
                "dev.soul": "# SOUL — {{agentName}} ({{role}})\n",
                "test.soul": "# SOUL — {{agentName}} ({{role}})\n",
                "lead.agents": "# AGENTS — {{agentName}}\n",
                "dev.agents": "# AGENTS — {{agentName}}\n",
                "test.agents": "# AGENTS — {{agentName}}\n",
                "lead.tools": "# TOOLS — {{agentName}}\n",
                "dev.tools": "# TOOLS — {{agentName}}\n",
                "test.tools": "# TOOLS — {{agentName}}\n",
            },
            "files": [
                {"path": "SOUL.md", "template": "soul"},
                {"path": "AGENTS.md", "template": "agents"},
                {"path": "TOOLS.md", "template": "tools"},
            ],
            "cronJobs": [
                {
                    "id": "loop",
                    "schedule": "*/30 * * * *",
                    "message": "ping {{teamId}}",
                    "enabledByDefault": True,
                }
            ],
        },
    )
    parser = _build_parser()
    args = parser.parse_args(
        [
            "--workspace-root",
            str(workspace_root),
            "--recipes-dir",
            str(recipes_dir),
            "scaffold-team",
            "--recipe-id",
            "dev-team-recipe",
            "--team-id",
            "dev-team",
            "--provision-profiles",
            "--install-cron",
            "on",
        ]
    )
    assert recipes_command(args) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert sorted(payload["roles"]) == ["dev", "lead", "test"]
    assert sorted(payload["agents"]) == ["dev-team-dev", "dev-team-lead", "dev-team-test"]
    assert payload["cron_jobs_declared"] == 1

    team_dir = workspace_root.parent / "workspace-dev-team"
    for role in ("lead", "dev", "test"):
        assert (team_dir / "roles" / role / "SOUL.md").exists()

    assert {p["name"] for p in payload["profiles_provisioned"]} == {
        "dev-team-lead",
        "dev-team-dev",
        "dev-team-test",
    }
    # cron reconciliation ran via the in-memory API
    assert len(fake_hooks["cron_api"].created) == 1
    state_file = team_dir / "notes" / "cron-jobs.json"
    assert state_file.exists()


def test_scaffold_team_install_cron_off_skips_reconcile(tmp_path, capsys, fake_hooks):
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    recipes_dir = tmp_path / "recipes"
    _write_recipe(
        recipes_dir,
        "tiny-team",
        {
            "id": "tiny-team",
            "kind": "team",
            "agents": [{"role": "lead"}],
            "templates": {"lead.soul": "x"},
            "files": [{"path": "SOUL.md", "template": "soul"}],
            "cronJobs": [
                {"id": "loop", "schedule": "* * * * *", "message": "ping"}
            ],
        },
    )
    parser = _build_parser()
    args = parser.parse_args(
        [
            "--workspace-root",
            str(workspace_root),
            "--recipes-dir",
            str(recipes_dir),
            "scaffold-team",
            "--recipe-id",
            "tiny-team",
            "--team-id",
            "tiny",
        ]
    )
    assert recipes_command(args) == 0
    capsys.readouterr()
    assert fake_hooks["cron_api"].created == []


# ── workflows ───────────────────────────────────────────────────────────────


def test_workflows_run_then_runner_once(tmp_path, capsys, fake_hooks):
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    team_dir = workspace_root.parent / "workspace-dev-team"
    workflows_dir = team_dir / "shared-context" / "workflows"
    workflows_dir.mkdir(parents=True)
    (workflows_dir / "marketing.workflow.json").write_text(
        json.dumps(
            {
                "id": "marketing-v1",
                "name": "Marketing v1",
                "nodes": [
                    {"id": "start", "kind": "start"},
                    {
                        "id": "draft",
                        "kind": "llm",
                        "assignedTo": {"agentId": "dev-team-lead"},
                        "action": {},
                    },
                ],
                "edges": [{"from": "start", "to": "draft"}],
            }
        ),
        encoding="utf-8",
    )

    parser = _build_parser()
    args = parser.parse_args(
        [
            "--workspace-root",
            str(workspace_root),
            "workflows",
            "run",
            "--team-id",
            "dev-team",
            "--workflow-file",
            "marketing.workflow.json",
        ]
    )
    assert recipes_command(args) == 0
    enqueue_out = json.loads(capsys.readouterr().out)
    assert enqueue_out["status"] == "queued"

    args = parser.parse_args(
        [
            "--workspace-root",
            str(workspace_root),
            "workflows",
            "runner-once",
            "--team-id",
            "dev-team",
        ]
    )
    assert recipes_command(args) == 0
    once_out = json.loads(capsys.readouterr().out)
    assert once_out["claimed"] == 1
    assert once_out["status"] == "waiting_workers"


def test_workflows_approve_and_resume_round_trip(tmp_path, capsys, fake_hooks):
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    team_dir = workspace_root.parent / "workspace-dev-team"
    shared = team_dir / "shared-context"
    (shared / "workflows").mkdir(parents=True)
    (shared / "workflows" / "wf.json").write_text(
        json.dumps(
            {
                "id": "wf",
                "nodes": [
                    {"id": "draft", "kind": "llm", "assignedTo": {"agentId": "lead"}},
                    {"id": "approve", "kind": "human_approval"},
                    {"id": "post", "kind": "tool", "assignedTo": {"agentId": "dev"}},
                ],
                "edges": [
                    {"from": "draft", "to": "approve"},
                    {"from": "approve", "to": "post"},
                ],
            }
        ),
        encoding="utf-8",
    )

    run_dir = shared / "workflow-runs" / "run-1"
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text(
        json.dumps(
            {
                "runId": "run-1",
                "teamId": "dev-team",
                "workflow": {"file": "wf.json"},
                "ticket": {"file": "work/in-progress/0001.md"},
                "status": "awaiting_approval",
                "events": [{"ts": "t0", "type": "node.completed", "nodeId": "draft"}],
                "nodeStates": {
                    "draft": {"status": "success", "ts": "t0"},
                    "approve": {"status": "waiting", "ts": "t1"},
                },
            }
        ),
        encoding="utf-8",
    )
    ticket = team_dir / "work" / "in-progress" / "0001.md"
    ticket.parent.mkdir(parents=True)
    ticket.write_text("# 0001\nStatus: in-progress\nOwner: dev\n", encoding="utf-8")
    approvals_dir = run_dir / "approvals"
    approvals_dir.mkdir()
    (approvals_dir / "approval.json").write_text(
        json.dumps(
            {"runId": "run-1", "status": "pending", "nodeId": "approve"}
        ),
        encoding="utf-8",
    )

    parser = _build_parser()
    args = parser.parse_args(
        [
            "--workspace-root",
            str(workspace_root),
            "workflows",
            "approve",
            "--team-id",
            "dev-team",
            "--run-id",
            "run-1",
            "--approved",
            "true",
        ]
    )
    assert recipes_command(args) == 0
    approve_out = json.loads(capsys.readouterr().out)
    assert approve_out["status"] == "approved"

    args = parser.parse_args(
        [
            "--workspace-root",
            str(workspace_root),
            "workflows",
            "resume",
            "--team-id",
            "dev-team",
            "--run-id",
            "run-1",
        ]
    )
    assert recipes_command(args) == 0
    resume_out = json.loads(capsys.readouterr().out)
    assert resume_out["status"] == "waiting_workers"


def test_workflows_cleanup_queues_returns_summary(tmp_path, capsys, fake_hooks):
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    parser = _build_parser()
    args = parser.parse_args(
        [
            "--workspace-root",
            str(workspace_root),
            "workflows",
            "cleanup-queues",
            "--team-id",
            "dev-team",
        ]
    )
    assert recipes_command(args) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True
    assert out["queues_processed"] == 0
