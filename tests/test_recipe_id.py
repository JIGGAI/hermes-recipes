"""Mirrors clawrecipes/tests/recipe-id.test.ts."""

import os
import tempfile

import pytest

from hermes_recipes.recipe_id import PickRecipeIdOpts, pick_recipe_id


async def test_returns_base_id_when_not_taken(tmp_path):
    result = await pick_recipe_id(
        PickRecipeIdOpts(
            base_id="free-id",
            recipes_dir=str(tmp_path),
            overwrite_recipe=False,
            auto_increment=False,
            is_taken=lambda _id: False,
            get_suggestions=lambda _id: ["a", "b"],
            get_conflict_error=lambda i, s: f"Conflict: {i} ({', '.join(s)})",
        )
    )
    assert result == "free-id"


async def test_returns_base_id_when_overwrite_true(tmp_path):
    # File exists -> overwrite is OK without overwrite_recipe_error.
    (tmp_path / "taken-id.md").write_text("", encoding="utf-8")
    result = await pick_recipe_id(
        PickRecipeIdOpts(
            base_id="taken-id",
            recipes_dir=str(tmp_path),
            overwrite_recipe=True,
            auto_increment=False,
            is_taken=lambda _id: True,
            get_suggestions=lambda _id: [],
            get_conflict_error=lambda _i, _s: "",
        )
    )
    assert result == "taken-id"


async def test_overwrite_raises_when_id_taken_by_non_workspace(tmp_path):
    # No file at builtin-id.md, but is_taken returns True (taken by built-in).
    with pytest.raises(ValueError, match="Non-workspace: builtin-id"):
        await pick_recipe_id(
            PickRecipeIdOpts(
                base_id="builtin-id",
                recipes_dir=str(tmp_path),
                overwrite_recipe=True,
                auto_increment=False,
                is_taken=lambda _id: True,
                get_suggestions=lambda _id: [],
                get_conflict_error=lambda _i, _s: "",
                overwrite_recipe_error=lambda i: f"Non-workspace: {i}",
            )
        )


async def test_auto_increment_finds_free_slot(tmp_path):
    (tmp_path / "base-id.md").write_text("", encoding="utf-8")

    def is_taken(candidate: str) -> bool:
        return os.path.exists(tmp_path / f"{candidate}.md")

    result = await pick_recipe_id(
        PickRecipeIdOpts(
            base_id="base-id",
            recipes_dir=str(tmp_path),
            overwrite_recipe=False,
            auto_increment=True,
            is_taken=is_taken,
            get_suggestions=lambda _id: [],
            get_conflict_error=lambda _i, _s: "",
        )
    )
    assert result == "base-id-2"


async def test_throws_conflict_when_neither_flag_set(tmp_path):
    with pytest.raises(ValueError, match=r"Exists: taken → taken-v2"):
        await pick_recipe_id(
            PickRecipeIdOpts(
                base_id="taken",
                recipes_dir=str(tmp_path),
                overwrite_recipe=False,
                auto_increment=False,
                is_taken=lambda _id: True,
                get_suggestions=lambda i: [f"{i}-v2"],
                get_conflict_error=lambda i, s: f"Exists: {i} → {', '.join(s)}",
            )
        )


async def test_accepts_async_is_taken(tmp_path):
    async def async_is_taken(_candidate: str) -> bool:
        return False

    result = await pick_recipe_id(
        PickRecipeIdOpts(
            base_id="async-id",
            recipes_dir=str(tmp_path),
            overwrite_recipe=False,
            auto_increment=False,
            is_taken=async_is_taken,
            get_suggestions=lambda _id: [],
            get_conflict_error=lambda _i, _s: "",
        )
    )
    assert result == "async-id"
