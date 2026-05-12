"""Covers hermes_recipes/integrations/."""

import subprocess
from unittest.mock import patch

import pytest

from hermes_recipes.integrations.hermes_cron import (
    HermesCronApi,
    InMemoryCronApi,
)
from hermes_recipes.integrations.hermes_profiles import (
    HermesProfileProvisioner,
    InMemoryProfileProvisioner,
)


# ── HermesProfileProvisioner ────────────────────────────────────────────────


def _completed(returncode: int = 0, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=["hermes"], returncode=returncode, stdout=stdout, stderr=stderr)


def test_hermes_profile_provisioner_create_success():
    with patch("subprocess.run", return_value=_completed(0, "created\n")) as mock_run:
        prov = HermesProfileProvisioner()
        outcome = prov.create_profile("dev-team-lead")
    mock_run.assert_called_once()
    cmd = mock_run.call_args.args[0]
    assert cmd == ["hermes", "profile", "create", "dev-team-lead"]
    assert outcome.created is True


def test_hermes_profile_provisioner_passes_clone_from():
    with patch("subprocess.run", return_value=_completed(0, "")) as mock_run:
        HermesProfileProvisioner().create_profile("dev-team-lead", clone_from="main")
    cmd = mock_run.call_args.args[0]
    assert "--clone-from" in cmd
    assert "main" in cmd


def test_hermes_profile_provisioner_existing_profile_is_idempotent():
    with patch(
        "subprocess.run",
        return_value=_completed(1, "", "Error: Profile 'lead' already exists"),
    ):
        outcome = HermesProfileProvisioner().create_profile("lead")
    assert outcome.created is False
    assert outcome.already_existed is True


def test_hermes_profile_provisioner_raises_on_unrecognized_failure():
    with patch(
        "subprocess.run",
        return_value=_completed(2, "", "Error: unable to write home dir"),
    ):
        with pytest.raises(RuntimeError, match="failed"):
            HermesProfileProvisioner().create_profile("lead")


# ── InMemoryProfileProvisioner ──────────────────────────────────────────────


def test_in_memory_profile_provisioner_records_creates():
    prov = InMemoryProfileProvisioner()
    one = prov.create_profile("a")
    two = prov.create_profile("a")  # second time → already_existed
    assert one.created is True
    assert two.already_existed is True
    assert prov.created == {"a"}
    assert prov.list_profiles() == ["a"]


# ── InMemoryCronApi ─────────────────────────────────────────────────────────


def test_in_memory_cron_api_round_trip():
    api = InMemoryCronApi()
    job = api.create_job({"name": "n", "schedule": "* * * * *", "prompt": "hi"})
    assert job["id"] == "cron-1"
    api.update_job("cron-1", {"enabled": False})
    assert api.jobs["cron-1"]["enabled"] is False
    assert api.get_job("cron-1")["id"] == "cron-1"
    assert api.get_job("cron-missing") is None
    assert [j["id"] for j in api.list_jobs()] == ["cron-1"]


# ── HermesCronApi (lazy import) ─────────────────────────────────────────────


def test_hermes_cron_api_raises_when_no_backing_module():
    # Construct directly with all-None — simulates the import-failed case.
    api = HermesCronApi(
        list_jobs_fn=None,
        create_job_fn=None,
        update_job_fn=None,
        get_job_fn=None,
    )
    with pytest.raises(RuntimeError, match="not importable"):
        api.list_jobs()
    with pytest.raises(RuntimeError, match="not available"):
        api.create_job({})


def test_hermes_cron_api_delegates_to_injected_callables():
    seen: dict = {}

    def _update(cid, patch):
        seen["update"] = (cid, dict(patch))
        return {"id": cid, **patch}

    api = HermesCronApi(
        list_jobs_fn=lambda: [{"id": "cron-99"}],
        create_job_fn=lambda payload: {"id": "cron-99", **payload},
        update_job_fn=_update,
        get_job_fn=lambda cid: {"id": cid} if cid == "cron-99" else None,
    )
    assert api.list_jobs() == [{"id": "cron-99"}]
    assert api.create_job({"name": "n"})["name"] == "n"
    api.update_job("cron-99", {"enabled": False})
    assert seen["update"] == ("cron-99", {"enabled": False})
    assert api.get_job("cron-99") == {"id": "cron-99"}
    assert api.get_job("missing") is None
