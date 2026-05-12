"""Covers hermes_recipes/cron_utils.py."""

import json

import pytest

from hermes_recipes.cron_utils import (
    CronMappingEntry,
    CronScope,
    cron_key,
    hash_spec,
    load_cron_mapping_state,
    parse_tool_text_json,
    save_cron_mapping_state,
)


def test_load_returns_empty_when_file_missing(tmp_path):
    assert load_cron_mapping_state(tmp_path / "missing.json") == {}


def test_load_skips_bad_version(tmp_path):
    p = tmp_path / "cron.json"
    p.write_text(json.dumps({"version": 0, "entries": {}}), encoding="utf-8")
    assert load_cron_mapping_state(p) == {}


def test_save_then_load_round_trip(tmp_path):
    p = tmp_path / "cron.json"
    entries = {
        "team:dev-team:recipe:r:cron:loop": CronMappingEntry(
            installed_cron_id="cron-1",
            spec_hash="abc",
            updated_at_ms=1700000000000,
        )
    }
    save_cron_mapping_state(p, entries)
    loaded = load_cron_mapping_state(p)
    assert loaded == entries


def test_cron_key_uses_scope():
    team_scope = CronScope(
        kind="team", team_id="dev-team", recipe_id="r", state_dir=...  # type: ignore[arg-type]
    )
    agent_scope = CronScope(
        kind="agent", agent_id="alice", recipe_id="r", state_dir=...  # type: ignore[arg-type]
    )
    assert cron_key(team_scope, "loop") == "team:dev-team:recipe:r:cron:loop"
    assert cron_key(agent_scope, "loop") == "agent:alice:recipe:r:cron:loop"


def test_cron_key_raises_when_id_missing():
    scope = CronScope(kind="team", recipe_id="r", state_dir=...)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        cron_key(scope, "loop")


def test_hash_spec_is_stable_under_key_order():
    a = {"b": 2, "a": 1, "c": [1, 2, 3]}
    b = {"a": 1, "c": [1, 2, 3], "b": 2}
    assert hash_spec(a) == hash_spec(b)


def test_parse_tool_text_json_handles_empty_and_invalid():
    assert parse_tool_text_json("", "label") is None
    assert parse_tool_text_json(None, "label") is None
    assert parse_tool_text_json('{"a": 1}', "label") == {"a": 1}
    with pytest.raises(ValueError, match="Failed parsing JSON"):
        parse_tool_text_json("not-json", "label")
