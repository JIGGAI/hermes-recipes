"""Mirrors clawrecipes/tests/template.test.ts."""

from hermes_recipes.template import render_template


def test_replaces_key_with_vars_value():
    assert render_template("Hello {{name}}!", {"name": "World"}) == "Hello World!"


def test_replaces_multiple_placeholders():
    assert render_template("{{a}} and {{b}}", {"a": "one", "b": "two"}) == "one and two"


def test_uses_empty_string_for_missing_key():
    assert render_template("Hello {{missing}}!", {}) == "Hello !"


def test_handles_key_with_dots_and_hyphens():
    assert render_template("{{foo.bar-baz}}", {"foo.bar-baz": "ok"}) == "ok"


def test_tolerates_whitespace_inside_braces():
    # The TS regex allows internal whitespace, so we match.
    assert render_template("{{ name }}", {"name": "Ada"}) == "Ada"
