"""Ticket file discovery, parsing, and numbering helpers.

Port of clawrecipes/src/lib/ticket-finder.ts. Pure file I/O on the lane
directories — no Hermes API dependencies.
"""

import re
from pathlib import Path
from typing import Iterable, Literal, Optional

from hermes_recipes.lanes import ticket_stage_dir

TicketLane = Literal["backlog", "in-progress", "testing", "done"]

LANE_SEARCH_ORDER: tuple[TicketLane, ...] = ("backlog", "in-progress", "testing", "done")

# Ticket filenames are 0001-some-slug.md.
TICKET_FILENAME_RE = re.compile(r"^(\d{4})-(.+)\.md$")


def lane_dir(team_dir: Path | str, lane: TicketLane) -> Path:
    return ticket_stage_dir(team_dir, lane)


def all_lane_dirs(team_dir: Path | str) -> list[Path]:
    return [ticket_stage_dir(team_dir, lane) for lane in LANE_SEARCH_ORDER]


def parse_ticket_filename(filename: str) -> Optional[dict[str, str]]:
    m = TICKET_FILENAME_RE.match(filename)
    if not m:
        return None
    return {"ticket_num_str": m.group(1), "slug": m.group(2)}


def parse_ticket_arg(ticket_arg_raw: str) -> dict[str, Optional[str]]:
    """Normalize a CLI ticket argument.

    Accepts shorthand like ``"30"`` (treated as ``"0030"``) and ids like
    ``"0007-some-ticket"``. Returns ``{ticket_arg, ticket_num}``;
    ``ticket_num`` is ``None`` when the arg has no leading 4-digit id.
    """
    raw = (ticket_arg_raw or "").strip()
    padded = raw.zfill(4) if raw.isdigit() and len(raw) < 4 else raw
    if re.fullmatch(r"\d{4}", padded):
        return {"ticket_arg": padded, "ticket_num": padded}
    m = re.match(r"^(\d{4})-", padded)
    return {"ticket_arg": padded, "ticket_num": m.group(1) if m else None}


def find_ticket_file(
    *,
    team_dir: Path | str,
    ticket: str,
    lanes: Optional[Iterable[TicketLane]] = None,
) -> Optional[Path]:
    search_lanes = tuple(lanes) if lanes is not None else LANE_SEARCH_ORDER
    parsed = parse_ticket_arg(ticket)
    ticket_arg = parsed["ticket_arg"]
    ticket_num = parsed["ticket_num"]

    for lane in search_lanes:
        d = lane_dir(team_dir, lane)
        if not d.exists():
            continue
        for entry in sorted(d.iterdir()):
            if not entry.name.endswith(".md"):
                continue
            if ticket_num and entry.name.startswith(f"{ticket_num}-"):
                return entry
            if not ticket_num and entry.name[: -len(".md")] == ticket_arg:
                return entry
    return None


def compute_next_ticket_number(team_dir: Path | str) -> int:
    """Return the next available ticket number (max existing + 1)."""
    max_num = 0
    for lane in LANE_SEARCH_ORDER:
        d = lane_dir(team_dir, lane)
        if not d.exists():
            continue
        for entry in d.iterdir():
            m = TICKET_FILENAME_RE.match(entry.name)
            if m:
                max_num = max(max_num, int(m.group(1)))
    return max_num + 1


def parse_owner_from_md(md: str) -> Optional[str]:
    m = re.search(r"^Owner:\s*(.+)\s*$", md, flags=re.MULTILINE)
    if not m:
        return None
    return m.group(1).strip() or None
