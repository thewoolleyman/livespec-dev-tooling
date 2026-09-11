"""Consumer-tier: the `SPECIFICATION/scenarios.md` scenario

    "a fabro sandbox hits the shared compilation cache"

WHAT A CHECK RUNNER OWNS OF IT. The scenario's subject is a console dispatch
compiling in a fabro sandbox against a redis on the factory host, reached over
the docker bridge. No redis answers here and no container starts here — but
every artifact BETWEEN those two ends is committed in this repository, and all
three of them are executable: the image's wiring (`docker/fabro-sandbox/agent/
Dockerfile`), the `rustc-wrapper` that decides whether a compile is served from
the shared cache at all (`sccache-or-rustc.sh`), and the emitter that turns a
finished cargo phase into the scenario's span (`otel_cargo_phase.py`). So this
file RUNS the wrapper and RUNS the emitter, and reads only the image wiring —
which is a Dockerfile, and so is text by nature.

WHY THE WIRING IS ASSERTED AS FILES RATHER THAN ENVIRONMENT. fabro spawns its
ACP nodes under a fail-closed env allowlist, so no `SCCACHE_*` variable can be
relied on to reach cargo inside the sandbox; the image therefore writes the
endpoint into sccache's own config and the wrapper into the cargo config, and
BOTH of those files are what the Given's "sets the compiler wrapper and the host
compilation-cache endpoint over the docker bridge" means. The endpoint's HOST is
asserted, not merely its presence: `172.17.0.1` is the bridge gateway, which
inside a container is the factory HOST, while a loopback endpoint is the
container itself — a cache of one, per dispatch, that answers every lookup with
a miss and reports no error anywhere.

WHY THE WRAPPER IS RUN RATHER THAN READ. "Those crates MUST be served from the
shared cache" is a statement about what the wrapper DECIDES, once per container,
from a probe whose answer a check runner can choose. Reading the script can say
it contains an `exec sccache`; only running it can say which of its two branches
a live backend reaches, that the probe is paid ONCE, and that a dead backend
still compiles (the degradation contract that keeps a cache fault from failing a
dispatch). Both arms are real runs of the committed script, with `sccache` and
`rustc` as recording stubs on `PATH` — the one boundary a check runner cannot
own — and the state directory under `tmp_path`.

WHY THE SPAN IS EMITTED RATHER THAN COMPUTED. The final Then is about what
arrives at the receiver, so the assertion is made on the bytes that arrive: the
committed emitter is driven through its own entry point with a stub `sccache`
answering `--show-stats`, and a loopback OTLP receiver stands in for the factory
host's, capturing the request the sandbox would really have posted. The Given's
allowlist half is asserted on that same captured payload as the one consequence
it has in THIS tree: the receiver admits the `build.cache.*` PREFIX, so a cache
attribute emitted outside that namespace is stripped in flight and the scenario's
final clause becomes unobservable while every artifact here still looks correct.

CONTROL ARMS. Every reader takes TEXT or a captured payload, so each is fed a
counter-example and asserted to convict; and the two runs are paired with runs of
the SAME artifact under the opposite condition — a probe that fails, a cache that
returns no hits, a backend that is the container's own disk. The zero-hit arm is
the one that matters most: it is the difference between asserting a ratio ABOVE
ZERO and asserting that some number was reported.
"""

from __future__ import annotations

import http.server
import json
import os
import re
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from livespec_dev_tooling.otel_cargo_phase import main

if TYPE_CHECKING:
    from collections.abc import Iterator

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SANDBOX = _REPO_ROOT / "docker" / "fabro-sandbox"
_AGENT_DOCKERFILE = _SANDBOX / "agent" / "Dockerfile"
_WRAPPER = _SANDBOX / "agent" / "sccache-or-rustc.sh"

# The wrapper's committed source and the path the cargo config names it by.
_WRAPPER_SOURCE = "docker/fabro-sandbox/agent/sccache-or-rustc.sh"
_WRAPPER_PATH = "/usr/local/bin/sccache-or-rustc"
# The docker bridge gateway: inside a sandbox container this address is the
# FACTORY HOST, which is the only thing that makes the cache a SHARED one.
_BRIDGE_GATEWAY = "172.17.0.1"
# The prefix the factory receiver's forwarded-attribute allowlist admits.
_CACHE_PREFIX = "build.cache."
# The two marker files the wrapper remembers its once-per-container verdict in.
_VERDICT_MARKERS = ("usable", "unusable")
_RUN_TIMEOUT_S = 60.0

