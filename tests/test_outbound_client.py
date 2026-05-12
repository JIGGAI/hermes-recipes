"""Covers hermes_recipes/workflows/outbound_client.py."""

import json

import pytest

from hermes_recipes.workflows.outbound_client import (
    OutboundApproval,
    OutboundMedia,
    OutboundPublishRequest,
    OutboundRunContext,
    outbound_publish,
)


def _build_request() -> OutboundPublishRequest:
    return OutboundPublishRequest(
        text="hello world",
        run_context=OutboundRunContext(
            team_id="dev-team",
            workflow_id="wf-1",
            workflow_run_id="run-1",
            node_id="post",
            ticket_path="work/in-progress/0001-x.md",
        ),
        media=[OutboundMedia(url="https://cdn/example.png", type="image")],
        approval=OutboundApproval(binding_id="telegram:home", code="abcd"),
    )


def test_outbound_publish_happy_path_posts_expected_payload():
    captured: dict = {}

    def transport(method, url, headers, body):
        captured["method"] = method
        captured["url"] = url
        captured["headers"] = headers
        captured["body"] = json.loads(body)
        return 200, json.dumps({"ok": True, "platform": "x", "id": "post-42"})

    res = outbound_publish(
        base_url="https://outbound.example.com",
        api_key="secret-key",
        platform="x",
        idempotency_key="idem-1",
        request=_build_request(),
        transport=transport,
    )
    assert res.ok is True
    assert res.id == "post-42"
    assert captured["url"] == "https://outbound.example.com/v1/x/publish"
    assert captured["headers"]["authorization"] == "Bearer secret-key"
    assert captured["headers"]["idempotency-key"] == "idem-1"
    assert captured["body"]["text"] == "hello world"
    assert captured["body"]["runContext"]["teamId"] == "dev-team"
    assert captured["body"]["media"][0]["url"] == "https://cdn/example.png"
    assert captured["body"]["approval"]["bindingId"] == "telegram:home"


def test_outbound_publish_strips_trailing_slash_from_base_url():
    captured: dict = {}

    def transport(method, url, headers, body):
        captured["url"] = url
        return 200, json.dumps({"ok": True, "platform": "x"})

    outbound_publish(
        base_url="https://outbound.example.com/",
        api_key="k",
        platform="x",
        idempotency_key="i",
        request=_build_request(),
        transport=transport,
    )
    assert captured["url"] == "https://outbound.example.com/v1/x/publish"


def test_outbound_publish_rejects_non_http_base_url():
    with pytest.raises(ValueError, match="http"):
        outbound_publish(
            base_url="example.com",
            api_key="k",
            platform="x",
            idempotency_key="i",
            request=_build_request(),
            transport=lambda *_: (200, "{}"),
        )


def test_outbound_publish_rejects_empty_api_key():
    with pytest.raises(ValueError, match="apiKey is required"):
        outbound_publish(
            base_url="https://outbound",
            api_key="",
            platform="x",
            idempotency_key="i",
            request=_build_request(),
            transport=lambda *_: (200, "{}"),
        )


def test_outbound_publish_raises_on_non_2xx():
    def transport(*_args):
        return 500, '{"ok": false, "error": "boom"}'

    with pytest.raises(RuntimeError, match="Outbound publish failed"):
        outbound_publish(
            base_url="https://outbound",
            api_key="k",
            platform="x",
            idempotency_key="i",
            request=_build_request(),
            transport=transport,
        )


def test_outbound_publish_raises_on_ok_false():
    def transport(*_args):
        return 200, '{"ok": false, "error": "rate-limit", "message": "try again"}'

    with pytest.raises(RuntimeError, match="ok=false"):
        outbound_publish(
            base_url="https://outbound",
            api_key="k",
            platform="x",
            idempotency_key="i",
            request=_build_request(),
            transport=transport,
        )


def test_outbound_publish_raises_on_non_json_body():
    def transport(*_args):
        return 200, "not-json"

    with pytest.raises(RuntimeError, match="non-JSON"):
        outbound_publish(
            base_url="https://outbound",
            api_key="k",
            platform="x",
            idempotency_key="i",
            request=_build_request(),
            transport=transport,
        )
