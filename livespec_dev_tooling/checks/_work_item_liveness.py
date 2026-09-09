"""The single shared work-item liveness resolver every stand-down gate calls.

This repository's `SPECIFICATION/spec.md` §"Non-goals" carves ONE exception
to the network-I/O prohibition: a check that stands down, weakens, or
exempts on an EXPLICITLY NAMED work-item id MAY resolve that id against the
repository's own configured work-item store, solely to learn whether it
exists and whether it is open. The same clause requires "one shared
mechanism, not per-gate hand-rolls" — a gate rolling its own lookup is
non-conforming even when its behaviour is otherwise correct. This module IS
that mechanism. `checks/no_todo_registry`'s release tier is its first
consumer; every other gate that stands down on a named id converges here.

WHY IT EXISTS. Before it, each such gate carried an UNIMPLEMENTED seam that
returned `None` unconditionally, so the branch convicting a closed owner was
unreachable in every consuming repository and the gate passed BY
CONSTRUCTION. Measured across the eleven governed repositories on
2026-09-08: 63 heading-coverage TODO rows named an already-closed owner and
41 named an id that does not exist, and not one of them could be convicted.
A check that cannot convict is worse than no check; that is the defect this
closes.

WHY A WHOLE-POPULATION SNAPSHOT RATHER THAN A PER-ID `bd show`. The second
reason is the load-bearing one:

- ONE subprocess per run instead of one per id. This repository's registry
  alone carries dozens of TODO rows.
- A per-id `bd show` CANNOT TELL "no such id" FROM "the store did not
  answer" — both exit non-zero. Reading the population once separates them
  structurally: a snapshot that arrives at all establishes reachability, so
  an id missing FROM it is genuinely nonexistent. The ratified clause
  requires the verdict to be "discriminating in both directions", and
  per-id probing structurally cannot be.

THE ABSENT ANSWER IS A FAILURE TRACK, NEVER `{}`. An unreachable store and
an empty one are different facts that must never share a spelling: `{}` says
the store answered and holds nothing, an `IOFailure` says it did not answer.
Collapsing them would reintroduce the vacuous-gate defect this module exists
to remove. The consuming gate turns the failure track into an explicit
"liveness unverified" diagnostic naming the id, never a silent pass — the
honest degradation the clause demands.

BOTH PUBLIC ANSWERS ARE ON THE `IOResult` RAILWAY — livespec-dev-tooling-qndn,
the fleet-wide ROP conversion. The sentinel this module used to return said
only THAT there was no answer; it could not say WHICH of the four
non-answers occurred, and one of the four — a `bd` that ran and exited
non-zero because the tenant password is not projected into the environment —
is a one-command repair on the operator's own host, while another (no `bd`
at all) is not. Collapsed onto a single `None`, the two were the same word.
`LedgerUnreachable` now carries the discriminating `reason` along with the
exact argv, so a stand-down diagnostic can tell an operator which fault they
are looking at. `resolve_liveness` FORWARDS that failure rather than
re-wrapping it: it adds no failure mode of its own, and a second error type
for one condition would make a caller distinguish two things that are one
thing.

NO LEVER. Nothing here reads an environment variable, flag, or
configuration key that could disable the resolution, force it to pass, or
convert a CLOSED verdict into a quiet one; the ratified clause forbids all
three. The credential-wrapper lookup below is HOST DISCOVERY, not a lever —
nothing configurable selects it, and its absence degrades to the bare
invocation rather than to a pass.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

# Carried even though every reader of this module reaches it BY IMPORT today:
# without it the vendored `returns` resolves only because whichever gate
# imported first happened to carry the preamble, which is a property of the
# caller rather than of this file.
_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.io import IOFailure, IOResult, IOSuccess  # noqa: E402  — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

from livespec_dev_tooling.checks._plan_ledger import parse_records  # noqa: E402

__all__: list[str] = [
    "NONEXISTENT",
    "UNREACHABLE",
    "LedgerReader",
    "LedgerUnreachable",
    "bd_status_reader",
    "resolve_liveness",
    "resolved_status",
]


# Beads normalizes the livespec lifecycle vocabulary onto its own, and a tenant
# may answer with either spelling of "this work is finished". Kept in step with
# `checks/_plan_ledger`'s own closed set, which reads the same field for the
# plan-lifecycle verdicts.
_CLOSED_STATUSES = frozenset({"closed", "done"})

# The two answers that are NOT a status: the store answered and does not hold
# the id, versus the store never answered. Both are reported verbatim by the
# consuming gate, because the ratified clause requires a surfaced stand-down to
# name "the id and its resolved status".
NONEXISTENT = "nonexistent"
UNREACHABLE = "unreachable"

# The tenant password is projected from 1Password rather than stored on disk,
# so a BARE `bd` on a fleet host answers `Error 1045 (28000): Access denied` —
# which this resolver would read as UNREACHABLE forever, leaving the gate as
# vacuous as it was before. Routing through the wrapper WHERE THE HOST INSTALLS
# IT is what lets the probe answer at all. Discovered on `PATH`, the same way
# the fleet's own charters invoke it.
_CREDENTIAL_WRAPPER = "with-livespec-env.sh"

# A store on the far side of a network hop must never be able to wedge a gate;
# a timeout degrades to UNREACHABLE like any other non-answer.
_QUERY_TIMEOUT_SECONDS = 30.0

# The four distinguishable ways the store fails to answer, kept apart because
# they call for different repairs. `query-refused` is the one an operator can
# almost always fix: it is the shape `Error 1045 (28000): Access denied` takes
# when the tenant password was never projected into the environment, and it is
# a re-run through the credential wrapper away from answering.
# `query-unrunnable` (no `bd` on the host, a fork failure, the timeout) is not.
# The last two say `bd` ran and answered with something that is not the record
# surface — a shim, a banner, a half-written stream.
_QUERY_UNRUNNABLE = "query-unrunnable"
_QUERY_REFUSED = "query-refused"
_OUTPUT_CARRIES_NO_JSON = "output-carries-no-json"
_OUTPUT_UNPARSEABLE = "output-unparseable"


@dataclass(frozen=True, kw_only=True)
class LedgerUnreachable:
    """The configured work-item store did not answer, and why.

    Deliberately NOT inhabited by "the store answered and holds nothing":
    that is `IOSuccess({})`, and keeping the two apart is the whole point of
    the module. Every field exists so an operator can act without guessing —
    `argv` is the exact command to re-run, and `reason` is which of the four
    non-answers occurred, the fact the pre-conversion `None` could not carry.
    """

    repo: str
    argv: str
    reason: str
    detail: str


class LedgerReader(Protocol):
    """Snapshot a repository's configured store as `{work-item id: status}`.

    The failure track means the store did not answer, and is never a spelling
    of "the store is empty". This is the seam a consuming gate injects for
    tests, so no unit test needs a reachable tracker.
    """

    def __call__(self, *, repo: Path) -> IOResult[dict[str, str], LedgerUnreachable]:
        """Return the snapshot for the store `repo` configures."""
        ...


def _unreachable(
    *, repo: Path, argv: tuple[str, ...], reason: str, detail: str
) -> IOResult[dict[str, str], LedgerUnreachable]:
    """The failure track, naming the invocation that did not produce a snapshot."""
    return IOFailure(
        LedgerUnreachable(repo=str(repo), argv=" ".join(argv), reason=reason, detail=detail)
    )


def bd_status_reader(*, repo: Path) -> IOResult[dict[str, str], LedgerUnreachable]:
    """Snapshot `repo`'s configured tenant through the pinned `bd` CLI.

    `--status all` is load-bearing: `bd list` OMITS every closed item by
    default, so without it a closed owner would be absent from the snapshot
    and convicted as nonexistent — the right verdict reached by a wrong
    reading, and a wrong one the moment the default view changes. Measured on
    this repository's own tenant: the default listing hid 58% of the ledger.

    Each non-answer rides the failure track under its OWN reason: the CLI is
    absent or fails to launch or times out, it exits non-zero (a missing
    credential projection looks exactly like this), or it answers with
    something that is not the JSON record surface. That last guard is not
    redundant — output carrying no JSON delimiter at all parses as an EMPTY
    population, which would convict every owned id as nonexistent on the
    strength of junk.
    """
    wrapper = shutil.which(_CREDENTIAL_WRAPPER)
    query = ("bd", "-C", str(repo), "list", "--status", "all", "--json")
    argv = (wrapper, "--", *query) if wrapper else query
    try:
        # S603: a fixed argv of literal arguments plus the repo path; no shell.
        completed = subprocess.run(
            argv,
            check=False,
            capture_output=True,
            text=True,
            timeout=_QUERY_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as unrunnable:
        return _unreachable(repo=repo, argv=argv, reason=_QUERY_UNRUNNABLE, detail=str(unrunnable))
    if completed.returncode != 0:
        return _unreachable(
            repo=repo,
            argv=argv,
            reason=_QUERY_REFUSED,
            detail=f"exit {completed.returncode}: {completed.stderr.strip()}",
        )
    if not any(mark in completed.stdout for mark in "[{"):
        return _unreachable(
            repo=repo,
            argv=argv,
            reason=_OUTPUT_CARRIES_NO_JSON,
            detail=completed.stdout.strip(),
        )
    try:
        records = parse_records(text=completed.stdout)
    except json.JSONDecodeError as unparseable:
        return _unreachable(
            repo=repo, argv=argv, reason=_OUTPUT_UNPARSEABLE, detail=str(unparseable)
        )
    snapshot: dict[str, str] = {}
    for record in records:
        item_id = record.get("id")
        status = record.get("status")
        if isinstance(item_id, str) and isinstance(status, str):
            snapshot[item_id] = status
    return IOSuccess(snapshot)


def resolved_status(
    *, work_item: str, snapshot: IOResult[dict[str, str], LedgerUnreachable]
) -> str:
    """The word to REPORT for `work_item` — its status, `nonexistent`, or `unreachable`.

    The boolean verdict alone cannot satisfy the ratified requirement that a
    surfaced stand-down name "the id and its resolved status", and it cannot
    tell a reader which half of "closed or nonexistent" they are looking at.

    Total by construction — every input has a word — so it stays off the
    railway itself and READS one instead. `UNREACHABLE` is the one word it
    prints for the whole failure track; a caller that needs to know WHICH
    non-answer occurred reads the `LedgerUnreachable` payload.
    """
    if isinstance(snapshot, IOFailure):
        return UNREACHABLE
    return unsafe_perform_io(snapshot.unwrap()).get(work_item, NONEXISTENT)


def _is_live(*, work_item: str, statuses: dict[str, str]) -> bool:
    """Whether an ANSWERING store holds `work_item` at a non-closed status."""
    status = statuses.get(work_item)
    return status is not None and status not in _CLOSED_STATUSES


def resolve_liveness(
    *, work_item: str, snapshot: IOResult[dict[str, str], LedgerUnreachable]
) -> IOResult[bool, LedgerUnreachable]:
    """Whether `work_item` is live; the failure track when the store did not answer.

    `False` covers BOTH halves of the ratified "closed or nonexistent"
    verdict, because a stand-down has the same defect either way: it names
    work nobody is going to do. `resolved_status` is what separates them for
    the reader.

    "I could not measure" is the FAILURE TRACK rather than a third value of
    the verdict, which is what stops a caller from reading it as a verdict by
    accident — the defect the `bool | None` shape invited, since `not None` is
    `True` and a forgotten `is None` arm silently convicted an unmeasured id.
    The store's failure is forwarded UNCHANGED: this function adds no failure
    mode of its own.
    """
    return snapshot.map(lambda statuses: _is_live(work_item=work_item, statuses=statuses))
