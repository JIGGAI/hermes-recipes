"""Ticket handler-level operations — list / move / assign / dispatch / complete.

Port of clawrecipes/src/handlers/tickets.ts plus the dispatch handler from
clawrecipes/index.ts. OpenClaw-specific hooks (``api.runtime.system.enqueueSystemEvent``,
``scheduleManifestRegeneration``) are exposed as optional callbacks so the
file-first work is testable in isolation.
"""

import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Literal, Optional

from hermes_recipes.constants import VALID_ROLES, VALID_STAGES
from hermes_recipes.fs_utils import ensure_dir, write_file_safely
from hermes_recipes.lanes import ticket_stage_dir
from hermes_recipes.ticket_finder import (
    TICKET_FILENAME_RE,
    compute_next_ticket_number,
    find_ticket_file,
)

Stage = Literal["backlog", "in-progress", "testing", "done"]

NudgeFn = Callable[[str, dict], None]
ManifestRegenFn = Callable[[], None]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _patch_field(md: str, key: str, value: str) -> str:
    line_re = re.compile(rf"^{re.escape(key)}:\s.*$", re.MULTILINE)
    if line_re.search(md):
        return line_re.sub(f"{key}: {value}", md, count=1)
    title_re = re.compile(r"^(# .+\n)", re.MULTILINE)
    return title_re.sub(lambda m: f"{m.group(1)}\n{key}: {value}\n", md, count=1)


def patch_ticket_field(md: str, key: str, value: str) -> str:
    return _patch_field(md, key, value)


def patch_ticket_owner(md: str, owner: str) -> str:
    return _patch_field(md, "Owner", owner)


def patch_ticket_status(md: str, status: str) -> str:
    return _patch_field(md, "Status", status)


@dataclass(frozen=True)
class TicketRow:
    stage: Stage
    number: Optional[int]
    id: str
    file: Path


def _read_tickets_in_lane(team_dir: Path, stage: Stage) -> list[TicketRow]:
    d = ticket_stage_dir(team_dir, stage)
    if not d.exists():
        return []
    rows: list[TicketRow] = []
    for entry in sorted(d.iterdir()):
        if not entry.name.endswith(".md"):
            continue
        m = TICKET_FILENAME_RE.match(entry.name)
        if m:
            rows.append(
                TicketRow(
                    stage=stage,
                    number=int(m.group(1)),
                    id=f"{m.group(1)}-{m.group(2)}",
                    file=entry,
                )
            )
        else:
            rows.append(
                TicketRow(stage=stage, number=None, id=entry.stem, file=entry)
            )
    return rows


def list_tickets(team_dir: Path | str) -> dict:
    """Read every ticket file across the four lanes and group them by stage."""
    base = Path(team_dir)
    backlog = _read_tickets_in_lane(base, "backlog")
    in_progress = _read_tickets_in_lane(base, "in-progress")
    testing = _read_tickets_in_lane(base, "testing")
    done = _read_tickets_in_lane(base, "done")
    return {
        "tickets": [*backlog, *in_progress, *testing, *done],
        "backlog": backlog,
        "in_progress": in_progress,
        "testing": testing,
        "done": done,
    }


def move_ticket(
    *,
    team_dir: Path | str,
    ticket: str,
    to: Stage,
    completed: bool = False,
    dry_run: bool = False,
    on_manifest_regen: Optional[ManifestRegenFn] = None,
) -> dict:
    if to not in VALID_STAGES:
        raise ValueError("to must be one of: backlog, in-progress, testing, done")
    base = Path(team_dir)
    src = find_ticket_file(team_dir=base, ticket=ticket)
    if src is None:
        raise FileNotFoundError(f"Ticket not found: {ticket}")

    dest_dir = ticket_stage_dir(base, to)
    ensure_dir(dest_dir)
    dest = dest_dir / src.name
    plan = {"from": src, "to": dest}
    if dry_run:
        return {"ok": True, "plan": plan}

    next_status = {
        "backlog": "queued",
        "in-progress": "in-progress",
        "testing": "testing",
        "done": "done",
    }[to]

    md = src.read_text(encoding="utf-8")
    patched = patch_ticket_status(md, next_status)
    if to == "done" and completed:
        completed_iso = _now_iso()
        completed_re = re.compile(r"^Completed:\s.*$", re.MULTILINE)
        if completed_re.search(patched):
            patched = completed_re.sub(f"Completed: {completed_iso}", patched, count=1)
        else:
            status_re = re.compile(r"^Status:.*$", re.MULTILINE)
            patched = status_re.sub(
                lambda m: f"{m.group(0)}\nCompleted: {completed_iso}", patched, count=1
            )
    src.write_text(patched, encoding="utf-8")
    if src.resolve() != dest.resolve():
        shutil.move(str(src), str(dest))

    if on_manifest_regen is not None:
        try:
            on_manifest_regen()
        except Exception:
            pass

    return {"ok": True, "from": src, "to": dest}


