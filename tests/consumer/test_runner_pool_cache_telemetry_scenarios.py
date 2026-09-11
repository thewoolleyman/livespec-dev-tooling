"""Consumer-tier: the three `SPECIFICATION/scenarios.md` cache degradation scenarios.

    "a cache fault degrades a job to cold and never fails it"
    "a canary job runs cold and is tagged"
    "a stale warm-cache generation fires the trigger"

WHY THIS FILE RUNS THE HOOK INSTEAD OF READING IT. Its sibling
`test_runner_pool_cache_isolation_scenarios.py` asserts the pool's cache
ISOLATION scenarios by reading the committed gitops, because what those
scenarios turn on — a real inode, a real redis reply — cannot be observed from a
check runner at all. The two degradation scenarios here are different in kind:
what they turn on is what the pod's `postStart` hook DECIDES, and that hook is a
POSIX shell script committed in full inside `arc/hook-pod-template.yaml`. A
regex cannot tell a recorded reason from a comment mentioning one, and it cannot
tell whether the script survives the condition at all — so this file EXECUTES
the committed script and asserts on what it left behind: its exit status, the
warm-copy rows it recorded, the kill-switch state it published, which seeds
survived, and whether it wrote the job's cargo configuration.

THE HARNESS AND ITS FOUR DOUBLES, NAMED. The script runs VERBATIM apart from
four substitutions at exactly the boundaries a check runner cannot own:

  - `/__w`, `/.cargo` and `/opt/ci-runner/bin` are rewritten to directories
    under `tmp_path`. They are absolute paths inside a job container; a test
    that created them would be mutating the host. The pool binary directory is
    left EMPTY on purpose, which exercises the real "a node without the pool's
    binaries degrades to no compilation cache, never to a pod that cannot
    start" path and keeps the redis probe short-circuited (its `[ -x …sccache ]`
    guard fails first), so no test here opens a socket.
  - `curl` is a stub on `PATH` whose exit status is the test's to choose. It IS
    the crates-proxy probe's answer, and choosing it is what makes the canary
    assertion discriminating: with the proxy ANSWERING, a skipped registry tier
    can only be the canary rule's doing.

The environment handed to the child is built from scratch rather than inherited,
so no coverage variable reaches it. The child is `sh`, never Python, so it
cannot self-instrument.

WHAT THE CONTROL ARMS ARE HERE. Each scenario's assertion is paired with a run
of the SAME script through the SAME reader under the opposite condition, which
is a stronger arm than a synthetic counter-example because the counter-example
is produced by the artifact under test:

  - the cache fault's non-empty `build.cache.error` is paired with a SEEDED run
    whose error is empty — so a hook that stamped an error unconditionally, or a
    reader that reported one regardless, fails.
  - the canary's every-tier-skipped is paired with a run at `CI_CACHE_CANARY_N=0`
    where the same seeds survive and the same proxy gets a cargo source
    replacement written — so a harness that simply never seeded anything fails.
  - the canary tag is paired with an operator-switched run tagged `operator`,
    which is the distinctness
    `non-functional-requirements.md` §"Cold canary" requires in as many words.

The stale-generation scenario has no runtime half a check runner can reach — it
is a host timer, a gauge and a Honeycomb trigger — so it keeps the sibling's
text-reader shape, with one assertion that cannot be satisfied by either file
alone: the trigger's threshold is computed against the populator CronJob's OWN
schedule, so the 2x relationship breaks if either artifact drifts.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PHASE2 = _REPO_ROOT / "ci-runner" / "k3s" / "phase2"
_OBSERVABILITY = _REPO_ROOT / "ci-runner" / "observability"

# The pod template carrying the lifecycle hooks every routed job's container runs.
_HOOK_TEMPLATE = _PHASE2 / "arc" / "hook-pod-template.yaml"
# The provisioner whose `setup` script makes (or declines to make) the warm seed.
_PROVISIONER = _PHASE2 / "local-path-provisioner" / "local-path-provisioner.yaml"
# The emitter that turns the hook's recorded rows into `cache.warm-copy` spans.
_SPAN_EMITTER = _PHASE2 / "cache-telemetry" / "ci-cache-span.sh"
# The populator whose publish schedule the stale-generation threshold is twice.
_POPULATOR = _PHASE2 / "warm-cache" / "warm-cache-cronjob.yaml"
# The host's liveness path: the gauge emitter and the timer that is its cadence.
_GAUGES = _OBSERVABILITY / "ci-cache-gauges.sh"
_GAUGES_TIMER = _OBSERVABILITY / "ci-cache-gauges.timer"
# The stale-generation value trigger, and the converge that applies it.
_STALE_TRIGGER = _OBSERVABILITY / "triggers" / "ci-cache-warm-generation-stale.json"
_APPLY_TRIGGERS = _OBSERVABILITY / "triggers" / "apply-triggers.sh"

_POOL_BIN = "/opt/ci-runner/bin"
_CACHE_TIERS = ("uv", "registry", "target")
_SEEDED_TIERS = ("uv", "target")
_ROW_COLUMNS = (
    "at_ns",
    "tier",
    "hit",
    "generation",
    "copy_ms",
    "copy_bytes",
    "copy_method",
    "error",
)
_UV_GENERATION = "20260911T000000Z"
_TARGET_GENERATION = "20260911T001500Z"
_HOOK_TIMEOUT_S = 60

# A population of pod names the canary rule is exercised over, and the one of
# them the committed rule selects at N=2. Fixed names, so the partition below is
# deterministic rather than sampled: nothing here can flake.
_POD_NAMES = tuple(f"runner-abc-{index}" for index in range(12))
_SELECTED_AT_TWO = "runner-abc-2"

_GAUGE_PREFIX = "livespec.ci_cache."
_AGE_GAUGE = f"{_GAUGE_PREFIX}generation_age_s"
_UV_TIER_FILTER = ("tier", "=", "uv")
_POPULATOR_NAME = "warm-cache-populate"
_POPULATOR_NAMESPACE = "ci-warm-cache"

_SET_ERREXIT = re.compile(r"^\s*set\s+-\w*e", re.MULTILINE)
_EMITTER_CALL = re.compile(
    rf"(?P<guard>\[ -x {re.escape(_POOL_BIN)}/ci-cache-span \] && )?"
    rf"{re.escape(_POOL_BIN)}/ci-cache-span \S+"
)
_PROVISIONER_SETUP = re.compile(r"^  setup: \|-\n(?P<body>.*?)\n  [a-z]", re.MULTILINE | re.DOTALL)
_GUARDED_UV_SEED = re.compile(
    r"if ! \(.*?cp -a --reflink=always.*?\); then\n(?P<recover>.*?)\n\s*else", re.DOTALL
)
_COMMON_BLOCK = re.compile(r"^common = \[(?P<body>.*?)\]\n", re.MULTILINE | re.DOTALL)
_ATTRIBUTE_NAME = re.compile(r'attr\("(?P<name>[\w.]+)"')
_CANARY_N = re.compile(r'name:\s*CI_CACHE_CANARY_N\s*\n\s*value:\s*"(?P<n>\d+)"')
_CRON_SCHEDULE = re.compile(r'^\s*schedule:\s*"\*/(?P<minutes>\d+) \* \* \* \*"', re.MULTILINE)
_GAUGE_SPEC_ROW = re.compile(
    r'^\s*\("(?P<gauge>[\w.]+)",\s*"(?P<reading>\w+)",\s*"(?P<unit>[^"]*)",.*?,'
    r"\s*(?P<attributes>\{[^}]*\}|None),\s*(?:True|False)\),$",
    re.MULTILINE,
)

# The synthetic counter-examples the text readers are fed: a provisioner whose
# seed failure aborts the whole setup script under its own `set -eu` (the shape
# that would fail volume provisioning, and so the pod, on a cache fault), a
# trigger that fires at ONE populate interval with no runbook, and a gauge table
# that publishes the age with no tier attribute.
_CONTROL_PROVISIONER = """\
apiVersion: v1
data:
  setup: |-
    #!/bin/sh
    set -eu
    mkdir -m 0777 -p "${VOL_DIR}"
    cp -a --reflink=always "${src}/." "${VOL_DIR}/_warm/uv"
  teardown: |-
    rm -rf "${VOL_DIR}"
