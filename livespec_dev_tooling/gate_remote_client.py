"""The delegated gate client's cluster plumbing — R4.S7a.

Drives ONE delegated gate run: push the tree under test to the mirror, submit
the rendered Job, wait for its terminal state, stream its logs to the operator's
terminal, delete the ref. Every reach into the world goes through the
`GateCommandRunner` seam, so the whole client runs against a canned runner with
no cluster, no mirror and no host touched.

EVERY CLUSTER COMMAND RUNS THROUGH `with-gates-kubeconfig`, never a bare
`kubectl` — the prefix is applied in `_kubectl`, the one place cluster commands
are built, so no step can be spelled without it. `gate_credential` carries why:
a bare `kubectl` authenticates with the pushing user's own environment, which on
the VPS login user holds no kubeconfig, and it never reaches the credential
refresh the wrapper exists to perform.

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

IT DOES NOT NAME THE JOB, AND THAT IS THE ONE PLACE IT MUST NOT
(livespec-dev-tooling-44fglo). A Job named by the tree alone can exist only once
per tree, and the template keeps a finished Job for an hour, so for that hour a
SECOND gate of one tree could not be submitted at all: `kubectl create` answers
`AlreadyExists`, which arrives here as a step that did not complete and is
reported as NO_VERDICT — the outcome reserved for a lost cluster. Measured
2026-10-18: `gate-livespec-473f0ffdee14` ended Failed at 07:02:17Z and an
independent replay of the same tree at 07:07Z was refused at submit. Two
ordinary moves reach it — a push refused on a red verdict and retried after a
cluster-side fix that changed nothing in the tree, and any independent replay of
a just-gated tree. The manifest therefore carries `generateName`, the API SERVER
assigns the name, and this client READS IT BACK off the submit rather than being
told one: uniqueness belongs to the only party that can enforce it when two
pushes of one tree race, and a suffix invented here could collide. The tree stays
selectable through the manifest's `livespec.gate/tree-hash` label, which is what
gathers every Job of one tree now that no name does.

A SECOND REF RIDES THE SAME PUSH, and it is not a second identity: the mirror
is created EMPTY (`git init --bare`), so it holds only what a gate push puts
there, while eight members of the aggregate judge the commit range
`origin/master..HEAD` rather than a tree. `refs/gates/<tree>.base` carries this
client's own `origin/master` and the pod's initContainer fetches it straight
into `refs/remotes/origin/master`. The push is `--atomic` so a tree ref without
its base cannot exist; the tree hash still names the tree, the served ref, this
Job and the token.

THE MIRROR PUSHES RUN WITH THE PUSHING REPOSITORY'S HOOKS DISABLED, and that is
what keeps this client from calling itself. git runs `pre-push` for EVERY push,
the mirror push included, and the only way this client is ever reached is FROM a
repository's own `pre-push` hook — so a push spelled with hooks live re-enters
that hook, which delegates again, which pushes again. The recursion is unbounded
and presents as a HANG rather than an error, because every level is doing exactly
what it was asked to do: measured on the VPS 2026-10-12, a worktree push sat 48
minutes and was refused NO_VERDICT. The 2026-09-10 proof called this client
directly rather than from a hook, which is why it could not see this at all.

The push is internal TRANSPORT of the tree being gated rather than a user push,
so `core.hooksPath=/dev/null` is set for that one git invocation and the user's
own push keeps its hooks. BOTH pushes here are spelled that way — the publish and
the collection — because git fires the hook for a `--delete` too, and a client
that disabled hooks on only one of them recurses one step later instead. The
prefix is therefore built in `_mirror_push`, the one place a mirror push is built,
exactly as `_kubectl` is the one place a cluster command is built: a hookless
push is not a property a step can be spelled without.

THE REF DELETION IS THE PART THAT FAILS SILENTLY. One gated push creates those
two refs and nothing in the protocol removes them, so this client is the FIRST
collector and `prune-gate-refs.sh` on the mirror host is the second — that sweep
exists precisely because a client which dies between the push and the verdict
leaves its refs behind. The delete therefore sits in a `finally`: it runs on the
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

from livespec_dev_tooling.gate_credential import with_gates_kubeconfig
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
    "GATE_BASE_REF_SUFFIX",
    "GATE_NAMESPACE",
    "GATE_RANGE_BASE_REF",
    "GateRunOutcome",
    "GateRunRequest",
    "run_gate",
]

# The namespace R4.S2 builds and the gate Job template already declares. Named
# here rather than passed by every caller, and still overridable per request.
GATE_NAMESPACE = "gates"

# The local ref whose commit becomes the gate's diff base. The same literal the
# checks themselves resolve — `red_green_replay`, `check_coverage_incremental`
# and `plan_no_live_handoff_file` all name `origin/master` — so it is a constant
# rather than a per-request knob: a gate that diffed against something else
# would return a verdict about a range the repository does not gate on.
GATE_RANGE_BASE_REF = "origin/master"

# The suffix that names the base ref beside the tree ref. LOCKSTEP WITH
# `ci-runner/k3s/phase2/gates/gate-job-template.yaml`, whose initContainer
# fetches `refs/gates/<tree>.base` into `refs/remotes/origin/master`. Neither
# file can see the other and a drifted suffix is a syntax error in neither: it
# is a fetch that finds nothing, at gate time, on the cluster — so a test holds
# this constant and that refspec together.
GATE_BASE_REF_SUFFIX = ".base"

# The hooks directory a mirror push runs with. `/dev/null` is not a DIRECTORY,
# so git finds no hook file beneath it and runs none — measured with git 2.43.0:
# a plain push fires `pre-push`, this form does not.
_NO_HOOKS_PATH = "/dev/null"

_READ_TREE_STEP = "read-tree-hash"
_PUSH_STEP = "push-gate-ref"
_SUBMIT_STEP = "submit-gate-job"
_AWAIT_STEP = "await-gate-terminal"
_STREAM_STEP = "stream-gate-logs"
_DELETE_STEP = "delete-gate-ref"

# The two Job conditions that mean the gate is OVER. Kubernetes reports every
# condition it has ever set, negative ones included, so the type alone does not
# say the gate finished — the condition must also be asserted `"True"`.
_COMPLETE_CONDITION = "Complete"
_TERMINAL_CONDITION_TYPES = frozenset({_COMPLETE_CONDITION, "Failed"})
_CONDITION_ASSERTED = "True"

# The failed pod's own last words. `containerStatuses` rather than
# `initContainerStatuses`: the aggregate container is the one whose refusal an
# operator has to act on, and the initContainer's own fatal paths already name
# themselves in the log. The Job object does not carry this — only its pod does
# — so it is a separate read, taken only when there is a failure to explain.
_TERMINATION_MESSAGE_JSONPATH = "{.items[*].status.containerStatuses[*].state.terminated.message}"

_JobPayload: TypeAlias = Mapping[str, Mapping[str, object]]
_Conditions: TypeAlias = Sequence[Mapping[str, str]]


@dataclass(frozen=True, kw_only=True)
class GateRunRequest:
    """Everything one delegated gate run needs to know about the world.

    Bundled rather than spread across `run_gate`'s parameters so the seams
    (the runner and the sleeper) stay the only other arguments — what the run
    NEEDS and how it REACHES the world are different kinds of thing.

    `manifest` arrives already rendered, by `render-gate-job.sh` from the gated
    repository's own workflow.

    THERE IS NO JOB NAME HERE, and its absence is the fix for
    livespec-dev-tooling-44fglo. A request used to carry the name the renderer
    was asked for, and the run waited on exactly that — which is sound only while
    one tree can have one Job. The manifest now carries `generateName`, so the
    name does not exist until the API server assigns it and nothing that could
    be bundled here would be it; the run learns its Job's name from the submit.
    """

    repo_root: Path
    mirror_url: str
    manifest: str
    namespace: str = GATE_NAMESPACE
    poll_interval_seconds: float = 10.0
    poll_timeout_seconds: float = 3600.0


@dataclass(frozen=True, kw_only=True)
class GateRunOutcome:
    """The RAW terminal outcome of one gate run — never a verdict.

    `terminal_state` is the Job condition type the cluster reported, verbatim,
    and `logs_returncode` is the log stream's own exit code. Both are
    observations for S7b to interpret; neither is a decision.

    `job_name` is the name the API SERVER gave this run's Job, read back off the
    submit — so it names THIS run even when the same tree has been gated before
    and the namespace still holds that gate's Job.

    `failure_message` is the failed pod's termination message, verbatim, and the
    empty string when there was none or when the gate did not fail. It is the
    pod's OWN account of why it stopped — notably the preflight's refusal naming
    a check recipe the tree under test does not provide — and it is carried
    rather than interpreted for the same reason `terminal_state` is: what to do
    about it is S7b's, and until then it is evidence.
    """

    tree_hash: str
    job_name: str
    terminal_state: str
    logs_returncode: int
    failure_message: str = ""


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
    push_argv = [
        *_mirror_push(),
        # `--atomic` is what makes the two refs ONE FACT. The mirror is created
        # empty and holds only what a gate push puts there, so the diff base is
        # not something the pod can find on its own; a partial push would land
        # the tree ref alone and the Job would then fail on a base that was
        # never pushed rather than on the code under test.
        "--atomic",
        request.mirror_url,
        f"HEAD:refs/gates/{tree_hash}",
        f"{GATE_RANGE_BASE_REF}:refs/gates/{tree_hash}{GATE_BASE_REF_SUFFIX}",
    ]
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


def _mirror_push() -> list[str]:
    """The HOOKLESS `git push` prefix every mirror push here shares.

    The hooks are disabled because this client is reached from a repository's own
    `pre-push` hook, and git fires that hook for every push — so a mirror push
    spelled with hooks live re-enters the hook, which delegates again, which
    pushes again, unbounded. It hangs rather than erroring: measured on the VPS
    2026-10-12, a worktree push sat 48 minutes and was refused NO_VERDICT.

    Built HERE, where a mirror push is built, so no step can be spelled without
    it — the same reason `_kubectl` below is the only place a cluster command is
    assembled. Only THIS invocation is hookless; the user's own push, which is
    the one a `pre-push` hook exists to gate, is untouched.
    """
    return ["git", "-c", f"core.hooksPath={_NO_HOOKS_PATH}", "push"]


def _kubectl(*, request: GateRunRequest) -> list[str]:
    """The namespaced `kubectl` prefix every cluster command here shares.

    THROUGH `with-gates-kubeconfig`, and that is not a convenience. A bare
    `kubectl` authenticates with whatever `KUBECONFIG` the pushing user's
    environment carries — on the VPS login user, none at all — and it never
    reaches the wrapper's refresh-on-rejection path, so the first gate after a
    control-plane boot fails 401 with nothing to fix it. The prefix is applied
    HERE, where every cluster command is built, so no step can be spelled
    without it.
    """
    return with_gates_kubeconfig(argv=["kubectl", "--namespace", request.namespace])


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
    """Collect the refs this run created — the first of the two collectors.

    BOTH refs, because the push created both. The `.base` companion is the same
    kind of litter as the tree ref and accumulates at the same rate, so naming
    only the tree ref would halve the collection while looking complete — and
    the shortfall is invisible until the mirror's namespace is measured.

    THROUGH `_mirror_push` for the same reason the publish is: a `--delete` is a
    push, and git fires `pre-push` for it too, so a collection spelled with hooks
    live re-enters the hook that started this gate and delegates another one.
    Fixing the publish alone leaves the recursion in place one step later, where
    it is harder to see — the tree has already been gated by then.
    """
    argv = [
        *_mirror_push(),
        "--delete",
        request.mirror_url,
        f"refs/gates/{tree_hash}",
        f"refs/gates/{tree_hash}{GATE_BASE_REF_SUFFIX}",
    ]
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

    `create` rather than `apply`, and `--output name` so the created object
    names itself back. `apply` would silently ADOPT an object of the same name,
    making a re-run a second attempt on the first run's Job; `create` against a
    `generateName` manifest is how a re-run becomes a NEW Job instead, since the
    API server assigns a name nothing can already hold. The template's
    `backoffLimit: 0` states the same rule for the same reason — a gate verdict
    is a measurement, so a re-run must be a new, separately identified gate.

    EVERY LATER STEP USES THE ASSIGNED NAME, which is why it is read here, at
    the one place the Job comes into existence: the poll, the pod read and the
    log stream all address the Job, and a name chosen before the submit would
    address whatever else happens to carry it — or nothing at all.

    The logs are streamed AFTER the terminal state rather than during: until
    Kueue admits the Job there is no pod to attach to, so a follow that starts
    at submit time races admission. The cost is that a long gate prints nothing
    until it ends, which is a known and separable improvement rather than a
    property anything here depends on.
    """
    submit_argv = [*_kubectl(request=request), "create", "--filename", "-", "--output", "name"]
    submitted = require_success(
        step=_SUBMIT_STEP,
        argv=submit_argv,
        outcome=runner(argv=submit_argv, cwd=request.repo_root, stdin=request.manifest),
    )
    if isinstance(submitted, Failure):
        return Failure(submitted.failure())
    named = _created_job_name(argv=submit_argv, stdout=submitted.unwrap().stdout)
    if isinstance(named, Failure):
        return Failure(named.failure())
    job_name = named.unwrap()
    terminal = _await_terminal_state(
        request=request, runner=runner, sleeper=sleeper, job_name=job_name
    )
    if isinstance(terminal, Failure):
        return Failure(terminal.failure())
    state = terminal.unwrap()
    # Read only when there is a failure to explain. That is a decision about
    # whether to spend an API call, NOT an adjudication: the message is carried
    # verbatim either way and this slice still forms no opinion about it.
    message = (
        ""
        if state == _COMPLETE_CONDITION
        else _failure_message(request=request, runner=runner, job_name=job_name)
    )
    logs_argv = [
        *_kubectl(request=request),
        "logs",
        f"job/{job_name}",
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
            job_name=job_name,
            terminal_state=state,
            logs_returncode=ran.returncode,
            failure_message=message,
        )
    )


