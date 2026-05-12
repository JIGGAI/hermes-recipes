"""Binding upsert / remove helpers (channel + peer → agent routing).

Port of the pure-logic half of clawrecipes/src/lib/recipes-config.ts. The
config I/O half (``loadOpenClawConfig`` / ``writeOpenClawConfig``) is
OpenClaw-specific and is intentionally not ported here; Phase 6 layers the
Hermes equivalent on top.

Bindings live in a list under ``cfg["bindings"]``. ``upsert_binding`` is
idempotent: same agentId + match signature is a no-op.
"""

from dataclasses import dataclass, field
from typing import Any, Literal, Optional

from hermes_recipes.stable_stringify import stable_stringify


PeerKind = Literal["dm", "group", "channel"]


@dataclass(frozen=True)
class Peer:
    kind: PeerKind
    id: str

    def to_dict(self) -> dict[str, str]:
        return {"kind": self.kind, "id": self.id}


@dataclass(frozen=True)
class BindingMatch:
    channel: str
    account_id: Optional[str] = None
    peer: Optional[Peer] = None
    guild_id: Optional[str] = None
    team_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"channel": self.channel}
        if self.account_id is not None:
            out["accountId"] = self.account_id
        if self.peer is not None:
            out["peer"] = self.peer.to_dict()
        if self.guild_id is not None:
            out["guildId"] = self.guild_id
        if self.team_id is not None:
            out["teamId"] = self.team_id
        return out


@dataclass(frozen=True)
class BindingSnippet:
    agent_id: str
    match: BindingMatch

    def to_dict(self) -> dict[str, Any]:
        return {"agentId": self.agent_id, "match": self.match.to_dict()}


def upsert_binding_in_config(cfg_obj: dict[str, Any], binding: BindingSnippet) -> dict:
    """Add or update a binding. Returns ``{"changed": bool, "note": str}``."""
    bindings = cfg_obj.get("bindings")
    if not isinstance(bindings, list):
        bindings = []
        cfg_obj["bindings"] = bindings

    snippet = binding.to_dict()
    target_sig = stable_stringify(snippet)
    for entry in bindings:
        if not isinstance(entry, dict):
            continue
        existing = {"agentId": entry.get("agentId"), "match": entry.get("match")}
        if stable_stringify(existing) == target_sig:
            # Update in place but no functional change.
            entry.update(snippet)
            return {"changed": False, "note": "already-present"}

    # Peer bindings push to the front (specific-first matching order).
    if binding.match.peer is not None:
        bindings.insert(0, snippet)
    else:
        bindings.append(snippet)
    return {"changed": True, "note": "added"}


def remove_bindings_in_config(
    cfg_obj: dict[str, Any],
    *,
    match: BindingMatch,
    agent_id: Optional[str] = None,
) -> dict:
    bindings = cfg_obj.get("bindings")
    if not isinstance(bindings, list):
        cfg_obj["bindings"] = []
        return {"removed_count": 0, "removed": []}

    target_match_sig = stable_stringify(match.to_dict())
    kept: list[Any] = []
    removed: list[Any] = []
    for entry in bindings:
        if not isinstance(entry, dict):
            kept.append(entry)
            continue
        same_agent = (
            agent_id is None or str(entry.get("agentId") or "") == agent_id
        )
        same_match = stable_stringify(entry.get("match") or {}) == target_match_sig
        if same_agent and same_match:
            removed.append(entry)
        else:
            kept.append(entry)
    cfg_obj["bindings"] = kept
    return {"removed_count": len(removed), "removed": removed}
