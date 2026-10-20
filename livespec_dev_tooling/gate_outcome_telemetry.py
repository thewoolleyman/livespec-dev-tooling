"""One outcome event per delegated gate run — the signal a broken delegation raises.

A DELEGATED GATE HAS TWO WAYS TO REFUSE A PUSH AND THEY ARE OPPOSITE FAULTS. A
RED TREE is the pushing repository's own problem and wants the author to fix the
tree; NO VERDICT is the delegation's problem — an unreachable API server, a
credential that could not be refreshed, a Job that was never submitted or was
lost — and wants an operator to fix the plumbing. The gate client's own output
has always distinguished them, but that output goes to ONE push's terminal: to
anyone not reading that log, a broken delegation reads as a failing repository.
This module is what makes the difference alertable instead.

THE OUTCOME IS A WORD, NOT A DETAIL STRING. `passed`, `failed-tree` and
`no-verdict` ride a span ATTRIBUTE, because a trigger can filter on an attribute
and cannot read prose. That is the whole reason the vocabulary is three values
rather than a boolean plus an explanation.

THE OUTCOME NAMES THE GATE'S VERDICT, NOT WHAT HAPPENED TO THE PUSH. A green
verdict on which the push is still refused — because `HEAD` no longer names the
gated tree, or because the green token could not be written — emits `passed`:
the gate did pass, and conflating the two would hide a healthy delegation behind
a push that went another way.

AN UNDETERMINED VALUE IS ABSENT, NEVER GUESSED. A run that stopped before the
API server assigned a Job name HAS no Job name, and an empty string or a
placeholder would be indistinguishable — to the reader of a trigger — from a
real one. `build_span_payload` therefore omits the attribute rather than
inventing a value for it.

DELIVERY IS ADVISORY AND THAT IS LOAD-BEARING, NOT A CONCESSION. This emitter
observes a gate that has ALREADY been decided, so a receiver that is down must
not be able to change a verdict, refuse a push, or raise anything a caller has
to handle. Both functions below therefore swallow every expected network and URL
failure and return `None`, and the POST carries a short timeout so a hung
receiver cannot hold a push either. The same shape, for the same reason, as
`otel_step_timer.post_span`, whose docstring records the catch breadth.

THE DEFAULT ENDPOINT IS THE HOST'S OWN LOOPBACK COLLECTOR, which is the fleet
convention for a host-side emitter: `ci-runner-heartbeat.sh` and
`ci-cache-gauges.sh` both default to `127.0.0.1:4319`, the receiver the host
otel-collector serves and exports from. A delegating host therefore needs no
configuration to be observed, and `LIVESPEC_GATE_OTLP_ENDPOINT` overrides it
where the receiver is elsewhere.
"""

from __future__ import annotations

import contextlib
import json
import os
import time
import urllib.error
import urllib.request

__all__: list[str] = [
    "DEFAULT_ENDPOINT",
    "ENDPOINT_ENV",
    "GATE_OUTCOME_FAILED_TREE",
    "GATE_OUTCOME_NO_VERDICT",
    "GATE_OUTCOME_PASSED",
    "build_span_payload",
    "emit_gate_outcome",
    "post_span",
]

# The three-word outcome vocabulary the delegated pre-push gate's telemetry
# contract names, in this repository's own `SPECIFICATION/contracts.md`.
GATE_OUTCOME_PASSED = "passed"
GATE_OUTCOME_FAILED_TREE = "failed-tree"
GATE_OUTCOME_NO_VERDICT = "no-verdict"

ENDPOINT_ENV = "LIVESPEC_GATE_OTLP_ENDPOINT"
DEFAULT_ENDPOINT = "http://127.0.0.1:4319"

# Bounded so a receiver that accepts a connection and then stalls cannot hold a
# push: the contract forbids waiting on delivery for longer than one attempt.
_POST_TIMEOUT_S = 2.0
_SERVICE_NAME = "livespec-delegated-gate"
_SCOPE_NAME = "livespec.delegated-gate"
_SPAN_NAME = "livespec.delegated-gate.outcome"


def build_span_payload(
    *, outcome: str, repository: str | None, tree_hash: str | None, job_name: str | None
) -> dict[str, object]:
    """Build the OTLP payload for EXACTLY ONE span describing one decided run.

    One span per run is the contract: a reader counting `no-verdict` events is
    counting broken delegations, so a run that emitted two would double its own
    fault and a run that emitted none would hide it.

    The start and end timestamps are the same instant on purpose. This span is a
    POINT EVENT — the outcome of a run that has already finished — and a
    fabricated duration would invite a reader to chart it as the gate's latency,
    which it is not.
    """
    identity = (
        ("livespec.gate.outcome", outcome),
        ("livespec.gate.repository", repository),
        ("livespec.gate.tree_hash", tree_hash),
        ("livespec.gate.job_name", job_name),
    )
    now = str(time.time_ns())
    return {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [{"key": "service.name", "value": {"stringValue": _SERVICE_NAME}}]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": _SCOPE_NAME},
                        "spans": [
                            {
                                "traceId": os.urandom(16).hex(),
                                "spanId": os.urandom(8).hex(),
                                "name": _SPAN_NAME,
                                "kind": 1,
                                "startTimeUnixNano": now,
                                "endTimeUnixNano": now,
                                "attributes": [
                                    {"key": key, "value": {"stringValue": value}}
                                    for key, value in identity
                                    if value is not None
                                ],
                            }
                        ],
                    }
                ],
            }
        ]
    }


def post_span(*, endpoint: str, payload: dict[str, object]) -> None:
    """Best-effort POST the payload to ``<endpoint>/v1/traces``.

    Swallows every expected network and URL failure — ``OSError`` covers
    connection refused, DNS and timeout, ``URLError`` wraps them, and
    ``ValueError`` covers a malformed endpoint — so a receiver outage can never
    surface into the verdict this span merely describes. Returns ``None`` on
    success and on failure alike, because the caller has nothing to decide
    either way.
    """
    request = urllib.request.Request(  # noqa: S310  — endpoint is a fixed http(s) receiver URL.
        url=f"{endpoint.removesuffix('/')}/v1/traces",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with (
        contextlib.suppress(urllib.error.URLError, OSError, ValueError),
        urllib.request.urlopen(request, timeout=_POST_TIMEOUT_S) as response,  # noqa: S310
    ):
        _ = response.read()


def emit_gate_outcome(
    *, outcome: str, repository: str | None, tree_hash: str | None, job_name: str | None
) -> None:
    """Emit one delegated gate run's outcome event to the configured receiver."""
    endpoint = (os.environ.get(ENDPOINT_ENV) or "").strip() or DEFAULT_ENDPOINT
    post_span(
        endpoint=endpoint,
        payload=build_span_payload(
            outcome=outcome, repository=repository, tree_hash=tree_hash, job_name=job_name
        ),
    )
