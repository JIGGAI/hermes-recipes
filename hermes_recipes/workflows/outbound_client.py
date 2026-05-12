"""Outbound publish HTTP client.

Port of clawrecipes/src/lib/workflows/outbound-client.ts. POSTs to
``<base_url>/v1/<platform>/publish`` with bearer auth and an idempotency key.
Implementation uses ``urllib.request`` so the package has no extra runtime
dependencies; the ``transport`` callable can be injected for testing.
"""

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Optional

OutboundPlatform = Literal["x", "discord", "youtube", "instagram", "tiktok"]
MediaType = Literal["image", "video"]


@dataclass(frozen=True)
class OutboundRunContext:
    team_id: str
    workflow_id: str
    workflow_run_id: str
    node_id: str
    ticket_path: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "teamId": self.team_id,
            "workflowId": self.workflow_id,
            "workflowRunId": self.workflow_run_id,
            "nodeId": self.node_id,
        }
        if self.ticket_path is not None:
            out["ticketPath"] = self.ticket_path
        return out


@dataclass(frozen=True)
class OutboundApproval:
    binding_id: Optional[str] = None
    code: Optional[str] = None
    approval_file_rel: Optional[str] = None
    requested_at: Optional[str] = None
    receipt: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        keys = (
            ("bindingId", self.binding_id),
            ("code", self.code),
            ("approvalFileRel", self.approval_file_rel),
            ("requestedAt", self.requested_at),
            ("receipt", self.receipt),
        )
        return {k: v for k, v in keys if v is not None}


@dataclass(frozen=True)
class OutboundMedia:
    url: str
    type: MediaType

    def to_dict(self) -> dict[str, str]:
        return {"url": self.url, "type": self.type}


@dataclass(frozen=True)
class OutboundPublishRequest:
    text: str
    run_context: OutboundRunContext
    media: list[OutboundMedia] = field(default_factory=list)
    approval: Optional[OutboundApproval] = None
    dry_run: bool = False

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "text": self.text,
            "runContext": self.run_context.to_dict(),
        }
        if self.media:
            out["media"] = [m.to_dict() for m in self.media]
        if self.approval is not None:
            out["approval"] = self.approval.to_dict()
        if self.dry_run:
            out["dryRun"] = True
        return out


@dataclass(frozen=True)
class OutboundPublishResponse:
    ok: bool
    platform: str
    id: Optional[str] = None
    url: Optional[str] = None
    error: Optional[str] = None
    message: Optional[str] = None


# Transport: takes (method, url, headers, body_bytes) → (status, response_body_text).
TransportFn = Callable[[str, str, dict[str, str], bytes], tuple[int, str]]


def _default_transport(
    method: str, url: str, headers: dict[str, str], body: bytes
) -> tuple[int, str]:
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")


_URL_SCHEME_RE = re.compile(r"^https?://", re.IGNORECASE)


def _normalize_base_url(base_url: str) -> str:
    cleaned = (base_url or "").strip().rstrip("/")
    if not cleaned:
        raise ValueError("Outbound baseUrl is required")
    if not _URL_SCHEME_RE.match(cleaned):
        raise ValueError(
            f"Outbound baseUrl must start with http(s):// (got: {base_url})"
        )
    return cleaned


def outbound_publish(
    *,
    base_url: str,
    api_key: str,
    platform: OutboundPlatform,
    idempotency_key: str,
    request: OutboundPublishRequest,
    extra_headers: Optional[dict[str, str]] = None,
    transport: TransportFn = _default_transport,
) -> OutboundPublishResponse:
    base = _normalize_base_url(base_url)
    key = (api_key or "").strip()
    if not key:
        raise ValueError("Outbound apiKey is required")
    plat = (platform or "").strip()
    if not plat:
        raise ValueError("Outbound platform is required")
    idem = (idempotency_key or "").strip()
    if not idem:
        raise ValueError("Outbound idempotencyKey is required")

    url = f"{base}/v1/{plat}/publish"
    headers: dict[str, str] = {
        "content-type": "application/json",
        "authorization": f"Bearer {key}",
        "idempotency-key": idem,
    }
    if extra_headers:
        headers.update(extra_headers)

    body = json.dumps(request.to_dict()).encode("utf-8")
    status, response_text = transport("POST", url, headers, body)

    if status < 200 or status >= 300:
        suffix = f" — {response_text}" if response_text else ""
        raise RuntimeError(f"Outbound publish failed: {status}{suffix}")

    try:
        parsed = json.loads(response_text) if response_text else {}
    except json.JSONDecodeError:
        raise RuntimeError(
            f"Outbound publish returned non-JSON: {response_text[:500]}"
        )

    if not isinstance(parsed, dict):
        raise RuntimeError(
            f"Outbound publish returned non-object body: {response_text[:500]}"
        )

    if parsed.get("ok") is False:
        err = f" ({parsed['error']})" if parsed.get("error") else ""
        msg = f" — {parsed['message']}" if parsed.get("message") else ""
        raise RuntimeError(f"Outbound publish returned ok=false{err}{msg}")

    return OutboundPublishResponse(
        ok=bool(parsed.get("ok", True)),
        platform=str(parsed.get("platform") or plat),
        id=parsed.get("id"),
        url=parsed.get("url"),
        error=parsed.get("error"),
        message=parsed.get("message"),
    )