"""
_CONTROL_TRIGGER = json.dumps(
    {
        "name": "CI warm cache stale",
        "description": "Fires when the uv generation is older than one populate interval.",
        "query": {
            "calculations": [{"op": "MAX", "column": _AGE_GAUGE}],
            "filters": [{"column": "host.name", "op": "=", "value": "poweredge-xubuntu"}],
        },
        "threshold": {"op": ">", "value": 1800},
        "tags": [{"key": "kind", "value": "derived"}],
    }
)
_CONTROL_GAUGES = """\
spec = [
  ("generation_age_s", "uv_generation_age_s", "s", "Seconds since publish", None, False),
]
"""
# A pod template whose `postStart` is defective in all three ways at once — it
# runs under `set -e`, calls the emitter with no `[ -x … ]` guard, and can fall
# off its end without an `exit 0` — and which declares no `preStop` at all. Each
# of those turns a cache fault into a killed container.
_CONTROL_TEMPLATE = f"""\
      lifecycle:
        postStart:
          exec:
            command:
              - sh
              - -c
              - |
                set -eu
                {_POOL_BIN}/ci-cache-span publish-endpoint
                rec uv false "" 0 0 reflink-seed ""
"""


@dataclass(frozen=True, kw_only=True)
class _HookRun:
    """What one real run of the committed `postStart` hook left behind in a work volume."""

    exit_code: int
    rows: tuple[dict[str, str], ...]
    kill_switch: str | None
    seeds_left: tuple[str, ...]
    cargo_config: str | None


def _lifecycle_script(*, template: str, hook: str) -> str:
    """The shell script a lifecycle hook runs, dedented out of its YAML block scalar."""
    block = re.compile(
        rf"^        {re.escape(hook)}:\n          exec:\n            command:\n"
        rf"              - sh\n              - -c\n              - \|\n"
        rf"(?P<body>(?:                [^\n]*\n|\n)*)",
        re.MULTILINE,
    ).search(template)
    if block is None:
        return ""
    lines = block.group("body").splitlines()
    return "\n".join(line[16:] if line.startswith(" " * 16) else line for line in lines)


def _run_post_start(
    *, root: Path, env: dict[str, str], seeded: bool, proxy_answers: bool
) -> _HookRun:
    """Run the committed `postStart` hook against a work volume under `root`."""
    work, cargo, pool_bin, stub = root / "w", root / "cargo", root / "bin", root / "stub"
    for made in (work, pool_bin, stub):
        made.mkdir(parents=True)
    if seeded:
        (work / "_warm" / "uv" / "pkg").mkdir(parents=True)
        (work / "_warm" / "uv" / "pkg" / "wheel.whl").write_text("seeded", encoding="utf-8")
        (work / "_warm" / ".uv-generation").write_text(f"{_UV_GENERATION}\n", encoding="utf-8")
        stamp = work / "_warm" / "target" / "console" / "asan"
        stamp.mkdir(parents=True)
        (stamp / ".generation").write_text(f"{_TARGET_GENERATION}\n", encoding="utf-8")
    (stub / "curl").write_text(f"#!/bin/sh\nexit {0 if proxy_answers else 7}\n", encoding="utf-8")
    (stub / "curl").chmod(0o755)
    script = _lifecycle_script(
        template=_HOOK_TEMPLATE.read_text(encoding="utf-8"), hook="postStart"
    )
    for absolute, local in (("/__w", work), ("/.cargo", cargo), (_POOL_BIN, pool_bin)):
        script = script.replace(absolute, str(local))
    hook = root / "post-start.sh"
    hook.write_text(script, encoding="utf-8")
    # The child is the committed hook under `sh`, never a Python interpreter, so it
    # cannot self-instrument under coverage; its environment is built from scratch
    # rather than inherited, so no `COVERAGE_*` variable reaches it either.
    done = subprocess.run(
        ["sh", str(hook)],
        capture_output=True,
        text=True,
        timeout=_HOOK_TIMEOUT_S,
        check=False,
        env={
            "PATH": f"{stub}{os.pathsep}{os.environ.get('PATH', '/usr/bin:/bin')}",
            "HOSTNAME": "runner-abc-default",
            **env,
        },
    )
    state = work / "_temp" / "_ci_cache"
    recorded = state / "warm-copy.tsv"
    switch = state / "kill_switch"
    config = cargo / "config.toml"
    rows = recorded.read_text(encoding="utf-8").splitlines() if recorded.is_file() else []
    return _HookRun(
        exit_code=done.returncode,
        rows=tuple(
            dict(zip(_ROW_COLUMNS, (row.split("\t") + [""] * 8)[:8], strict=True)) for row in rows
        ),
        kill_switch=switch.read_text(encoding="utf-8") if switch.is_file() else None,
        seeds_left=tuple(tier for tier in _SEEDED_TIERS if (work / "_warm" / tier).exists()),
        cargo_config=config.read_text(encoding="utf-8") if config.is_file() else None,
    )


def _tier_rows(*, run: _HookRun) -> dict[str, dict[str, str]]:
    """The warm-copy row the hook recorded for each cache tier, by tier."""
    return {row["tier"]: row for row in run.rows}


def _canary_verdicts(*, root: Path, canary_n: int) -> dict[str, str]:
    """The pool's own canary verdict for each pod name, from a real run of the hook."""
    return {
        name: _run_post_start(
            root=root / f"n{canary_n}-{index}",
            env={"CI_CACHE_CANARY_N": str(canary_n), "HOSTNAME": name},
            seeded=False,
            proxy_answers=False,
        ).kill_switch
        or ""
        for index, name in enumerate(_POD_NAMES)
    }


