#!/usr/bin/env python3
"""otel_cargo_phase — emit one factory build-telemetry span for a cargo phase.

Baked onto the fabro-sandbox python-rust image PATH as
``livespec-cargo-phase-timer`` and invoked by the sibling ``cargo`` shim AFTER
the shim has already run the real cargo, reading the timing, phase, and exit
code from the environment::

    BUILD_PHASE=compile BUILD_SUBCMD=build \
    BUILD_START_NANO=<ns> BUILD_END_NANO=<ns> BUILD_EXIT_CODE=0 \
      livespec-cargo-phase-timer

It best-effort POSTs ONE OTLP/HTTP-JSON span — conforming to the shared
build-telemetry attribute scheme (``build.env=factory``, ``build.phase``,
``repo``, ``git.commit.sha``, ``toolchain.version``) — to the host OTel receiver
at ``$LIVESPEC_SANDBOX_OTEL_ENDPOINT`` (default ``http://172.17.0.1:4318``, the
same seam the ``prepare.*`` step-timer uses). The receiver routes a span to its
Honeycomb dataset by ``service.name``; this span carries
``service.name=github-ci`` so factory build phases land in the SAME
``github-ci`` dataset the CI build-telemetry spans use, discriminated by the
``build.env`` attribute — so NO Honeycomb ingest key need enter the sandbox.

Factory failure contract: an emission failure is reported LOUDLY to stderr so it
surfaces in the fabro run log (the scheme's factory row), but it NEVER changes
the build's outcome — the shim has already run cargo and owns the exit code, and
a broken stopwatch never breaks the run.

STDLIB ONLY + self-contained: the image ``COPY``s this one file to
``/usr/local/bin/livespec-cargo-phase-timer`` and runs it on the base image's
system python3 (outside any virtualenv), so it imports only the standard library
and duplicates the few tiny helpers it shares in spirit with ``otel_step_timer``
rather than importing a sibling that is not on the baked ``sys.path``.
"""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from collections.abc import Callable

# Only names that cross a module boundary. `parse_env`, `gather_source_facts`,
# `build_span_payload`, `post_span` and `run` are internal helpers of this baked
# CLI, reached only by this module's own tests; `main` stays because the baked
# `livespec-cargo-phase-timer` binary enters through it.
__all__: list[str] = [
    "BUILD_ENV",
    "DATASET",
    "DEFAULT_ENDPOINT",
    "main",
]

DATASET = "github-ci"
NAMESPACE = "livespec-family"
BUILD_ENV = "factory"
DEFAULT_ENDPOINT = "http://172.17.0.1:4318"
_ENDPOINT_ENV = "LIVESPEC_SANDBOX_OTEL_ENDPOINT"
_WORK_ITEM_ENV = "LIVESPEC_WORK_ITEM_ID"
_SCOPE_NAME = "livespec.build-telemetry"
_SCOPE_VERSION = "1.0.0"
_POST_TIMEOUT_S = 2.0
_HTTP_OK = 200
_UNKNOWN = "unknown"
_USAGE = (
    "livespec-cargo-phase-timer: usage: set BUILD_PHASE, BUILD_SUBCMD, "
    "BUILD_START_NANO, BUILD_END_NANO, BUILD_EXIT_CODE in the environment\n"
)


def parse_env(*, environ: dict[str, str]) -> dict[str, object] | None:
    """Read the five required ``BUILD_*`` inputs the shim exports.

    Returns a dict of the parsed inputs, or ``None`` when any required
    variable is missing or the three integer variables are not integers —
    ``None`` signals a usage error the caller reports without emitting.
    """
    phase = environ.get("BUILD_PHASE", "")
    subcmd = environ.get("BUILD_SUBCMD", "")
    if not phase or not subcmd:
        return None
    numbers: dict[str, int] = {}
    for key in ("BUILD_START_NANO", "BUILD_END_NANO", "BUILD_EXIT_CODE"):
        raw = environ.get(key, "")
        if not (raw.lstrip("-").isdigit()):
            return None
        numbers[key] = int(raw)
    return {
        "phase": phase,
        "subcmd": subcmd,
        "start_ns": numbers["BUILD_START_NANO"],
        "end_ns": numbers["BUILD_END_NANO"],
        "exit_code": numbers["BUILD_EXIT_CODE"],
        "work_item_id": environ.get(_WORK_ITEM_ENV) or None,
    }


def _stdout_of(*, command: list[str]) -> str:
    """Best-effort first line of ``command``'s stdout, ``""`` on any failure."""
    with contextlib.suppress(OSError, ValueError, subprocess.SubprocessError):
        completed = subprocess.run(  # noqa: S603  — fixed git argv, no shell.
            command, capture_output=True, text=True, check=False, timeout=_POST_TIMEOUT_S
        )
        if completed.returncode == 0:
            return completed.stdout.strip()
    return ""


def _repo_from_remote(*, remote_url: str) -> str:
    """Reduce a github remote URL to ``owner/name`` (``unknown`` when unparseable)."""
    trimmed = remote_url.strip()
    for marker in ("github.com:", "github.com/"):
        _, sep, tail = trimmed.partition(marker)
        if sep:
            return tail.removesuffix(".git") or _UNKNOWN
    return _UNKNOWN


