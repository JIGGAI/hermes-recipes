"""Verify the bundled recipes ship with the package and parse cleanly."""

from pathlib import Path

import pytest

import hermes_recipes
from hermes_recipes.recipe_frontmatter import normalize_cron_jobs, parse_frontmatter
from hermes_recipes.recipe_loader import list_recipe_ids, load_recipe_md
from hermes_recipes.scaffold import scaffold_team_from_recipe


BUNDLED_DIR = Path(hermes_recipes.__file__).parent / "bundled_recipes"


def test_bundled_dir_exists_and_includes_default_recipes():
    assert BUNDLED_DIR.is_dir(), f"bundled_recipes/ must ship with the package"
    ids = list_recipe_ids([BUNDLED_DIR])
    assert "development-team" in ids
    assert "marketing-team" in ids


def test_each_bundled_recipe_parses_and_declares_team_kind():
    for recipe_id in ("development-team", "marketing-team"):
        loaded = load_recipe_md(recipe_id, recipe_dirs=[BUNDLED_DIR])
        frontmatter, body = parse_frontmatter(loaded.md)
        assert frontmatter.get("id") == recipe_id
        assert frontmatter.get("kind") == "team"
        assert isinstance(frontmatter.get("agents"), list) and frontmatter["agents"], (
            f"{recipe_id} must declare a non-empty agents[] list"
        )
        normalize_cron_jobs(frontmatter)  # cron specs must be valid


def test_bundled_recipes_have_no_residual_openclaw_references():
    """Sanity check: the port should not leak `openclaw recipes`-style
    command references into bundled recipes."""
    for recipe_id in ("development-team", "marketing-team"):
        text = (BUNDLED_DIR / f"{recipe_id}.md").read_text(encoding="utf-8")
        assert "openclaw recipes" not in text
        assert "openclaw cron" not in text
        assert "openclaw gateway" not in text


def test_scaffold_development_team_from_bundled(tmp_path):
    loaded = load_recipe_md("development-team", recipe_dirs=[BUNDLED_DIR])
    frontmatter, _ = parse_frontmatter(loaded.md)
    result = scaffold_team_from_recipe(frontmatter, team_id="dev", team_dir=tmp_path)
    # Sanity-check the shape — 5 roles, declared cron jobs visible.
    assert set(result.role_results.keys()) == {"lead", "dev", "devops", "test", "workflow-runner"}
    assert sorted(s.id for s in result.snippets) == [
        "dev-dev",
        "dev-devops",
        "dev-lead",
        "dev-test",
        "dev-workflow-runner",
    ]
    assert result.cron_jobs_declared >= 8  # 9 in the recipe; allow drift
    # Role-prefixed templates resolved — lead/SOUL.md gets lead.soul content.
    lead_soul = (tmp_path / "roles" / "lead" / "SOUL.md").read_text(encoding="utf-8")
    assert "Team Lead" in lead_soul
    dev_soul = (tmp_path / "roles" / "dev" / "SOUL.md").read_text(encoding="utf-8")
    assert "Software Engineer" in dev_soul
    # Per-role continuity bootstrap.
    assert (tmp_path / "roles" / "lead" / "MEMORY.md").exists()
    assert (tmp_path / "roles" / "lead" / "agent-outputs" / "README.md").exists()
    # Team-level bootstrap.
    assert (tmp_path / "TEAM.md").exists()
    assert (tmp_path / "work" / "backlog").is_dir()


def test_scaffold_marketing_team_from_bundled(tmp_path):
    loaded = load_recipe_md("marketing-team", recipe_dirs=[BUNDLED_DIR])
    frontmatter, _ = parse_frontmatter(loaded.md)
    result = scaffold_team_from_recipe(frontmatter, team_id="marketing", team_dir=tmp_path)
    # 12 roles, all marketing-* agent ids
    assert len(result.role_results) == 12
    expected_roles = {
        "lead", "seo", "copywriter", "ads", "social", "designer",
        "analyst", "video", "compliance", "offer", "funnel", "lifecycle",
    }
    assert set(result.role_results.keys()) == expected_roles
    for role in expected_roles:
        assert (tmp_path / "roles" / role / "SOUL.md").exists()
        assert (tmp_path / "roles" / role / "MEMORY.md").exists()


def test_bundled_recipes_resolved_via_default_cli_path(tmp_path):
    """The CLI's _resolve_recipe_dirs adds the package's bundled_recipes/ to
    the end of the lookup path; new users should be able to scaffold a team
    without passing --recipes-dir."""
    from hermes_recipes._cli import _resolve_recipe_dirs

    class _Args:
        workspace_root = str(tmp_path)
        recipes_dir = None

    dirs = _resolve_recipe_dirs(_Args())
    assert BUNDLED_DIR in [d.resolve() for d in dirs]
