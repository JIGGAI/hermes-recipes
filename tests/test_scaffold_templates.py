"""Smoke tests for the static scaffold templates."""

from hermes_recipes.scaffold_templates import render_team_md, render_tickets_md


def test_render_team_md_includes_team_id_and_lanes():
    out = render_team_md("my-team")
    assert out.startswith("# my-team")
    for lane in ("backlog", "in-progress", "testing", "done"):
        assert f"work/{lane}/" in out


def test_render_tickets_md_documents_qa_handoff():
    out = render_tickets_md("my-team")
    assert "Tickets — my-team" in out
    assert "Owner: dev" in out
    assert "Owner: test" in out
    assert "QA handoff" in out
