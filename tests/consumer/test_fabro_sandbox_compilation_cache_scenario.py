"""Consumer-tier: `SPECIFICATION/scenarios.md` §"a fabro sandbox hits the shared compilation cache".

    Given the factory sandbox image sets the compiler wrapper and the host
    compilation-cache endpoint over the docker bridge
    And the factory receiver's allowlist admits `build.cache.*`
    When a console dispatch compiles dependency crates the populator already built
    Then those crates MUST be served from the shared cache
    And the dispatch's `build.cargo-*` spans MUST carry
    `build.cache.sccache.hit_ratio` greater than zero

Two of the three moving parts are committed HERE and are driven as such: the
sandbox's `rustc-wrapper` (`docker/fabro-sandbox/agent/sccache-or-rustc.sh`,
run over fake compilers under `tmp_path`) and the baked span emitter
(`livespec_dev_tooling.otel_cargo_phase`, driven through its own injected
`emit` / `facts` / `stats` seams). The third — the factory receiver's attribute
allowlist — lives in `livespec-orchestrator-beads-fabro`, not in this
repository, and `.ai/factory-span-receiver.md` is this repository's record of
that; nothing here asserts it, and nothing here pretends to.

The scenario's "MUST be served from the shared cache" and "hit_ratio greater
than zero" are one claim seen from two ends: a wrapper that decides the cache
is unusable produces exactly the same span as one that never had a cache, so
the wrapper's VERDICT and the span's RATIO have to be checked against each
other. Both arms of both are driven — a cache that answers and a cache that
does not — because the failure this closes was a wrapper that flipped itself to
`unusable` under load and built plainly for the rest of the container while
every span it emitted still looked well-formed.
"""

from __future__ import annotations

import json
import os
import re
import stat
import subprocess
from pathlib import Path
from typing import Any

import pytest

from livespec_dev_tooling.otel_cargo_phase import BUILD_ENV, DEFAULT_ENDPOINT, run

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SANDBOX = _REPO_ROOT / "docker" / "fabro-sandbox" / "agent"
_WRAPPER = _SANDBOX / "sccache-or-rustc.sh"
_DOCKERFILE = _SANDBOX / "Dockerfile"

# The wrapper's two verdict markers, and the path the image bakes it at — the
# value a `rustc-wrapper` line has to name for cargo to reach it at all.
_USABLE = "usable"
_UNUSABLE = "unusable"
_BAKED_WRAPPER = "/usr/local/bin/sccache-or-rustc"

# The docker BRIDGE gateway: the address a sandbox container reaches its host's
# services on. The compilation cache and the OTLP receiver are both behind it,
# which is the "over the docker bridge" the scenario names.
_BRIDGE_GATEWAY = "172.17.0.1"

_SCCACHE_ENDPOINT_ARG = re.compile(
    r"^ARG SCCACHE_REDIS_ENDPOINT=(?P<endpoint>\S+)\s*$", re.MULTILINE
)
_RUSTC_WRAPPER = re.compile(r'rustc-wrapper = "(?P<wrapper>[^"]+)"')

_HIT_RATIO = "build.cache.sccache.hit_ratio"
_BACKEND = "build.cache.sccache.backend"
_ENABLED = "build.cache.sccache.enabled"
_BUILD_ENV_KEY = "build.env"

# A dependency-crate phase whose crates the populator already built: sccache
# answered for four in five. The shape is sccache's own
# `--show-stats --stats-format=json`, which is what the baked emitter reads.
_WARM_STATS = json.dumps(
    {
        "stats": {
            "cache_hits": {"counts": {"Rust": 40}},
            "cache_misses": {"counts": {"Rust": 10}},
            "cache_errors": {"counts": {}},
            "cache_location": f"Redis: redis://{_BRIDGE_GATEWAY}:6379",
        }
    }
)

