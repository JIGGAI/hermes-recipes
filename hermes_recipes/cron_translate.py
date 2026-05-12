"""Translate a recipe ``CronJobSpec`` into a Hermes-cron job payload.

The OpenClaw plugin builds a payload for ``openclaw cron add``; Hermes uses
``cron.jobs.create_job`` from hermes-agent. The shapes differ — Hermes jobs
are keyed by ``profile`` (not ``agentId``) and use a flat ``prompt`` field
instead of OpenClaw's ``payload.{agentTurn|systemEvent}`` discriminated union.

Recipe template variables (``{{recipeId}}``, ``{{teamId}}``, ``{{agentId}}``)
are interpolated here so the caller can hand the result straight to Hermes
without further processing.
"""

from dataclasses import dataclass
from typing import Any, Optional

from hermes_recipes.cron_utils import CronScope
from hermes_recipes.recipe_frontmatter import CronJobSpec
from hermes_recipes.template import render_template


def _interpolate(value: Optional[str], variables: dict[str, str]) -> Optional[str]:
    if value is None:
        return None
    return render_template(value, variables)


@dataclass(frozen=True)
class HermesCronPayload:
    """Job payload accepted by Hermes ``cron.jobs.create_job``/``update_job``."""

    name: str
    schedule: str
    prompt: str
    profile: Optional[str]
    description: str = ""
    timezone: Optional[str] = None
    enabled: bool = True
    timeout_seconds: Optional[int] = None
    delivery: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "name": self.name,
            "schedule": self.schedule,
            "prompt": self.prompt,
            "description": self.description,
            "enabled": self.enabled,
        }
        if self.profile is not None:
            out["profile"] = self.profile
        if self.timezone is not None:
            out["timezone"] = self.timezone
        if self.timeout_seconds is not None:
            out["timeout_seconds"] = self.timeout_seconds
        if self.delivery is not None:
            out["delivery"] = self.delivery
        return out


def translate_recipe_cron(
    *,
    scope: CronScope,
    spec: CronJobSpec,
    want_enabled: bool,
) -> HermesCronPayload:
    """Apply template vars and produce a Hermes cron payload from a recipe spec.

    The mapping rules:
      - ``spec.agent_id`` (template-rendered) → ``profile``. If empty, defaults
        to ``<teamId>-lead`` (team scope) or ``agent_id`` (agent scope).
      - ``spec.message`` → ``prompt``.
      - ``spec.delivery``:
          - ``"none"`` (default): no delivery block
          - ``"announce"`` (or ``channel``/``to`` present): announce + best-effort
    """
    variables = scope.template_vars()
    name = _interpolate(spec.name, variables) or (
        f"{scope.team_id or scope.agent_id} • {scope.recipe_id} • {spec.id}"
    )
    schedule = _interpolate(spec.schedule, variables) or ""
    timezone = _interpolate(spec.timezone, variables)
    channel = _interpolate(spec.channel, variables)
    to = _interpolate(spec.to, variables)
    raw_agent = _interpolate(spec.agent_id, variables)
    agent_id = raw_agent.strip() if isinstance(raw_agent, str) and raw_agent.strip() else None
    description = _interpolate(spec.description, variables) or ""
    message = _interpolate(spec.message, variables) or ""

    if agent_id is None:
        if scope.kind == "team" and scope.team_id:
            agent_id = f"{scope.team_id}-lead"
        elif scope.kind == "agent" and scope.agent_id:
            agent_id = scope.agent_id

    delivery: Optional[dict[str, Any]]
    if spec.delivery == "none":
        delivery = {"mode": "none"}
    elif spec.delivery == "announce" or channel or to:
        delivery = {"mode": "announce", "bestEffort": True}
        if channel:
            delivery["channel"] = channel
        if to:
            delivery["to"] = to
    else:
        # Match the OpenClaw plugin: default to "none" so isolated agent crons
        # don't fail when no channel target is available.
        delivery = {"mode": "none"}

    return HermesCronPayload(
        name=name,
        schedule=schedule,
        prompt=message,
        profile=agent_id,
        description=description,
        timezone=timezone,
        enabled=want_enabled,
        timeout_seconds=spec.timeout_seconds,
        delivery=delivery,
    )
