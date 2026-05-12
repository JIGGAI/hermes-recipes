"""Covers hermes_recipes/recipe_loader.py."""

import pytest

from hermes_recipes.recipe_loader import (
    find_recipe_path,
    list_recipe_ids,
    load_recipe_md,
)


def test_load_recipe_md_returns_first_hit(tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    (a / "foo.md").write_text("from-a", encoding="utf-8")
    (b / "foo.md").write_text("from-b", encoding="utf-8")
    loaded = load_recipe_md("foo", recipe_dirs=[a, b])
    assert loaded.md == "from-a"
    assert loaded.path == a / "foo.md"


def test_load_recipe_md_raises_when_missing(tmp_path):
    with pytest.raises(FileNotFoundError, match="Recipe not found"):
        load_recipe_md("missing", recipe_dirs=[tmp_path])


def test_find_recipe_path_returns_none_when_missing(tmp_path):
    assert find_recipe_path("missing", recipe_dirs=[tmp_path]) is None


def test_list_recipe_ids_unions_and_deduplicates(tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    (a / "x.md").write_text("", encoding="utf-8")
    (a / "y.md").write_text("", encoding="utf-8")
    (b / "x.md").write_text("", encoding="utf-8")  # dup
    (b / "z.md").write_text("", encoding="utf-8")
    out = list_recipe_ids([a, b])
    assert sorted(out) == ["x", "y", "z"]


def test_list_recipe_ids_skips_non_directory(tmp_path):
    assert list_recipe_ids([tmp_path / "nope"]) == []
