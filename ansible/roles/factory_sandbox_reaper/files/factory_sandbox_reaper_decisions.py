"""Retention-policy decisions for the factory sandbox reaper.

This module has no host I/O.  Keeping the evidence-based deletion rule separate
from the executable's subprocess plumbing makes it possible to test every
keep/delete decision without invoking Fabro, git, or the sandbox driver.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

__all__ = [
    "Run",
    "Sandbox",
    "Verdict",
    "classify",
    "finalize",
    "run_end",
]

TERMINAL_KINDS = frozenset({"succeeded", "failed"})
_PRESERVED_PREFIX = "refs/heads/needs-human/"


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


def run_end(*, run: Run) -> datetime | None:
    """Return `start_time + wall_time_ms`, or None when either is unreadable."""
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
        if sandbox.state not in {"stopped", "running"}:
            keeps.append(
                _keep(sandbox=sandbox, reason=f"state is {sandbox.state}, not stopped or running")
            )
        elif run is None:
            keeps.append(
                _keep(sandbox=sandbox, reason="UNKNOWN RUN: not found in fabro ps -a, kept")
            )
        elif run.kind not in TERMINAL_KINDS:
            reason = f"run is {run.kind}, not terminal"
            if sandbox.state == "running":
                reason = f"state is running, not stopped; {reason}"
            keeps.append(_keep(sandbox=sandbox, reason=reason))
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
                    f"{sandbox.state}, run ended past the horizon, no preserved ref",
                )
            )
    return verdicts
