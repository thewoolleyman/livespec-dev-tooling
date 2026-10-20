"""Best-effort OTLP outcome spans for delegated pre-push gate runs."""

from __future__ import annotations

import contextlib
import json
import os
import time
import urllib.error
import urllib.request

__all__: list[str] = ["emit_gate_outcome"]

_ENDPOINT_ENV = "LIVESPEC_GATE_OTLP_ENDPOINT"
_DEFAULT_ENDPOINT = "http://127.0.0.1:4319"
_POST_TIMEOUT_S = 2.0
_SERVICE_NAME = "livespec-delegated-gate"


def build_span_payload(
    *, outcome: str, repository: str, tree_hash: str, job_name: str | None
) -> dict[str, object]:
    """Build exactly one OTLP span for one already-decided delegated gate."""
    attributes: list[dict[str, object]] = [
        {"key": "livespec.gate.outcome", "value": {"stringValue": outcome}},
        {"key": "livespec.gate.repository", "value": {"stringValue": repository}},
        {"key": "livespec.gate.tree_hash", "value": {"stringValue": tree_hash}},
    ]
    if job_name is not None:
        attributes.append({"key": "livespec.gate.job_name", "value": {"stringValue": job_name}})
    now = str(time.time_ns())
    return {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [{"key": "service.name", "value": {"stringValue": _SERVICE_NAME}}]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "livespec.delegated-gate", "version": "1.0.0"},
                        "spans": [
                            {
                                "traceId": os.urandom(16).hex(),
                                "spanId": os.urandom(8).hex(),
                                "name": "livespec.delegated-gate.outcome",
                                "kind": 1,
                                "startTimeUnixNano": now,
                                "endTimeUnixNano": now,
                                "attributes": attributes,
                            }
                        ],
                    }
                ],
            }
        ]
    }


def post_span(*, endpoint: str, payload: dict[str, object]) -> bool:
    """Post a span without allowing receiver failure to affect the gate verdict."""
    request = urllib.request.Request(
        url=f"{endpoint.removesuffix('/')}/v1/traces",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with contextlib.suppress(urllib.error.URLError, OSError, ValueError):
        with urllib.request.urlopen(request, timeout=_POST_TIMEOUT_S) as response:  # noqa: S310
            _ = response.read()
            return getattr(response, "status", 200) == 200
    return False


def emit_gate_outcome(
    *, outcome: str, repository: str, tree_hash: str, job_name: str | None
) -> bool:
    """Emit one outcome event; delivery is intentionally advisory."""
    endpoint = (os.environ.get(_ENDPOINT_ENV) or "").strip() or _DEFAULT_ENDPOINT
    return post_span(
        endpoint=endpoint,
        payload=build_span_payload(
            outcome=outcome,
            repository=repository,
            tree_hash=tree_hash,
            job_name=job_name,
        ),
    )