def _lifecycle_fail_soft_gaps(*, template: str) -> list[str]:
    """Each way a lifecycle hook could FAIL THE POD rather than degrade the job to cold."""
    gaps: list[str] = []
    for hook in ("postStart", "preStop"):
        body = _lifecycle_script(template=template, hook=hook)
        unguarded = [
            call.group(0) for call in _EMITTER_CALL.finditer(body) if not call.group("guard")
        ]
        gaps += [
            f"{hook}: the hook {missing}"
            for missing, present in (
                ("does not end in an unconditional `exit 0`", body.rstrip().endswith("exit 0")),
                (
                    "runs under `set -e`, so one failing command aborts it",
                    not _SET_ERREXIT.search(body),
                ),
                (f"invokes the emitter unguarded: {unguarded}", not unguarded),
            )
            if not present
        ]
    return gaps


def _provisioner_setup_script(*, manifest: str) -> str:
    """The script the provisioner runs while it provisions a job's work volume."""
    block = _PROVISIONER_SETUP.search(manifest)
    return "" if block is None else block.group("body")


def _seed_failure_gaps(*, manifest: str) -> list[str]:
    """Each way an absent or failed warm seed would fail provisioning rather than go cold."""
    setup = _provisioner_setup_script(manifest=manifest)
    guarded = _GUARDED_UV_SEED.search(setup)
    recovery = "" if guarded is None else guarded.group("recover")
    return [
        missing
        for missing, present in (
            ("the setup script does not run under `set -eu`", "set -eu" in setup),
            ("the uv seed is not inside a failure guard", guarded is not None),
            (
                "a failed seed is not cleaned back to NO cache",
                'rm -rf "${VOL_DIR}/_warm"' in recovery,
            ),
            (
                "a failed seed aborts the script instead of going cold",
                guarded is not None and "exit" not in recovery,
            ),
            ("an absent generation link is not guarded", 'if [ -L "${warm}/uv" ]; then' in setup),
        )
        if not present
    ]


