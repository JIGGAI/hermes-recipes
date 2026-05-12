"""Provision Hermes profiles for recipe-scaffolded agents.

In OpenClaw, recipe agents map to entries in ``agents.list[]``. In Hermes the
durable equivalent is **a profile** — ``hermes profile create <agentId>``
produces an isolated config / sessions / skills / memory / cron / credentials
namespace per agent. Team scaffolding provisions one profile per role.

The :class:`HermesProfileProvisioner` shells out to the ``hermes`` CLI; tests
inject :class:`InMemoryProfileProvisioner` to avoid the subprocess.
"""

import subprocess
from dataclasses import dataclass, field
from typing import Optional, Protocol


@dataclass(frozen=True)
class ProfileCreateResult:
    name: str
    created: bool
    already_existed: bool = False
    message: Optional[str] = None


class ProfileProvisioner(Protocol):
    def create_profile(
        self, name: str, *, clone_from: Optional[str] = None
    ) -> ProfileCreateResult: ...

    def list_profiles(self) -> list[str]: ...


class HermesProfileProvisioner:
    """Default implementation — invokes ``hermes profile`` over subprocess.

    Idempotent: a "profile exists" failure on the CLI side surfaces as
    ``already_existed=True`` rather than raising.
    """

    def __init__(self, hermes_bin: str = "hermes", timeout: float = 30.0) -> None:
        self.hermes_bin = hermes_bin
        self.timeout = timeout

    def _run(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [self.hermes_bin, *args],
            capture_output=True,
            text=True,
            timeout=self.timeout,
            check=False,
        )

    def create_profile(
        self, name: str, *, clone_from: Optional[str] = None
    ) -> ProfileCreateResult:
        cmd = ["profile", "create", name]
        if clone_from:
            cmd.extend(["--clone-from", clone_from])
        result = self._run(cmd)
        combined = (result.stdout or "") + "\n" + (result.stderr or "")
        if result.returncode == 0:
            return ProfileCreateResult(name=name, created=True, message=combined.strip() or None)
        # Treat "already exists" as success — `hermes profile create` exits non-zero
        # in that case but the desired end state is reached.
        if "already exists" in combined.lower() or "exists" in combined.lower():
            return ProfileCreateResult(
                name=name,
                created=False,
                already_existed=True,
                message=combined.strip() or None,
            )
        raise RuntimeError(
            f"`hermes profile create {name}` failed (code={result.returncode}): {combined.strip()}"
        )

    def list_profiles(self) -> list[str]:
        result = self._run(["profile", "list"])
        if result.returncode != 0:
            return []
        lines = (result.stdout or "").splitlines()
        return [line.strip() for line in lines if line.strip()]


class InMemoryProfileProvisioner:
    """In-memory ``ProfileProvisioner`` for tests and ``--dry-run`` scaffolds."""

    def __init__(self) -> None:
        self._profiles: set[str] = set()

    @property
    def created(self) -> set[str]:
        return set(self._profiles)

    def create_profile(
        self, name: str, *, clone_from: Optional[str] = None
    ) -> ProfileCreateResult:
        if name in self._profiles:
            return ProfileCreateResult(name=name, created=False, already_existed=True)
        self._profiles.add(name)
        return ProfileCreateResult(name=name, created=True)

    def list_profiles(self) -> list[str]:
        return sorted(self._profiles)
