"""Ticket lifecycle transitions (take, handoff) — file moves + frontmatter patches.

Port of clawrecipes/src/lib/ticket-workflow.ts. The OpenClaw plugin used an
``assignment stubs`` lane that's been deprecated; we preserve any pre-existing
stub files but never create new ones, matching the TS behavior.
"""

import re
import shutil
from pathlib import Path
from typing import Optional

from hermes_recipes.lanes import ensure_lane_dir
from hermes_recipes.ticket_finder import find_ticket_file


_OWNER_RE = re.compile(r"^Owner:\s.*$", re.MULTILINE)
_STATUS_RE = re.compile(r"^Status:\s.*$", re.MULTILINE)
_TITLE_RE = re.compile(r"^(# .+\n)", re.MULTILINE)
_OWNER_NORMALIZE_RE = re.compile(r"[^a-z0-9_-]+")


def _normalize_owner(owner: Optional[str], default: str) -> str:
    candidate = (owner or default).strip() or default
    lowered = candidate.lower()
    safe = _OWNER_NORMALIZE_RE.sub("-", lowered).strip("-")
    return safe or default


def patch_ticket_fields(md: str, *, owner_safe: str, status: str) -> str:
    out = md
    if _OWNER_RE.search(out):
        out = _OWNER_RE.sub(f"Owner: {owner_safe}", out, count=1)
    else:
        out = _TITLE_RE.sub(lambda m: f"{m.group(1)}\nOwner: {owner_safe}\n", out, count=1)

    if _STATUS_RE.search(out):
        out = _STATUS_RE.sub(f"Status: {status}", out, count=1)
    else:
        out = _TITLE_RE.sub(lambda m: f"{m.group(1)}\nStatus: {status}\n", out, count=1)

    return out


def _transition(
    *,
    team_dir: Path | str,
    ticket: str,
    target_lane: str,
    new_owner: str,
    new_status: str,
    command_label: str,
    refuse_when_done: str,
) -> dict:
    src = find_ticket_file(team_dir=team_dir, ticket=ticket)
    if src is None:
        raise FileNotFoundError(f"Ticket not found: {ticket}")
    if f"{Path('work') / 'done'}" in str(src):
        raise ValueError(refuse_when_done)

    lane_result = ensure_lane_dir(team_dir=team_dir, lane=target_lane, command=command_label)  # type: ignore[arg-type]
    dest_dir: Path = lane_result["path"]
    dest = dest_dir / src.name

    already_in_lane = src.resolve() == dest.resolve()

    md = src.read_text(encoding="utf-8")
    next_md = patch_ticket_fields(md, owner_safe=new_owner, status=new_status)
    src.write_text(next_md, encoding="utf-8")

    if not already_in_lane:
        shutil.move(str(src), str(dest))

    return {"src_path": src, "dest_path": dest, "moved": not already_in_lane}


def take_ticket(
    *,
    team_dir: Path | str,
    ticket: str,
    owner: Optional[str] = None,
    overwrite_assignment: bool = False,
) -> dict:
    """Assign a ticket to *owner* and move it to ``work/in-progress``."""
    owner_safe = _normalize_owner(owner, default="dev")
    return _transition(
        team_dir=team_dir,
        ticket=ticket,
        target_lane="in-progress",
        new_owner=owner_safe,
        new_status="in-progress",
        command_label="hermes recipes take",
        refuse_when_done="Cannot take a done ticket (already completed)",
    )


def handoff_ticket(
    *,
    team_dir: Path | str,
    ticket: str,
    tester: Optional[str] = None,
    overwrite_assignment: bool = False,
) -> dict:
    """Assign to *tester* and move to ``work/testing`` (the QA handoff)."""
    tester_safe = _normalize_owner(tester, default="test")
    return _transition(
        team_dir=team_dir,
        ticket=ticket,
        target_lane="testing",
        new_owner=tester_safe,
        new_status="testing",
        command_label="hermes recipes handoff",
        refuse_when_done="Cannot handoff a done ticket (already completed)",
    )
