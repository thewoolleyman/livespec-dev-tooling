"""Consumer-tier: the three `SPECIFICATION/scenarios.md` cache-TELEMETRY scenarios.

    "a cache fault degrades a job to cold and never fails it"
    "a canary job runs cold and is tagged"
    "a stale warm-cache generation fires the trigger"

Each of these ends in an observation that has to EXIST — a span carrying a
named attribute, a trigger that fires — and every one of them fails silently
when it is wrong. A cold tier reported with an empty error reads exactly like a
healthy tier with nothing to copy; a canary whose spans carry a different
attribute set than a normal job's cannot be compared against one; a value
trigger reading a column no emitter writes never fires and never says so.

The first two are driven through the pool's OWN emitter,
`ci-runner/k3s/phase2/cache-telemetry/ci-cache-span.sh`, over the test seams it
already documents (`CI_CACHE_STATE_DIR`, `CI_CACHE_OTLP_ENDPOINT`,
`CI_CACHE_EVENT_JSON`), with a loopback receiver standing in for the host
collector and capturing the OTLP payload. The state the emitter replays is
built from the committed hook pod template's OWN recorded columns, so a fixture
cannot drift away from what a real job would write.

The third has no runtime seam in this repository — the trigger is applied to
Honeycomb and the gauge is emitted by a host timer — so it is asserted where it
is decidable: across the three committed files that have to agree for it to
fire at all.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PHASE2 = _REPO_ROOT / "ci-runner" / "k3s" / "phase2"
_EMITTER = _PHASE2 / "cache-telemetry" / "ci-cache-span.sh"
_HOOK_TEMPLATE = _PHASE2 / "arc" / "hook-pod-template.yaml"
_POPULATE_CRONJOB = _PHASE2 / "warm-cache" / "warm-cache-cronjob.yaml"
_GAUGES = _REPO_ROOT / "ci-runner" / "observability" / "ci-cache-gauges.sh"
_STALE_TRIGGER = (
    _REPO_ROOT / "ci-runner" / "observability" / "triggers" / "ci-cache-warm-generation-stale.json"
)

_WARM_COPY_SPAN = "cache.warm-copy"
_HIT = "build.cache.hit"
_ERROR = "build.cache.error"
_TIER = "build.cache.tier"
_KILL_SWITCH = "build.cache.kill_switch"
_CANARY = "canary"

# The generation-age gauge the host's liveness path emits, and the tier it is
# emitted for. The trigger's query column must be this exact name: a column
# nothing writes yields no datapoints, so the trigger never fires and the
# absence is indistinguishable from a healthy cache.
_AGE_GAUGE_PREFIX = "livespec.ci_cache."
_AGE_GAUGE_SUFFIX = "generation_age_s"
_AGE_GAUGE = _AGE_GAUGE_PREFIX + _AGE_GAUGE_SUFFIX
_AGE_TIER = "uv"

# The scenario's bound: "longer than TWICE its schedule interval".
_STALE_MULTIPLE = 2
_SECONDS_PER_MINUTE = 60

# The in-pod path the template probes for the warm uv seed, and the assignment
# the branch behind it has to make. Both are read rather than run: the path is
# absolute and belongs to a job container, so a machine with no such path takes
# the COLD branch — which is exactly the fault arm this file drives.
_SEED_PROBE = "-d /__w/_warm/uv"
_REASON_CLEARED = 'uv_err=""'

_CRON_SCHEDULE = re.compile(r'^\s*schedule:\s*"(?P<schedule>[^"]+)"', re.MULTILINE)
_EVERY_N_MINUTES = re.compile(r"^\*/(?P<minutes>\d+) \* \* \* \*$")
_REC_CALL = re.compile(r"^\s*rec (?P<tier>\S+) (?P<rest>.*)$", re.MULTILINE)


class _CapturingHandler(BaseHTTPRequestHandler):
    """A loopback stand-in for the host collector's keyless pod-facing listener."""

    payloads: list[dict[str, Any]] = []  # noqa: RUF012  — per-server, reset by `_receiver`.

    def do_POST(self) -> None:  # noqa: N802  — BaseHTTPRequestHandler's own spelling.
        length = int(self.headers.get("content-length") or 0)
        body = self.rfile.read(length)
        type(self).payloads.append(json.loads(body.decode("utf-8")))
        self.send_response(200)
        self.send_header("content-length", "0")
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        """Silence the handler's stderr access log; the test reads payloads, not logs."""