def _fault_span_gaps(*, emitter: str) -> list[str]:
    """Each missing thing that would stop a recorded fault becoming the scenario's span."""
    return [
        missing
        for missing, present in (
            ("the `cache.warm-copy` span name", 'span("cache.warm-copy"' in emitter),
            (
                "`build.cache.hit` read as a boolean from the recorded row",
                'attr("build.cache.hit", hit == "true")' in emitter,
            ),
            (
                "`build.cache.error` carried from the recorded row",
                'attr("build.cache.error", error)' in emitter,
            ),
            (
                "a replay of the rows the hook recorded",
                'os.path.join(STATE, "warm-copy.tsv")' in emitter,
            ),
            (
                "an emit failure kept away from the job",
                "except Exception as exc:" in emitter and "urlopen(req, timeout=2)" in emitter,
            ),
        )
        if not present
    ]


def _span_common_attributes(*, emitter: str) -> list[str]:
    """Every attribute the emitter puts on EVERY cache span it builds for a job."""
    block = _COMMON_BLOCK.search(emitter)
    if block is None:
        return []
    return sorted({found.group("name") for found in _ATTRIBUTE_NAME.finditer(block.group("body"))})


def _configured_canary_n(*, template: str) -> int | None:
    """The canary fraction's N as the pod template ships it; None when it ships none."""
    stated = _CANARY_N.search(template)
    return None if stated is None else int(stated.group("n"))


def _populator_interval_s(*, manifest: str) -> int | None:
    """The populator CronJob's publish interval in seconds; None when it is not a minute step."""
    stated = _CRON_SCHEDULE.search(manifest)
    return None if stated is None else int(stated.group("minutes")) * 60


def _published_gauge(*, gauges: str, gauge: str) -> dict[str, str] | None:
    """A gauge's reading name, unit and attributes as the emitter publishes it."""
    for row in _GAUGE_SPEC_ROW.finditer(gauges):
        if row.group("gauge") == gauge:
            return {
                "reading": row.group("reading"),
                "unit": row.group("unit"),
                "attributes": row.group("attributes"),
            }
    return None


def _liveness_gauge_gaps(*, gauges: str, timer: str) -> list[str]:
    """Each missing thing that would stop the host's liveness path emitting the age gauge."""
    return [
        missing
        for missing, present in (
            (
                "the age is not read from the current generation's own mtime",
                'put uv_generation_age_s "$(( now - $(stat -c %Y "${target}") ))"' in gauges,
            ),
            (
                f"the readings are not published under the {_GAUGE_PREFIX} namespace",
                f'return {{"name": "{_GAUGE_PREFIX}" + name,' in gauges,
            ),
            (
                "the emission is not the host's liveness path",
                '"service.name": "ci-runner-liveness"' in gauges,
            ),
            ("the liveness path is not on a fixed cadence", "OnUnitActiveSec=5min" in timer),
            (
                "an unreadable warm root does not make the run fail closed",
                'log "warm root ${WARM_ROOT}/uv has no current generation; omitting the uv tier"'
                in gauges
                and 'exit "${failed}"' in gauges,
            ),
        )
        if not present
    ]


def _stale_trigger_gaps(*, trigger: str, interval_s: int | None) -> list[str]:
    """Each missing thing that would stop the stale-generation VALUE trigger firing."""
    try:
        rule = json.loads(trigger)
    except json.JSONDecodeError:
        return ["the trigger definition is not parseable JSON"]
    query = rule.get("query", {})
    calculated = {(row.get("op"), row.get("column")) for row in query.get("calculations", [])}
    scoped = {
        (row.get("column"), row.get("op"), row.get("value")) for row in query.get("filters", [])
    }
    threshold = rule.get("threshold", {})
    tagged = {tag.get("key"): tag.get("value") for tag in rule.get("tags", [])}
    described = rule.get("description", "")
    return [
        missing
        for missing, present in (
            (
                f"the trigger does not calculate MAX({_AGE_GAUGE})",
                ("MAX", _AGE_GAUGE) in calculated,
            ),
            ("the trigger is not scoped to the warm uv tier", _UV_TIER_FILTER in scoped),
            (
                f"the threshold is not twice the populator's {interval_s}s interval",
                interval_s is not None
                and threshold.get("op") == ">"
                and threshold.get("value") == 2 * interval_s,
            ),
            ("the trigger is not registered as a value trigger", tagged.get("kind") == "value"),
            ("the description carries no runbook", "Runbook:" in described),
            (
                f"the runbook does not name the populator ({_POPULATOR_NAME}/{_POPULATOR_NAMESPACE})",
                _POPULATOR_NAME in described and _POPULATOR_NAMESPACE in described,
            ),
        )
        if not present
    ]


