"""Whether a package `dpkg --audit` names is a guard run's own leftover.

Governing specification: `SPECIFICATION/non-functional-requirements.md`
section "Docker engine install guard", "Package fence", as amended in
revise v075. Governing design: `docs/docker-engine-guard-design.md` G7
(the install completes the trigger handlers its own packages activate,
systemd and man-db being the measured ones) and F6 (a fresh transaction
starts from an empty `dpkg --audit`).

This module answers ONE question and mutates nothing: of the packages
`dpkg --audit` names, which are the guard's own unfinished work and which
are somebody else's. It reads only records the host already carries — the
intended set every guard run wrote before it mutated anything, the
pre-install audit record the last run wrote immediately before it issued
`dpkg -i`, and dpkg's own log. It is separate from the step
(`_docker_engine_guard_packages.py`) because attribution is a question
about the host's HISTORY, asked before anything is mutated, while that
module is the transaction.

Expected refusals are RETURNED as the reason an operator reads, never
raised: the modules are copied onto the guarded host and run against its
bare interpreter, where the `returns` railway is not importable.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Final

__all__: list[str] = [
    "DPKG_LOG",
    "INTENDED_FILE",
    "PRE_INSTALL_AUDIT_FILE",
    "leftover_refusal",
]

# Where dpkg records every action it takes, as the specification names it.
# The `log` line of `/etc/dpkg/dpkg.cfg` is what points dpkg here, and the
# fence already holds a committed digest for that file — so the path this
# reads is a path a human vouched for rather than one assumed.
DPKG_LOG: Final[Path] = Path("/var/log/dpkg.log")

# The provenance record design R7 requires: written into the run's own
# directory BEFORE the first package mutation, so a run interrupted
# anywhere in the install leaves behind what it intended to install.
INTENDED_FILE: Final[str] = "intended.json"

# What `dpkg --audit` said after the recovery and immediately before the
# install, written into the run's own directory beside the record above.
# Design F6 requires a fresh transaction to start from an empty report,
# and this is the only statement of what it actually started from: dpkg
# keeps no history, so after the install nothing on the host can say
# whether a package it names was left by THIS transaction or was already
# unfinished when the step was entered.
PRE_INSTALL_AUDIT_FILE: Final[str] = "pre-install-audit.json"

# The five actions the specification reads dpkg's log for, and the whole
# mechanism of the second arm below. dpkg logs trigger processing as
# `trigproc` and every state change as `status`, so neither is here: a
# handler that the guard's own `dpkg -i` ACTIVATED leaves `trigproc` and
# `status` lines and no action at all, while another transaction
# installing, upgrading, removing, purging or configuring a package
# leaves one of these. That is exactly the line between the guard's own
# leftover and somebody else's, read off dpkg's own record of it.
_LOG_ACTIONS: Final[frozenset[str]] = frozenset(
    {
        "configure",
        "install",
        "purge",
        "remove",
        "upgrade",
    }
)

# How many whitespace-separated fields a line must carry to be one of
# those actions: the date, the time, the action and the package. A line
# with fewer is not one — including the TORN line a SIGKILL during
# `dpkg -i` leaves at the end of the log.
_ACTION_FIELDS: Final[int] = 4

# dpkg's own timestamp spelling, which is LOCAL time carrying no zone.
# The comparison below is made IN this spelling rather than through an
# instant: the fixed-width form orders lexicographically exactly as it
# orders chronologically, so turning dpkg's zoneless stamp into an instant
# would have to invent the zone this avoids.
_LOG_TIMESTAMP: Final[str] = "%Y-%m-%d %H:%M:%S"


def _recorded_packages(*, runs: Path) -> frozenset[str]:
    """Every package ANY guard run on this host recorded as intended.

    The union, not this run's own record, and that is implementation
    rider point 4: a rollback from `publishing` leaves the PREVIOUS run's
    packages part-installed, and a recovery keyed to the current run's id
    would read them as foreign and strand the host for every later run.

    A record that cannot be parsed is skipped rather than refused on: an
    intended record interrupted mid-write is not evidence of a foreign
    package, and the names it would have carried are already covered by
    the refusal below if nothing else accounts for them.
    """
    names: set[str] = set()
    for record in sorted(runs.glob(f"*/{INTENDED_FILE}")):
        try:
            payload = json.loads(record.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        names.update(str(addition).split("=")[0] for addition in payload["additions"])
    return frozenset(names)


def _latest_audit_record(*, runs: Path) -> Path | None:
    """The pre-install audit record ANY guard run on this host wrote last.

    Across every run rather than this one's, for implementation rider
    point 4's reason again: the run that has to finish what a rollback
    from `publishing` left behind is the NEXT one, so the evidence it
    reads cannot be keyed to a run id.

    The modification time is what orders them, because the record carries
    no timestamp of its own: the step renames it into place through
    `write_durable`, so its mtime IS when it was written.
    """
    records = sorted(
        runs.glob(f"*/{PRE_INSTALL_AUDIT_FILE}"), key=lambda record: record.stat().st_mtime
    )
    return records[-1] if records else None


def _record_refusal(*, record: Path) -> str | None:
    """Why that record is not evidence the guard's own install started clean.

    A record NAMING a package says that run entered its install over a
    transaction somebody had already left unfinished, so nothing flagged
    since is attributable to the guard.

    A record that cannot be READ says nothing either way, and the absence
    of the evidence is not the evidence: read as a clean start it would
    attribute every flagged package on a host whose record was truncated
    mid-write.
    """
    try:
        flagged = json.loads(record.read_text(encoding="utf-8"))["flagged"]
    except (OSError, json.JSONDecodeError, KeyError):
        return f"the most recent pre-install audit record {record} could not be read"
    if flagged:
        return f"the most recent pre-install audit record {record} already named {tuple(flagged)}"
    return None


def _written_at(*, record: Path) -> str:
    """When that record was written, in dpkg's own log timestamp spelling."""
    return time.strftime(_LOG_TIMESTAMP, time.localtime(record.stat().st_mtime))


