"""Scaffold helpers — pure logic pieces shared by agent and team scaffolders.

Port of clawrecipes/src/lib/scaffold-utils.ts, minus the OpenClaw-specific
recipe loading. The recipe-loading half lands in Phase 6 once Hermes plugin
context is wired; until then callers pass an already-loaded recipe.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import yaml

from hermes_recipes.fs_utils import write_file_safely
from hermes_recipes.recipe_frontmatter import parse_frontmatter
from hermes_recipes.skill_install import detect_missing_skills, skill_install_commands


@dataclass(frozen=True)
class RecipeValidationOk:
    ok: bool
    recipe: dict[str, Any]
    body: str
    workspace_root: Path


@dataclass(frozen=True)
class RecipeValidationMissingSkills:
    ok: bool
    missing_skills: list[str]
    install_commands: list[str]


RecipeValidationResult = RecipeValidationOk | RecipeValidationMissingSkills


def validate_recipe_and_skills(
    *,
    recipe_md: str,
    expected_kind: str,
    workspace_root: Path,
    skills_dir_name: str = "skills",
) -> RecipeValidationResult:
    """Parse a recipe, enforce expected kind, and check for missing skills.

    On the OpenClaw side this also loaded the recipe by id; the Python port
    keeps that out so this helper stays pure. The caller resolves the recipe
    text up-front and passes it in.
    """
    frontmatter, body = parse_frontmatter(recipe_md)
    kind = frontmatter.get("kind") or expected_kind
    if kind != expected_kind:
        article = "an" if expected_kind == "agent" else "a"
        raise ValueError(f"Recipe is not {article} {expected_kind} recipe: kind={frontmatter.get('kind')}")

    required = frontmatter.get("requiredSkills") or []
    if not isinstance(required, list):
        raise ValueError("frontmatter.requiredSkills must be an array")
    install_dir = workspace_root / skills_dir_name
    missing = detect_missing_skills(install_dir, [str(s) for s in required])
    if missing:
        return RecipeValidationMissingSkills(
            ok=False,
            missing_skills=missing,
            install_commands=skill_install_commands(missing),
        )
    return RecipeValidationOk(
        ok=True, recipe=frontmatter, body=body, workspace_root=workspace_root
    )


def write_workspace_recipe_file(
    *,
    source_md: str,
    recipes_dir: Path | str,
    workspace_recipe_id: str,
    overwrite_recipe: bool,
) -> dict:
    """Write the per-workspace recipe copy with the chosen id.

    Rewrites the `id` (and `name`, when unset) in the YAML frontmatter to the
    workspace-local id while preserving everything else.
    """
    frontmatter, body = parse_frontmatter(source_md)
    next_fm = {
        **frontmatter,
        "id": workspace_recipe_id,
        "name": frontmatter.get("name") or workspace_recipe_id,
    }
    yaml_text = yaml.safe_dump(next_fm, sort_keys=False)
    next_md = f"---\n{yaml_text}---\n{body}"
    target = Path(recipes_dir) / f"{workspace_recipe_id}.md"
    mode = "overwrite" if overwrite_recipe else "createOnly"
    return write_file_safely(target, next_md, mode)


def recipe_id_taken_for_team(recipes_dir: Path | str, candidate: str) -> bool:
    return (Path(recipes_dir) / f"{candidate}.md").exists()


def recipe_id_taken_for_agent(
    recipes_dir: Path | str,
    candidate: str,
    *,
    builtin_recipe_ids: Optional[set[str]] = None,
) -> bool:
    """Stricter agent check: workspace file OR built-in recipe.

    The OpenClaw version calls ``loadRecipeById`` which walks both the
    workspace and the plugin's bundled recipes. We accept the bundled-id set
    as an argument so callers can plug in whichever discovery source they use
    (filesystem walk or Hermes plugin discovery).
    """
    if (Path(recipes_dir) / f"{candidate}.md").exists():
        return True
    if builtin_recipe_ids and candidate in builtin_recipe_ids:
        return True
    return False
