"""Covers hermes_recipes/scaffold.py (agent + team scaffolding)."""

from pathlib import Path

import pytest

from hermes_recipes.scaffold import (
    scaffold_agent_from_recipe,
    scaffold_team_from_recipe,
)


_AGENT_RECIPE = {
    "id": "writer",
    "kind": "agent",
    "name": "Writer",
    "templates": {
        "soul": "I am {{agentName}}, agent id {{agentId}}.",
        "agents": "# AGENTS — {{agentName}}\n\n## Role\nwriter\n",
        "tools": "# TOOLS — {{agentName}}\n",
    },
    "files": [
        {"path": "SOUL.md", "template": "soul"},
        {"path": "AGENTS.md", "template": "agents"},
        {"path": "TOOLS.md", "template": "tools"},
    ],
    "tools": {"profile": "writer", "allow": ["fs:read"]},
}


def test_scaffold_agent_renders_files_and_returns_snippet(tmp_path):
    res = scaffold_agent_from_recipe(
        _AGENT_RECIPE,
        agent_id="writer-1",
        agent_name="Writer One",
        files_root_dir=tmp_path,
        workspace_root_dir=tmp_path,
        vars={"agentId": "writer-1", "agentName": "Writer One"},
    )
    soul = (tmp_path / "SOUL.md").read_text(encoding="utf-8")
    assert "writer-1" in soul
    assert "Writer One" in soul
    assert (tmp_path / "AGENTS.md").exists()
    assert (tmp_path / "TOOLS.md").exists()
    assert res.snippet is not None
    assert res.snippet.id == "writer-1"
    assert res.snippet.identity == {"name": "Writer One"}
    assert res.snippet.tools == {"profile": "writer", "allow": ["fs:read"]}


def test_scaffold_agent_respects_update_flag(tmp_path):
    (tmp_path / "SOUL.md").write_text("prev", encoding="utf-8")
    res = scaffold_agent_from_recipe(
        _AGENT_RECIPE,
        agent_id="w",
        files_root_dir=tmp_path,
        workspace_root_dir=tmp_path,
        vars={"agentId": "w", "agentName": "W"},
        update=False,
    )
    # createOnly should refuse to overwrite
    soul_after = (tmp_path / "SOUL.md").read_text(encoding="utf-8")
    assert soul_after == "prev"
    # update=True should rewrite
    scaffold_agent_from_recipe(
        _AGENT_RECIPE,
        agent_id="w",
        files_root_dir=tmp_path,
        workspace_root_dir=tmp_path,
        vars={"agentId": "w", "agentName": "W"},
        update=True,
    )
    assert (tmp_path / "SOUL.md").read_text(encoding="utf-8") != "prev"


def test_scaffold_agent_rejects_missing_template(tmp_path):
    recipe = {
        "id": "x",
        "templates": {"soul": "hi"},
        "files": [{"path": "SOUL.md", "template": "missing"}],
    }
    with pytest.raises(ValueError, match="Missing template"):
        scaffold_agent_from_recipe(
            recipe,
            agent_id="x",
            files_root_dir=tmp_path,
            workspace_root_dir=tmp_path,
        )


# ── team scaffolding ───────────────────────────────────────────────────────


_TEAM_RECIPE = {
    "id": "dev-team-recipe",
    "kind": "team",
    "name": "Dev Team",
    "agents": [
        {"role": "lead", "name": "Lead"},
        {"role": "dev", "name": "Dev"},
        {"role": "test", "name": "Test"},
    ],
    # Per-role files use bare template names ("soul", "agents", "tools") and
    # get scaffold_team_from_recipe to look them up as "<role>.soul" etc.
    # Team-level files (shared-context/, notes/) use explicit dotted names so
    # they're not role-prefixed.
    "templates": {
        "lead.soul": "# SOUL — {{agentName}} ({{role}})\nteam: {{teamId}}\n",
        "dev.soul": "# SOUL — {{agentName}} ({{role}})\nteam: {{teamId}}\n",
        "test.soul": "# SOUL — {{agentName}} ({{role}})\nteam: {{teamId}}\n",
        "lead.agents": "# AGENTS — {{agentName}}\n",
        "dev.agents": "# AGENTS — {{agentName}}\n",
        "test.agents": "# AGENTS — {{agentName}}\n",
        "lead.tools": "# TOOLS — {{agentName}}\n",
        "dev.tools": "# TOOLS — {{agentName}}\n",
        "test.tools": "# TOOLS — {{agentName}}\n",
        "sharedContext.overview": "# shared-context — {{teamId}}\n",
        "sharedContext.notes": "# notes — {{teamId}}\n",
    },
    "files": [
        {"path": "SOUL.md", "template": "soul"},
        {"path": "AGENTS.md", "template": "agents"},
        {"path": "TOOLS.md", "template": "tools"},
        {"path": "shared-context/team-overview.md", "template": "sharedContext.overview"},
        {"path": "notes/team-overview.md", "template": "sharedContext.notes"},
    ],
    "cronJobs": [
        {"id": "loop", "schedule": "*/30 * * * *", "message": "ping"},
    ],
}


def test_scaffold_team_lays_out_directories_and_per_role_files(tmp_path):
    res = scaffold_team_from_recipe(_TEAM_RECIPE, team_id="dev-team", team_dir=tmp_path)
    # Team-level dir layout
    assert (tmp_path / "TEAM.md").exists()
    assert (tmp_path / "TICKETS.md").exists()
    assert (tmp_path / "inbox").is_dir()
    assert (tmp_path / "work" / "backlog").is_dir()
    # Per-role files
    for role in ("lead", "dev", "test"):
        role_dir = tmp_path / "roles" / role
        assert (role_dir / "SOUL.md").exists()
        assert "team: dev-team" in (role_dir / "SOUL.md").read_text(encoding="utf-8")
        assert (role_dir / "AGENTS.md").exists()
        assert (role_dir / "TOOLS.md").exists()
        # Team-level paths should NOT be duplicated per role
        assert not (role_dir / "shared-context").exists()
        assert not (role_dir / "notes").exists()
    # Team-level paths land at the team root
    assert (tmp_path / "shared-context" / "team-overview.md").exists()
    assert (tmp_path / "notes" / "team-overview.md").exists()
    # Snippets returned for each role
    assert sorted(res.role_results.keys()) == ["dev", "lead", "test"]
    assert sorted(s.id for s in res.snippets) == ["dev-team-dev", "dev-team-lead", "dev-team-test"]
    assert res.cron_jobs_declared == 1


def test_scaffold_team_auto_enables_qa_checklist_when_test_role_present(tmp_path):
    scaffold_team_from_recipe(_TEAM_RECIPE, team_id="dev-team", team_dir=tmp_path)
    assert (tmp_path / "notes" / "QA_CHECKLIST.md").exists()


def test_scaffold_team_does_not_emit_qa_checklist_without_test_role(tmp_path):
    recipe = {**_TEAM_RECIPE, "agents": [{"role": "lead"}]}
    scaffold_team_from_recipe(recipe, team_id="dev-team", team_dir=tmp_path)
    assert not (tmp_path / "notes" / "QA_CHECKLIST.md").exists()