def _created_job_name(*, argv: Sequence[str], stdout: str) -> Result[str, GateStepFailed]:
    """The name the API SERVER gave this run's Job, off `create --output name`.

    THE SUBMIT'S OWN ANSWER IS THE ONLY HANDLE ON THE JOB IT CREATED. With a
    `generateName` manifest the name does not exist until the create returns, so
    a submit this cannot be read out of leaves the run with nothing to poll,
    nothing to stream and nothing to explain. That is the failure track rather
    than a wait on the empty string: an unreadable answer is not a gate, and the
    one thing a delegated gate may never do is report a verdict it did not
    obtain.

    `kubectl` prints the resource-qualified form (`job.batch/<name>`), so the
    last `/`-separated segment is the name; the last non-empty LINE is taken
    because a printer that ever prefaced it with a warning would otherwise make
    the warning the name.
    """
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    name = lines[-1].rsplit("/", maxsplit=1)[-1] if lines else ""
    if not name:
        return Failure(
            GateStepFailed(
                step=_SUBMIT_STEP,
                argv=tuple(argv),
                returncode=None,
                detail=f"the submit named no Job, so there is none to wait on: {stdout!r}",
            )
        )
    return Success(name)


def _failure_message(*, request: GateRunRequest, runner: GateCommandRunner, job_name: str) -> str:
    """The failed pod's termination message, or the empty string.

    EVIDENCE, NEVER A VERDICT, which is why every unreadable shape answers the
    empty string rather than a failure. The gate has already reported a real
    terminal condition by the time this runs; a pod that has been collected, a
    read the API server declines, or a container that wrote nothing must not be
    able to turn that red verdict into a no-verdict — the push is refused
    either way, and losing the explanation is strictly better than losing the
    verdict that carries it.
    """
    argv = [
        *_kubectl(request=request),
        "get",
        "pods",
        "--selector",
        f"job-name={job_name}",
        "--output",
        f"jsonpath={_TERMINATION_MESSAGE_JSONPATH}",
    ]
    read = runner(argv=argv, cwd=request.repo_root)
    return read.map(lambda ran: ran.stdout.strip()).value_or("")


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
    *, request: GateRunRequest, runner: GateCommandRunner, sleeper: Sleeper, job_name: str
) -> Result[str, GateStepFailed]:
    """Poll the Job until it reports a terminal condition, or give up.

    `job_name` is the name the submit came back with rather than one the request
    carried, so the gate this waits on is the gate this run created — never a
    gate of the same tree that some earlier push left in the namespace.

    A read that could not be MADE is not a gate that has not finished YET, so a
    refused `get` ends the wait rather than being polled through: continuing
    would spend the whole budget re-asking a question the cluster has already
    declined to answer.
    """
    argv = [*_kubectl(request=request), "get", "job", job_name, "--output", "json"]
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
                f"{job_name} reached no terminal condition "
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
