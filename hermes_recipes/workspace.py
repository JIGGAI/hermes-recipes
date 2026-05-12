"""Hermes-flavored workspace resolution.

Replaces clawrecipes/src/lib/workspace.ts. The TS module is OpenClaw-specific
(``api.config.agents?.defaults?.workspace`` + ``OPENCLAW_WORKSPACE`` env +
``~/.openclaw/workspace`` default). This Python module follows the same
*shape* but resolves against Hermes:

  1. explicit ``workspace_root`` argument (caller-injected from Hermes config)
  2. ``HERMES_RECIPES_WORKSPACE`` env var
  3. default: ``~/.hermes/recipes/workspace``

The OpenClaw plugin remains the source of truth on OpenClaw; this module is
purely the Hermes equivalent and never reads the OpenClaw config.
"""

import os
from pathlib import Path
from typing import Optional

DEFAULT_HERMES_RECIPES_WORKSPACE_ENV = "HERMES_RECIPES_WORKSPACE"
DEFAULT_HERMES_RECIPES_TEAM_DIR_ENV = "HERMES_RECIPES_TEAM_DIR"


def default_hermes_home() -> Path:
    """Return ``~/.hermes`` — same convention Hermes Agent itself uses."""
    return Path.home() / ".hermes"


def resolve_workspace_root(
    *,
    explicit: Optional[str] = None,
    env: Optional[dict[str, str]] = None,
    hermes_home: Optional[Path] = None,
) -> Path:
    """Resolve the recipes workspace root.

    Args:
        explicit: workspace path coming from Hermes config (preferred).
        env: optional environment mapping (defaults to ``os.environ``).
        hermes_home: override for ``~/.hermes`` (tests).
    """
    if explicit:
        return Path(explicit).expanduser()
    env_map = env if env is not None else os.environ
    env_root = env_map.get(DEFAULT_HERMES_RECIPES_WORKSPACE_ENV)
    if env_root:
        return Path(env_root).expanduser()
    home = hermes_home or default_hermes_home()
    return home / "recipes" / "workspace"


def _try_resolve_team_dir_from_any_dir(start: Path | str, team_id: str) -> Optional[Path]:
    seg = f"workspace-{team_id}"
    abs_path = Path(start).expanduser().resolve()
    parts = abs_path.parts
    # Walk from leaf to root, find last occurrence of the workspace-<teamId> segment.
    indices = [i for i, p in enumerate(parts) if p == seg]
    if indices:
        idx = indices[-1]
        return Path(*parts[: idx + 1])
    return None


def resolve_team_dir(
    team_id: str,
    *,
    workspace_root: Optional[Path] = None,
    explicit_team_dir: Optional[str] = None,
    env: Optional[dict[str, str]] = None,
    cwd: Optional[Path] = None,
) -> Path:
    """Resolve the ``workspace-<teamId>`` directory.

    Mirrors the TS logic: prefer env override, then look for the workspace-<id>
    segment in the explicit workspace root, then in the current working
    directory, then fall back to ``<workspace_root>/../workspace-<teamId>``.
    """
    env_map = env if env is not None else os.environ
    env_team_dir = env_map.get(DEFAULT_HERMES_RECIPES_TEAM_DIR_ENV)
    if env_team_dir:
        return Path(env_team_dir).expanduser().resolve()

    if workspace_root is not None:
        resolved = _try_resolve_team_dir_from_any_dir(workspace_root, team_id)
        if resolved is not None:
            return resolved

    cwd_resolved = _try_resolve_team_dir_from_any_dir(cwd or Path.cwd(), team_id)
    if cwd_resolved is not None:
        return cwd_resolved

    root = workspace_root or resolve_workspace_root(env=env_map)
    return (root.parent / f"workspace-{team_id}").resolve()


def ensure_ticket_stage_dirs(team_dir: Path | str) -> None:
    from hermes_recipes.lanes import ticket_stage_dir

    base = Path(team_dir)
    (base / "work").mkdir(parents=True, exist_ok=True)
    for stage in ("backlog", "in-progress", "testing", "done", "assignments"):
        ticket_stage_dir(base, stage).mkdir(parents=True, exist_ok=True)  # type: ignore[arg-type]


def resolve_team_context(
    team_id: str,
    *,
    workspace_root: Optional[Path] = None,
    env: Optional[dict[str, str]] = None,
) -> dict:
    """Return ``{"workspace_root", "team_dir"}`` after ensuring lane dirs."""
    team_dir = resolve_team_dir(
        team_id, workspace_root=workspace_root, env=env
    )
    # Canonical workspace root is the sibling of workspace-<teamId>.
    canonical_root = (team_dir.parent / "workspace").resolve()
    ensure_ticket_stage_dirs(team_dir)
    return {"workspace_root": canonical_root, "team_dir": team_dir}