_PHASE_ENV = {
    "BUILD_PHASE": "compile",
    "BUILD_SUBCMD": "build",
    "BUILD_START_NANO": "1000000000",
    "BUILD_END_NANO": "2000000000",
    "BUILD_EXIT_CODE": "0",
}

_FACTS = {
    "repo": "thewoolleyman/livespec-console-beads-fabro",
    "sha": "0" * 40,
    "toolchain": "1.90.0",
}


def _fake(*, directory: Path, name: str, body: str) -> None:
    """Write an executable stand-in for one compiler onto a scratch PATH."""
    directory.mkdir(parents=True, exist_ok=True)
    tool = directory / name
    _ = tool.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    tool.chmod(tool.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _assert_the_remembered_verdict_is_read(*, root: Path, first_sccache: list[str]) -> None:
    """Drive the wrapper a SECOND time against a state directory it already judged.

    Every compile after a container's first one takes the remembered-verdict
    branch, not the probe branch, so a wrapper that stopped reaching the cache
    once its verdict was recorded would serve the whole run cold while its
    first invocation still looked right. The probe must not run again either:
    its synthetic compile is the one sccache call the caller did not ask for,
    and re-paying it per compile is what the marker exists to avoid.
    """
    repeat_rc, repeat_sccache, repeat_rustc = _drive_wrapper(root=root, cache_answers=True)
    assert (
        repeat_rc == 0
    ), f"the caller's own exit code must survive the cached verdict too; rc={repeat_rc}"
    assert repeat_rustc == [], (
        f"a remembered-usable cache must not fall back to the plain compiler — that branch is "
        f"every compile in the container after the first; rustc invocations={repeat_rustc}"
    )
    assert len(repeat_sccache) > len(first_sccache), (
        f"the second caller's request must go through sccache as well; "
        f"before={first_sccache} after={repeat_sccache}"
    )
    probes = [line for line in repeat_sccache if "--edition 2021" in line]
    assert len(probes) == 1, (
        f"and the probe must have run exactly ONCE across both invocations — a verdict that is "
        f"recorded but not READ costs a bounded probe per compile; probes={probes}"
    )


def _drive_wrapper(*, root: Path, cache_answers: bool) -> tuple[int, list[str], list[str]]:
    """Run the committed wrapper once; return (rc, sccache argv lines, rustc argv lines).

    The two fakes stand in for the compilers the wrapper chooses between:
    `sccache` exits non-zero for the probe when the cache does not answer,
    which is exactly what an unreachable backend looks like at first use, and
    `rustc` is the plain compiler the wrapper must fall back to.
    """
    scratch = root / "bin"
    sccache_log = root / "sccache.log"
    rustc_log = root / "rustc.log"
    _fake(
        directory=scratch,
        name="sccache",
        body=f'printf "%s\\n" "$*" >> "{sccache_log}"\nexit {0 if cache_answers else 1}',
    )
    _fake(directory=scratch, name="rustc", body=f'printf "%s\\n" "$*" >> "{rustc_log}"\nexit 0')
    env = dict(os.environ)
    env["PATH"] = f"{scratch}{os.pathsep}{env.get('PATH', '')}"
    env["SCCACHE_OR_RUSTC_STATE"] = str(root / "state")
    env["SCCACHE_OR_RUSTC_PROBE_TIMEOUT_S"] = "20"
    completed = subprocess.run(
        ["sh", str(_WRAPPER), "rustc", "--version"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=120,
    )
    return (
        completed.returncode,
        sccache_log.read_text(encoding="utf-8").splitlines() if sccache_log.exists() else [],
        rustc_log.read_text(encoding="utf-8").splitlines() if rustc_log.exists() else [],
    )


def _emitted_span(*, stats_text: str | None) -> tuple[str, dict[str, Any]]:
    """Drive the baked cargo-phase emitter once; return (endpoint, span)."""
    captured: list[tuple[str, dict[str, Any]]] = []

    def _emit(*, endpoint: str, payload: dict[str, Any]) -> bool:
        captured.append((endpoint, payload))
        return True

    def _facts() -> dict[str, str]:
        return dict(_FACTS)

    def _stats(*, environ: dict[str, str]) -> str | None:
        _ = environ
        return stats_text

    assert run(environ=dict(_PHASE_ENV), emit=_emit, facts=_facts, stats=_stats) == 0
    assert len(captured) == 1, f"exactly one span per cargo phase; captured={captured}"
    endpoint, payload = captured[0]
    return endpoint, payload["resourceSpans"][0]["scopeSpans"][0]["spans"][0]


def _attributes(*, span: dict[str, Any]) -> dict[str, Any]:
    """One span's attributes as a plain key -> scalar mapping."""
    return {entry["key"]: next(iter(entry["value"].values())) for entry in span["attributes"]}


def test_a_sandbox_reaches_the_shared_cache_over_the_bridge_and_says_so_in_its_span(
    *, tmp_path: Path
) -> None:
    """The whole scenario, as the two halves this repository owns.

    THE WRAPPER, driven both ways. "Those crates MUST be served from the shared
    cache" is a decision the sandbox makes ONCE per container, and the decision
    is the scenario: a container that judged the cache unusable compiles every
    crate itself while nothing about the run looks different. So the cache that
    ANSWERS must leave the caller's own request going through sccache, and the
    cache that does not must leave the caller compiling plainly with its own
    exit code intact — a cache fault must never change a run's cargo outcome,
    which is why the wrapper exists instead of a bare `rustc-wrapper = sccache`.

    THE SPAN, driven both ways. "`build.cargo-*` spans MUST carry
    `build.cache.sccache.hit_ratio` greater than zero" is only meaningful
    against the arm where there is no cache: a ratio attribute that is always
    present and always zero satisfies a naive reading and reports nothing. The
    warm arm must name the redis backend and a positive ratio; the cold arm
    must be the same eight keys with the cache reported off, so one query shape
    covers both.

    OVER THE BRIDGE, read. The endpoint the span goes to and the endpoint the
    cache is reached at are the same host address by construction — the docker
    bridge gateway — and both are baked into the image rather than passed in,
    because fabro's spawn allowlist can strip an environment variable but not a
    file. The wrapper the image bakes must be THIS script at the path the
    `rustc-wrapper` line names, or cargo never calls it and the whole decision
    above never happens.
    """
    warm_rc, warm_sccache, warm_rustc = _drive_wrapper(root=tmp_path / "warm", cache_answers=True)
    assert warm_rc == 0, f"the caller's own exit code must survive the wrapper; rc={warm_rc}"
    assert (tmp_path / "warm" / "state" / _USABLE).exists(), (
        f"a cache that answers the probe must be REMEMBERED as usable — the decision is made "
        f"once per container, and re-probing per compile is what the marker exists to avoid; "
        f"state={sorted(p.name for p in (tmp_path / 'warm' / 'state').iterdir())}"
    )
    assert any("--version" in line for line in warm_sccache), (
        f"with the cache usable, the CALLER's request must go through sccache — that is what "
        f"'served from the shared cache' means at the only point this repository controls; "
        f"sccache invocations={warm_sccache}"
    )
    assert warm_rustc == [], (
        f"and it must not ALSO reach the plain compiler, or the wrapper is compiling twice "
        f"and the cache is decoration; rustc invocations={warm_rustc}"
    )

    _assert_the_remembered_verdict_is_read(root=tmp_path / "warm", first_sccache=warm_sccache)

    cold_rc, cold_sccache, cold_rustc = _drive_wrapper(root=tmp_path / "cold", cache_answers=False)
    assert cold_rc == 0, (
        f"a cache fault must NEVER change the run's outcome: the wrapper's whole reason for "
        f"existing is that sccache's own client fails the build when its server cannot start "
        f"against an unreachable backend; rc={cold_rc}"
    )
    assert (tmp_path / "cold" / "state" / _UNUSABLE).exists(), (
        f"the failed probe's verdict must be remembered too, or every compile in the "
        f"container pays the probe again; state="
        f"{sorted(p.name for p in (tmp_path / 'cold' / 'state').iterdir())}"
    )
    assert any(
        "--version" in line for line in cold_rustc
    ), f"and the caller's request must reach the plain compiler; rustc={cold_rustc}"
    assert not any("--version" in line for line in cold_sccache), (
        f"the caller's request must NOT have gone through the sccache the probe just judged "
        f"unusable — only the probe's own synthetic compile may; sccache={cold_sccache}"
    )

    warm_endpoint, warm_span = _emitted_span(stats_text=_WARM_STATS)
    warm_attributes = _attributes(span=warm_span)
    assert warm_span["name"] == "build.cargo-build", (
        f"the span must be a `build.cargo-*` one, named for the subcommand the phase ran; "
        f"name={warm_span['name']!r}"
    )
    assert warm_attributes[_HIT_RATIO] > 0 and warm_attributes[_BACKEND] == "redis", (
        f"a dispatch compiling crates the populator already built must report a positive "
        f"hit ratio against the SHARED backend — a positive ratio against a local disk cache "
        f"would satisfy the arithmetic and none of the scenario; attributes={warm_attributes}"
    )
    assert warm_attributes[_BUILD_ENV_KEY] == BUILD_ENV, (
        f"and it must be labelled as factory work: the same baked image serves the CI lane, "
        f"and a mislabelled span pollutes every factory query in the shared dataset; "
        f"attributes={warm_attributes}"
    )
    assert warm_endpoint == DEFAULT_ENDPOINT and _BRIDGE_GATEWAY in DEFAULT_ENDPOINT, (
        f"with no receiver configured, a factory sandbox posts to the host over the docker "
        f"bridge — the same path the cache is reached on; endpoint={warm_endpoint!r}"
    )

    _, cold_span = _emitted_span(stats_text=None)
    cold_attributes = _attributes(span=cold_span)
    assert cold_attributes[_ENABLED] is False and cold_attributes[_HIT_RATIO] == 0, (
        f"a phase with no cache at all must report the cache OFF with a zero ratio — that is "
        f"what makes the positive ratio above evidence of a hit rather than of an attribute "
        f"that is always there; attributes={cold_attributes}"
    )
    assert sorted(cold_attributes) == sorted(warm_attributes), (
        f"and the two must carry the SAME keys, so one query shape covers a sandbox with the "
        f"shared cache and one without; cold={sorted(cold_attributes)} "
        f"warm={sorted(warm_attributes)}"
    )

    dockerfile = _DOCKERFILE.read_text(encoding="utf-8")
    endpoint_arg = _SCCACHE_ENDPOINT_ARG.search(dockerfile)
    assert endpoint_arg is not None and _BRIDGE_GATEWAY in endpoint_arg.group("endpoint"), (
        f"the image must BAKE the host compilation-cache endpoint at the bridge gateway: "
        f"sccache reads it from a config file precisely because the factory's spawn allowlist "
        f"can strip an environment variable and cannot strip a file; "
        f"ARG={endpoint_arg.group('endpoint') if endpoint_arg else None}"
    )
    wrapper = _RUSTC_WRAPPER.search(dockerfile)
    assert wrapper is not None and wrapper.group("wrapper") == _BAKED_WRAPPER, (
        f"and cargo must be pointed at the wrapper driven above rather than at sccache "
        f"itself, or the one-probe-per-container decision never runs and an unreachable "
        f"backend fails the build; rustc-wrapper={wrapper.group('wrapper') if wrapper else None}"
    )
    assert f"{_WRAPPER.relative_to(_REPO_ROOT)} {_BAKED_WRAPPER}" in dockerfile, (
        f"and the file baked at that path must be THIS committed script, or the test above "
        f"drives something the image does not ship; dockerfile="
        f"{_DOCKERFILE.relative_to(_REPO_ROOT)}"
    )