_REDIS_ENDPOINT_ARG = re.compile(r"^ARG\s+SCCACHE_REDIS_ENDPOINT=(?P<url>\S+)", re.MULTILINE)
_ENDPOINT_HOST = re.compile(r"^[a-z]+://(?P<host>[^:/]+)")

# The counter-examples the control arms feed back through the readers: an image
# pointing sccache at the container's own loopback, wiring nothing into either
# config file and baking no wrapper — and, for the attribute reader, a payload
# whose cache keys sit outside the namespace the receiver forwards.
_CONTROL_DOCKERFILE = """\
ARG SCCACHE_REDIS_ENDPOINT=redis://127.0.0.1:6379
RUN printf 'nothing at all\\n' > /dev/null
"""
_CONTROL_ATTRIBUTES = [
    {"key": "sccache.hit_ratio", "value": {"doubleValue": 0.9}},
    {"key": "build.cache.sccache.hits", "value": {"intValue": "9"}},
    {"key": "cache.registry.hit", "value": {"boolValue": True}},
]

_SCCACHE_STUB = """\
#!/bin/sh
echo "$*" >> "$SCCACHE_LOG"
case "$*" in
  *probe.rs*) exit "$PROBE_EXIT" ;;
esac
echo sccache >> "$COMPILE_LOG"
exit 0
"""
_RUSTC_STUB = """\
#!/bin/sh
echo rustc >> "$COMPILE_LOG"
exit 0
"""
_STATS_STUB = """\
#!/bin/sh
case "$*" in
  *--show-stats*) cat %(stats)s ;;
esac
exit 0
"""

# Decoded OTLP payloads exactly as they arrived, so the walk below is over
# nested JSON rather than over a shape this file declared for itself.
_RECEIVED: list[Any] = []


@dataclass(frozen=True, kw_only=True)
class _Span:
    """One span as it reached the receiver, with its attributes unwrapped."""

    name: str
    attributes: list[dict[str, object]]
    values: dict[str, object]


class _Receiver(http.server.BaseHTTPRequestHandler):
    """The factory host's OTLP receiver, standing in on loopback."""

    def do_POST(self) -> None:  # noqa: N802 — the stdlib handler's own name.
        """Record the payload the sandbox posted and answer 200, as the receiver does."""
        length = int(self.headers.get("Content-Length", "0"))
        _RECEIVED.append(json.loads(self.rfile.read(length)))
        self.send_response(200)
        self.end_headers()

    def log_message(self, *_args: object, **_kwargs: object) -> None:
        """Silence the handler's per-request access log."""


@pytest.fixture(name="receiver")
def _receiver_fixture() -> Iterator[str]:
    """A loopback OTLP receiver; yields the endpoint the emitter is pointed at."""
    _RECEIVED.clear()
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Receiver)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()
    thread.join(timeout=_RUN_TIMEOUT_S)


def _endpoint_host(*, url: str) -> str:
    """The host an endpoint URL names; ``""`` when it names none."""
    found = _ENDPOINT_HOST.match(url)
    return "" if found is None else found.group("host")


def _bridge_wiring_gaps(*, dockerfile: str) -> list[str]:
    """Each way the image would leave a sandbox pointed at no shared cache."""
    gaps: list[str] = []
    declared = _REDIS_ENDPOINT_ARG.search(dockerfile)
    if declared is None:
        gaps.append("no SCCACHE_REDIS_ENDPOINT: the image bakes no cache endpoint at all")
    elif _endpoint_host(url=declared.group("url")) != _BRIDGE_GATEWAY:
        gaps.append(f"the endpoint {declared.group('url')} is not the docker bridge gateway")
    if "[cache.redis]" not in dockerfile or "/root/.config/sccache/config" not in dockerfile:
        gaps.append("the endpoint is never written into sccache's own config file")
    if f'rustc-wrapper = "{_WRAPPER_PATH}"' not in dockerfile:
        gaps.append(f"the cargo config does not set rustc-wrapper to {_WRAPPER_PATH}")
    if f"{_WRAPPER_SOURCE} {_WRAPPER_PATH}" not in dockerfile:
        gaps.append("the committed wrapper is never copied to the path the cargo config names")
    return gaps


