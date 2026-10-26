#!/usr/bin/env python3
"""Reap the Kubernetes sandbox records of Fabro runs that ended long ago.

Work-item bd-ib-u5facl (livespec-orchestrator-beads-fabro ledger).

WHY. Petri calls the kubernetes provider's `stop` (the pod is deleted) when a
run ends, but never `delete`. So the sandbox-driver-kubernetes record store keeps
a `stopped` / `no-pod` record for every run, and each run's node workspace
directory under /srv/factory-workspaces (~0.5 G) is never removed. The driver's
own `delete` clears pod, workspace and record, so this reaper calls it.

THE RETENTION RULE (coordinator ruling, binding). No ledger is reachable from the
factory sandbox host, so retention is AGE-ONLY (default 24 h) plus an evidence
guard. A sandbox is deleted only when ALL of these hold; each failure KEEPS it,
and every keep names its reason:

  1. its state is `stopped` (never running, starting or anything else);
  2. its Fabro run is found in `fabro ps -a` (an unknown run is kept and shouted);
  3. that run is terminal (succeeded or failed) and its end time is known;
  4. the run ended at least REAPER_MIN_AGE_HOURS ago;
  5. origin holds no preserved ref `refs/heads/needs-human/<dispatch id>` for the
     run's dispatch, and origin could be asked (an ls-remote failure keeps every
     sandbox of that repository);
  6. fewer than REAPER_MAX_DELETIONS deletions were already chosen this pass.

Every doubt resolves toward NOT deleting. DRY-RUN IS THE DEFAULT: the script only
reports unless REAPER_APPLY is `1`.

Environment (set by the systemd unit from the role's variables):
  REAPER_FABRO_BIN, REAPER_FABRO_SERVER, REAPER_LITHOS_BIN, REAPER_PROVIDER,
  REAPER_MIN_AGE_HOURS, REAPER_MAX_DELETIONS, REAPER_APPLY.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

__all__: list[str] = []

TERMINAL_KINDS = frozenset({"succeeded", "failed"})
_RUN_IN_NAME = re.compile(r"^petri-(?P<run>[0-9A-Za-z]+)-l[0-9]+$")
_DISPATCH_LABEL = "livespec.dispatch.id"
_PRESERVED_GLOB = "refs/heads/needs-human/*"
_PRESERVED_PREFIX = "refs/heads/needs-human/"
COMMAND_TIMEOUT_SECONDS = 300

Runner = Callable[[Sequence[str]], "subprocess.CompletedProcess[str]"]


@dataclass(frozen=True)
class Sandbox:
    sandbox_id: str
    state: str
    run_id: str | None


@dataclass(frozen=True)
class Run:
    run_id: str
    kind: str
    start_time: str | None
    wall_time_ms: int | None
    dispatch_id: str | None
    origin_url: str | None


@dataclass(frozen=True)
class Verdict:
    sandbox_id: str
    run_id: str | None
    action: str  # "delete" or "keep"
    reason: str


def sandbox_run_id(*, record: Mapping[str, object]) -> str | None:
    """The Fabro run a sandbox record belongs to: the petri.run label, else the name."""
    label = (record.get("labels") or {}).get("petri.run")  # type: ignore[attr-defined]
    if label:
        return str(label).upper()
    match = _RUN_IN_NAME.match(str(record.get("name", "")))
    return match["run"].upper() if match else None


def run_end(*, run: Run) -> datetime | None:
    """start_time + wall_time_ms, or None when either is missing or unreadable."""
    if run.start_time is None or run.wall_time_ms is None:
        return None
    try:
        started = datetime.fromisoformat(run.start_time)
    except ValueError:
        return None
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    return started + timedelta(milliseconds=run.wall_time_ms)


def _keep(*, sandbox: Sandbox, reason: str) -> Verdict:
    return Verdict(sandbox.sandbox_id, sandbox.run_id, "keep", reason)


def classify(
    *,
    sandboxes: Sequence[Sandbox],
    runs: Mapping[str, Run],
    now: datetime,
    min_age: timedelta,
) -> tuple[list[Verdict], list[tuple[Sandbox, Run, datetime]]]:
    """Split sandboxes into immediate keeps and candidates still owing the origin check."""
    keeps: list[Verdict] = []
    candidates: list[tuple[Sandbox, Run, datetime]] = []
    for sandbox in sandboxes:
        run = runs.get(sandbox.run_id) if sandbox.run_id else None
        ended = run_end(run=run) if run is not None else None
        if sandbox.state != "stopped":
            keeps.append(_keep(sandbox=sandbox, reason=f"state is {sandbox.state}, not stopped"))
        elif run is None:
            keeps.append(
                _keep(sandbox=sandbox, reason="UNKNOWN RUN: not found in fabro ps -a, kept")
            )
        elif run.kind not in TERMINAL_KINDS:
            keeps.append(_keep(sandbox=sandbox, reason=f"run is {run.kind}, not terminal"))
        elif ended is None:
            keeps.append(_keep(sandbox=sandbox, reason="run end time unknown, kept"))
        elif now - ended < min_age:
            hours = (now - ended).total_seconds() / 3600
            keeps.append(
                _keep(
                    sandbox=sandbox, reason=f"run ended {hours:.1f} h ago, younger than the horizon"
                )
            )
        else:
            candidates.append((sandbox, run, ended))
    return keeps, candidates


def finalize(
    *,
    candidates: Sequence[tuple[Sandbox, Run, datetime]],
    preserved: Mapping[str, frozenset[str] | None],
    max_deletions: int,
) -> list[Verdict]:
    """Apply the origin evidence guard and the per-pass cap, oldest-ended first."""
    verdicts: list[Verdict] = []
    chosen = 0
    for sandbox, run, _ended in sorted(candidates, key=lambda item: item[2]):
        refs = preserved.get(run.origin_url) if run.origin_url is not None else None
        if refs is None:
            verdicts.append(
                _keep(
                    sandbox=sandbox,
                    reason=(
                        f"ORIGIN UNOBSERVABLE ({run.origin_url}): "
                        "no origin or ls-remote failed, kept"
                    ),
                )
            )
        elif run.dispatch_id is None:
            verdicts.append(
                _keep(
                    sandbox=sandbox,
                    reason="run has no livespec.dispatch.id label, preserved ref unknowable, kept",
                )
            )
        elif run.dispatch_id in refs:
            verdicts.append(
                _keep(sandbox=sandbox, reason=f"origin holds {_PRESERVED_PREFIX}{run.dispatch_id}")
            )
        elif chosen >= max_deletions:
            verdicts.append(
                _keep(
                    sandbox=sandbox,
                    reason=f"per-pass cap of {max_deletions} deletions reached, deferred",
                )
            )
        else:
            chosen += 1
            verdicts.append(
                Verdict(
                    sandbox.sandbox_id,
                    run.run_id,
                    "delete",
                    "stopped, run ended past the horizon, no preserved ref",
                )
            )
    return verdicts


def parse_sandboxes(*, text: str) -> list[Sandbox]:
    return [
        Sandbox(str(rec["id"]), str(rec.get("state", "")), sandbox_run_id(record=rec))
        for rec in json.loads(text)
    ]


def parse_runs(*, text: str) -> dict[str, Run]:
    runs = [
        Run(
            run_id=str(row["run_id"]).upper(),
            kind=str((row.get("status") or {}).get("kind", "")),
            start_time=row.get("start_time"),
            wall_time_ms=row.get("wall_time_ms"),
            dispatch_id=(row.get("labels") or {}).get(_DISPATCH_LABEL),
            origin_url=row.get("repo_origin_url"),
        )
        for row in json.loads(text)
    ]
    return {run.run_id: run for run in runs}


def preserved_dispatch_ids(*, output: str) -> frozenset[str]:
    """Dispatch ids named by `git ls-remote` lines for refs/heads/needs-human/*."""
    refs = (line.split("\t")[-1].strip() for line in output.splitlines())
    return frozenset(
        ref[len(_PRESERVED_PREFIX) :]
        for ref in refs
        if ref.startswith(_PRESERVED_PREFIX) and len(ref) > len(_PRESERVED_PREFIX)
    )


def fetch_preserved(*, origins: Sequence[str], run: Runner) -> dict[str, frozenset[str] | None]:
    """One ls-remote per origin; None marks an origin that could not be asked."""
    result: dict[str, frozenset[str] | None] = {}
    for origin in sorted(set(origins)):
        done = run(["git", "ls-remote", origin, _PRESERVED_GLOB])
        result[origin] = (
            preserved_dispatch_ids(output=done.stdout) if done.returncode == 0 else None
        )
    return result


def render(*, verdicts: Sequence[Verdict], apply: bool) -> list[str]:
    mode = "APPLY" if apply else "DRY-RUN"
    lines = [
        f"{mode} {v.action.upper():6} {v.sandbox_id} run={v.run_id or '-'} {v.reason}"
        for v in verdicts
    ]
    deletes = sum(v.action == "delete" for v in verdicts)
    return [
        *lines,
        f"{mode} summary: {deletes} to delete, "
        f"{len(verdicts) - deletes} kept, {len(verdicts)} sandboxes",
    ]


def reap(
    *,
    env: Mapping[str, str],
    run: Runner,
    now: datetime,
    emit: Callable[[str], None],
) -> int:
    """One pass: list, decide, report, and (only when REAPER_APPLY=1) delete."""
    provider = env.get("REAPER_PROVIDER", "kubernetes")
    min_age = timedelta(hours=float(env.get("REAPER_MIN_AGE_HOURS", "24")))
    max_deletions = int(env.get("REAPER_MAX_DELETIONS", "50"))
    apply = env.get("REAPER_APPLY", "0") == "1"
    driver = [env["REAPER_LITHOS_BIN"], "--provider", provider, "--events", "off"]

    listed = run([*driver, "--output", "json", "sandbox", "list"])
    ps = run(
        [env["REAPER_FABRO_BIN"], "ps", "-a", "--json", "--server", env["REAPER_FABRO_SERVER"]]
    )
    if listed.returncode != 0 or ps.returncode != 0:
        emit(
            f"ERROR: sandbox list rc={listed.returncode}, fabro ps rc={ps.returncode}; "
            "nothing deleted"
        )
        return 1

    keeps, candidates = classify(
        sandboxes=parse_sandboxes(text=listed.stdout),
        runs=parse_runs(text=ps.stdout),
        now=now,
        min_age=min_age,
    )
    preserved = fetch_preserved(
        origins=[c[1].origin_url for c in candidates if c[1].origin_url is not None], run=run
    )
    verdicts = keeps + finalize(
        candidates=candidates, preserved=preserved, max_deletions=max_deletions
    )
    list(map(emit, render(verdicts=verdicts, apply=apply)))

    failures = 0
    for verdict in verdicts if apply else ():
        if verdict.action != "delete":
            continue
        done = run([*driver, "sandbox", "delete", verdict.sandbox_id])
        if done.returncode == 0:
            emit(f"DELETED {verdict.sandbox_id}")
        else:
            failures += 1
            emit(
                f"ERROR: delete of {verdict.sandbox_id} failed (rc {done.returncode}): "
                f"{done.stderr.strip()}"
            )
    return 1 if failures else 0


def subprocess_runner(argv: Sequence[str]) -> subprocess.CompletedProcess[str]:
    """Run one command; a missing binary or a timeout is a failed command, not a crash."""
    try:
        return subprocess.run(  # noqa: S603
            list(argv),
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT_SECONDS,
            check=False,
            env=os.environ | {"GIT_TERMINAL_PROMPT": "0"},
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return subprocess.CompletedProcess(list(argv), 127, "", str(error))


def main() -> int:
    return reap(
        env=os.environ,
        run=subprocess_runner,
        now=datetime.now(timezone.utc),
        emit=print,
    )


if __name__ == "__main__":
    sys.exit(main())
