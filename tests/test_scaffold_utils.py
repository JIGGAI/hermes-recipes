"""Covers hermes_recipes/scaffold_utils.py — recipe validation and workspace recipe writing."""

import pytest

from hermes_recipes.recipe_frontmatter import parse_frontmatter
from hermes_recipes.scaffold_utils import (
    RecipeValidationMissingSkills,
    RecipeValidationOk,
    recipe_id_taken_for_agent,
    recipe_id_taken_for_team,
    validate_recipe_and_skills,
    write_workspace_recipe_file,
)


_AGENT_RECIPE = """---
id: writer
kind: agent
name: Writer
requiredSkills: []
---
Body content for the writer recipe.
"""

_TEAM_RECIPE_MISSING_SKILL = """---
id: ops
kind: team
name: Ops Team
requiredSkills:
  - "ops-runbook"
  - "incident-toolkit"
---
Body content for the team.
"""


def test_validate_recipe_returns_ok_when_no_skills_required(tmp_path):
    result = validate_recipe_and_skills(
        recipe_md=_AGENT_RECIPE, expected_kind="agent", workspace_root=tmp_path
    )
    assert isinstance(result, RecipeValidationOk)
    assert result.recipe["id"] == "writer"
    assert result.body.startswith("Body content")


def test_validate_recipe_returns_missing_skills_with_install_commands(tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "ops-runbook").mkdir()  # one present, one missing
    result = validate_recipe_and_skills(
        recipe_md=_TEAM_RECIPE_MISSING_SKILL,
        expected_kind="team",
        workspace_root=tmp_path,
    )
    assert isinstance(result, RecipeValidationMissingSkills)
    assert result.missing_skills == ["incident-toolkit"]
    assert any("hermes skills install incident-toolkit" in cmd for cmd in result.install_commands)


def test_validate_recipe_rejects_wrong_kind(tmp_path):
    with pytest.raises(ValueError, match="not an agent recipe"):
        validate_recipe_and_skills(
            recipe_md=_TEAM_RECIPE_MISSING_SKILL,
            expected_kind="agent",
            workspace_root=tmp_path,
        )


def test_write_workspace_recipe_file_create_only(tmp_path):
    out = write_workspace_recipe_file(
        source_md=_AGENT_RECIPE,
        recipes_dir=tmp_path,
        workspace_recipe_id="my-writer",
        overwrite_recipe=False,
    )
    assert out["wrote"] is True
    target = tmp_path / "my-writer.md"
    assert target.exists()
    new_fm, body = parse_frontmatter(target.read_text("utf-8"))
    assert new_fm["id"] == "my-writer"
    assert new_fm["name"] == "Writer"  # name preserved
    assert body.strip().startswith("Body content")


def test_write_workspace_recipe_file_refuses_when_exists_in_create_only(tmp_path):
    target = tmp_path / "my-writer.md"
    target.write_text("existing", encoding="utf-8")
    out = write_workspace_recipe_file(
        source_md=_AGENT_RECIPE,
        recipes_dir=tmp_path,
        workspace_recipe_id="my-writer",
        overwrite_recipe=False,
    )
    assert out == {"wrote": False, "reason": "exists"}
    assert target.read_text("utf-8") == "existing"


def test_write_workspace_recipe_file_overwrites_when_requested(tmp_path):
    target = tmp_path / "my-writer.md"
    target.write_text("existing", encoding="utf-8")
    out = write_workspace_recipe_file(
        source_md=_AGENT_RECIPE,
        recipes_dir=tmp_path,
        workspace_recipe_id="my-writer",
        overwrite_recipe=True,
    )
    assert out["wrote"] is True
    assert "id: my-writer" in target.read_text("utf-8")


def test_recipe_id_taken_helpers(tmp_path):
    (tmp_path / "foo.md").write_text("", encoding="utf-8")
    assert recipe_id_taken_for_team(tmp_path, "foo") is True
    assert recipe_id_taken_for_team(tmp_path, "bar") is False
    assert recipe_id_taken_for_agent(tmp_path, "foo") is True
    assert recipe_id_taken_for_agent(tmp_path, "bar") is False
    assert (
        recipe_id_taken_for_agent(tmp_path, "developer", builtin_recipe_ids={"developer"})
        is True
    )
