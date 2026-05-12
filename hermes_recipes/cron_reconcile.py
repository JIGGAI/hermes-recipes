"""Reconcile recipe-declared cron jobs with the host cron system.

Port of the reconciliation algorithm from clawrecipes/src/handlers/cron.ts.
The OpenClaw plugin shells out to ``openclaw cron add/edit/list``; the
Hermes port hands the same algorithm a ``CronApi`` protocol that Phase 6
wires to ``hermes_agent.cron.jobs``.
"""

import time
from dataclasses import dataclass, field
from typing import Any, Literal, Optional, Protocol

from hermes_recipes.cron_translate import HermesCronPayload, translate_recipe_cron
from hermes_recipes.cron_utils import (
    CronMappingEntry,
    CronScope,
    cron_key,
    hash_spec,
)
from hermes_recipes.recipe_frontmatter import CronJobSpec


CronAction = Literal[
    "created", "updated", "unchanged", "disabled-removed"
]


@dataclass(frozen=True)
class CronReconcileEntry:
    action: CronAction
    key: str
    installed_cron_id: str


@dataclass(frozen=True)
class CronReconcileResult:
    results: list[CronReconcileEntry] = field(default_factory=list)
    mapping: dict[str, CronMappingEntry] = field(default_factory=dict)


CronInstallMode = Literal["off", "prompt", "on"]


class CronApi(Protocol):
    """Operations the reconcile algorithm needs from the host cron system."""

    def list_jobs(self) -> list[dict[str, Any]]: ...
    def create_job(self, payload: dict[str, Any]) -> dict[str, Any]: ...
    def update_job(self, cron_id: str, patch: dict[str, Any]) -> dict[str, Any]: ...
    def get_job(self, cron_id: str) -> Optional[dict[str, Any]]: ...


def _index_jobs_by_id(jobs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(j.get("id")): j for j in jobs if isinstance(j.get("id"), str)}


def _hashable_spec(payload: HermesCronPayload) -> dict[str, Any]:
    """Return only the fields that should drive the spec hash."""
    out = payload.to_dict()
    # ``enabled`` is reconciled separately (install mode / orphan disable), not
    # part of the spec identity.
    out.pop("enabled", None)
    return out


def reconcile_recipe_cron_jobs(
    *,
    api: CronApi,
    scope: CronScope,
    recipe_cron_jobs: list[CronJobSpec],
    state: dict[str, CronMappingEntry],
    install_mode: CronInstallMode = "on",
) -> CronReconcileResult:
    """Reconcile *recipe_cron_jobs* against the host's cron system.

    Algorithm (matches the OpenClaw plugin):
      1. Determine desired ``enabled`` per job: ``install_mode == "on"`` honors
         ``spec.enabled_by_default``; ``"prompt"`` or ``"off"`` defaults to
         disabled (Phase 6 wires the interactive prompt).
      2. For each job, compute the Hermes payload + spec hash.
      3. If the job is in *state* and its hash matches, mark ``unchanged``.
      4. If the job is in *state* but its hash drifted, call ``update_job``.
      5. If the job is new, call ``create_job``.
      6. After all desired jobs are processed, sweep ``state`` for entries
         that belong to this recipe but are NOT in the new desired set — those
         are orphans, set ``enabled=False`` via ``update_job`` and mark the
         mapping entry as ``orphaned``.
    """
    results: list[CronReconcileEntry] = []
    mapping: dict[str, CronMappingEntry] = dict(state)
    desired_ids: set[str] = set()
    now_ms = int(time.time() * 1000)

    if install_mode == "off":
        return CronReconcileResult(results=results, mapping=mapping)

    existing = _index_jobs_by_id(api.list_jobs())

    for spec in recipe_cron_jobs:
        desired_ids.add(spec.id)
        key = cron_key(scope, spec.id)

        want_enabled = (
            spec.enabled_by_default if install_mode == "on" else False
        )
        payload = translate_recipe_cron(
            scope=scope, spec=spec, want_enabled=want_enabled
        )
        spec_hash = hash_spec(_hashable_spec(payload))

        prev = mapping.get(key)
        if prev is not None and prev.installed_cron_id in existing:
            if prev.spec_hash == spec_hash and not prev.orphaned:
                results.append(
                    CronReconcileEntry(
                        action="unchanged",
                        key=key,
                        installed_cron_id=prev.installed_cron_id,
                    )
                )
                continue
            patch = payload.to_dict()
            api.update_job(prev.installed_cron_id, patch)
            mapping[key] = CronMappingEntry(
                installed_cron_id=prev.installed_cron_id,
                spec_hash=spec_hash,
                updated_at_ms=now_ms,
                orphaned=False,
            )
            results.append(
                CronReconcileEntry(
                    action="updated",
                    key=key,
                    installed_cron_id=prev.installed_cron_id,
                )
            )
            continue

        created = api.create_job(payload.to_dict())
        cron_id = str(created.get("id") or "")
        if not cron_id:
            raise RuntimeError(f"create_job did not return an id for {key}")
        mapping[key] = CronMappingEntry(
            installed_cron_id=cron_id,
            spec_hash=spec_hash,
            updated_at_ms=now_ms,
            orphaned=False,
        )
        results.append(
            CronReconcileEntry(action="created", key=key, installed_cron_id=cron_id)
        )

    # Sweep orphans: mapping entries for this recipe that aren't desired.
    for key, entry in list(mapping.items()):
        if f":recipe:{scope.recipe_id}:cron:" not in key:
            continue
        cron_id_token = key.rsplit(":cron:", 1)[-1]
        if cron_id_token in desired_ids:
            continue
        job = existing.get(entry.installed_cron_id)
        if job and job.get("enabled"):
            api.update_job(entry.installed_cron_id, {"enabled": False})
            results.append(
                CronReconcileEntry(
                    action="disabled-removed",
                    key=key,
                    installed_cron_id=entry.installed_cron_id,
                )
            )
        # If the orphaned job is already disabled, we just mark mapping
        # orphaned below without emitting a result — matches the TS semantics.
        mapping[key] = CronMappingEntry(
            installed_cron_id=entry.installed_cron_id,
            spec_hash=entry.spec_hash,
            updated_at_ms=now_ms,
            orphaned=True,
        )

    return CronReconcileResult(results=results, mapping=mapping)
