"""Pick an available recipe id, applying overwrite/auto-increment semantics.

Port of clawrecipes/src/lib/recipe-id.ts. The TS version is async and accepts
async callbacks; the port keeps that shape (sync callbacks are accepted too —
they get wrapped). Used by both agent and team scaffold handlers.
"""

import inspect
import os
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional, Union

from hermes_recipes.constants import MAX_RECIPE_ID_AUTO_INCREMENT

IsTakenFn = Callable[[str], Union[bool, Awaitable[bool]]]


@dataclass(frozen=True)
class PickRecipeIdOpts:
    base_id: str
    recipes_dir: str
    overwrite_recipe: bool
    auto_increment: bool
    is_taken: IsTakenFn
    get_suggestions: Callable[[str], list[str]]
    get_conflict_error: Callable[[str, list[str]], str]
    overwrite_recipe_error: Optional[Callable[[str], str]] = None


async def _is_taken(fn: IsTakenFn, candidate: str) -> bool:
    result = fn(candidate)
    if inspect.isawaitable(result):
        return bool(await result)
    return bool(result)


async def pick_recipe_id(opts: PickRecipeIdOpts) -> str:
    """Return an unused recipe id under opts.recipes_dir.

    Behavior matches the TS port:
      * If base_id is not taken, return it.
      * If overwrite_recipe is True: return base_id, but if a workspace file
        for base_id does not exist and overwrite_recipe_error is provided,
        raise it (the conflict is with a built-in recipe, not a workspace one).
      * If auto_increment is True: try base_id-2, base_id-3, ... up to
        MAX_RECIPE_ID_AUTO_INCREMENT.
      * Otherwise raise the conflict error built from get_suggestions.
    """
    if not await _is_taken(opts.is_taken, opts.base_id):
        return opts.base_id

    if opts.overwrite_recipe:
        base_path = os.path.join(opts.recipes_dir, f"{opts.base_id}.md")
        if not os.path.exists(base_path) and opts.overwrite_recipe_error is not None:
            raise ValueError(opts.overwrite_recipe_error(opts.base_id))
        return opts.base_id

    if opts.auto_increment:
        n = 2
        while n < MAX_RECIPE_ID_AUTO_INCREMENT:
            candidate = f"{opts.base_id}-{n}"
            if not await _is_taken(opts.is_taken, candidate):
                return candidate
            n += 1
        raise ValueError(
            f"No available recipe id found for {opts.base_id} (tried up to -{MAX_RECIPE_ID_AUTO_INCREMENT - 1})"
        )

    suggestions = opts.get_suggestions(opts.base_id)
    raise ValueError(opts.get_conflict_error(opts.base_id, suggestions))
