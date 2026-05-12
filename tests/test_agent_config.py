"""Mirrors clawrecipes/tests/agent-config.test.ts."""

from hermes_recipes.agent_config import AgentConfigSnippet, upsert_agent_in_config


def test_adds_new_agent_to_empty_list():
    cfg: dict = {"agents": {"list": []}}
    upsert_agent_in_config(cfg, AgentConfigSnippet(id="a1", workspace="/w1"))
    assert len(cfg["agents"]["list"]) == 1
    entry = cfg["agents"]["list"][0]
    assert entry["id"] == "a1"
    assert entry["workspace"] == "/w1"


def test_updates_existing_agent_in_place():
    cfg: dict = {"agents": {"list": [{"id": "a1", "workspace": "/old"}]}}
    upsert_agent_in_config(cfg, AgentConfigSnippet(id="a1", workspace="/new"))
    assert len(cfg["agents"]["list"]) == 1
    assert cfg["agents"]["list"][0]["workspace"] == "/new"


def test_deep_merges_tools_preserves_existing_deny():
    cfg: dict = {
        "agents": {
            "list": [
                {
                    "id": "a1",
                    "workspace": "/w1",
                    "tools": {"profile": "coding", "allow": ["group:fs"], "deny": ["exec"]},
                }
            ]
        }
    }
    upsert_agent_in_config(
        cfg,
        AgentConfigSnippet(id="a1", workspace="/w1", tools={"allow": ["group:web"]}),
    )
    assert cfg["agents"]["list"][0]["tools"] == {
        "profile": "coding",
        "allow": ["group:web"],
        "deny": ["exec"],
    }


def test_explicit_clearing_when_snippet_sets_deny_empty():
    cfg: dict = {
        "agents": {"list": [{"id": "a1", "workspace": "/w1", "tools": {"deny": ["exec"]}}]}
    }
    upsert_agent_in_config(
        cfg, AgentConfigSnippet(id="a1", workspace="/w1", tools={"deny": []})
    )
    assert cfg["agents"]["list"][0]["tools"] == {"deny": []}


def test_creates_agents_root_when_missing():
    cfg: dict = {}
    upsert_agent_in_config(cfg, AgentConfigSnippet(id="solo", workspace="/s"))
    assert cfg["agents"]["list"][0]["id"] == "solo"
