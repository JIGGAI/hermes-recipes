"""Covers the binding upsert/remove helpers ported from recipes-config.ts."""

from hermes_recipes.bindings import (
    BindingMatch,
    BindingSnippet,
    Peer,
    remove_bindings_in_config,
    upsert_binding_in_config,
)


def test_upsert_appends_when_no_peer():
    cfg: dict = {}
    res = upsert_binding_in_config(
        cfg,
        BindingSnippet(agent_id="lead", match=BindingMatch(channel="telegram", team_id="t")),
    )
    assert res == {"changed": True, "note": "added"}
    assert cfg["bindings"] == [
        {"agentId": "lead", "match": {"channel": "telegram", "teamId": "t"}}
    ]


def test_upsert_prepends_peer_bindings():
    cfg: dict = {
        "bindings": [
            {"agentId": "lead", "match": {"channel": "telegram", "teamId": "t"}}
        ]
    }
    upsert_binding_in_config(
        cfg,
        BindingSnippet(
            agent_id="dev",
            match=BindingMatch(channel="telegram", peer=Peer(kind="dm", id="42")),
        ),
    )
    assert cfg["bindings"][0]["agentId"] == "dev"
    assert cfg["bindings"][0]["match"]["peer"] == {"kind": "dm", "id": "42"}


def test_upsert_is_idempotent():
    cfg: dict = {}
    snippet = BindingSnippet(
        agent_id="lead", match=BindingMatch(channel="telegram", team_id="t")
    )
    upsert_binding_in_config(cfg, snippet)
    res2 = upsert_binding_in_config(cfg, snippet)
    assert res2 == {"changed": False, "note": "already-present"}
    assert len(cfg["bindings"]) == 1


def test_remove_bindings_by_match_only():
    cfg: dict = {
        "bindings": [
            {"agentId": "lead", "match": {"channel": "telegram", "teamId": "t"}},
            {"agentId": "dev", "match": {"channel": "telegram", "teamId": "t"}},
            {"agentId": "lead", "match": {"channel": "discord", "teamId": "t"}},
        ]
    }
    res = remove_bindings_in_config(
        cfg, match=BindingMatch(channel="telegram", team_id="t")
    )
    assert res["removed_count"] == 2
    assert [b["match"]["channel"] for b in cfg["bindings"]] == ["discord"]


def test_remove_bindings_by_agent_and_match():
    cfg: dict = {
        "bindings": [
            {"agentId": "lead", "match": {"channel": "telegram", "teamId": "t"}},
            {"agentId": "dev", "match": {"channel": "telegram", "teamId": "t"}},
        ]
    }
    res = remove_bindings_in_config(
        cfg, match=BindingMatch(channel="telegram", team_id="t"), agent_id="dev"
    )
    assert res["removed_count"] == 1
    assert cfg["bindings"][0]["agentId"] == "lead"
