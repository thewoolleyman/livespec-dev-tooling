#!/usr/bin/env python3
"""otel_step_timer — time a Fabro sandbox prepare step and emit a best-effort span.

Baked onto the fabro-sandbox image PATH as ``livespec-step-timer`` and invoked::

    livespec-step-timer <step-name> -- <command...>

It runs ``<command>`` with stdin/stdout/stderr and the exit code passed through
UNCHANGED, times the run, and best-effort POSTs ONE OTLP/HTTP-JSON trace span to
the host receiver at ``$LIVESPEC_SANDBOX_OTEL_ENDPOINT`` (default
``http://172.17.0.1:4318``) so the in-sandbox setup/janitor timing becomes
MEASURED in the ``fabro-sandbox`` Honeycomb dataset (the receiver routes a span
to its dataset by ``service.name``). A telemetry failure — unreachable endpoint,
DNS error, malformed env — NEVER changes the wrapped command's exit code,
output, or observable timing: a broken stopwatch never breaks the run.

STDLIB ONLY: the baked copy runs OUTSIDE any virtualenv (the first prepare steps
run before ``uv sync``), so this module imports only the standard library and
writes nothing to the wrapped command's streams (a lone usage error goes to
stderr). It doubles as an importable package module so the behaviour is unit
tested; the image ``COPY``s this same file to ``/usr/local/bin/livespec-step-timer``.
"""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable

# Only names that cross a module boundary. `parse_argv`, `build_trace_payload`,
# `run` and `post_span` are internal helpers of this baked CLI — each measured at
# ZERO references across all eight sibling repos, reached only by this module's own
# tests. `main` stays: the baked `livespec-step-timer` binary is referenced 15 times
# fleet-wide and every one of those enters through it.
__all__: list[str] = [
    "DATASET",
    "DEFAULT_ENDPOINT",
    "main",
]

DEFAULT_ENDPOINT = "http://172.17.0.1:4318"
DATASET = "fabro-sandbox"
_ENDPOINT_ENV = "LIVESPEC_SANDBOX_OTEL_ENDPOINT"
_WORK_ITEM_ENV = "LIVESPEC_WORK_ITEM_ID"
_SCOPE_NAME = "livespec-step-timer"
_POST_TIMEOUT_S = 2.0
_USAGE = "livespec-step-timer: usage: <step-name> -- <command...>\n"


def parse_argv(*, argv: list[str]) -> tuple[str, list[str]] | None:
    """Split ``<step-name> -- <command...>`` on the FIRST ``--`` separator.

    Returns ``(step_name, command)`` or ``None`` when the invocation is
    malformed — no ``--`` present, more or fewer than one token before it,
    or an empty command after it. ``None`` signals a usage error the caller
    reports without running anything.
    """
    if "--" not in argv:
        return None
    separator = argv.index("--")
    head = argv[:separator]
    command = argv[separator + 1 :]
    if len(head) != 1 or not head[0] or not command:
        return None
    return head[0], command


def build_trace_payload(
    *,
    step_name: str,
    start_ns: int,
    end_ns: int,
    exit_code: int,
    work_item_id: str | None,
) -> dict[str, object]:
    """Build the OTLP/HTTP-JSON trace request for one timed prepare step.

    Shapes a single-span ``resourceSpans`` payload the host receiver
    understands: ``service.name`` (a resource attribute) routes the span to
    the ``fabro-sandbox`` dataset; the span carries the step name, the
    start/end nanosecond timestamps, the wrapped command's ``exit_code``, and
    — when the dispatcher injected one into the sandbox env — the
    ``work_item_id`` for correlation. int64 fields are JSON strings per the
    proto3-JSON mapping Honeycomb expects. Trace/span ids are freshly random
    (this is an independent, un-parented span in v1).
    """
    attributes: list[dict[str, object]] = [
        {"key": "step.name", "value": {"stringValue": step_name}},
        {"key": "exit_code", "value": {"intValue": str(exit_code)}},
    ]
    if work_item_id:
        attributes.append({"key": "work_item_id", "value": {"stringValue": work_item_id}})
    span: dict[str, object] = {
        "traceId": os.urandom(16).hex(),
        "spanId": os.urandom(8).hex(),
        "name": f"prepare.{step_name}",
        "kind": 1,
        "startTimeUnixNano": str(start_ns),
        "endTimeUnixNano": str(end_ns),
        "attributes": attributes,
        "status": {"code": 1 if exit_code == 0 else 2},
    }
    return {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": DATASET}},
                    ],
                },
                "scopeSpans": [{"scope": {"name": _SCOPE_NAME}, "spans": [span]}],
            },
        ],
    }


def post_span(
    *, endpoint: str, payload: dict[str, object], timeout: float = _POST_TIMEOUT_S
) -> None:
    """Best-effort POST the OTLP payload to ``<endpoint>/v1/traces``.

    Swallows every expected network/URL failure (``OSError`` covers connection
    refused, DNS, and timeout; ``ValueError`` covers a malformed endpoint) so a
    telemetry outage can never surface into the wrapped command's result. On
    success or failure it returns ``None``.
    """
    request = urllib.request.Request(  # noqa: S310  — endpoint is a fixed http(s) receiver URL.
        url=f"{endpoint}/v1/traces",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with (
        contextlib.suppress(urllib.error.URLError, OSError, ValueError),
        urllib.request.urlopen(request, timeout=timeout) as response,  # noqa: S310
    ):
        _ = response.read()


def run(
    *,
    argv: list[str],
    environ: dict[str, str],
    emit: Callable[..., None] = post_span,
) -> int:
    """Time and run one prepare step, emit its span, return its exit code.

    ``emit`` is the span-emitter seam (defaults to :func:`post_span`; tests
    inject a recorder). The wrapped command inherits this process's
    stdin/stdout/stderr, so its output is untouched. The returned int IS the
    wrapped command's exit code; a malformed invocation writes a usage line to
    stderr and returns ``2`` without emitting.
    """
    parsed = parse_argv(argv=argv)
    if parsed is None:
        _ = sys.stderr.write(_USAGE)
        return 2
    step_name, command = parsed
    start_ns = time.time_ns()
    completed = subprocess.run(command, check=False)  # noqa: S603  — wrapped prepare-step command.
    end_ns = time.time_ns()
    payload = build_trace_payload(
        step_name=step_name,
        start_ns=start_ns,
        end_ns=end_ns,
        exit_code=completed.returncode,
        work_item_id=environ.get(_WORK_ITEM_ENV) or None,
    )
    endpoint = (environ.get(_ENDPOINT_ENV) or "").strip() or DEFAULT_ENDPOINT
    emit(endpoint=endpoint, payload=payload)
    return completed.returncode


def main() -> int:
    return run(argv=sys.argv[1:], environ=dict(os.environ))


if __name__ == "__main__":
    raise SystemExit(main())
