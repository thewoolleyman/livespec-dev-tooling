"""The delegated gate client's FAIL-CLOSED verdict and token write — R4.S7b.

S7a's `run_gate` reports what the cluster DID and adjudicates nothing. This
module is the adjudication, and it is fail-closed by construction: exactly ONE
observation authorises a push, and every other shape the world can produce —
including shapes nobody has enumerated yet — lands in the refusal. That
asymmetry is the whole design. A delegated gate reaches its verdict across a
tailnet, an API server, a queue and a pod, so the ways it can fail to produce an
answer vastly outnumber the ways it can produce one, and an interpretation
written as "refuse these known faults" would silently pass every fault its
author did not think of.

THE VERDICT CONTRACT IS `gate-run.sh`'s, TRANSPOSED. The local detached runner
treats its `exit_code` file being PRESENT as the one marker that a verdict
exists: 0 is PASSED, 1..127 is a real FAILED verdict, and everything else — a
signal death, a vanished process, a run directory with no such file — is
DIED_WITHOUT_VERDICT, which is neither a pass nor a refusal to reason from. The
delegated gate's analogue of that file is the Job's TERMINAL CONDITION, which
`run_gate` already carries out verbatim: `Complete` is the aggregate having
exited 0 inside the pod, `Failed` is a real red verdict, and every plumbing
fault — a lost connection, an API server that cannot be reached, a kubeconfig
the server rejects — arrives instead on `run_gate`'s FAILURE track as a
`GateStepFailed`, which is this module's `GATE_NO_VERDICT`. The three words
below are that contract's three states under different names.

NO NEW TOKEN FORMAT. A pass calls the EXISTING
`python -m livespec_dev_tooling.green_token write`, through the same command
seam every other step uses, so the token this client leaves behind is
byte-for-byte the one a local aggregate leaves behind and the existing skip path
in `check-pre-push` completes the push with no second reader to keep in step.
ONE VALUE ties it all together: `git rev-parse HEAD^{tree}` names the pushed
tree, the mirror ref S7a served it at, the Job's re-derived checkout, and this
token.

THE TREE IS RE-READ BEFORE THE TOKEN IS WRITTEN, and that is not belt-and-braces.
`green_token write` derives `HEAD^{tree}` ITSELF, at write time, which is many
minutes after the gate started. If HEAD moved in between — an amend, a rebase, a
commit in the same worktree — that write would mark a tree GREEN THAT WAS NEVER
GATED, and the existing skip path would then complete a push with no aggregate
run against it at all. Nothing errors on that path; the hole is silent and
lasting. So the tree is read again through the seam and compared to the one the
gate ran against, which is this repository's "confirm the reader before you
write" ordering rule applied to the token: name the state you are about to
create, and establish that the component which will hold it still holds what you
think it does.

WHY A PASS CAN STILL REFUSE. What authorises the push is a WRITTEN TOKEN FOR THE
GATED TREE, never the verdict alone — the token is the artifact the next process
reads, and a verdict no one can read authorises nothing. So a green gate whose
token could not be written (the tree moved, or the write never ran) refuses too.
The cost of that refusal is one locally-run aggregate; the cost of the opposite
default is an ungated push, and only one of the two is recoverable.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from livespec_dev_tooling.gate_remote_client import GateRunOutcome, GateRunRequest, run_gate
from livespec_dev_tooling.gate_remote_invocation import (
    GateCommandRunner,
    GateStepFailed,
    Sleeper,
    default_gate_command_runner,
    default_sleeper,
    require_success,
)

# `returns` is VENDORED, not installed; a bare import here would resolve only
# when some earlier import in the process happened to run first.
_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.result import Failure, Result  # noqa: E402  — vendor-path-aware import.

__all__: list[str] = [
    "GATE_FAILED",
    "GATE_NO_VERDICT",
    "GATE_PASSED",
    "GateVerdict",
    "run_gated_push",
]

# The three states of the transposed `gate-run.sh` contract. PASSED and FAILED
# are verdicts the gate produced; NO_VERDICT is its DIED_WITHOUT_VERDICT — the
# state that says nothing was decided, so nothing may be concluded.
GATE_PASSED = "PASSED"
GATE_FAILED = "FAILED"
GATE_NO_VERDICT = "NO_VERDICT"

# The ONE Job condition that means the gated aggregate exited 0 in the pod.
# Written as an equality against this single word rather than as a set of
# rejected words, so a condition type Kubernetes adds later is refused by
# default instead of falling through the gaps of a rejection list.
_COMPLETE = "Complete"

_REREAD_STEP = "confirm-tree-hash"
# S105 fires on the name, not the value — the same false positive `green_token`
# itself suppresses on `_TOKEN_FILE`. This is a step label an operator reads.
_TOKEN_STEP = "write-green-token"  # noqa: S105

# The EXISTING CLI, invoked as a module through this interpreter. `sys.executable`
# rather than a bare `python`: the token must be written by the environment the
# client is already running in, which is the one that resolves the package.
_GREEN_TOKEN_WRITE_ARGV = (sys.executable, "-m", "livespec_dev_tooling.green_token", "write")


@dataclass(frozen=True, kw_only=True)
class GateVerdict:
    """What the delegated gate decided, and what the client did about it.

    `state` is the gate's own answer and `token_written` is the client's, and
    the two are kept apart because they can disagree: a gate that PASSED on a
    tree HEAD has since left is a true verdict about a tree nobody is pushing.
    Collapsing them into one boolean would lose exactly the case an operator
    needs the `detail` to explain.
    """

    state: str
    detail: str
    token_written: bool

    @property
    def refuses_push(self) -> bool:
        """True unless the gate passed AND its token was written.

        Stated as the negation of the single authorising case on purpose: the
        push proceeds only on the one shape spelled out here, so a state this
        module has never heard of cannot become a pass by omission.
        """
        return not (self.state == GATE_PASSED and self.token_written)


def run_gated_push(
    *,
    request: GateRunRequest,
    runner: GateCommandRunner = default_gate_command_runner,
    sleeper: Sleeper = default_sleeper,
) -> GateVerdict:
    """Gate the current HEAD tree on the cluster and decide whether to push.

    The failure track of `run_gate` is EVERY plumbing fault at once — the ref
    that would not push, the manifest the API server refused, the poll that
    could not be answered, the wait that gave up — and all of them mean the same
    thing here: no verdict was obtained. They are deliberately not
    re-discriminated. Which fault it was belongs in the `detail` an operator
    reads; what the client does about it is identical either way.
    """
    gated = run_gate(request=request, runner=runner, sleeper=sleeper)
    if isinstance(gated, Failure):
        return _no_verdict(failure=gated.failure())
    return _adjudicate(outcome=gated.unwrap(), request=request, runner=runner)


def _no_verdict(*, failure: GateStepFailed) -> GateVerdict:
    """Every plumbing fault, under one word: nothing was decided."""
    return GateVerdict(
        state=GATE_NO_VERDICT,
        detail=f"{failure.step} did not complete, so the gate reached no verdict: {failure.detail}",
        token_written=False,
    )


def _adjudicate(
    *, outcome: GateRunOutcome, request: GateRunRequest, runner: GateCommandRunner
) -> GateVerdict:
    """Read the terminal condition as the exit code it stands in for."""
    if outcome.terminal_state != _COMPLETE:
        return GateVerdict(
            state=GATE_FAILED,
            detail=(
                f"the gate Job {outcome.job_name} ended {outcome.terminal_state} "
                f"on tree {outcome.tree_hash}"
            ),
            token_written=False,
        )
    return _write_green_token(outcome=outcome, request=request, runner=runner)


def _passed_without_token(*, detail: str) -> GateVerdict:
    """A true green verdict the client cannot hand on — so it does not."""
    return GateVerdict(state=GATE_PASSED, detail=detail, token_written=False)


def _current_head_tree(
    *, request: GateRunRequest, runner: GateCommandRunner
) -> Result[str, GateStepFailed]:
    """Re-read the tree at HEAD, now that the gate has finished.

    The same command S7a ran before the push, asked again for a different
    question: not "what shall we gate" but "is what we gated still what a token
    would name".
    """
    argv = ["git", "rev-parse", "HEAD^{tree}"]
    lifted = require_success(
        step=_REREAD_STEP, argv=argv, outcome=runner(argv=argv, cwd=request.repo_root)
    )
    return lifted.map(lambda ran: ran.stdout.strip())


def _write_green_token(
    *, outcome: GateRunOutcome, request: GateRunRequest, runner: GateCommandRunner
) -> GateVerdict:
    """Confirm the tree, then let the EXISTING CLI write its own token."""
    current = _current_head_tree(request=request, runner=runner)
    if isinstance(current, Failure):
        return _passed_without_token(
            detail=(
                f"the gate passed on tree {outcome.tree_hash}, but HEAD's tree could not be "
                f"re-read, so no token was written: {current.failure().detail}"
            )
        )
    if current.unwrap() != outcome.tree_hash:
        return _passed_without_token(
            detail=(
                f"the gate passed on tree {outcome.tree_hash}, but HEAD now resolves to "
                f"{current.unwrap()}; that tree was never gated, so no token was written"
            )
        )
    argv = list(_GREEN_TOKEN_WRITE_ARGV)
    written = require_success(
        step=_TOKEN_STEP, argv=argv, outcome=runner(argv=argv, cwd=request.repo_root)
    )
    if isinstance(written, Failure):
        return _passed_without_token(
            detail=(
                f"the gate passed on tree {outcome.tree_hash}, but the green token could not "
                f"be written: {written.failure().detail}"
            )
        )
    return GateVerdict(
        state=GATE_PASSED,
        detail=f"the gate passed on tree {outcome.tree_hash}; its green token completes the push",
        token_written=True,
    )