def _write_stub(*, path: Path, body: str) -> None:
    """Write one executable stub onto the run's PATH."""
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def _run_wrapper(*, root: Path, probe_exit: int, calls: int = 1) -> dict[str, list[str]]:
    """Run the committed wrapper ``calls`` times; report what it did.

    ``sccache`` and ``rustc`` are recording stubs — the one boundary a check
    runner cannot own — and the probe's verdict is the test's to choose. The
    child's environment is built from scratch, and it is ``sh`` rather than
    Python, so nothing of the harness reaches it.
    """
    binaries = root / "bin"
    binaries.mkdir(parents=True, exist_ok=True)
    _write_stub(path=binaries / "sccache", body=_SCCACHE_STUB)
    _write_stub(path=binaries / "rustc", body=_RUSTC_STUB)
    state = root / "state"
    compiled, logged = root / "compiled", root / "sccache-argv"
    for _ in range(calls):
        done = subprocess.run(
            ["sh", str(_WRAPPER), "rustc", "--crate-name", "serde", "--edition", "2021"],
            capture_output=True,
            text=True,
            timeout=_RUN_TIMEOUT_S,
            check=False,
            env={
                "PATH": f"{binaries}{os.pathsep}/usr/bin{os.pathsep}/bin",
                "SCCACHE_OR_RUSTC_STATE": str(state),
                "SCCACHE_OR_RUSTC_PROBE_TIMEOUT_S": "20",
                "PROBE_EXIT": str(probe_exit),
                "COMPILE_LOG": str(compiled),
                "SCCACHE_LOG": str(logged),
            },
        )
        assert done.returncode == 0, (
            f"a compile through the wrapper must exit with the compiler's own code — a cache "
            f"fault never fails a dispatch; rc={done.returncode} stderr={done.stderr!r}"
        )
    return {
        "compilers": _lines(path=compiled),
        "probes": [line for line in _lines(path=logged) if "probe.rs" in line],
        "verdicts": sorted(
            entry.name for entry in state.iterdir() if entry.name in _VERDICT_MARKERS
        ),
    }


def _lines(*, path: Path) -> list[str]:
    """The non-empty lines a stub recorded, or none when it never ran."""
    return path.read_text(encoding="utf-8").split() if path.exists() else []


