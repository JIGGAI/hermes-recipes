"""Mirrors clawrecipes/tests/outbound-sanitize.test.ts."""

from hermes_recipes.workflows.outbound_sanitize import sanitize_outbound_post_text


def test_removes_disclaimers_and_preserves_body():
    input_text = "\n".join(
        [
            "Draft only — do not post without approval.",
            "",
            "Hook line",
            "",
            "Body line 1",
            "Body line 2",
        ]
    )
    expected = "\n".join(["Hook line", "", "Body line 1", "Body line 2"])
    assert sanitize_outbound_post_text(input_text) == expected


def test_collapses_extra_blank_lines():
    input_text = "\n".join(
        [
            "Internal only",
            "",
            "",
            "Hello world",
            "",
            "",
            "",
            "Do not publish",
            "",
        ]
    )
    assert sanitize_outbound_post_text(input_text) == "Hello world"


def test_handles_none_and_empty():
    assert sanitize_outbound_post_text(None) == ""
    assert sanitize_outbound_post_text("") == ""
    assert sanitize_outbound_post_text("   \n\n") == ""