def test_a_cache_fault_degrades_a_job_to_cold_and_never_fails_it(*, tmp_path: Path) -> None:
    """§"a cache fault degrades a job to cold and never fails it", clause by clause.

    THE GIVEN, AS THE POD ACTUALLY MEETS IT. "The warm-cache tree is absent or
    unreadable on the node" reaches a job pod as ONE observable and nothing
    else: no seed in its work volume. The provisioner resolves the generation
    link, copies it, and on ANY failure removes the half-made seed and says so
    on stderr — so an absent tree, an unpublished generation, a filesystem
    without reflink and a failed copy are indistinguishable downstream, by
    design. The fault arm below provisions a work volume with no seed, which is
    every one of those conditions at once.

    THE JOB MUST RUN TO ITS OWN OUTCOME. In Kubernetes a `postStart` hook that
    exits non-zero KILLS the container, so "never fails it" is carried by this
    script's exit status and by nothing else — which is why it is asserted from
    a real run rather than read. Three further ways the degradation could become
    a failure are asserted structurally, because each is silent until the day it
    fires: the hook must not run under `set -e` (one failing probe would abort
    it mid-tier), it must reach its `exit 0` unconditionally, and it must invoke
    the emitter only behind an `[ -x … ]` guard so a node that has not installed
    the pool binaries degrades to no telemetry rather than to a pod that cannot
    start. The provisioner half is asserted the same way and for a sharper
    reason: its setup script DOES run under `set -eu`, so the `if !` guard
    around the seed is the only thing standing between a failed copy and a
    failed volume provision — and a volume that fails to provision fails the
    job, which is exactly this scenario's prohibition.

    A SPAN WITH `hit` FALSE AND A NON-EMPTY `error`. The hook records a row per
    tier and the preStop emitter replays it, so the clause needs both halves.
    The recorded half is the fault arm's uv row: cold with a REASON. An empty
    error there would be indistinguishable from an ordinary miss, which is how a
    node whose warm tree has gone unreadable looks like nothing but a slow job —
    it is the shape this repository shipped until this scenario was covered. The
    emitter half must carry that column through to `build.cache.error`, read
    `hit` back as a boolean, and keep its own POST failures away from the job.

    THE CONTROL ARM IS THE SEEDED RUN. The same script, read by the same reader,
    with a seed present: the uv row is a hit and its error is EMPTY. A hook that
    stamped a reason unconditionally, or a reader that reported one regardless,
    passes the fault arm and fails this one.
    """
    faulted = _run_post_start(root=tmp_path / "fault", env={}, seeded=False, proxy_answers=False)
    assert faulted.exit_code == 0, (
        f"a `postStart` hook that exits non-zero KILLS the container, so this exit status IS "
        f'the scenario\'s "never fails it": a cache fault must leave the job running to its '
        f"own outcome; exit={faulted.exit_code}"
    )

    cold = _tier_rows(run=faulted)
    assert sorted(cold) == sorted(_CACHE_TIERS), (
        f"a faulted job must still be a MEASURED cold job — every tier reports, or the "
        f"degradation is invisible and indistinguishable from an emitter that died; "
        f"recorded={sorted(cold)} expected={sorted(_CACHE_TIERS)}"
    )
    assert cold["uv"]["hit"] == "false" and cold["uv"]["error"], (
        f"with no seed in the volume the warm-uv tier must record a cold row carrying a "
        f"REASON: an empty error is read as an ordinary miss, so a node whose warm tree has "
        f"gone unreadable presents as nothing but a slow job; row={cold['uv']}"
    )
    assert faulted.seeds_left == () and faulted.cargo_config is None, (
        f"the job must actually be COLD: no seed survives a fault, and a backend that did "
        f"not answer its probe must leave the job's own cargo configuration untouched rather "
        f"than point it at a dead proxy; seeds={faulted.seeds_left} cargo={faulted.cargo_config}"
    )

    template = _HOOK_TEMPLATE.read_text(encoding="utf-8")
    failable = _lifecycle_fail_soft_gaps(template=template)
    seeding = _seed_failure_gaps(manifest=_PROVISIONER.read_text(encoding="utf-8"))
    assert not failable and not seeding, (
        f"every layer between a cache fault and the job must be fail-soft: a hook under "
        f"`set -e` aborts mid-tier, a hook that can miss its `exit 0` kills the container, an "
        f"unguarded emitter call fails on a node without the pool binaries, and the "
        f"provisioner's seed runs under `set -eu` — so its failure guard is the only thing "
        f"between a failed copy and a failed volume provision, which fails the job; "
        f"hooks={failable} provisioner={seeding}"
    )

    emission = _fault_span_gaps(emitter=_SPAN_EMITTER.read_text(encoding="utf-8"))
    assert not emission, (
        f"the recorded reason must reach the scenario's span: the emitter replays the hook's "
        f"rows as `cache.warm-copy` spans, reads `hit` back as a boolean and carries the "
        f"error column to `build.cache.error` — and its own POST must never reach the job; "
        f"gaps={emission}"
    )

    warm = _run_post_start(root=tmp_path / "control", env={}, seeded=True, proxy_answers=False)
    seeded_uv = _tier_rows(run=warm)["uv"]
    assert seeded_uv["hit"] == "true" and seeded_uv["error"] == "", (
        f"CONTROL ARM: the same hook, the same reader, a seed present — the uv row must be a "
        f"hit with an EMPTY error. A hook that stamped a reason unconditionally, or a reader "
        f"that reported one regardless, satisfies the fault arm and fails here; "
        f"row={seeded_uv}"
    )
    assert seeded_uv["generation"] == _UV_GENERATION, (
        f"and the hit must identify the generation it read, or `build.cache.generation_age_s` "
        f"has nothing to age; generation={seeded_uv['generation']!r}"
    )
    assert _seed_failure_gaps(manifest=_CONTROL_PROVISIONER) == [
        "the uv seed is not inside a failure guard",
        "a failed seed is not cleaned back to NO cache",
        "a failed seed aborts the script instead of going cold",
        "an absent generation link is not guarded",
    ], "the provisioner reader must still convict a seed whose failure aborts `set -eu` setup"
    assert (
        len(_fault_span_gaps(emitter="")) == 5
    ), "the emitter reader must still convict an emitter that carries no error column"
    assert _lifecycle_fail_soft_gaps(template=_CONTROL_TEMPLATE) == [
        "postStart: the hook does not end in an unconditional `exit 0`",
        "postStart: the hook runs under `set -e`, so one failing command aborts it",
        f"postStart: the hook invokes the emitter unguarded: "
        f"['{_POOL_BIN}/ci-cache-span publish-endpoint']",
        "preStop: the hook does not end in an unconditional `exit 0`",
    ], "the fail-soft reader must still convict a hook that turns a cache fault into a kill"


