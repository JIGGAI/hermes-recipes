"""Lightweight recipe lint for common scaffolding pitfalls.

Port of clawrecipes/src/lib/recipe-lint.ts. Warnings should be actionable and
low-noise — the goal is to catch obvious team-recipe shape mistakes before
scaffold runs.
"""

import re
from dataclasses import dataclass
from typing import Literal

from hermes_recipes.recipe_frontmatter import RecipeFrontmatter

LintLevel = Literal["warn", "error"]

_ROLE_TEMPLATE_SUFFIX_RE = re.compile(r"\.(soul|agents|tools|status|notes)$")


@dataclass(frozen=True)
class RecipeLintIssue:
    level: LintLevel
    code: str
    message: str


def lint_recipe(recipe: RecipeFrontmatter) -> list[RecipeLintIssue]:
    issues: list[RecipeLintIssue] = []

    if (recipe.get("kind") or "") != "team":
        return issues

    agents = recipe.get("agents") or []
    files = recipe.get("files") or []
    templates = recipe.get("templates") or {}

    if agents and not files:
        has_role_templates = any(
            "." in key and _ROLE_TEMPLATE_SUFFIX_RE.search(key)
            for key in templates.keys()
        )
        suffix = (
            "(Detected role templates; likely meant to scaffold role files.)"
            if has_role_templates
            else ""
        )
        issues.append(
            RecipeLintIssue(
                level="warn",
                code="team.missing_files",
                message=(
                    "Team recipe has agents[] but no files[]. Per-role workspaces will be empty. "
                    "Add a files: section (e.g. SOUL.md/AGENTS.md/TOOLS.md/STATUS.md/NOTES.md) "
                    f"or rely on scaffold defaults. {suffix}"
                ).strip(),
            )
        )

    if agents and templates and files:
        base_templates = {
            str(f.get("template") or "").strip()
            for f in files
            if isinstance(f, dict)
        }
        base_templates.discard("")
        missing = [
            core
            for core in ("soul", "agents", "tools")
            if core not in base_templates
            and not any(t.endswith(f".{core}") for t in base_templates)
        ]
        if missing:
            issues.append(
                RecipeLintIssue(
                    level="warn",
                    code="team.files.missing_core_templates",
                    message=(
                        f"Team recipe files[] is missing some common templates "
                        f"({', '.join(missing)}). This may be intentional, but usually "
                        "each role should have SOUL.md/AGENTS.md/TOOLS.md at minimum."
                    ),
                )
            )

    return issues