def assign_ticket(
    *,
    team_dir: Path | str,
    ticket: str,
    owner: str,
    dry_run: bool = False,
) -> dict:
    if owner not in VALID_ROLES:
        raise ValueError("owner must be one of: dev, devops, lead, test")
    base = Path(team_dir)
    src = find_ticket_file(team_dir=base, ticket=ticket)
    if src is None:
        raise FileNotFoundError(f"Ticket not found: {ticket}")
    plan = {"ticket_path": src, "owner": owner}
    if dry_run:
        return {"ok": True, "plan": plan}
    md = src.read_text(encoding="utf-8")
    src.write_text(patch_ticket_owner(md, owner), encoding="utf-8")
    return {"ok": True, "plan": plan}


def _slugify(text: str, *, fallback: str = "request", max_length: int = 60) -> str:
    lowered = text.lower()
    cleaned = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    return (cleaned[:max_length] or fallback)


def _now_key() -> str:
    d = datetime.now()
    return f"{d.year}-{d.month:02d}-{d.day:02d}-{d.hour:02d}{d.minute:02d}"


def dispatch_request(
    *,
    team_dir: Path | str,
    team_id: str,
    request_text: str,
    owner: str = "dev",
    dry_run: bool = False,
    on_nudge: Optional[NudgeFn] = None,
    on_manifest_regen: Optional[ManifestRegenFn] = None,
) -> dict:
    """Create an inbox entry + numbered backlog ticket for a new request."""
    if owner not in VALID_ROLES:
        raise ValueError("owner must be one of: dev, devops, lead, test")
    cleaned = (request_text or "").strip()
    if not cleaned:
        raise ValueError("Request cannot be empty")

    base = Path(team_dir)
    inbox_dir = base / "inbox"
    backlog_dir = ticket_stage_dir(base, "backlog")
    ticket_num = compute_next_ticket_number(base)
    ticket_num_str = f"{ticket_num:04d}"
    title = cleaned if len(cleaned) <= 80 else cleaned[:77] + "…"
    base_slug = _slugify(title)

    inbox_path = inbox_dir / f"{_now_key()}-{base_slug}.md"
    ticket_path = backlog_dir / f"{ticket_num_str}-{base_slug}.md"
    received_iso = _now_iso()

    inbox_md = (
        f"# Inbox — {team_id}\n\n"
        f"Received: {received_iso}\n\n"
        f"## Request\n{cleaned}\n\n"
        f"## Proposed work\n"
        f"- Ticket: {ticket_num_str}-{base_slug}\n"
        f"- Owner: {owner}\n\n"
        f"## Links\n"
        f"- Ticket: {ticket_path.relative_to(base)}\n"
    )
    ticket_md = (
        f"# {ticket_num_str}-{base_slug}\n\n"
        f"Created: {received_iso}\n"
        f"Owner: {owner}\n"
        f"Status: queued\n"
        f"Inbox: {inbox_path.relative_to(base)}\n\n"
        f"## Context\n{cleaned}\n\n"
        f"## Requirements\n- (fill in)\n\n"
        f"## Acceptance criteria\n- (fill in)\n\n"
        f"## Tasks\n- [ ] (fill in)\n\n"
        f"## Comments\n- (use this section for @mentions, questions, decisions, and dated replies)\n"
    )

    plan = {
        "team_id": team_id,
        "request": cleaned,
        "files": [
            {"path": inbox_path, "kind": "inbox", "summary": title},
            {"path": ticket_path, "kind": "backlog-ticket", "summary": title},
        ],
    }
    if dry_run:
        return {"ok": True, "plan": plan}

    ensure_dir(inbox_dir)
    ensure_dir(backlog_dir)
    write_file_safely(inbox_path, inbox_md, "createOnly")
    write_file_safely(ticket_path, ticket_md, "createOnly")

    nudge_queued = False
    if on_nudge is not None:
        try:
            lead_agent_id = f"{team_id}-lead"
            on_nudge(
                "\n".join(
                    [
                        f"Dispatch created new intake for team: {team_id}",
                        f"- Inbox: {inbox_path.relative_to(base)}",
                        f"- Backlog: {ticket_path.relative_to(base)}",
                        "Action: please triage/normalize the ticket (fill Requirements/AC/tasks) and move it through the workflow.",
                    ]
                ),
                {"session_key": f"agent:{lead_agent_id}:main"},
            )
            nudge_queued = True
        except Exception:
            nudge_queued = False

    if on_manifest_regen is not None:
        try:
            on_manifest_regen()
        except Exception:
            pass

    return {
        "ok": True,
        "wrote": [str(f["path"]) for f in plan["files"]],
        "nudge_queued": nudge_queued,
    }
