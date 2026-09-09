"""The delegated gate client's cluster plumbing — R4.S7a.

Drives ONE delegated gate run: push the tree under test to the mirror, submit
the rendered Job, wait for its terminal state, stream its logs to the operator's
terminal, delete the ref. Every reach into the world goes through the
`GateCommandRunner` seam, so the whole client runs against a canned runner with
no cluster, no mirror and no host touched.

WHAT THIS SLICE DELIBERATELY DOES NOT DO IS ADJUDICATE. A `Failed` gate comes
back from here as an ordinary SUCCESS carrying the terminal state it read;
deciding pass from fail, and writing the existing green token on a pass, is
S7b. A client that folded "the Job failed" into its own failure track would
leave S7b nothing to interpret and would make a plumbing fault and a red tree
indistinguishable — which is the one distinction a delegated gate has to keep,
because the two want opposite responses.

ONE VALUE names the pushed tree, the served ref and (in S7b) the token:
`git rev-parse HEAD^{tree}`. It is the value `green_token` keys its marker on
and the value the Job's `initContainer` re-derives after checkout and refuses to
proceed without, so a verdict cannot be separated from the tree it was produced
against.

THE REF DELETION IS THE PART THAT FAILS SILENTLY. One gated push creates one
ref and nothing in the protocol removes it, so this client is the FIRST
collector and `prune-gate-refs.sh` on the mirror host is the second — that sweep
exists precisely because a client which dies between the push and the verdict
leaves its ref behind. The delete therefore sits in a `finally`: it runs on the
success path, on a failed step, on a step that RAISED, and on the wait giving
up. An orphan ref raises no error anywhere and is visible only as unbounded
namespace growth weeks later.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias, cast

from livespec_dev_tooling.gate_remote_invocation import (
    GateCommandRunner,
    GateStepFailed,
    Sleeper,
    StepOutcome,
    default_gate_command_runner,
    default_sleeper,
    require_invocation,
    require_success,
)

# `returns` is VENDORED, not installed; a bare import here would resolve only
# when some earlier import in the process happened to run first.
_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.result import Failure, Result, Success  # noqa: E402  — vendor-path-aware import.

__all__: list[str] = [
    "GATE_NAMESPACE",
    "GateRunOutcome",
    "GateRunRequest",
    "run_gate",
]

# The namespace R4.S2 builds and the gate Job template already declares. Named
# here rather than passed by every caller, and still overridable per request.
GATE_NAMESPACE = "gates"

_READ_TREE_STEP = "read-tree-hash"
_PUSH_STEP = "push-gate-ref"
_SUBMIT_STEP = "submit-gate-job"
_AWAIT_STEP = "await-gate-terminal"
_STREAM_STEP = "stream-gate-logs"
_DELETE_STEP = "delete-gate-ref"

# The two Job conditions that mean the gate is OVER. Kubernetes reports every
# condition it has ever set, negative ones included, so the type alone does not
# say the gate finished — the condition must also be asserted `"True"`.
_TERMINAL_CONDITION_TYPES = frozenset({"Complete", "Failed"})
_CONDITION_ASSERTED = "True"

_JobPayload: TypeAlias = Mapping[str, Mapping[str, object]]
_Conditions: TypeAlias = Sequence[Mapping[str, str]]


@dataclass(frozen=True, kw_only=True)
class GateRunRequest:
    """Everything one delegated gate run needs to know about the world.

    Bundled rather than spread across `run_gate`'s parameters so the seams
    (the runner and the sleeper) stay the only other arguments — what the run
    NEEDS and how it REACHES the world are different kinds of thing.

    `manifest` arrives already rendered, by `render-gate-job.sh` from the gated
    repository's own workflow; `job_name` is the name that renderer was asked
    for, since nothing here parses YAML to rediscover it.
    """

    repo_root: Path
    mirror_url: str
    manifest: str
    job_name: str
    namespace: str = GATE_NAMESPACE
    poll_interval_seconds: float = 10.0
    poll_timeout_seconds: float = 3600.0


@dataclass(frozen=True, kw_only=True)
class GateRunOutcome:
    """The RAW terminal outcome of one gate run — never a verdict.

    `terminal_state` is the Job condition type the cluster reported, verbatim,
    and `logs_returncode` is the log stream's own exit code. Both are
    observations for S7b to interpret; neither is a decision.
    """

    tree_hash: str
    job_name: str
    terminal_state: str
    logs_returncode: int


def run_gate(
    *,
    request: GateRunRequest,
    runner: GateCommandRunner = default_gate_command_runner,
    sleeper: Sleeper = default_sleeper,
) -> Result[GateRunOutcome, GateStepFailed]:
    """Gate the current HEAD tree on the cluster and report what happened.

    The ref is deleted by the `finally` below on EVERY path out of the gated
    section, including an exception no `Result` models. A delete that itself
    fails is reported rather than swallowed — an orphan ref the run knows about
    is worth more than a clean-looking return — but a failure from the gate
    itself wins, because it is the one the operator has to act on first.
    """
    tree = _head_tree_hash(request=request, runner=runner)
    if isinstance(tree, Failure):
        return Failure(tree.failure())
    tree_hash = tree.unwrap()
    push_argv = ["git", "push", request.mirror_url, f"HEAD:refs/gates/{tree_hash}"]
    pushed = require_success(
        step=_PUSH_STEP, argv=push_argv, outcome=runner(argv=push_argv, cwd=request.repo_root)
    )
    # Nothing to collect when the push never landed: there is no ref of ours on
    # the mirror, and no tree for a gate Job to fetch.
    if isinstance(pushed, Failure):
        return Failure(pushed.failure())
    try:
        gated = _gate_a_pushed_tree(
            request=request, runner=runner, sleeper=sleeper, tree_hash=tree_hash
        )
    finally:
        deleted = _delete_gate_ref(request=request, runner=runner, tree_hash=tree_hash)
    if isinstance(gated, Failure):
        return gated
    if isinstance(deleted, Failure):
        return Failure(deleted.failure())
    return gated


def _kubectl(*, request: GateRunRequest) -> list[str]:
    """The namespaced `kubectl` prefix every cluster command here shares."""
    return ["kubectl", "--namespace", request.namespace]


def _head_tree_hash(
    *, request: GateRunRequest, runner: GateCommandRunner
) -> Result[str, GateStepFailed]:
    """Read the tree the gate will run against, through the seam.

    Deliberately NOT `green_token`'s own reader: that one calls `subprocess`
    directly with `check=True`, so borrowing it would put a raise and an
    unstubbable command in the middle of a client whose whole testability rests
    on the seam.
    """
    argv = ["git", "rev-parse", "HEAD^{tree}"]
    lifted = require_success(
        step=_READ_TREE_STEP, argv=argv, outcome=runner(argv=argv, cwd=request.repo_root)
    )
    return lifted.map(lambda ran: ran.stdout.strip())


def _delete_gate_ref(
    *, request: GateRunRequest, runner: GateCommandRunner, tree_hash: str
) -> StepOutcome:
    """Collect the ref this run created — the first of the two collectors."""
    argv = ["git", "push", "--delete", request.mirror_url, f"refs/gates/{tree_hash}"]
    return require_success(
        step=_DELETE_STEP, argv=argv, outcome=runner(argv=argv, cwd=request.repo_root)
    )


def _gate_a_pushed_tree(
    *,
    request: GateRunRequest,
    runner: GateCommandRunner,
    sleeper: Sleeper,
    tree_hash: str,
) -> Result[GateRunOutcome, GateStepFailed]:
    """Submit, wait, stream — the section that owns the pushed ref.

    `create` rather than `apply`: re-gating the same tree yields the same Job
    name, and `apply` would silently ADOPT the existing object, making a re-run
    a second attempt on the first run's Job. The template's `backoffLimit: 0`
    states the same rule for the same reason — a gate verdict is a measurement,
    so a re-run must be a new, separately identified gate.

    The logs are streamed AFTER the terminal state rather than during: until
    Kueue admits the Job there is no pod to attach to, so a follow that starts
    at submit time races admission. The cost is that a long gate prints nothing
    until it ends, which is a known and separable improvement rather than a
    property anything here depends on.
    """
    submit_argv = [*_kubectl(request=request), "create", "--filename", "-"]
    submitted = require_success(
        step=_SUBMIT_STEP,
        argv=submit_argv,
        outcome=runner(argv=submit_argv, cwd=request.repo_root, stdin=request.manifest),
    )
    if isinstance(submitted, Failure):
        return Failure(submitted.failure())
    terminal = _await_terminal_state(request=request, runner=runner, sleeper=sleeper)
    if isinstance(terminal, Failure):
        return Failure(terminal.failure())
    logs_argv = [
        *_kubectl(request=request),
        "logs",
        f"job/{request.job_name}",
        "--all-containers",
        "--follow",
    ]
    # `require_invocation`, not `require_success`: this exit code is
    # OBSERVATIONAL — it echoes the gate's own — so a red gate must not read as
    # the log step having failed to stream.
    streamed = require_invocation(
        step=_STREAM_STEP,
        argv=logs_argv,
        outcome=runner(argv=logs_argv, cwd=request.repo_root, stream=True),
    )
    return streamed.map(
        lambda ran: GateRunOutcome(
            tree_hash=tree_hash,
            job_name=request.job_name,
            terminal_state=terminal.unwrap(),
            logs_returncode=ran.returncode,
        )
    )


def _poll_budget(*, request: GateRunRequest) -> int:
    """How many polls the timeout buys at this interval.

    Derived rather than read from a clock, so the client needs no time source
    beyond the `Sleeper` its tests already substitute. It therefore bounds
    POLLS, not wall-clock: a slow API server makes each poll longer and the real
    ceiling correspondingly later. That is the honest cost of one fewer seam,
    and the bound's job is to stop an unbounded wait, not to time it.
    """
    return max(1, int(request.poll_timeout_seconds // request.poll_interval_seconds))


def _await_terminal_state(
    *, request: GateRunRequest, runner: GateCommandRunner, sleeper: Sleeper
) -> Result[str, GateStepFailed]:
    """Poll the Job until it reports a terminal condition, or give up.

    A read that could not be MADE is not a gate that has not finished YET, so a
    refused `get` ends the wait rather than being polled through: continuing
    would spend the whole budget re-asking a question the cluster has already
    declined to answer.
    """
    argv = [*_kubectl(request=request), "get", "job", request.job_name, "--output", "json"]
    for _ in range(_poll_budget(request=request)):
        lifted = require_success(
            step=_AWAIT_STEP, argv=argv, outcome=runner(argv=argv, cwd=request.repo_root)
        )
        if isinstance(lifted, Failure):
            return Failure(lifted.failure())
        condition = _terminal_condition(argv=argv, payload=lifted.unwrap().stdout)
        if isinstance(condition, Failure):
            return Failure(condition.failure())
        state = condition.unwrap()
        if state is not None:
            return Success(state)
        sleeper(seconds=request.poll_interval_seconds)
    return Failure(
        GateStepFailed(
            step=_AWAIT_STEP,
            argv=tuple(argv),
            returncode=None,
            detail=(
                f"{request.job_name} reached no terminal condition "
                f"within {request.poll_timeout_seconds:g}s"
            ),
        )
    )


def _terminal_condition(*, argv: Sequence[str], payload: str) -> Result[str | None, GateStepFailed]:
    """The terminal condition's type, or `None` for a gate still running.

    `None` is an ABSENCE every caller acts on as ordinary control flow — "not
    finished yet, poll again" — and is the majority answer. A payload that
    cannot be READ is the failure track instead: neither "finished" nor "still
    running" may be inferred from nonsense, and guessing either way is how a
    delegated gate reports a verdict it never obtained.
    """
    try:
        parsed = cast("_JobPayload", json.loads(payload))
    except json.JSONDecodeError as unreadable:
        return Failure(
            GateStepFailed(
                step=_AWAIT_STEP,
                argv=tuple(argv),
                returncode=None,
                detail=f"unreadable job status: {unreadable}",
            )
        )
    conditions = cast("_Conditions", parsed.get("status", {}).get("conditions", ()))
    for condition in conditions:
        asserted = condition.get("status") == _CONDITION_ASSERTED
        if asserted and condition.get("type") in _TERMINAL_CONDITION_TYPES:
            return Success(condition["type"])
    return Success(None)
