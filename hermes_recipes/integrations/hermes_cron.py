"""Bridge :class:`hermes_recipes.cron_reconcile.CronApi` to Hermes's cron module.

The :class:`HermesCronApi` adapter loads ``hermes_agent.cron.jobs`` (or the
hermes-agent equivalent — Hermes Agent's package layout exposes ``cron.jobs``)
and surfaces the four operations the reconciler needs. Tests use
:class:`InMemoryCronApi` to avoid touching the real cron store.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Optional


class HermesCronApi:
    """Adapter that wraps the Hermes cron module behind the :class:`CronApi` shape.

    Hermes exposes :mod:`cron.jobs` (a flat module — not under a package) with
    functions like ``create_job``, ``update_job``, ``delete_job``, ``list_jobs``.
    Each function signature varies slightly, so the adapter accepts injected
    callables; the default factory imports the module lazily so that hermes-
    recipes stays importable in environments without ``hermes_agent`` installed.
    """

    def __init__(
        self,
        *,
        list_jobs_fn: Optional[Callable[[], list[dict[str, Any]]]] = None,
        create_job_fn: Optional[Callable[[dict[str, Any]], dict[str, Any]]] = None,
        update_job_fn: Optional[Callable[[str, dict[str, Any]], dict[str, Any]]] = None,
        get_job_fn: Optional[Callable[[str], Optional[dict[str, Any]]]] = None,
    ) -> None:
        if list_jobs_fn is None and create_job_fn is None and update_job_fn is None:
            list_jobs_fn, create_job_fn, update_job_fn, get_job_fn = _import_hermes_cron()
        self._list = list_jobs_fn
        self._create = create_job_fn
        self._update = update_job_fn
        self._get = get_job_fn or (lambda _id: None)

    def list_jobs(self) -> list[dict[str, Any]]:
        if self._list is None:
            raise RuntimeError("hermes_agent.cron.jobs is not importable")
        return list(self._list() or [])

    def create_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self._create is None:
            raise RuntimeError("hermes_agent.cron.jobs.create_job is not available")
        return dict(self._create(payload) or {})

    def update_job(self, cron_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        if self._update is None:
            raise RuntimeError("hermes_agent.cron.jobs.update_job is not available")
        return dict(self._update(cron_id, patch) or {})

    def get_job(self, cron_id: str) -> Optional[dict[str, Any]]:
        return self._get(cron_id) if self._get else None


def _import_hermes_cron() -> tuple[Optional[Callable], Optional[Callable], Optional[Callable], Optional[Callable]]:
    """Best-effort import of Hermes's cron module.

    Returns a 4-tuple of (list_jobs, create_job, update_job, get_job) callables,
    each of which may be ``None`` if the underlying function isn't found. Caller
    is responsible for surfacing the missing-symbol error at call time.
    """
    try:
        from cron import jobs as _jobs  # type: ignore[import-not-found]
    except ImportError:
        return (None, None, None, None)
    list_fn = getattr(_jobs, "list_jobs", None) or getattr(_jobs, "load_jobs", None)
    create_fn = getattr(_jobs, "create_job", None)
    update_fn = getattr(_jobs, "update_job", None)
    get_fn = getattr(_jobs, "get_job", None)
    return (list_fn, create_fn, update_fn, get_fn)


@dataclass
class InMemoryCronApi:
    """In-process implementation of :class:`CronApi` for tests and dry runs."""

    jobs: dict[str, dict[str, Any]] = field(default_factory=dict)
    _counter: int = 0
    created: list[dict[str, Any]] = field(default_factory=list)
    updates: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    def list_jobs(self) -> list[dict[str, Any]]:
        return list(self.jobs.values())

    def create_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._counter += 1
        cron_id = f"cron-{self._counter}"
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