def _emit_span(*, root: Path, endpoint: str, stats: str | None, warm_registry: bool) -> _Span:
    """Drive the committed emitter once through its own entry point; return its span.

    ``stats`` is the JSON a live ``sccache --show-stats`` would print, or
    ``None`` for a sandbox with no compilation cache at all.
    """
    binaries = root / "emit-bin"
    binaries.mkdir(parents=True, exist_ok=True)
    if stats is not None:
        answer = root / "stats.json"
        answer.write_text(stats, encoding="utf-8")
        _write_stub(path=binaries / "sccache", body=_STATS_STUB % {"stats": answer})
    cargo_home = root / "cargo-home"
    if warm_registry:
        (cargo_home / "registry" / "cache").mkdir(parents=True, exist_ok=True)
    environment = {
        "PATH": f"{binaries}{os.pathsep}/usr/bin{os.pathsep}/bin",
        "BUILD_PHASE": "compile",
        "BUILD_SUBCMD": "build",
        "BUILD_START_NANO": "1000",
        "BUILD_END_NANO": "2000",
        "BUILD_EXIT_CODE": "0",
        "CARGO_HOME": str(cargo_home),
        "SCCACHE_REDIS_RW_MODE": "READ_ONLY",
        "LIVESPEC_SANDBOX_OTEL_ENDPOINT": endpoint,
    }
    before = len(_RECEIVED)
    with pytest.MonkeyPatch.context() as patched:
        patched.setattr(os, "environ", environment)
        patched.chdir(root)
        assert main() == 0, "the emitter must report a clean emission for a well-formed phase"
    assert len(_RECEIVED) == before + 1, (
        f"exactly one span must reach the receiver per measured cargo phase; "
        f"received={len(_RECEIVED) - before}"
    )
    arrived = _RECEIVED[-1]["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
    attributes = list(arrived["attributes"])
    return _Span(
        name=str(arrived["name"]),
        attributes=attributes,
        values={
            str(entry["key"]): next(iter(dict(entry["value"]).values())) for entry in attributes
        },
    )


def _attributes_outside_the_allowlist(*, attributes: list[dict[str, object]]) -> list[str]:
    """Each cache attribute the factory receiver's `build.cache.*` allowlist would strip."""
    return sorted(
        str(entry["key"])
        for entry in attributes
        if "cache" in str(entry["key"]) and not str(entry["key"]).startswith(_CACHE_PREFIX)
    )


def _stats(*, hits: int, misses: int, location: str) -> str:
    """The stats document a live sccache prints for one measured phase."""
    return json.dumps(
        {
            "stats": {
                "cache_hits": {"counts": {"Rust": hits}},
                "cache_misses": {"counts": {"Rust": misses}},
                "cache_errors": {"counts": {}},
                "cache_location": location,
            }
        }
    )


def test_a_fabro_sandbox_hits_the_shared_compilation_cache(tmp_path: Path, receiver: str) -> None:
    """§"a fabro sandbox hits the shared compilation cache", clause by clause.

    THE IMAGE SETS THE WRAPPER AND THE HOST ENDPOINT OVER THE DOCKER BRIDGE:
    four committed facts, each silent when wrong. The endpoint must name the
    BRIDGE GATEWAY — a loopback endpoint resolves to the container itself, which
    gives every dispatch a private cache that reports no error and never hits.
    It must be written into sccache's own config FILE, and the wrapper into the
    cargo config FILE, because fabro's fail-closed env allowlist means no
    `SCCACHE_*` variable can be relied on to arrive. And the wrapper the cargo
    config names must be the committed script, or the path names nothing.

    THOSE CRATES MUST BE SERVED FROM THE SHARED CACHE: asserted by RUNNING the
    committed wrapper. With the backend answering the probe, the compile is
    exec'd through sccache — which is what "served from the shared cache" is at
    this seam — the probe is paid exactly ONCE however many compiles follow
    (cargo starts several rustc at once; a per-compile probe would spend the
    sandbox's four vCPUs on synthetic crates), and the verdict is remembered.

    THE SPANS MUST CARRY `build.cache.sccache.hit_ratio` GREATER THAN ZERO:
    asserted on the bytes that reach a receiver, from a real run of the
    committed emitter. The span's NAME must match `build.cargo-*`, since the
    scenario names those spans and a phase emitted under any other name is
    absent from the query that would observe this. The backend must be the
    SHARED one: a hit ratio above zero against a container-local disk satisfies
    the arithmetic and not the scenario.

    THE RECEIVER'S ALLOWLIST ADMITS `build.cache.*`: the emitter's half of that
    Given is that every cache attribute it produces sits INSIDE that namespace.
    An attribute named outside it is dropped in flight — the span still arrives,
    still looks well formed, and the clause above becomes unobservable.

    CONTROL ARMS, each a run of the same artifact under the opposite condition:
    a probe that FAILS falls back to plain rustc, records `unusable`, and still
    exits zero; a cache that returns NO hits reports a ratio of exactly 0.0
    through the same reader; and a container-local backend is reported as
    `local-disk` rather than the shared `redis`.
    """
    wiring = _bridge_wiring_gaps(dockerfile=_AGENT_DOCKERFILE.read_text(encoding="utf-8"))
    assert not wiring, (
        f"the sandbox image must point cargo at the wrapper and the wrapper's sccache at the "
        f"factory host over the docker bridge, and must do it in FILES — fabro's env allowlist "
        f"is fail-closed, so an `SCCACHE_*` variable cannot be relied on to reach cargo at all; "
        f"gaps={wiring}"
    )

    live = _run_wrapper(root=tmp_path / "live", probe_exit=0, calls=2)
    assert live["compilers"] == ["sccache", "sccache"] and live["verdicts"] == ["usable"], (
        f"with the backend answering, every compile must be exec'd THROUGH sccache — that is "
        f"what 'served from the shared cache' is at this seam — and the verdict must be "
        f"remembered rather than re-decided; ran={live['compilers']} state={live['verdicts']}"
    )
    assert len(live["probes"]) == 1, (
        f"the probe is a synthetic compile paid ONCE per container: cargo starts several rustc "
        f"together, so a probe per compile spends the sandbox's four vCPUs deciding a question "
        f"already answered; probes={live['probes']}"
    )

    warm = _emit_span(
        root=tmp_path / "warm",
        endpoint=receiver,
        stats=_stats(hits=9, misses=3, location=f"Redis: redis://{_BRIDGE_GATEWAY}:6379"),
        warm_registry=True,
    )
    served = warm.values
    assert warm.name.startswith("build.cargo-"), (
        f"the scenario names the dispatch's `build.cargo-*` spans, so a measured phase emitted "
        f"under any other name is absent from the query that observes it; name={warm.name!r}"
    )
    assert served["build.cache.sccache.hit_ratio"] > 0, (
        f"a dispatch compiling crates the populator already built must report a hit ratio above "
        f"zero; attributes={served}"
    )
    assert served["build.cache.sccache.backend"] == "redis", (
        f"the cache must be the SHARED one: a hit ratio above zero against a container-local "
        f"disk satisfies the arithmetic and not the scenario; backend="
        f"{served['build.cache.sccache.backend']!r}"
    )
    assert served["build.env"] == "factory" and served["build.cache.registry.hit"] is True, (
        f"the span must ride the factory lane the receiver forwards under, and report the warm "
        f"crate registry the sandbox image bakes; attributes={served}"
    )

    stripped = _attributes_outside_the_allowlist(attributes=warm.attributes)
    assert not stripped, (
        f"the factory receiver forwards by an ALLOWLIST over the `build.cache.*` prefix, so a "
        f"cache attribute emitted outside that namespace is dropped in flight — the span still "
        f"arrives and still looks well formed, and the hit ratio becomes unobservable; "
        f"outside={stripped}"
    )

    dead = _run_wrapper(root=tmp_path / "dead", probe_exit=1)
    assert dead["compilers"] == ["rustc"] and dead["verdicts"] == ["unusable"], (
        f"a backend that cannot answer must fall back to a plain local compile, so the wrapper "
        f"assertion above cannot be satisfied by a wrapper that only ever does one thing; "
        f"ran={dead['compilers']} state={dead['verdicts']}"
    )

    cold = _emit_span(
        root=tmp_path / "cold",
        endpoint=receiver,
        stats=_stats(hits=0, misses=12, location=f"Redis: redis://{_BRIDGE_GATEWAY}:6379"),
        warm_registry=False,
    ).values
    assert cold["build.cache.sccache.hit_ratio"] == 0.0 and cold["build.cache.sccache.enabled"], (
        f"a cache that served nothing must report exactly 0.0 through the same reader — that is "
        f"the difference between asserting a ratio ABOVE ZERO and asserting that some number was "
        f"reported at all; attributes={cold}"
    )
    assert (
        cold["build.cache.registry.hit"] is False
    ), f"and the registry probe must report a cold sandbox as cold; attributes={cold}"

    local = _emit_span(
        root=tmp_path / "local",
        endpoint=receiver,
        stats=_stats(hits=9, misses=3, location="Local disk: /root/.cache/sccache"),
        warm_registry=False,
    ).values
    assert local["build.cache.sccache.backend"] == "local-disk", (
        f"a container-private cache must be reported as such, or 'shared' is a word the backend "
        f"attribute cannot carry; backend={local['build.cache.sccache.backend']!r}"
    )

    absent = _emit_span(
        root=tmp_path / "absent", endpoint=receiver, stats=None, warm_registry=False
    ).values
    assert absent["build.cache.sccache.enabled"] is False, (
        f"a sandbox with no compilation cache must still emit the phase, degraded rather than "
        f"dropped — the attributes are the same eight either way; attributes={absent}"
    )

    assert _bridge_wiring_gaps(dockerfile=_CONTROL_DOCKERFILE) == [
        "the endpoint redis://127.0.0.1:6379 is not the docker bridge gateway",
        "the endpoint is never written into sccache's own config file",
        f"the cargo config does not set rustc-wrapper to {_WRAPPER_PATH}",
        "the committed wrapper is never copied to the path the cargo config names",
    ], "the wiring reader must still convict an image whose cache is the container's own loopback"
    assert len(_bridge_wiring_gaps(dockerfile="")) == 4, (
        "and must still convict an image that wires nothing at all, rather than reading an "
        "absent endpoint as an acceptable one"
    )
    assert _attributes_outside_the_allowlist(attributes=_CONTROL_ATTRIBUTES) == [
        "cache.registry.hit",
        "sccache.hit_ratio",
    ], "the allowlist reader must still convict cache attributes outside the forwarded namespace"