def _emit(
    *, state_dir: Path, args: list[str], event: Path, live: bool = True
) -> list[dict[str, Any]]:
    """Run the committed emitter against a loopback receiver; return the spans it POSTed.

    `live=False` points it at a closed port instead, which is how the fail-soft
    contract is exercised: the emitter must still exit 0 and the caller must
    still get an empty list rather than an exception.

    `COVERAGE_PROCESS_START` / `COV_CORE_*` are scrubbed because the emitter
    runs a python3 heredoc, and an instrumented grandchild writes `.coverage.*`
    files that race the parallel check dispatcher.
    """
    _CapturingHandler.payloads = []
    server = ThreadingHTTPServer((("127.0.0.1"), 0), _CapturingHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1] if live else 1
        env = {
            key: value
            for key, value in os.environ.items()
            if key != "COVERAGE_PROCESS_START" and not key.startswith("COV_CORE_")
        }
        env["CI_CACHE_STATE_DIR"] = str(state_dir)
        env["CI_CACHE_OTLP_ENDPOINT"] = f"http://127.0.0.1:{port}"
        env["CI_CACHE_EVENT_JSON"] = str(event)
        env["CI_RUNNER_NODE_NAME"] = "fixture-node"
        # Nothing must be listening where the job's own sccache server would
        # be: a job that never ran cargo has none, and this file's subject is
        # the warm-copy spans rather than the summary's counters.
        env["SCCACHE_SERVER_PORT"] = "1"
        completed = subprocess.run(
            ["sh", str(_EMITTER), *args],
            capture_output=True,
            text=True,
            env=env,
            check=False,
            timeout=120,
        )
        assert completed.returncode == 0, (
            f"the emitter's contract is that it ALWAYS exits 0 — it is called from a "
            f"lifecycle hook, and a non-zero exit there is a job the cache broke; "
            f"rc={completed.returncode} stderr={completed.stderr!r}"
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    return [
        span
        for payload in _CapturingHandler.payloads
        for resource in payload["resourceSpans"]
        for scope in resource["scopeSpans"]
        for span in scope["spans"]
    ]


def _attributes(*, span: dict[str, Any]) -> dict[str, Any]:
    """One span's attributes as a plain key -> scalar mapping."""
    return {entry["key"]: next(iter(entry["value"].values())) for entry in span["attributes"]}


def _event_json(*, root: Path) -> Path:
    """A synthetic `event.json`, the file the runner writes and the emitter reads."""
    path = root / "event.json"
    _ = path.write_text(
        json.dumps(
            {
                "repository": {"full_name": "thewoolleyman/livespec-dev-tooling"},
                "ref": "refs/heads/master",
                "after": "0" * 40,
            }
        ),
        encoding="utf-8",
    )
    return path


def _state(*, root: Path, kill_switch: str, rows: list[tuple[str, str, str]]) -> Path:
    """A postStart state directory: the kill switch it decided and the tiers it recorded.

    `rows` are `(tier, hit, error)`; the remaining columns are the emitter's
    documented TSV order — `at_ns tier hit generation copy_ms copy_bytes
    copy_method error` — which is the same order the hook template's own `rec`
    writes, and is asserted as a shared contract by the tier test below.
    """
    root.mkdir(parents=True, exist_ok=True)
    _ = (root / "kill_switch").write_text(kill_switch, encoding="utf-8")
    _ = (root / "warm-copy.tsv").write_text(
        "".join(
            f"0\t{tier}\t{hit}\t20260906T000000Z\t7\t0\treflink-seed\t{error}\n"
            for tier, hit, error in rows
        ),
        encoding="utf-8",
    )
    return root


def _post_start_block() -> str:
    """The hook pod template's postStart SCRIPT, as committed.

    Bounded to the block-scalar body rather than to the next key: the design
    comments that introduce `preStop` sit between the two at a shallower
    indent, and reading them as part of the script would let a phrase in prose
    stand in for a line of shell.
    """
    lines = _HOOK_TEMPLATE.read_text(encoding="utf-8").splitlines()
    start = next(index for index, line in enumerate(lines) if line.strip() == "postStart:")
    opener = next(index for index, line in enumerate(lines[start:], start) if line.strip() == "- |")
    body = lines[opener + 1 :]
    indent = len(body[0]) - len(body[0].lstrip())
    # The block runs to the first line indented BACK OUT of it. Collecting every
    # dedent index and taking the first — with the end-of-file index appended as
    # the fallback — keeps that "or the file simply ended" case from becoming a
    # conditional arc no committed template can take, which is dead code rather
    # than a guard: this template's postStart is never its last block.
    dedents = [
        index
        for index, line in enumerate(body)
        if line.strip() and len(line) - len(line.lstrip()) < indent
    ]
    return "\n".join(body[: [*dedents, len(body)][0]])


def _uv_tier_decision(*, root: Path) -> tuple[str, str, str]:
    """RUN the template's own uv-tier decision here; return the `(tier, hit, error)` it records.

    The committed lines from the `uv_hit` assignment through the `rec uv` call
    are lifted VERBATIM and executed, with only `rec`, `ms` and `uv_gen`
    supplied around them — the two shell functions the surrounding hook defines
    and the generation stamp it read. Nothing about the decision is rewritten,
    and in particular the absolute seed path is left exactly as the template
    spells it, because a machine running this suite has no `/__w/_warm/uv`:
    that IS the scenario's Given, "the warm-cache tree is absent", and running
    the decision against it is what makes the recorded row an observation
    rather than a fixture somebody typed.
    """
    lines = _post_start_block().splitlines()
    first = next(index for index, line in enumerate(lines) if "uv_hit=false" in line)
    last = next(index for index, line in enumerate(lines[first:], first) if "rec uv " in line)
    recorded = root / "warm-copy.tsv"
    root.mkdir(parents=True, exist_ok=True)
    script = "\n".join(
        [
            f'rec() {{ printf "%s\\t%s\\t%s\\t%s\\t%s\\t%s\\t%s\\t%s\\n" 0 "$@" >> "{recorded}"; }}',
            "ms() { echo 0; }",
            "uv_gen=",
            *(line.strip() for line in lines[first : last + 1]),
        ]
    )
    completed = subprocess.run(
        ["sh", "-c", script], capture_output=True, text=True, check=False, timeout=60
    )
    assert completed.returncode == 0, (
        f"the template's own uv-tier decision must run to completion; "
        f"rc={completed.returncode} stderr={completed.stderr!r} script={script!r}"
    )
    columns = recorded.read_text(encoding="utf-8").rstrip("\n").split("\t")
    assert len(columns) == 8, f"the recorded row must carry the emitter's eight columns; {columns}"
    return columns[1], columns[2], columns[7]


def test_a_cold_tier_carries_a_reason_and_no_path_through_the_emitter_can_fail_a_job(
    *, tmp_path: Path
) -> None:
    """§"a cache fault degrades a job to cold and never fails it".

    Both clauses, and the second one is the one that is easy to get almost
    right. "a `cache.warm-copy` span with `build.cache.hit` false and a
    NON-EMPTY `build.cache.error` MUST be emitted" — non-empty, because the
    fault has to be distinguishable from the ordinary absence of anything to
    copy. A cold tier reported with an empty error is a valid span, lands in
    the dataset, and answers every query about hit ratio correctly while saying
    nothing at all about the node whose warm tree went unreadable.

    DRIVEN END TO END, and this is the point: the row the emitter replays is
    not typed here, it is the row the TEMPLATE'S OWN uv-tier decision records
    when it runs against an absent warm tree — the scenario's Given exactly.
    Hook and emitter are two artifacts in two files, and a reason the hook
    stops supplying is a reason the emitter faithfully reports as empty, so
    checking either alone leaves the fault invisible in the pair.

    THE CONTROL: replaying a healthy row must produce hit=true with an empty
    error, which is what makes the assertion above about the fault rather than
    about an emitter that decorates every span. The template's own SEEDED
    branch cannot be driven the same way — its probe names the absolute
    in-pod seed path, and manufacturing that path would mutate the machine
    running this suite rather than a fixture — so the one thing that branch has
    to do, CLEAR the reason, is read from the committed lines instead.

    NEVER FAILS IT, driven: the emitter run against an endpoint nothing is
    listening on must still exit 0 and emit nothing. That is the whole
    "degrades ... and never fails it" clause on the emitter's side, and the
    `_emit` helper asserts the exit code on every call in this file. Read on
    the hook's side: the postStart block ends in `exit 0` and takes no
    `set -e`, so no branch of it can carry a failure into the container.
    """
    event = _event_json(root=tmp_path)
    tier, hit, error = _uv_tier_decision(root=tmp_path / "decision")
    assert (tier, hit) == ("uv", "false"), (
        f"with no warm tree on the machine, the template's own decision must record the uv "
        f"tier COLD — that is the scenario's Given, and the rest of this test replays what it "
        f"recorded; row=({tier!r}, {hit!r}, {error!r})"
    )
    faulted = _emit(
        state_dir=_state(root=tmp_path / "faulted", kill_switch="", rows=[(tier, hit, error)]),
        args=["job-end"],
        event=event,
    )
    cold = [span for span in faulted if span["name"] == _WARM_COPY_SPAN]
    assert len(cold) == 1, (
        f"the faulted tier must produce exactly one `{_WARM_COPY_SPAN}` span; got "
        f"{[span['name'] for span in faulted]}"
    )
    cold_attributes = _attributes(span=cold[0])
    assert cold_attributes[_HIT] is False and cold_attributes[_ERROR], (
        f"a cache fault must arrive as a cold tier WITH a reason: an empty `{_ERROR}` beside "
        f"`{_HIT}=false` is indistinguishable from a tier that simply had nothing to copy, "
        f"and the unreadable warm tree behind it is then invisible; "
        f"attributes={cold_attributes}"
    )

    healthy = _emit(
        state_dir=_state(root=tmp_path / "healthy", kill_switch="", rows=[("uv", "true", "")]),
        args=["job-end"],
        event=event,
    )
    healthy_attributes = _attributes(
        span=next(span for span in healthy if span["name"] == _WARM_COPY_SPAN)
    )
    assert healthy_attributes[_HIT] is True and not healthy_attributes[_ERROR], (
        f"and a healthy tier must arrive with no reason at all, or the assertion above is "
        f"satisfied by an emitter that reports a fault on every span; "
        f"attributes={healthy_attributes}"
    )

    silent = _emit(
        state_dir=_state(root=tmp_path / "silent", kill_switch="", rows=[(tier, hit, error)]),
        args=["job-end"],
        event=event,
        live=False,
    )
    assert silent == [], (
        f"with no collector reachable the emitter must emit nothing and still exit 0 — the "
        f"job runs to its OWN outcome, and a telemetry POST that failed the container would "
        f"be the cache failing the job; spans={silent}"
    )

    post_start = _post_start_block()
    seeded_branch = [
        line.strip() for line in post_start.splitlines() if _SEED_PROBE in line and "uv_err" in line
    ]
    assert seeded_branch and all(_REASON_CLEARED in line for line in seeded_branch), (
        f"the branch the SEED-PRESENT probe guards must clear the reason: leave it set and "
        f"every healthy job reports a fault, which costs the attribute the meaning the cold "
        f"arm above depends on. This branch is unreachable from a machine with no in-pod seed "
        f"path, so it is read rather than run; lines={seeded_branch}"
    )
    assert "set -e" not in post_start and post_start.rstrip().endswith("exit 0"), (
        "the postStart must remain fail-soft end to end — no `set -e`, and an unconditional "
        "`exit 0` — because the container's start is what a failure there would take with it"
    )


def test_a_canary_reports_every_tier_cold_under_one_tag_and_stays_query_comparable(
    *, tmp_path: Path
) -> None:
    """§"a canary job runs cold and is tagged".

    EVERY TIER SKIPPED: "every cache tier MUST be skipped for that job" is a
    claim about ALL of them, so the switched-off branch's tiers are held
    against the tiers the NORMAL path reports — not against a list written
    here, and not against themselves. Read against itself the assertion is
    self-fulfilling: drop a `rec` from the canary branch and the expectation
    shrinks with it. Read against the normal path, a tier the pool warms and
    the canary silently stops reporting is exactly what convicts, and that is
    the shape a forgotten tier actually has.

    TAGGED: every span of a canary job carries
    `build.cache.kill_switch == "canary"`, and — the half that is easy to lose
    — the tag is on the JOB-SUMMARY span too, not only the per-tier ones. The
    summary is where a canary's compile timings live, and an untagged summary
    is a cold job sitting in the middle of the warm population.

    QUERYABLE AGAINST NON-CANARY JOBS: "the job's timings MUST be queryable
    against non-canary jobs of the same repository and phase" is a statement
    about the SHAPE of the two, and it is decidable — a canary span and a
    normal span must differ in their attribute VALUES and in nothing else. Give
    the canary path an attribute the normal path lacks (or drop one it has) and
    every comparison silently reads across two different span schemas, which is
    exactly the state in which a cold baseline stops being a baseline.
    """
    recorded = [
        (match.group("tier"), "off:$switch" in match.group("rest"), match.group("rest").split()[0])
        for match in _REC_CALL.finditer(_post_start_block())
    ]
    switched_off = {tier: hit for tier, off, hit in recorded if off}
    warmed = {tier for tier, off, _ in recorded if not off}
    assert warmed and set(switched_off) == warmed, (
        f"the switched-off branch must report EVERY tier the normal path does: a tier the "
        f"pool warms and the canary quietly stops reporting leaves the cold baseline missing "
        f"exactly the row it was measured for, and nothing says so; "
        f"switched off={sorted(switched_off)} warmed={sorted(warmed)}"
    )
    still_warm = sorted(tier for tier, hit in switched_off.items() if hit != "false")
    assert not still_warm, (
        f"and it must record each of them as a literal COLD row rather than passing the tier's "
        f"own hit through: a canary that reports a hit on a tier it turned off is a warm "
        f"reading in the middle of the cold baseline; still warm={still_warm}"
    )

    event = _event_json(root=tmp_path)
    tiers = sorted(warmed)
    canary = _emit(
        state_dir=_state(
            root=tmp_path / "canary",
            kill_switch=_CANARY,
            rows=[(tier, switched_off[tier], f"off:{_CANARY}") for tier in tiers],
        ),
        args=["job-end"],
        event=event,
    )
    normal = _emit(
        state_dir=_state(
            root=tmp_path / "normal",
            kill_switch="",
            rows=[(tier, "true", "") for tier in tiers],
        ),
        args=["job-end"],
        event=event,
    )

    canary_tiers = {
        _attributes(span=span)[_TIER] for span in canary if span["name"] == _WARM_COPY_SPAN
    }
    assert canary_tiers == set(tiers), (
        f"every tier the canary skipped must still REPORT, or a cold canary is a job with "
        f"missing rows rather than a measured cold baseline; reported={sorted(canary_tiers)} "
        f"expected={tiers}"
    )
    untagged = [
        span["name"] for span in canary if _attributes(span=span).get(_KILL_SWITCH) != _CANARY
    ]
    assert not untagged, (
        f"EVERY span of a canary job must carry `{_KILL_SWITCH}={_CANARY}` — the summary "
        f"included, since that is where the canary's timings are — or an untagged cold job "
        f"sits inside the warm population it exists to be compared against; "
        f"untagged={untagged}"
    )
    cold_tiers = [
        _attributes(span=span)[_HIT] for span in canary if span["name"] == _WARM_COPY_SPAN
    ]
    assert cold_tiers and not any(cold_tiers), (
        f"a canary runs every tier cold by construction, so no tier of it may report a hit; "
        f"hits={cold_tiers}"
    )

    canary_shape = {span["name"]: sorted(_attributes(span=span)) for span in canary}
    normal_shape = {span["name"]: sorted(_attributes(span=span)) for span in normal}
    assert canary_shape == normal_shape, (
        f"a canary's spans must differ from a normal job's in their VALUES and in nothing "
        f"else: one query shape is what makes the two comparable, and a schema that forks on "
        f"the tag turns the cold baseline into a separate dataset nobody joins; "
        f"canary={canary_shape} normal={normal_shape}"
    )
    assert all(_attributes(span=span).get(_KILL_SWITCH) == "" for span in normal), (
        "and a normal job must carry the tag EMPTY rather than absent, or the comparison "
        "above holds only because both sides are missing it"
    )


def test_the_stale_generation_trigger_is_a_value_trigger_at_twice_the_populator_schedule() -> None:
    """§"a stale warm-cache generation fires the trigger".

    Three committed files have to agree for this to fire, and each disagreement
    is silent in its own way.

    THE BOUND: "the populator has not published a generation for longer than
    TWICE its schedule interval". The interval is the CronJob's own `schedule`
    and the bound is the trigger's threshold, and they live in different files
    in different formats — change the schedule and the threshold keeps the old
    arithmetic, still firing, now at the wrong age.

    THE COLUMN: the trigger reads `MAX` of a gauge over a window, so it can
    only fire on a column something actually writes. A trigger pointed at a
    gauge no emitter emits produces no datapoints, never fires, and looks
    exactly like a warm cache — the failure that makes a VALUE trigger worth
    checking against its emitter rather than against itself.

    THE RUNBOOK: "MUST fire with a runbook naming the populator". A trigger
    that fires with nothing to act on is an alert that gets muted, so the
    populator's CronJob name and its namespace both have to appear in what the
    trigger carries to whoever it wakes.
    """
    schedule = _CRON_SCHEDULE.search(_POPULATE_CRONJOB.read_text(encoding="utf-8"))
    assert schedule is not None, (
        f"the populator's schedule must be readable from its committed CronJob — it is the "
        f"interval the scenario's bound is twice of; "
        f"cronjob={_POPULATE_CRONJOB.relative_to(_REPO_ROOT)}"
    )
    every = _EVERY_N_MINUTES.match(schedule.group("schedule"))
    assert every is not None, (
        f"the schedule must stay a plain every-N-minutes expression, or the bound below "
        f"cannot be derived from it at all; schedule={schedule.group('schedule')!r}"
    )
    interval_s = int(every.group("minutes")) * _SECONDS_PER_MINUTE

    trigger = json.loads(_STALE_TRIGGER.read_text(encoding="utf-8"))
    assert trigger["threshold"]["value"] == _STALE_MULTIPLE * interval_s, (
        f"the trigger must fire at exactly twice the populator's schedule interval "
        f"({_STALE_MULTIPLE} x {interval_s}s): the two numbers are hand-maintained in "
        f"different files, so a schedule change leaves a threshold that still fires and no "
        f"longer means what it says; threshold={trigger['threshold']}"
    )
    assert trigger["threshold"]["op"] == ">" and trigger["query"]["calculations"] == [
        {"op": "MAX", "column": _AGE_GAUGE}
    ], (
        f"it must be a VALUE trigger on the generation-age gauge — an age is a value, and a "
        f"dead-man count over the same column answers a different question; "
        f"query={trigger['query']} threshold={trigger['threshold']}"
    )
    assert {"column": "tier", "op": "=", "value": _AGE_TIER} in trigger["query"]["filters"], (
        f"and it must select the tier the gauge is emitted per, or a MAX over every tier "
        f"reports the oldest of them under the name of one; filters={trigger['query']['filters']}"
    )

    gauges = _GAUGES.read_text(encoding="utf-8")
    # The emitter names its gauges by CONCATENATING the family prefix with each
    # spec row's suffix, so the trigger's full column name never appears as one
    # literal there. Both halves are asserted where they actually live.
    emitted = re.search(
        rf'\("{re.escape(_AGE_GAUGE_SUFFIX)}",[^)]*\{{"tier": "{_AGE_TIER}"\}}', gauges
    )
    assert _AGE_GAUGE_PREFIX in gauges and emitted is not None, (
        f"the column the trigger reads must be one the host's liveness emitter actually "
        f"writes, under the tier it filters on: a trigger on a gauge nobody emits has no "
        f"datapoints, never fires, and is indistinguishable from a warm cache; "
        f"emitter={_GAUGES.relative_to(_REPO_ROOT)}"
    )

    runbook = f"{trigger['name']} {trigger['description']}"
    assert "warm-cache-populate" in runbook and "ci-warm-cache" in runbook, (
        f"the trigger must carry a runbook naming the POPULATOR — its CronJob and the "
        f"namespace it runs in — because that is the thing whose silence the age measures; "
        f"carried={runbook!r}"
    )
