"""Covers hermes_recipes/cron_reconcile.py."""

from pathlib import Path
from typing import Any, Optional

import pytest

from hermes_recipes.cron_reconcile import (
    CronReconcileEntry,
    reconcile_recipe_cron_jobs,
)
from hermes_recipes.cron_utils import CronMappingEntry, CronScope, cron_key
from hermes_recipes.recipe_frontmatter import CronJobSpec


class FakeCronApi:
    """In-memory cron backend for tests."""

    def __init__(self) -> None:
        self.jobs: dict[str, dict[str, Any]] = {}
        self.counter = 0
        self.created: list[dict[str, Any]] = []
        self.updates: list[tuple[str, dict[str, Any]]] = []

    def list_jobs(self) -> list[dict[str, Any]]:
        return list(self.jobs.values())

    def create_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.counter += 1
        cron_id = f"cron-{self.counter}"
        job = {"id": cron_id, **payload}
        self.jobs[cron_id] = job
        self.created.append(job)
        return job

    def update_job(self, cron_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        job = self.jobs.setdefault(cron_id, {"id": cron_id})
        job.update(patch)
        self.updates.append((cron_id, dict(patch)))
        return job

    def get_job(self, cron_id: str) -> Optional[dict[str, Any]]:
        return self.jobs.get(cron_id)


def _scope() -> CronScope:
    return CronScope(
        kind="team",
        team_id="dev-team",
        recipe_id="development-team",
        state_dir=Path("/tmp"),
    )


def test_creates_jobs_when_state_empty():
    api = FakeCronApi()
    spec = CronJobSpec(id="loop", schedule="*/30 * * * *", message="ping")
    result = reconcile_recipe_cron_jobs(
        api=api, scope=_scope(), recipe_cron_jobs=[spec], state={}
    )
    actions = [r.action for r in result.results]
    assert actions == ["created"]
    assert len(api.created) == 1
    key = cron_key(_scope(), "loop")
    assert result.mapping[key].installed_cron_id == "cron-1"
    assert result.mapping[key].orphaned is False


def test_unchanged_when_hash_matches():
    api = FakeCronApi()
    spec = CronJobSpec(id="loop", schedule="*/30 * * * *", message="ping")
    first = reconcile_recipe_cron_jobs(
        api=api, scope=_scope(), recipe_cron_jobs=[spec], state={}
    )
    second = reconcile_recipe_cron_jobs(
        api=api, scope=_scope(), recipe_cron_jobs=[spec], state=first.mapping
    )
    assert [r.action for r in second.results] == ["unchanged"]
    assert len(api.created) == 1
    assert api.updates == []


def test_updates_when_spec_drifts():
    api = FakeCronApi()
    spec_v1 = CronJobSpec(id="loop", schedule="*/30 * * * *", message="ping")
    first = reconcile_recipe_cron_jobs(
        api=api, scope=_scope(), recipe_cron_jobs=[spec_v1], state={}
    )
    spec_v2 = CronJobSpec(id="loop", schedule="0 9 * * *", message="ping")
    second = reconcile_recipe_cron_jobs(
        api=api, scope=_scope(), recipe_cron_jobs=[spec_v2], state=first.mapping
    )
    actions = [r.action for r in second.results]
    assert actions == ["updated"]
    assert len(api.updates) == 1
    cron_id, patch = api.updates[0]
    assert cron_id == "cron-1"
    assert patch["schedule"] == "0 9 * * *"


def test_orphan_sweep_disables_jobs_no_longer_declared():
    api = FakeCronApi()
    # enabled_by_default=True so the sweep actually has to flip enabled=False.
    spec_a = CronJobSpec(
        id="loop-a", schedule="*/30 * * * *", message="ping a", enabled_by_default=True
    )
    spec_b = CronJobSpec(
        id="loop-b", schedule="*/30 * * * *", message="ping b", enabled_by_default=True
    )
    first = reconcile_recipe_cron_jobs(
        api=api, scope=_scope(), recipe_cron_jobs=[spec_a, spec_b], state={}
    )
    # Drop loop-b from the recipe; sweep should disable it.
    second = reconcile_recipe_cron_jobs(
        api=api, scope=_scope(), recipe_cron_jobs=[spec_a], state=first.mapping
    )
    actions = sorted(r.action for r in second.results)
    assert actions == ["disabled-removed", "unchanged"]
    key_b = cron_key(_scope(), "loop-b")
    orphan_entry = second.mapping.get(key_b)
    assert orphan_entry is not None
    assert orphan_entry.orphaned is True


def test_orphan_sweep_is_quiet_when_job_already_disabled():
    api = FakeCronApi()
    # enabled_by_default defaults to False — sweep should NOT emit "disabled"
    # since there's no API call to make (matches the TS no-result-when-already-off).
    spec = CronJobSpec(id="loop", schedule="*/30 * * * *", message="ping")
    first = reconcile_recipe_cron_jobs(
        api=api, scope=_scope(), recipe_cron_jobs=[spec], state={}
    )
    second = reconcile_recipe_cron_jobs(
        api=api, scope=_scope(), recipe_cron_jobs=[], state=first.mapping
    )
    # No result entries; mapping is still marked orphaned.
    assert second.results == []
    key = cron_key(_scope(), "loop")
    assert second.mapping[key].orphaned is True


def test_install_mode_off_is_a_no_op():
    api = FakeCronApi()
    spec = CronJobSpec(
        id="loop", schedule="*/30 * * * *", message="ping", enabled_by_default=True
    )
    result = reconcile_recipe_cron_jobs(
        api=api,
        scope=_scope(),
        recipe_cron_jobs=[spec],
        state={},
        install_mode="off",
    )
    assert result.results == []
    assert api.created == []


def test_install_mode_prompt_defaults_to_disabled_for_new_jobs():
    api = FakeCronApi()
    spec = CronJobSpec(
        id="loop", schedule="*/30 * * * *", message="ping", enabled_by_default=True
    )
    result = reconcile_recipe_cron_jobs(
        api=api,
        scope=_scope(),
        recipe_cron_jobs=[spec],
        state={},
        install_mode="prompt",
    )
    assert [r.action for r in result.results] == ["created"]
    assert api.created[0]["enabled"] is False
