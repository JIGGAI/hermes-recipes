"""Mirrors clawrecipes/tests/frontmatter.test.ts."""

import pytest

from hermes_recipes.recipe_frontmatter import normalize_cron_jobs, parse_frontmatter


def test_parse_frontmatter_requires_starting_marker_and_id():
    with pytest.raises(ValueError, match="must start with YAML frontmatter"):
        parse_frontmatter("nope")

    md = "---\nname: x\n---\nbody"
    with pytest.raises(ValueError, match="must include id"):
        parse_frontmatter(md)


def test_parse_frontmatter_returns_body():
    md = "---\nid: foo\n---\nhello body"
    fm, body = parse_frontmatter(md)
    assert fm["id"] == "foo"
    assert body == "hello body"


def test_normalize_cron_jobs_validates_required_and_duplicates():
    assert normalize_cron_jobs({}) == []

    with pytest.raises(ValueError, match="must be an array"):
        normalize_cron_jobs({"cronJobs": {}})

    with pytest.raises(ValueError, match=r"Duplicate cronJobs\[\]\.id"):
        normalize_cron_jobs(
            {
                "cronJobs": [
                    {"id": "a", "schedule": "* * * * *", "message": "hi"},
                    {"id": "a", "schedule": "* * * * *", "message": "hi"},
                ]
            }
        )

    with pytest.raises(ValueError, match="schedule is required"):
        normalize_cron_jobs(
            {"cronJobs": [{"id": "x", "schedule": "", "message": "m"}]}
        )
    with pytest.raises(ValueError, match="message is required"):
        normalize_cron_jobs(
            {"cronJobs": [{"id": "x", "schedule": "* * * * *", "message": ""}]}
        )

    out = normalize_cron_jobs(
        {"cronJobs": [{"id": "job", "schedule": "* * * * *", "message": "ping"}]}
    )
    assert len(out) == 1
    assert out[0].id == "job"
    assert out[0].message == "ping"


def test_normalize_cron_jobs_message_fallbacks():
    with_task = normalize_cron_jobs(
        {"cronJobs": [{"id": "t", "schedule": "* * * * *", "task": "run task"}]}
    )
    assert with_task[0].message == "run task"

    with_prompt = normalize_cron_jobs(
        {"cronJobs": [{"id": "p", "schedule": "* * * * *", "prompt": "run prompt"}]}
    )
    assert with_prompt[0].message == "run prompt"

    message_wins = normalize_cron_jobs(
        {
            "cronJobs": [
                {"id": "m", "schedule": "* * * * *", "message": "msg", "task": "task"}
            ]
        }
    )
    assert message_wins[0].message == "msg"


def test_normalize_cron_jobs_passes_through_optional_fields():
    out = normalize_cron_jobs(
        {
            "cronJobs": [
                {
                    "id": "full",
                    "schedule": "0 9 * * *",
                    "message": "hi",
                    "name": "Morning ping",
                    "timezone": "America/New_York",
                    "agentId": "team-lead",
                    "enabledByDefault": True,
                    "delivery": "announce",
                    "timeoutSeconds": 1800,
                }
            ]
        }
    )
    spec = out[0]
    assert spec.name == "Morning ping"
    assert spec.timezone == "America/New_York"
    assert spec.agent_id == "team-lead"
    assert spec.enabled_by_default is True
    assert spec.delivery == "announce"
    assert spec.timeout_seconds == 1800


def test_normalize_cron_jobs_rejects_invalid_delivery_and_timeout():
    out = normalize_cron_jobs(
        {
            "cronJobs": [
                {
                    "id": "bad",
                    "schedule": "* * * * *",
                    "message": "hi",
                    "delivery": "carrier-pigeon",
                    "timeoutSeconds": -5,
                }
            ]
        }
    )
    assert out[0].delivery is None
    assert out[0].timeout_seconds is None
