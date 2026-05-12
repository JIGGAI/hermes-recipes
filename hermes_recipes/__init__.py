"""hermes-recipes — port of ClawRecipes for the Hermes Agent runtime.

Phase 1 ships only pure-logic modules (DSL parser, templater, id picker, lint).
Phases 2–6 add scaffold, tickets, workflow runner, cron, and the plugin CLI.
The `register(ctx)` entrypoint is a placeholder until Phase 6 wires the CLI.
"""

from hermes_recipes.recipe_frontmatter import (
    CronJobSpec,
    RecipeFrontmatter,
    normalize_cron_jobs,
    parse_frontmatter,
)
from hermes_recipes.recipe_id import pick_recipe_id
from hermes_recipes.recipe_lint import RecipeLintIssue, lint_recipe
from hermes_recipes.template import render_template

__all__ = [
    "CronJobSpec",
    "RecipeFrontmatter",
    "RecipeLintIssue",
    "lint_recipe",
    "normalize_cron_jobs",
    "parse_frontmatter",
    "pick_recipe_id",
    "render_template",
]


def register(ctx) -> None:
    """Hermes plugin entrypoint — registers the ``hermes recipes`` command.

    Hermes calls this once per process during plugin discovery. Phase 6a
    wires the file-first ticket family (tickets / dispatch / take / handoff /
    assign / move-ticket / complete). Phase 6b will add scaffold + workflow
    commands once Hermes profile-create + cron.jobs integration land.
    """
    from hermes_recipes._cli import recipes_command, register_cli

    ctx.register_cli_command(
        name="recipes",
        help="Markdown recipes that scaffold agents, teams, and file-first workflows.",
        setup_fn=register_cli,
        handler_fn=recipes_command,
        description=(
            "Hermes-native port of ClawRecipes. Manages team tickets across "
            "backlog/in-progress/testing/done lanes on disk."
        ),
    )