def _log_text(*, log: Path) -> str | None:
    """dpkg's log, or `None` when it is not there to be read."""
    if not log.is_file():
        return None
    return log.read_text(encoding="utf-8", errors="replace")


def _action(*, line: str) -> tuple[str, str, str] | None:
    """One log line's timestamp, action and package, if it carries an action.

    The package field is `name:arch`, and the architecture is dropped:
    the intended sets, `dpkg --audit` and `dpkg-query` all name packages
    without it, so keeping it would make every comparison a miss.
    """
    fields = line.split()
    if len(fields) < _ACTION_FIELDS or fields[2] not in _LOG_ACTIONS:
        return None
    return (f"{fields[0]} {fields[1]}", fields[2], fields[3].split(":")[0])


def _log_refusal(*, log: Path, since: str, recorded: frozenset[str]) -> str | None:
    """The first action dpkg logged since `since` outside every intended set.

    The exclusion is scoped to packages OUTSIDE those sets, which is
    narrower than "any action at all" and deliberately so: an unattended
    upgrade of a package some guard run intended does not switch this arm
    off, so a handler THAT action activated would be completed as the
    guard's. The fences around it bound that — the audit refuses on any
    installed version which moved under it, the post-install difference
    must equal the audited additions, and `reserve` refuses once the
    commit marker exists — and completing a handler's own configuration
    is idempotent. So the clause is left as the specification states it
    rather than widened here (ratification review of v075, point 2).

    A log that cannot be read refuses, because "no action since that
    record" is a claim about dpkg's whole record of itself, and a record
    that is not there supports no such claim.
    """
    text = _log_text(log=log)
    if text is None:
        return f"dpkg's log at {log} could not be read, so nothing since {since} is ruled out"
    for line in text.splitlines():
        action = _action(line=line)
        if action is None:
            continue
        stamp, verb, package = action
        if stamp >= since and package not in recorded:
            return (
                f"dpkg's log records `{verb} {package}` at {stamp}, on a package outside "
                "every recorded intended set and since that record was written"
            )
    return None


def _attribution_refusal(*, runs: Path, recorded: frozenset[str], log: Path) -> str | None:
    """Why this host's own records do not make what is flagged the guard's.

    The record is read FIRST because it is what BOUNDS the log read:
    without one there is no instant to read dpkg's log since, and reading
    the log from the beginning of the host's life would refuse on every
    transaction the host has ever made.
    """
    record = _latest_audit_record(runs=runs)
    if record is None:
        return "no guard run has written a pre-install audit record on this host"
    refusal = _record_refusal(record=record)
    if refusal is not None:
        return refusal
    return _log_refusal(log=log, since=_written_at(record=record), recorded=recorded)


def leftover_refusal(*, flagged: tuple[str, ...], runs: Path, log: Path) -> str | None:
    """Every flagged package that is no guard run's leftover, or `None`.

    `dpkg --audit` naming something is not by itself a reason to stop: a
    rollback from `publishing` leaves a guard run's packages part
    installed, and a kill during `dpkg -i` leaves the trigger handler
    that install activated unfinished. Both are the guard's own work to
    finish; what the step may never do is step over somebody else's
    interrupted transaction.

    Two arms decide it, exactly as the specification states them. The
    first is membership in the union of every guard run's recorded
    intended set. The second covers the handlers no intended set names,
    and it is a fact about the HOST rather than about one package: the
    most recent pre-install audit record any guard run wrote is empty, so
    the guard's own `dpkg -i` started on a clean dpkg database, and
    dpkg's log records no foreign action since, so nothing else has
    touched that database. Anything flagged on such a host was put there
    by the guard's own transaction.
    """
    recorded = _recorded_packages(runs=runs)
    foreign = tuple(sorted(name for name in flagged if name not in recorded))
    if not foreign:
        return None
    unattributed = _attribution_refusal(runs=runs, recorded=recorded, log=log)
    if unattributed is None:
        return None
    return (
        f"dpkg --audit names {foreign}, which no guard run recorded as intended, "
        f"and {unattributed}"
    )
