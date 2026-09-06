#!/usr/bin/env python3
"""otel_cargo_phase — emit one factory build-telemetry span for a cargo phase.

Baked onto the fabro-sandbox python-rust image PATH as
``livespec-cargo-phase-timer`` and invoked by the sibling ``cargo`` shim AFTER
the shim has already run the real cargo, reading the timing, phase, and exit
code from the environment::

    BUILD_PHASE=compile BUILD_SUBCMD=build \
    BUILD_START_NANO=<ns> BUILD_END_NANO=<ns> BUILD_EXIT_CODE=0 \
      livespec-cargo-phase-timer

Invoked a second way, BEFORE cargo, to zero the compilation cache's counters so
the span's counts describe THIS phase and not the sandbox's whole life::

    livespec-cargo-phase-timer --zero-stats

It best-effort POSTs ONE OTLP/HTTP-JSON span — conforming to the shared
build-telemetry attribute scheme (``build.env``, ``build.phase``,
``repo``, ``git.commit.sha``, ``toolchain.version``, and the pool's
``build.cache.*`` namespace: ``build.cache.sccache.enabled|hits|misses|errors|
hit_ratio|backend|rw_mode`` plus ``build.cache.registry.hit``) — to the host
OTel receiver
at ``$LIVESPEC_SANDBOX_OTEL_ENDPOINT`` (default ``http://172.17.0.1:4318``, the
same seam the ``prepare.*`` step-timer uses). The receiver routes a span to its
Honeycomb dataset by ``service.name``; this span carries
``service.name=github-ci`` so factory build phases land in the SAME
``github-ci`` dataset the CI build-telemetry spans use, discriminated by the
``build.env`` attribute — so NO Honeycomb ingest key need enter the sandbox.

TWO LANES, ONE IMAGE. The same baked shim runs in the fabro factory sandbox AND
in the k3s CI job container that pins this image, so ``build.env`` is RESOLVED
at emit time from the forge's own ``GITHUB_ACTIONS`` marker (``ci`` when it is
``true``, ``factory`` otherwise) rather than hardcoded — a CI-lane span labelled
``factory`` would pollute every factory query in the shared dataset. In the CI
lane the factory's default endpoint (a docker-bridge address of the factory
host) is UNREACHABLE from a workflow pod, and each unreachable POST cost that
job ``_POST_TIMEOUT_S``; so when the CI lane has NO endpoint configured the
emission is skipped outright rather than paid for and thrown away. An
explicitly configured endpoint is still posted to, as ``build.env=ci``.

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
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import cast

# Only names that cross a module boundary. `parse_env`, `gather_source_facts`,
# `build_span_payload`, `post_span`, `run` and the `*_sccache_*` / `registry_hit`
# / `cache_attributes` cache probe are internal helpers of this baked CLI,
# reached only by this module's own tests; `main` stays because the baked
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
_CI_ENV = "GITHUB_ACTIONS"
_WORK_ITEM_ENV = "LIVESPEC_WORK_ITEM_ID"
_SCOPE_NAME = "livespec.build-telemetry"
_SCOPE_VERSION = "1.0.0"
_POST_TIMEOUT_S = 2.0
_HTTP_OK = 200
_UNKNOWN = "unknown"
_NONE = "none"
_SCCACHE_RW_MODE_ENV = "SCCACHE_REDIS_RW_MODE"
# The pool MOUNTS its pinned sccache here rather than each image baking one, so
# this is the last resort after a PATH lookup.
_POOL_SCCACHE_BIN = "/opt/ci-runner/bin/sccache"
_DEFAULT_RW_MODE = "READ_WRITE"
_CARGO_HOME_ENV = "CARGO_HOME"
# The sandbox image installs rustup under /root/.cargo (see the python-rust
# Dockerfile), which is also cargo's own default for a root-run build.
_DEFAULT_CARGO_HOME = "/root/.cargo"
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
        completed = subprocess.run(  # noqa: S603  — fixed git/sccache argv, no shell.
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


def _sccache_binary(*, environ: dict[str, str]) -> str:
    """Resolve the sccache binary: PATH first, then the pool's read-only mount.

    Returns ``""`` when neither resolves to an executable — the signal the
    callers degrade on. The PATH is read from the passed ``environ`` rather than
    the process's, so the resolution stays a pure function of its input.
    """
    for candidate in ("sccache", _POOL_SCCACHE_BIN):
        found = shutil.which(candidate, path=environ.get("PATH", ""))
        if found:
            return found
    return ""


def _sccache_output(*, environ: dict[str, str], args: list[str]) -> str | None:
    """Best-effort ``sccache <args>`` stdout; ``None`` when sccache cannot answer.

    ``None`` covers all three degraded shapes at once — no binary, a binary that
    will not spawn, and a non-zero or silent run — because the caller treats
    them identically: ``build.cache.sccache.enabled=false``. Every sccache
    subcommand used here prints on success, so empty stdout IS a failure.
    """
    binary = _sccache_binary(environ=environ)
    return (_stdout_of(command=[binary, *args]) or None) if binary else None


def zero_sccache_stats(*, environ: dict[str, str]) -> bool:
    """Zero sccache's counters before cargo; report whether the zeroing landed.

    Called by the shim BEFORE the measured cargo so the counts the span carries
    describe THIS phase only. Best-effort by contract: a ``False`` return
    changes nothing about the build, it only means the phase's counts will be
    cumulative rather than phase-scoped.
    """
    return _sccache_output(environ=environ, args=["--zero-stats"]) is not None


def read_sccache_stats(*, environ: dict[str, str]) -> str | None:
    """Best-effort ``sccache --show-stats --stats-format=json`` text, or ``None``."""
    return _sccache_output(environ=environ, args=["--show-stats", "--stats-format=json"])


def _counter_total(*, value: object) -> int:
    """Total one sccache counter: a bare int, or a ``{"counts": {<lang>: n}}`` map.

    sccache reports the per-kind counters as a nested ``counts`` map and the
    scalar ones as bare integers, and which is which has moved between
    releases; reading both keeps the parse version-tolerant. Anything else
    totals to 0 rather than raising — a stats shape we do not recognise must
    never perturb a build that has already finished.
    """
    if isinstance(value, int):
        return value
    with contextlib.suppress(AttributeError, KeyError, TypeError, ValueError):
        counts = cast("dict[str, dict[str, int]]", value)["counts"]
        return sum(int(n) for n in counts.values())
    return 0


def _backend_of(*, location: str) -> str:
    """Reduce sccache's ``cache_location`` to a backend TOKEN.

    sccache spells the location ``"<Backend><: or ,> <detail>"`` — ``"Redis:
    redis://host:6379"``, ``"Local disk: /root/.cache/sccache"``, ``"S3, bucket:
    …"`` — so the HEAD is the backend and the detail is dropped. Dropping it is
    the point: the detail embeds the cache's endpoint and, for a
    URL-authenticated backend, its credential, and the runner-pool
    cache-telemetry rule in non-functional-requirements forbids an emitter
    carrying either. A head that is not a bare word — a naked path, say — is
    therefore reported as ``unknown`` rather than emitted verbatim.
    """
    head = location.split(":")[0].split(",")[0].strip().lower().replace(" ", "-")
    return head if head.replace("-", "").isalnum() else _UNKNOWN


def parse_sccache_stats(*, text: str) -> tuple[int, int, int, str] | None:
    """``(hits, misses, errors, backend)`` from sccache's JSON stats.

    Returns ``None`` when the text is not sccache stats at all — the signal the
    caller degrades to ``build.cache.sccache.enabled=false`` on.
    """
    with contextlib.suppress(AttributeError, KeyError, TypeError, ValueError):
        # The `cast` is the single typed parse boundary: `json.loads` yields
        # `Any`, and every field it names is re-validated by the suppressed
        # exceptions above — a stats document of another shape returns `None`.
        stats = cast("dict[str, dict[str, object]]", json.loads(text))["stats"]
        return (
            _counter_total(value=stats.get("cache_hits")),
            _counter_total(value=stats.get("cache_misses")),
            _counter_total(value=stats.get("cache_errors")),
            _backend_of(location=str(stats.get("cache_location", ""))),
        )
    return None


def registry_hit(*, environ: dict[str, str]) -> bool:
    """Whether a warm crate-registry cache is already present in this sandbox.

    The factory's counterpart to the pool's per-tier ``build.cache.registry.hit``:
    a populated ``$CARGO_HOME/registry/cache`` means this phase started from a
    warm registry rather than fetching every crate cold.
    """
    home = (environ.get(_CARGO_HOME_ENV) or "").strip() or _DEFAULT_CARGO_HOME
    cache = Path(home) / "registry" / "cache"
    # `is_dir()` swallows ENOENT but not EACCES. On a host where the default
    # /root is 0700 and this runs unprivileged — the fleet's post-merge
    # janitor — the probe raised out of the span builder and turned a green
    # PR into a red master (2026-09-04). A stat failure of any kind reads as
    # "absent", the same fail-soft posture as the module's other probes.
    with contextlib.suppress(OSError):
        return cache.is_dir()
    return False


def cache_attributes(*, environ: dict[str, str], stats: str | None) -> list[dict[str, object]]:
    """The span's ``build.cache.*`` attributes for one cargo phase.

    Always the SAME eight keys, so one Honeycomb query shape covers CI and
    factory: a missing or non-functioning sccache degrades to
    ``enabled=false`` with zeroed counts and a ``none`` backend rather than
    dropping the attributes. ``rw_mode`` reads the reader-side
    ``SCCACHE_REDIS_RW_MODE`` the pool's hook template sets (``READ_ONLY``
    expected), falling back to sccache's own read-write default.
    """
    parsed = parse_sccache_stats(text=stats) if stats is not None else None
    hits, misses, errors, backend = parsed or (0, 0, 0, _NONE)
    ratio = hits / (hits + misses) if hits + misses else 0.0
    declared = (environ.get(_SCCACHE_RW_MODE_ENV) or "").strip().upper() or _DEFAULT_RW_MODE
    rw_mode = declared if parsed is not None else _NONE
    return [
        {"key": "build.cache.sccache.enabled", "value": {"boolValue": parsed is not None}},
        {"key": "build.cache.sccache.hits", "value": {"intValue": str(hits)}},
        {"key": "build.cache.sccache.misses", "value": {"intValue": str(misses)}},
        {"key": "build.cache.sccache.errors", "value": {"intValue": str(errors)}},
        {"key": "build.cache.sccache.hit_ratio", "value": {"doubleValue": ratio}},
        {"key": "build.cache.sccache.backend", "value": {"stringValue": backend}},
        {"key": "build.cache.sccache.rw_mode", "value": {"stringValue": rw_mode}},
        {"key": "build.cache.registry.hit", "value": {"boolValue": registry_hit(environ=environ)}},
    ]


def resolve_build_env(*, environ: dict[str, str]) -> str:
    """The span's ``build.env`` for THIS lane: ``ci`` under Actions, else ``factory``.

    ``GITHUB_ACTIONS=true`` is the forge's own marker of a job container and is
    present in the k3s lane's container (measured 2026-09-04); the fabro sandbox
    never carries it. Resolving here rather than hardcoding ``factory`` is what
    lets ONE baked image serve both lanes without a CI-lane span landing in the
    factory's slice of the shared ``github-ci`` dataset.
    """
    return "ci" if environ.get(_CI_ENV, "").strip().lower() == "true" else BUILD_ENV


def build_span_payload(
    *,
    inputs: dict[str, object],
    facts: dict[str, str],
    cache: list[dict[str, object]],
    build_env: str,
) -> dict[str, object]:
    """Build the single-span OTLP/HTTP-JSON request for one cargo phase.

    ``service.name=github-ci`` (a resource attribute) routes the span to the
    ``github-ci`` dataset; the span carries the shared build-telemetry scheme
    attributes, the ``cache`` block's ``build.cache.*`` attributes, and the
    optional ``work_item_id`` correlation tag. ``build_env`` is the lane label
    the CALLER resolved (``resolve_build_env``), passed in rather than read here
    so this builder stays a pure function of its arguments. int64 fields
    are JSON strings per the proto3-JSON mapping Honeycomb expects; trace/span
    ids are freshly random (each cargo phase is its own independent span in v1).
    """
    exit_code = int(inputs["exit_code"])  # type: ignore[call-overload]
    attributes: list[dict[str, object]] = [
        {"key": "build.env", "value": {"stringValue": build_env}},
        {"key": "build.phase", "value": {"stringValue": str(inputs["phase"])}},
        {"key": "repo", "value": {"stringValue": facts["repo"]}},
        {"key": "git.commit.sha", "value": {"stringValue": facts["sha"]}},
        {"key": "toolchain.version", "value": {"stringValue": facts["toolchain"]}},
        {"key": "cargo.subcommand", "value": {"stringValue": str(inputs["subcmd"])}},
        {"key": "exit_code", "value": {"intValue": str(exit_code)}},
    ]
    attributes.extend(cache)
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
    stats: Callable[..., str | None] = read_sccache_stats,
) -> int:
    """Emit one cargo-phase span for THIS lane from the environment; return 0/2.

    ``emit``, ``facts`` and ``stats`` are seams tests inject. A malformed
    environment writes a usage line to stderr and returns ``2`` without
    emitting. The return value is advisory only — the shim discards it and exits
    with cargo's own code — but a clean 0/2 keeps the CLI unit-testable.

    The CI lane with NO configured endpoint returns early WITHOUT emitting, and
    before the git and sccache probes, which cost the job too. The factory's
    default endpoint is a docker-bridge address of the FACTORY host, unreachable
    from a k3s workflow pod, so a POST there could only ever spend the emitter's
    timeout per measured cargo invocation and discard the span. Configuring an
    endpoint (the pod-reachable host collector) restores the emission, labelled
    ``build.env=ci``.
    """
    inputs = parse_env(environ=environ)
    if inputs is None:
        _ = sys.stderr.write(_USAGE)
        return 2
    endpoint = (environ.get(_ENDPOINT_ENV) or "").strip()
    build_env = resolve_build_env(environ=environ)
    # Only the FACTORY lane may fall back to DEFAULT_ENDPOINT, which is an
    # address of the factory host; any other lane without a configured receiver
    # has nowhere to post and skips rather than paying the timeout to discover it.
    if build_env != BUILD_ENV and not endpoint:
        return 0
    cache = cache_attributes(environ=environ, stats=stats(environ=environ))
    payload = build_span_payload(inputs=inputs, facts=facts(), cache=cache, build_env=build_env)
    _ = emit(endpoint=endpoint or DEFAULT_ENDPOINT, payload=payload)
    return 0


def main() -> int:
    """Baked entry point: ``--zero-stats`` zeroes before cargo, else emits the span.

    Both modes return 0 unconditionally on a well-formed invocation; the shim
    discards the code and exits with cargo's own.
    """
    environ = dict(os.environ)
    if "--zero-stats" in sys.argv[1:]:
        _ = zero_sccache_stats(environ=environ)
        return 0
    return run(environ=environ)


if __name__ == "__main__":
    raise SystemExit(main())