def test_a_canary_job_runs_cold_and_is_tagged(*, tmp_path: Path) -> None:
    """§"a canary job runs cold and is tagged", clause by clause.

    GIVEN THE POOL'S CANARY FRACTION IS ONE JOB IN N. N is a plain value in the
    pod template (`CI_CACHE_CANARY_N`), and the rule is
    `cksum(pod name) % N == 0`. Two properties make that "the pool's
    deterministic rule" rather than a coin flip, and both are asserted from real
    runs: the same pod name yields the same verdict every time, and across a
    population of pod names the rule PARTITIONS — at N=2 some are selected and
    some are not. The partition arm is what rules out the two degenerate
    readings a single run cannot tell apart, a rule that selects everything and
    a rule that selects nothing. At the committed N the selected set must stay a
    minority, because a canary that ran most jobs cold would be the kill switch
    wearing the canary's name. The rule reads only the pod name the kubelet set
    and N from the template — never a workflow value, which
    §"Trust by construction" forbids for any per-job decision.

    EVERY CACHE TIER MUST BE SKIPPED. Asserted against a run where every tier
    WAS available: the seeds are in the volume and the crates proxy answers its
    probe. The canary then removes both seeded trees and writes no cargo
    configuration at all — so the registry and compilation tiers are off because
    the rule turned them off, not because their backend was missing. That is the
    whole reason this arm chooses a succeeding probe; the `CI_CACHE_CANARY_N=0`
    control runs the same script against the same answering proxy and DOES get
    its seeds and its source replacement, which is what makes the canary arm's
    emptiness attributable.

    EVERY CACHE SPAN MUST CARRY `build.cache.kill_switch` EQUAL TO `canary`.
    Two halves again. The hook must publish `canary` into the state directory —
    and publish it BEFORE the skip branch, or a canary job's spans could not
    carry the tag at all — and every row it then records must say `off:canary`.
    The emitter must read that state into the attributes COMMON to every cache
    span, not just the warm-copy ones, which is the difference between "every
    cache span for that job" and "most of them". The operator control arm is the
    distinctness §"Cold canary" demands in as many words: the same hook, the
    same reader, `CI_CACHE_KILL_SWITCH=operator` — tagged `operator`, never
    `canary`.

    THE TIMINGS MUST BE QUERYABLE AGAINST NON-CANARY JOBS OF THE SAME
    REPOSITORY AND PHASE. A canary that emitted nothing would be cold and
    unqueryable, which is the failure mode this clause exists to forbid: the
    skip branch must still record a row per tier, each with its own elapsed
    `copy_ms`. The comparison's axes are then the common attributes — `repo` for
    the repository, `k8s.pod.name` to join the job's own phase spans, and the
    kill-switch column itself, which is what makes "non-canary jobs" a
    selectable set rather than an assumption.
    """
    template = _HOOK_TEMPLATE.read_text(encoding="utf-8")
    canary_n = _configured_canary_n(template=template)
    assert canary_n is not None and canary_n > 1, (
        f"the scenario's Given is a canary fraction of one job in N, so the pool must ship a "
        f"concrete N above 1 as a plain template value an operator can change without "
        f"deploying any routed repository; CI_CACHE_CANARY_N={canary_n}"
    )

    canary = _run_post_start(
        root=tmp_path / "canary",
        env={"CI_CACHE_CANARY_N": "1"},
        seeded=True,
        proxy_answers=True,
    )
    assert canary.exit_code == 0 and canary.kill_switch == "canary", (
        f"a selected job must publish `canary` into its state directory, and must publish it "
        f"before the skip branch — the emitter reads that file at preStop, so a tag written "
        f"later or not at all is a cold job no query can find; "
        f"exit={canary.exit_code} kill_switch={canary.kill_switch!r}"
    )
    assert canary.seeds_left == () and canary.cargo_config is None, (
        f"EVERY tier must be skipped, asserted against a job where every tier was AVAILABLE: "
        f"both seeds were in the volume and the crates proxy answered its probe, so an empty "
        f"volume and an unwritten cargo configuration can only be the rule's doing; "
        f"seeds={canary.seeds_left} cargo={canary.cargo_config}"
    )

    tagged = _tier_rows(run=canary)
    assert sorted(tagged) == sorted(_CACHE_TIERS), (
        f"a canary that emitted nothing would be cold and UNQUERYABLE, which is what this "
        f"scenario's third Then forbids — every tier must still report; "
        f"recorded={sorted(tagged)}"
    )
    assert all(row["hit"] == "false" and row["error"] == "off:canary" for row in tagged.values()), (
        f"every cache row for a canary job must be a miss carrying the canary tag, so the "
        f"cold reading is attributable to the sampler rather than to a fault; rows={tagged}"
    )
    assert all(row["copy_ms"].isdigit() for row in tagged.values()), (
        f"and each row must carry its own elapsed cost, or the warm-versus-cold comparison "
        f"this scenario exists to make possible has no left-hand side; rows={tagged}"
    )

    common = _span_common_attributes(emitter=_SPAN_EMITTER.read_text(encoding="utf-8"))
    missing = sorted(
        {"build.cache.kill_switch", "repo", "git.branch", "k8s.pod.name"} - set(common)
    )
    assert not missing, (
        f"the tag must ride the attributes common to EVERY cache span the emitter builds — "
        f"warm-copy and job-summary alike — beside the axes the comparison needs: `repo` for "
        f"the repository, `k8s.pod.name` to join this job's own phase spans, and the "
        f'kill-switch column that makes "non-canary jobs" selectable; '
        f"missing={missing} common={common}"
    )

    plain = _run_post_start(
        root=tmp_path / "plain",
        env={"CI_CACHE_CANARY_N": "0"},
        seeded=True,
        proxy_answers=True,
    )
    assert plain.kill_switch == "" and plain.seeds_left == _SEEDED_TIERS, (
        f"CONTROL ARM: the same hook against the same answering proxy with the sampler off "
        f"must keep both seeds and tag nothing. Without this arm a harness that simply never "
        f"seeded anything would satisfy the canary assertion above; "
        f"kill_switch={plain.kill_switch!r} seeds={plain.seeds_left}"
    )
    assert plain.cargo_config is not None and "replace-with" in plain.cargo_config, (
        f"and it must get the crates-io source replacement the canary did not, which is what "
        f"makes the canary's unwritten configuration a SKIP rather than an unreachable "
        f"backend; cargo={plain.cargo_config}"
    )

    operator = _run_post_start(
        root=tmp_path / "operator",
        env={"CI_CACHE_KILL_SWITCH": "operator"},
        seeded=True,
        proxy_answers=True,
    )
    assert operator.kill_switch == "operator" and all(
        row["error"] == "off:operator" for row in _tier_rows(run=operator).values()
    ), (
        f"CONTROL ARM: an operator-switched job is equally cold and must be tagged "
        f"DISTINCTLY — that distinctness is what lets the hit-floor trigger exclude a "
        f"deliberate switch-off without also discarding the canary baseline; "
        f"kill_switch={operator.kill_switch!r} rows={_tier_rows(run=operator)}"
    )

    partitioned = _canary_verdicts(root=tmp_path / "partition", canary_n=2)
    assert set(partitioned.values()) == {"canary", ""}, (
        f"the rule must PARTITION a population of pod names rather than select all of them "
        f"or none — the two degenerate readings a single run cannot tell apart; "
        f"verdicts={partitioned}"
    )
    sampled = _canary_verdicts(root=tmp_path / "sampled", canary_n=canary_n)
    selected = [name for name, verdict in sampled.items() if verdict == "canary"]
    assert len(selected) * 2 < len(_POD_NAMES), (
        f"at the committed N the selected set must stay a minority: a canary running most "
        f"jobs cold is the kill switch wearing the canary's name; "
        f"selected={selected} of {len(_POD_NAMES)} at N={canary_n}"
    )
    repeated = [
        _run_post_start(
            root=tmp_path / f"repeat-{attempt}",
            env={"CI_CACHE_CANARY_N": "2", "HOSTNAME": _SELECTED_AT_TWO},
            seeded=False,
            proxy_answers=False,
        ).kill_switch
        for attempt in range(3)
    ]
    assert repeated == ["canary"] * 3, (
        f"and the rule must be DETERMINISTIC on the pod name: the same pod selected once is "
        f"selected every time, so the canary is a standing query and not a coin flip; "
        f"verdicts={repeated}"
    )
    assert (
        _configured_canary_n(template="") is None
    ), "the N reader must report an absent fraction rather than assuming the shipped default"
    assert (
        _span_common_attributes(emitter="") == []
    ), "the common-attribute reader must still convict an emitter that builds no common block"