def _toolchain_version(*, text: str) -> str:
    """Extract the pinned channel from ``rust-toolchain.toml`` text."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("channel"):
            _, _, value = stripped.partition("=")
            return value.strip().strip("\"'") or _UNKNOWN
    return _UNKNOWN


def gather_source_facts() -> dict[str, str]:
    """Best-effort read ``repo``, ``git.commit.sha`` and toolchain from the cwd.

    Every field degrades to ``"unknown"`` rather than raising — the wrapped
    cargo has already run, so no probe here may perturb the build.
    """
    remote = _stdout_of(command=["git", "remote", "get-url", "origin"])
    sha = _stdout_of(command=["git", "rev-parse", "HEAD"])
    toolchain_text = ""
    with contextlib.suppress(OSError):
        toolchain_text = _read_text(path="rust-toolchain.toml")
    return {
        "repo": _repo_from_remote(remote_url=remote) if remote else _UNKNOWN,
        "sha": sha or _UNKNOWN,
        "toolchain": _toolchain_version(text=toolchain_text) if toolchain_text else _UNKNOWN,
    }


def _read_text(*, path: str) -> str:
    with open(path, encoding="utf-8") as handle:  # noqa: PTH123  — stdlib-only baked script.
        return handle.read()


def build_span_payload(
    *,
    inputs: dict[str, object],
    facts: dict[str, str],
) -> dict[str, object]:
    """Build the single-span OTLP/HTTP-JSON request for one cargo phase.

    ``service.name=github-ci`` (a resource attribute) routes the span to the
    ``github-ci`` dataset; the span carries the shared build-telemetry scheme
    attributes plus the optional ``work_item_id`` correlation tag. int64 fields
    are JSON strings per the proto3-JSON mapping Honeycomb expects; trace/span
    ids are freshly random (each cargo phase is its own independent span in v1).
    """
    exit_code = int(inputs["exit_code"])  # type: ignore[call-overload]
    attributes: list[dict[str, object]] = [
        {"key": "build.env", "value": {"stringValue": BUILD_ENV}},
        {"key": "build.phase", "value": {"stringValue": str(inputs["phase"])}},
        {"key": "repo", "value": {"stringValue": facts["repo"]}},
        {"key": "git.commit.sha", "value": {"stringValue": facts["sha"]}},
        {"key": "toolchain.version", "value": {"stringValue": facts["toolchain"]}},
        {"key": "cargo.subcommand", "value": {"stringValue": str(inputs["subcmd"])}},
        {"key": "exit_code", "value": {"intValue": str(exit_code)}},
    ]
    work_item_id = inputs["work_item_id"]
    if work_item_id:
        attributes.append({"key": "work_item_id", "value": {"stringValue": str(work_item_id)}})
    span: dict[str, object] = {
        "traceId": os.urandom(16).hex(),
        "spanId": os.urandom(8).hex(),
        "name": f"build.cargo-{inputs['subcmd']}",
        "kind": 1,
        "startTimeUnixNano": str(inputs["start_ns"]),
        "endTimeUnixNano": str(inputs["end_ns"]),
        "attributes": attributes,
        "status": {"code": 1 if exit_code == 0 else 2},
    }
    return {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": DATASET}},
                        {"key": "service.namespace", "value": {"stringValue": NAMESPACE}},
                    ],
                },
                "scopeSpans": [
                    {
                        "scope": {"name": _SCOPE_NAME, "version": _SCOPE_VERSION},
                        "spans": [span],
                    },
                ],
            },
        ],
    }


def post_span(
    *,
    endpoint: str,
    payload: dict[str, object],
    timeout: float = _POST_TIMEOUT_S,
) -> bool:
    """POST the OTLP payload to ``<endpoint>/v1/traces``; return whether it landed.

    Unlike the fail-soft ``prepare.*`` emitter, a factory emission failure is
    reported LOUDLY to ``stderr`` so it surfaces in the fabro run log. It still
    never RAISES — the shim owns the exit code — so the expected network/URL
    failures are suppressed and reported as a ``False`` return, not an exception.
    """
    request = urllib.request.Request(  # noqa: S310  — fixed http(s) receiver URL.
        url=f"{endpoint}/v1/traces",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with contextlib.suppress(urllib.error.URLError, OSError, ValueError):
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            status = getattr(response, "status", 200)
            _ = response.read()
        if status == _HTTP_OK:
            return True
        _ = sys.stderr.write(f"build-telemetry(factory): receiver returned HTTP {status}\n")
        return False
    _ = sys.stderr.write(f"build-telemetry(factory): emission to {endpoint} failed (unreachable)\n")
    return False


def run(
    *,
    environ: dict[str, str],
    emit: Callable[..., bool] = post_span,
    facts: Callable[[], dict[str, str]] = gather_source_facts,
) -> int:
    """Emit one factory cargo-phase span from the environment; return 0/2.

    ``emit`` and ``facts`` are seams tests inject. A malformed environment
    writes a usage line to stderr and returns ``2`` without emitting. The return
    value is advisory only — the shim discards it and exits with cargo's own
    code — but a clean 0/2 keeps the CLI unit-testable.
    """
    inputs = parse_env(environ=environ)
    if inputs is None:
        _ = sys.stderr.write(_USAGE)
        return 2
    payload = build_span_payload(inputs=inputs, facts=facts())
    endpoint = (environ.get(_ENDPOINT_ENV) or "").strip() or DEFAULT_ENDPOINT
    _ = emit(endpoint=endpoint, payload=payload)
    return 0


def main() -> int:
    return run(environ=dict(os.environ))


if __name__ == "__main__":
    raise SystemExit(main())
