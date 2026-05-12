"""Ticket lane directory layout.

Port of clawrecipes/src/lib/lanes.ts. Lanes are the four canonical work
states (backlog/in-progress/testing/done) plus the deprecated *assignments*
holding pen. Phase 3 layers a kanban-backed delegate on top, but the on-disk
layout is preserved for compatibility with existing recipe workspaces.
"""

from pathlib import Path
from typing import Literal, Optional

TicketStage = Literal["backlog", "in-progress", "testing", "done", "assignments"]
TicketLane = Literal["backlog", "in-progress", "testing", "done"]


class RecipesCliError(Exception):
    """Actionable CLI error mirroring the TS class.

    Carries ``code``, ``command``, ``missing_path``, and ``suggested_fix`` for
    downstream formatting; falls back to a plain string message otherwise.
    """

    def __init__(
        self,
        *,
        message: str,
        code: str,
        command: Optional[str] = None,
        missing_path: Optional[str] = None,
        suggested_fix: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.command = command
        self.missing_path = missing_path
        self.suggested_fix = suggested_fix


def ticket_stage_dir(team_dir: Path | str, stage: TicketStage) -> Path:
    base = Path(team_dir) / "work"
    return base / stage


def ensure_lane_dir(
    *,
    team_dir: Path | str,
    lane: TicketLane,
    command: Optional[str] = None,
    quiet: bool = False,
) -> dict:
    lane_dir = Path(team_dir) / "work" / lane
    existed = lane_dir.exists()
    if not existed:
        try:
            lane_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            cmd_part = f" (command: {command})" if command else ""
            raise RecipesCliError(
                code="LANE_DIR_CREATE_FAILED",
                command=command,
                missing_path=str(lane_dir),
                suggested_fix=f"mkdir -p work/{lane}",
                message=(
                    f"Failed to create required lane directory: {lane_dir}{cmd_part}"
                    f"\nUnderlying error: {e}"
                ),
            ) from e
        if not quiet:
            import sys

            print(
                f"[recipes] migration: created work/{lane}/ (older workspace missing this lane)",
                file=sys.stderr,
            )
    return {"path": lane_dir, "created": not existed}
