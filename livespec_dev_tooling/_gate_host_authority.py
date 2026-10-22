"""What a delegated push's AUTHORITY-DECLARING members answered on the pushing host.

The one exception in the "What the delegated gate runs" bullet of this
repository's own `SPECIFICATION/contracts.md`, delegated pre-push gate section,
ratified v082. Everything else a delegated gate runs, runs in the Job. A member
that declares it reads an AUTHORIZATION held outside the tree — the work-items
ledger, the forge's repository administration settings — does not, because the
Job is handed no authority BY DESIGN and a check that cannot reach a credential
it needs fails inside a gate Job where the local fall-through would only warn.
So the pre-push gate runs that member HERE, on the pushing host, with the
pushing host's own credentials, against the same committed tree.

THE DELEGATED VERDICT IS A CONJUNCTION, and this module owns one of its two
halves. The Job's verdict authorises nothing on its own: the members it cannot
evaluate are exactly the ones carrying a maintainer's authorization, so a green
Job over a tree whose approval was never read is not a gated tree.
`run_host_authority_members` observes what the host answered and
`host_authority_decision` ANDs that into the Job's verdict — in that direction
only, because the Job half is already fail-closed and nothing here may widen it.

THE THREE OUTCOMES ARE KEPT APART, and that is the whole shape of the record.
A member that RAN carries its real exit code. A member that could not be RUN at
all carries `None`, exactly as `GateStepFailed` does, because an absent `just`
is an install problem and a non-zero exit is an authorization problem and an
operator sent after the wrong one has been sent nowhere. And a DECLARATION this
host cannot read arrives as a record for the member it names, with no exit code,
rather than as a dropped row: a dropped row reads as "this member needs no
authority", which is precisely how a ledger-reading member gets handed back to a
pod holding no ledger — the state measured on 2026-10-19 in Job
`gate-livespec-dev-tooling-54f19942138d`.

EVERY MEMBER RUNS, even after one has already failed. The push is refused either
way, so stopping early would buy nothing and would hide the second authorization
problem until the first is fixed — two pushes to learn what one could have said.

A PRIVATE MODULE WITH A PUBLIC SURFACE, per this package's own convention for a
cohesion split (`_gate_remote_assembly.py` and its siblings): the names in
`__all__` are the interface `gate_remote_delegate` composes.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from livespec_dev_tooling.check_authority import repository_authority_members
from livespec_dev_tooling.gate_remote_invocation import GateCommandRunner
from livespec_dev_tooling.gate_remote_verdict import GateVerdict

# `returns` is VENDORED, not installed; a bare import here would resolve only
# when some earlier import in the process happened to run first.
_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.pipeline import is_successful  # noqa: E402  — vendor-path-aware import.
from returns.result import Failure  # noqa: E402  — same.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — same.

__all__: list[str] = [
    "GATE_HOST_AUTHORITY_REFUSED",
    "HostAuthorityRun",
    "host_authority_decision",
    "run_host_authority_members",
]

# The verdict state of a push the GATE JOB cleared and the PUSHING HOST did not.
# A fourth word beside `gate_remote_verdict`'s three rather than a reuse of
# `GATE_FAILED`, because the two name different facts about the same push: the
# tree the Job judged was green, and the authorization this host judged was not.
# `GateVerdict.refuses_push` admits exactly one state, so a word it has never
# heard of refuses by construction — which is why adding one is safe here.
GATE_HOST_AUTHORITY_REFUSED = "HOST_AUTHORITY_REFUSED"

# What such a push says. It names no member yet; naming the one that refused is
# the next thing this file owes its reader.
_HOST_AUTHORITY_REFUSAL = (
    "the gate Job reported a green verdict, but an authorization-declaring member of this "
    "repository's check set did not pass on the pushing host, so this push is refused"
)


@dataclass(frozen=True, kw_only=True)
class HostAuthorityRun:
    """What ONE authority-declaring member answered on the pushing host.

    `returncode` is `None` — never a stand-in number — when nothing ran, which
    is the one thing that tells a caller the host could not evaluate the member
    rather than evaluated it and was refused. `tree_hash` is carried on the
    record rather than left to the caller to remember, because the whole claim
    this record supports is "that member ran against the tree the Job was
    handed", and a record that cannot say which tree supports a weaker claim.
    """

    member: str
    tree_hash: str
    returncode: int | None
    detail: str


def run_host_authority_members(
    *, repo_root: Path, tree_hash: str, runner: GateCommandRunner
) -> tuple[HostAuthorityRun, ...]:
    """Run `repo_root`'s authority-declaring members here, and report what each answered.

    In INVENTORY ORDER, invoked exactly as the aggregate invokes them
    (`just <member>`) and in the PUSHING WORKTREE, so a member reads the same
    committed tree the Job was handed and reaches the same credentials a local
    `just check` would have given it.

    AN UNREADABLE REGISTRY RETURNS ONE RECORD, not an empty tuple. Emptiness is
    the answer a correctly-declared repository with no authority member gives,
    so spelling "I could not read the declarations" the same way would let the
    first registry typo silently restore the behaviour this exception removed.
    """
    resolved = repository_authority_members(repo_root=repo_root)
    if not is_successful(resolved):
        malformed = unsafe_perform_io(resolved.failure())
        return (
            HostAuthorityRun(
                member=malformed.target,
                tree_hash=tree_hash,
                returncode=None,
                detail=(
                    f"{malformed.value!r} names no authority this gate knows: "
                    f"{malformed.reason}"
                ),
            ),
        )
    ran: list[HostAuthorityRun] = []
    for member in unsafe_perform_io(resolved.unwrap()):
        argv = ["just", member]
        outcome = runner(argv=argv, cwd=repo_root)
        if isinstance(outcome, Failure):
            ran.append(
                HostAuthorityRun(
                    member=member,
                    tree_hash=tree_hash,
                    returncode=None,
                    detail=outcome.failure().detail,
                )
            )
            continue
        answered = outcome.unwrap()
        ran.append(
            HostAuthorityRun(
                member=member,
                tree_hash=tree_hash,
                returncode=answered.returncode,
                detail=answered.stderr,
            )
        )
    return tuple(ran)


def host_authority_decision(
    *, verdict: GateVerdict, ran: tuple[HostAuthorityRun, ...]
) -> GateVerdict:
    """AND the pushing host's authority half into the gate Job's verdict.

    A PASS IS THE ONLY THING THAT CARRIES THE VERDICT THROUGH, which is the same
    asymmetry `gate_remote_verdict` is built on: exactly one observation leaves
    the verdict standing, and every other shape a host can produce — a non-zero
    exit, a member that never ran, a declaration nothing could read — refuses.
    An authority half written as "refuse these known faults" would pass every
    fault nobody enumerated, and the thing it would be passing is a maintainer
    authorization that was never read.

    THE JOB'S TOKEN IS CARRIED FORWARD RATHER THAN RETRACTED, and that is sound
    rather than lenient. The green token memoizes only the members whose verdict
    the committed tree alone decides, and an authority-reading member is
    world-reading by construction — it reads a label or a repository setting —
    so the next push of this byte-identical tree runs it again on the pushing
    host either way. Retracting the token would re-gate the tree-pure members
    the Job did judge, for no verdict anyone would read differently.
    """
    if all(run.returncode == 0 for run in ran):
        return verdict
    return GateVerdict(
        state=GATE_HOST_AUTHORITY_REFUSED,
        detail=_HOST_AUTHORITY_REFUSAL,
        token_written=verdict.token_written,
        job_name=verdict.job_name,
    )
