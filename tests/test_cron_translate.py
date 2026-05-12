"""Covers hermes_recipes/cron_translate.py."""

from pathlib import Path

from hermes_recipes.cron_translate import translate_recipe_cron
from hermes_recipes.cron_utils import CronScope
from hermes_recipes.recipe_frontmatter import CronJobSpec


def _team_scope() -> CronScope:
    return CronScope(
        kind="team",
        team_id="dev-team",
        recipe_id="development-team",
        state_dir=Path("/tmp"),
    )


def test_translate_defaults_profile_to_team_lead():
    spec = CronJobSpec(id="loop", schedule="*/30 * * * *", message="ping")
    out = translate_recipe_cron(scope=_team_scope(), spec=spec, want_enabled=True)
    assert out.profile == "dev-team-lead"
    assert out.schedule == "*/30 * * * *"
    assert out.prompt == "ping"
    assert out.delivery == {"mode": "none"}
    assert out.enabled is True


def test_translate_interpolates_template_vars():
    spec = CronJobSpec(
        id="loop",
        schedule="*/30 * * * *",
        message="hi {{teamId}}",
        agent_id="{{teamId}}-dev",
        name="{{teamId}} • loop",
    )
    out = translate_recipe_cron(scope=_team_scope(), spec=spec, want_enabled=False)
    assert out.profile == "dev-team-dev"
    assert out.name == "dev-team • loop"
    assert out.prompt == "hi dev-team"
    assert out.enabled is False


def test_translate_announce_delivery_with_channel():
    spec = CronJobSpec(
        id="loop",
        schedule="*/30 * * * *",
        message="ping",
        channel="telegram",
        to="@team-chat",
        delivery="announce",
    )
    out = translate_recipe_cron(scope=_team_scope(), spec=spec, want_enabled=True)
    assert out.delivery == {
        "mode": "announce",
        "bestEffort": True,
        "channel": "telegram",
        "to": "@team-chat",
    }


def test_translate_passes_timeout_seconds():
    spec = CronJobSpec(
        id="loop",
        schedule="*/30 * * * *",
        message="ping",
        timeout_seconds=1800,
    )
    out = translate_recipe_cron(scope=_team_scope(), spec=spec, want_enabled=True)
    assert out.timeout_seconds == 1800
    assert out.to_dict()["timeout_seconds"] == 1800