def test_a_stale_warm_cache_generation_fires_the_trigger() -> None:
    """§"a stale warm-cache generation fires the trigger", clause by clause.

    WHY THIS ONE IS READ RATHER THAN RUN. Its two siblings above turn on a
    decision a committed shell script makes, so they execute it. This scenario's
    subject is a host systemd timer, an OTLP gauge and a Honeycomb trigger
    evaluated in Honeycomb — none of which a check runner can reach, and the
    emitter's own readings come from a node path (`/var/lib/rancher/k3s/storage`)
    the provisioner keeps 0700 root precisely so nothing else can. So this
    asserts the committed definitions, and asserts the one thing about them that
    neither file can satisfy alone.

    THE HOST'S LIVENESS PATH MUST EMIT THE GENERATION-AGE GAUGE. Four things
    make that true and each is separately silent. The reading must come from the
    CURRENT generation's own mtime, so the age is the publish age rather than a
    symlink's. It must be published as `livespec.ci_cache.generation_age_s`
    carrying `tier=uv`, because the trigger filters on that tier and a gauge
    published without the attribute matches nothing while still arriving. It
    must ride the liveness path's resource (`service.name=ci-runner-liveness`)
    on the path's fixed cadence, which is what makes "the host's liveness path"
    true of it and what the dead-man trigger counts. And an unreadable warm root
    must make the run FAIL CLOSED — omit the gauge and exit non-zero — rather
    than emit a comforting zero: the absent column is what the dead-man fires
    on, and a false zero would be read as a freshly published generation.

    THE TRIGGER MUST FIRE AT TWICE THE POPULATE INTERVAL. This is the assertion
    neither artifact can satisfy on its own, and the reason the threshold is not
    simply compared to 3600: the bound is read out of the populator CronJob's
    OWN schedule and doubled, so re-scheduling the populator without moving the
    trigger — or moving the trigger without the populator — breaks this test.
    The rest of the clause is shape: a MAX calculation over the gauge the host
    emits, scoped to the uv tier, registered as a `value` trigger (a trigger
    that exists but is not of that kind never evaluates), and living in the
    directory the converge script globs, since a definition the converge cannot
    see is a file and not a trigger.

    WITH A RUNBOOK NAMING THE POPULATOR. A stale generation is not actionable
    from the gauge: the age says a publish did not happen and nothing about why,
    so the clause requires the description to carry a runbook and to NAME the
    populator — the CronJob and the namespace an operator types next.

    CONTROL ARMS. Every reader takes TEXT, so each is fed a counter-example that
    is wrong in exactly the way the real artifact is right: a trigger thresholded
    at ONE populate interval with no runbook and the wrong kind, a gauge table
    publishing the age with no tier attribute, a schedule that is not a minute
    step, and the empty document.
    """
    interval_s = _populator_interval_s(manifest=_POPULATOR.read_text(encoding="utf-8"))
    assert interval_s is not None and interval_s > 0, (
        f"the scenario's bound is stated in populate intervals, so the populator's schedule "
        f"must be readable as one; interval={interval_s}"
    )
    populator = _POPULATOR.read_text(encoding="utf-8")
    assert (
        f"name: {_POPULATOR_NAME}" in populator
        and f"namespace: {_POPULATOR_NAMESPACE}" in populator
    ), (
        f"and it must be the populator the runbook names, or the trigger sends an operator to "
        f"a CronJob that does not exist; expected {_POPULATOR_NAME} in {_POPULATOR_NAMESPACE}"
    )

    gauges = _GAUGES.read_text(encoding="utf-8")
    emission = _liveness_gauge_gaps(gauges=gauges, timer=_GAUGES_TIMER.read_text(encoding="utf-8"))
    assert not emission, (
        f"the host's liveness path must emit the generation age from the current "
        f"generation's own mtime, on the path's fixed cadence, under the liveness resource — "
        f"and must FAIL CLOSED on an unreadable warm root rather than emit a comforting zero "
        f"a reader cannot tell from a fresh publish; gaps={emission}"
    )
    assert _published_gauge(gauges=gauges, gauge="generation_age_s") == {
        "reading": "uv_generation_age_s",
        "unit": "s",
        "attributes": '{"tier": "uv"}',
    }, (
        "the age must be published in seconds carrying `tier=uv`: the trigger filters on "
        "that attribute, and a gauge published without it matches nothing while still arriving"
    )

    trigger = _STALE_TRIGGER.read_text(encoding="utf-8")
    gaps = _stale_trigger_gaps(trigger=trigger, interval_s=interval_s)
    assert not gaps, (
        f"the stale-generation VALUE trigger must calculate MAX({_AGE_GAUGE}) for the uv "
        f"tier and fire above TWICE the populator's own {interval_s}s schedule — the bound is "
        f"read from the CronJob rather than written twice, so moving either artifact without "
        f"the other breaks here — and must carry a runbook naming the populator, since the "
        f"gauge says a publish did not happen and nothing about why; gaps={gaps}"
    )
    assert _STALE_TRIGGER.parent == _APPLY_TRIGGERS.parent and (
        '"${SCRIPT_DIR}"/*.json' in _APPLY_TRIGGERS.read_text(encoding="utf-8")
    ), (
        "and the definition must live where the converge script globs it: a trigger "
        "definition the converge cannot see is a committed file, not a trigger that fires"
    )

    assert _stale_trigger_gaps(trigger=_CONTROL_TRIGGER, interval_s=interval_s) == [
        "the trigger is not scoped to the warm uv tier",
        f"the threshold is not twice the populator's {interval_s}s interval",
        "the trigger is not registered as a value trigger",
        "the description carries no runbook",
        f"the runbook does not name the populator ({_POPULATOR_NAME}/{_POPULATOR_NAMESPACE})",
    ], "the trigger reader must still convict a one-interval threshold with no runbook"
    assert _stale_trigger_gaps(trigger="{", interval_s=interval_s) == [
        "the trigger definition is not parseable JSON"
    ], "and must report an unparseable definition rather than silently finding no gaps"
    assert _published_gauge(gauges=_CONTROL_GAUGES, gauge="generation_age_s") == {
        "reading": "uv_generation_age_s",
        "unit": "s",
        "attributes": "None",
    }, "the gauge reader must still convict an age published with no tier attribute"
    assert (
        _published_gauge(gauges=gauges, gauge="generation_age_ms") is None
    ), "and must report an unpublished gauge rather than the first row it happens to match"
    assert (
        len(_liveness_gauge_gaps(gauges="", timer="")) == 5
    ), "the liveness reader must still convict an emitter that publishes no age at all"
    assert (
        _populator_interval_s(manifest='  schedule: "*/15 * * * *"') == 900
    ), "the interval reader must follow the populator's schedule rather than a memorized 30"
    assert (
        _populator_interval_s(manifest='  schedule: "0 3 * * *"') is None
    ), "and must report a schedule that is not a minute step rather than guessing one"
