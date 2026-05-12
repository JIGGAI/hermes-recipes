"""Lint covers the surface in clawrecipes/src/lib/recipe-lint.ts."""

from hermes_recipes.recipe_lint import lint_recipe


def test_non_team_recipes_pass_clean():
    assert lint_recipe({"id": "agent", "kind": "agent"}) == []


def test_team_with_agents_but_no_files_warns():
    issues = lint_recipe(
        {
            "id": "t",
            "kind": "team",
            "agents": [{"role": "lead"}, {"role": "dev"}],
            "files": [],
            "templates": {},
        }
    )
    assert len(issues) == 1
    assert issues[0].code == "team.missing_files"


def test_team_warns_with_role_template_hint():
    issues = lint_recipe(
        {
            "id": "t",
            "kind": "team",
            "agents": [{"role": "lead"}],
            "files": [],
            "templates": {"lead.soul": "body"},
        }
    )
    assert "Detected role templates" in issues[0].message


def test_team_with_files_missing_core_templates_warns():
    issues = lint_recipe(
        {
            "id": "t",
            "kind": "team",
            "agents": [{"role": "lead"}],
            "files": [{"template": "soul", "path": "SOUL.md"}],
            "templates": {"soul": "body"},
        }
    )
    assert len(issues) == 1
    assert issues[0].code == "team.files.missing_core_templates"
    assert "agents" in issues[0].message
    assert "tools" in issues[0].message
