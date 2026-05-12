"""Build and upsert agent entries into a Hermes-side agent index.

Port of clawrecipes/src/lib/agent-config.ts. The TS version writes into
OpenClaw's ``agents.list``. Here the function is platform-neutral: it mutates
any mapping whose ``agents.list`` matches the same shape. Phase 6 wires the
output into Hermes — typically into ``~/.hermes/recipes/recipe-agents.json``
or directly into a Hermes config slot once the plugin context lands.
"""

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class AgentConfigSnippet:
    id: str
    workspace: str
    identity: Optional[dict[str, Any]] = None
    tools: Optional[dict[str, Any]] = None


def _normalize_tools(prev_tools: Any) -> Optional[dict[str, Any]]:
    if not isinstance(prev_tools, dict):
        return None
    out: dict[str, Any] = {}
    if isinstance(prev_tools.get("profile"), str):
        out["profile"] = prev_tools["profile"]
    if isinstance(prev_tools.get("allow"), list):
        out["allow"] = list(prev_tools["allow"])
    if isinstance(prev_tools.get("deny"), list):
        out["deny"] = list(prev_tools["deny"])
    return out


def upsert_agent_in_config(cfg_obj: dict[str, Any], snippet: AgentConfigSnippet) -> None:
    """Idempotent in-place upsert of an agent record.

    Tools are deep-merged: keys present in *snippet.tools* override prev tools
    (including explicit empty lists, which clear the field), while keys absent
    from *snippet.tools* are preserved from the previous record.
    """
    agents = cfg_obj.setdefault("agents", {})
    if not isinstance(agents, dict):
        cfg_obj["agents"] = {}
        agents = cfg_obj["agents"]
    if not isinstance(agents.get("list"), list):
        agents["list"] = []
    agent_list: list[dict[str, Any]] = agents["list"]

    idx = next(
        (i for i, a in enumerate(agent_list) if isinstance(a, dict) and a.get("id") == snippet.id),
        -1,
    )
    prev: dict[str, Any] = agent_list[idx] if idx >= 0 else {}

    prev_tools = _normalize_tools(prev.get("tools"))
    if snippet.tools is None:
        next_tools = prev_tools
    else:
        # Start from prev_tools, then override with the snippet's explicit keys
        # (including empty-list values).
        merged: dict[str, Any] = dict(prev_tools or {})
        merged.update(snippet.tools)
        next_tools = merged

    next_agent: dict[str, Any] = {
        **prev,
        "id": snippet.id,
        "workspace": snippet.workspace,
        "identity": {**(prev.get("identity") or {}), **(snippet.identity or {})},
        "tools": next_tools,
    }

    if idx >= 0:
        agent_list[idx] = next_agent
    else:
        agent_list.append(next_agent)
