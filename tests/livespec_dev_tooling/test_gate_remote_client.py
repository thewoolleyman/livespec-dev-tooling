"""The delegated gate client's cluster plumbing — R4.S7a.

Every test here runs against a STUBBED cluster: the client's only reach into the
world is its `GateCommandRunner` seam, so a canned runner is the whole host and
the whole cluster. No process is spawned, no mirror is pushed to, no manifest
reaches an API server, and no ref is created anywhere.

FOUR PROPERTIES ARE LOAD-BEARING and each is here because its absence would be
SILENT.

The first is the ref cleanup. One gated push creates one ref, and nothing in the
protocol removes it; the mirror's hourly sweep is the SECOND collector precisely
because a client that cannot establish the Job's terminal state leaves its ref
behind. Collection is safe only after the Job has reported that terminal state:
an early delete makes a queued Job fail to fetch its input.

The second is that a gate reached FROM a repository's `pre-push` hook — the only
way it is ever reached — must not start another one. git runs that hook for every
push, the client's own mirror pushes included, so a push spelled with hooks live
re-enters the hook, which delegates again, which pushes again, unbounded. Nothing
errors at any level, so the symptom is a HANG and then a refusal that names the
timeout rather than the cause: measured on the VPS 2026-10-12, 48 minutes and
NO_VERDICT. `_PrePushHookedHost` below is that hook, emulated around the canned
cluster, so the re-entry is a COUNT this suite can read rather than a wall-clock
mystery on a host.

The third is that this slice does NOT adjudicate. A `Failed` gate comes back
here as an ordinary SUCCESS carrying the terminal state it read, because
deciding pass from fail — and writing the green token on a pass — is S7b's job.
A client that quietly folded "the Job failed" into its own failure track would
leave S7b nothing to interpret and would make a plumbing fault and a red tree
indistinguishable, which is the one distinction the delegation has to keep.

The fourth is that the Job's name is READ BACK off the submit rather than
predicted. The manifest asks for a `generateName`, which is what makes a
re-gate of one tree a new measurement instead of an `AlreadyExists` refusal — so
the name does not exist until the API server has made one. A client that still
derived the old `gate-<repo>-<tree[:12]>` name would poll, read and stream the
PREVIOUS run's Job for the hour that one survives its TTL, and that Job already
carries a terminal condition: another run's verdict would come back at once,
with nothing anywhere raising an error.
"""

from __future__ import annotations

import dataclasses
import hashlib
import importlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from returns.pipeline import is_successful
from returns.result import Failure, Success

from livespec_dev_tooling.gate_credential import GATES_WRAPPER
from livespec_dev_tooling.gate_remote_client import GateRunRequest, run_gate
from livespec_dev_tooling.gate_remote_invocation import (
    GateCommandNotRun,
    GateCommandOutcome,
    GateCommandResult,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

__all__: list[str] = []


_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
_MIRROR = "cwoolley@poweredge-xubuntu:/var/cache/ci-runner/gates-mirror/widget.git"
# The name the API SERVER assigns, which is the only place a Job's name now
# exists: the manifest asks for a `generateName`, so nothing here — and nothing
# in the client — can predict it. The five random characters are Kubernetes's
# own suffix shape.
_JOB = "gate-widget-7f2qd"
_MANIFEST = "apiVersion: batch/v1\nkind: Job\nmetadata:\n  generateName: gate-widget-\n"
_CREATED = json.dumps({"apiVersion": "batch/v1", "kind": "Job", "metadata": {"name": _JOB}})
# The mirror ref THIS run owns. It carries the gated tree AND a per-run nonce,
# because the client deletes the refs it created on its way out: a name shared
# with a concurrent gate of the same tree is a name one run can delete while the
# other's pod has not fetched it yet.
_GATE_REF = f"refs/gates/{_TREE}-4c1d9f3b2a7e"
_REQUEST = GateRunRequest(
    repo_root=Path("/repo"),
    mirror_url=_MIRROR,
    manifest=_MANIFEST,
    gate_ref=_GATE_REF,
)


def _job_status(*, state: str) -> str:
    """One `kubectl get job --output json` payload, as the API server shapes it.

    A Job that has not finished carries its conditions with `status: "False"` —
    the field is PRESENT and negative rather than absent, so a reader that tests
    only for the type's presence would call a running gate terminal.
    """
    finished = state in {"Complete", "Failed"}
    return json.dumps(
        {
            "spec": {"suspend": state == "Suspended"},
            "status": {"conditions": [{"type": state, "status": str(finished)}]},
        },
    )


@dataclass(frozen=True, kw_only=True)
class _Invocation:
    kind: str
    argv: tuple[str, ...]
    stdin: str | None
    stream: bool


def _kind_of(*, argv: Sequence[str]) -> str:
    """Name the plumbing step one argv belongs to, for the assertions below."""
    if "rev-parse" in argv:
        return "read-tree"
    if "--delete" in argv or "delete" in argv:
        return "delete-ref" if "--delete" in argv else "delete-job"
    if "push" in argv:
        return "push-ref"
    if "create" in argv:
        return "submit-job"
    if "logs" in argv:
        return "stream-logs"
    return "get-job"


class _StubCluster:
    """The whole world the client can reach, canned.

    `job_states` is read one poll at a time and its LAST entry repeats, so
    `("Suspended", "Suspended", "Complete")` is a gate that finishes on the third
    poll and `("Suspended",)` is one that never finishes at all.
    """

    def __init__(
        self,
        *,
        job_states: Iterable[str] = ("Complete",),
        fails: Iterable[str] = (),
        never_runs: Iterable[str] = (),
        raises: str | None = None,
        refused_gets: int = 0,
        job_status_payload: str | None = None,
        job_status_payloads: Iterable[str] = (),
        created_payload: str | None = None,
        log_output: str = "",
    ) -> None:
        self._log_output = log_output
        self.calls: list[_Invocation] = []
        self.naps: list[float] = []
        self._states = list(job_states)
        self._fails = frozenset(fails)
        self._never_runs = frozenset(never_runs)
        self._raises = raises
        self._refused_gets = refused_gets
        self._job_status_payload = job_status_payload
        self._job_status_payloads = list(job_status_payloads)
        self._created_payload = created_payload

    def __call__(
        self,
        *,
        argv: list[str],
        cwd: Path,
        stdin: str | None = None,
        stream: bool = False,
    ) -> GateCommandOutcome:
        _ = cwd
        kind = _kind_of(argv=argv)
        self.calls.append(_Invocation(kind=kind, argv=tuple(argv), stdin=stdin, stream=stream))
        if kind == self._raises:
            raise RuntimeError("the host went away mid-run")
        if kind == "get-job" and self._refused_gets:
            self._refused_gets -= 1
            return Success(GateCommandResult(returncode=1, stdout="", stderr="get-job refused\n"))
        if kind in self._never_runs:
            return Failure(GateCommandNotRun(argv=tuple(argv), detail=f"{argv[0]} not on PATH"))
        if kind in self._fails:
            return Success(GateCommandResult(returncode=1, stdout="", stderr=f"{kind} refused\n"))
        return Success(GateCommandResult(returncode=0, stdout=self._stdout(kind=kind), stderr=""))

    def sleep(self, *, seconds: float) -> None:
        self.naps.append(seconds)

    @property
    def kinds(self) -> list[str]:
        return [call.kind for call in self.calls]

    def only(self, *, kind: str) -> _Invocation:
        matches = [call for call in self.calls if call.kind == kind]
        assert len(matches) == 1, f"expected exactly one {kind}, saw {len(matches)}"
        return matches[0]

    def _stdout(self, *, kind: str) -> str:
        if kind == "read-tree":
            return f"{_TREE}\n"
        if kind == "get-job":
            if self._job_status_payloads:
                return self._next_status_payload()
            return self._job_status_payload or _job_status(state=self._next_state())
        if kind == "submit-job":
            return self._created_payload if self._created_payload is not None else _CREATED
        if kind == "stream-logs":
            return self._log_output
        return ""

    def _next_state(self) -> str:
        if len(self._states) > 1:
            return self._states.pop(0)
        return self._states[0]

    def _next_status_payload(self) -> str:
        if len(self._job_status_payloads) > 1:
            return self._job_status_payloads.pop(0)
        return self._job_status_payloads[0]


# How many times the emulated hook below may re-enter the gate. The real thing is
# UNBOUNDED, and an unbounded recursion inside a test is a hang or a
# `RecursionError` rather than a failed assertion — what has to be readable here
# is the COUNT, so the emulation fires once and then stands down.
_HOOK_REENTRY_LIMIT = 1

# The one spelling that makes git run no hook for a push. Written out rather than
# imported from the client: it is the client's own private constant, and a test
# that imported it would assert the client agrees with itself.
_HOOKS_DISABLED = "core.hooksPath=/dev/null"


def _fires_the_pre_push_hook(*, argv: tuple[str, ...]) -> bool:
    """Whether git would run the repository's `pre-push` hook for this argv.

    git runs it for EVERY push, a `--delete` push included, unless the invocation
    points `core.hooksPath` at somewhere that holds no hook. Measured with git
    2.43.0 against a real hook and a real bare remote: a plain push fires it, a
    plain `--delete` push fires it, and neither fires when the invocation carries
    `-c core.hooksPath=/dev/null`.
    """
    return argv[0] == "git" and "push" in argv and _HOOKS_DISABLED not in argv


class _PrePushHookedHost:
    """The pushing repository's OWN `pre-push` hook, wrapped around the cluster.

    A delegated gate is only ever reached FROM this hook: `check-pre-push.sh`
    misses the green token and runs the client. So every push the client makes is
    a push made from inside the hook, and git's hook dispatch — not the client —
    is what decides whether that push starts a second gate. This stub is that
    dispatch, which is otherwise invisible at the seam: the runner answers the
    push exactly as the canned cluster would, and THEN, if git would have run the
    hook, runs the gate again, which is what the hook does.

    `nested_gates` is the whole measurement. Zero means a gate run from a hook
    started no second gate; anything else is the recursion, counted instead of
    waited out.
    """

    def __init__(self, *, cluster: _StubCluster) -> None:
        self.cluster = cluster
        self.nested_gates = 0

    def __call__(
        self,
        *,
        argv: list[str],
        cwd: Path,
        stdin: str | None = None,
        stream: bool = False,
    ) -> GateCommandOutcome:
        outcome = self.cluster(argv=argv, cwd=cwd, stdin=stdin, stream=stream)
        if _fires_the_pre_push_hook(argv=tuple(argv)) and self.nested_gates < _HOOK_REENTRY_LIMIT:
            self.nested_gates += 1
            _ = run_gate(request=_REQUEST, runner=self, sleeper=self.cluster.sleep)
        return outcome


def test_a_gate_run_from_a_pre_push_hook_publishes_its_refs_exactly_once() -> None:
    """The recursion, asserted as a count rather than waited out as a hang.

    Every push this client makes is made from inside the hook that started it, so
    a push that leaves hooks enabled delegates AGAIN: the hook has no way to tell
    the gate's own transport apart from a user's push, and neither level errors.
    Measured on the VPS 2026-10-12 after livespec-dev-tooling-qdqrau — a worktree
    push hung 48 minutes and was refused NO_VERDICT, and `GIT_TRACE` on a manual
    mirror push shows git starting `.git/hooks/pre-push` for the gates-mirror
    remote. The 2026-09-10 R4 proof called the client directly rather than from a
    hook, which is exactly why it could not see this.

    BOTH mirror pushes are covered by the publish count. The collection push is a
    push too, and git fires `pre-push` for a `--delete` just as it does for a
    publish, so a client that disabled hooks on only one of them still re-enters
    the gate — and the nested gate publishes a second time, which is what the
    count here reads.
    """
    cluster = _StubCluster()
    host = _PrePushHookedHost(cluster=cluster)

    outcome = run_gate(request=_REQUEST, runner=host, sleeper=cluster.sleep)

    assert is_successful(outcome)
    assert host.nested_gates == 0
    assert cluster.kinds.count("push-ref") == 1
    assert cluster.kinds.count("delete-ref") == 1


def test_the_emulated_hook_does_re_enter_the_gate_for_a_push_that_leaves_hooks_live() -> None:
    """The CONTROL — an instrument that cannot see the defect proves nothing.

    The zero above is read off `_PrePushHookedHost`, so a host that never
    re-entered would report the fixed shape for a client that still recursed, and
    the measurement would be a tautology. This drives that host with the spelling
    the client used BEFORE the fix — a plain `git push` of the gate refs — and
    asserts it starts a gate, which is what makes the zero a measurement.

    One push in, TWO pushes out: the one driven here and the one the gate it
    started made. That is the recursion in miniature, bounded at one re-entry
    rather than run to the hang it is on a host.
    """
    cluster = _StubCluster()
    host = _PrePushHookedHost(cluster=cluster)

    outcome = host(
        argv=["git", "push", "--atomic", _MIRROR, f"HEAD:{_GATE_REF}"],
        cwd=_REQUEST.repo_root,
    )

    assert is_successful(outcome)
    assert host.nested_gates == 1
    assert cluster.kinds.count("push-ref") == 2


def test_the_tree_under_test_is_pushed_to_the_mirror_at_a_ref_named_for_its_tree_hash() -> None:
    """One value names the pushed tree, the served ref, and later the token."""
    cluster = _StubCluster()
    outcome = run_gate(request=_REQUEST, runner=cluster, sleeper=cluster.sleep)
    assert is_successful(outcome)
    assert cluster.only(kind="read-tree").argv == ("git", "rev-parse", "HEAD^{tree}")
    assert cluster.only(kind="push-ref").argv == (
        "git",
        "-c",
        "core.hooksPath=/dev/null",
        "push",
        "--atomic",
        _MIRROR,
        f"HEAD:{_GATE_REF}",
        f"origin/master:{_GATE_REF}.base",
    )
    assert outcome.unwrap().tree_hash == _TREE


def test_the_mirror_push_runs_with_the_pushing_repositorys_hooks_disabled() -> None:
    """The mirror push is internal TRANSPORT, so it must fire no `pre-push` hook.

    git runs `pre-push` for EVERY push, and the only way this client is ever
    reached is from a repository's own `pre-push` hook: so a mirror push spelled
    with hooks live re-enters that hook, which delegates again, which pushes
    again — unbounded recursion that presents as a HANG rather than an error,
    because each level is doing exactly what it was asked to do. Measured on the
    VPS 2026-10-12: a worktree push sat 48 minutes and was refused NO_VERDICT,
    and `GIT_TRACE` on a manual mirror push shows git starting
    `.git/hooks/pre-push` for the gates-mirror remote.

    `core.hooksPath=/dev/null` is what suppresses it: `/dev/null` is not a
    directory, so git finds no hook file under it and runs none. Measured with
    git 2.43.0 — a plain push fires the hook, the `-c` form does not, and
    neither does a `--delete` push spelled the same way (a plain `--delete`
    DOES fire it, which is why the collection below is spelled identically).

    Asserted on the SPELLING because the recursion is invisible in the push's
    effect: the refs land either way, and what differs is only what else runs.
    """
    cluster = _StubCluster()
    _ = run_gate(request=_REQUEST, runner=cluster, sleeper=cluster.sleep)
    assert cluster.only(kind="push-ref").argv[:4] == (
        "git",
        "-c",
        "core.hooksPath=/dev/null",
        "push",
    )


def test_the_diff_base_rides_the_same_atomic_push_as_the_tree_under_test() -> None:
    """A gate ref without its `.base` companion is a gate with NO DIFF BASE.

    The mirror is created empty (`git init --bare`) and holds only what a gate
    push puts there, so `origin/master` is not something the pod can find on its
    own — and eight members of the aggregate judge `origin/master..HEAD` rather
    than a tree. `--atomic` is what makes the two refs one fact: without it a
    partial push lands the tree ref alone, the Job starts, and it fails on a base
    that was never pushed rather than on the code under test.

    Asserted as a whole argv above and as the INVARIANT here, because the two
    say different things: that one is the command, this one is why it cannot be
    two commands.
    """
    cluster = _StubCluster()
    _ = run_gate(request=_REQUEST, runner=cluster, sleeper=cluster.sleep)
    push = cluster.only(kind="push-ref")
    assert "--atomic" in push.argv
    assert push.argv[-2:] == (
        f"HEAD:{_GATE_REF}",
        f"origin/master:{_GATE_REF}.base",
    )


def test_the_rendered_job_is_submitted_to_the_cluster_on_stdin() -> None:
    """The manifest is submitted as rendered — this slice does not re-shape it."""
    cluster = _StubCluster()
    _ = run_gate(request=_REQUEST, runner=cluster, sleeper=cluster.sleep)
    submit = cluster.only(kind="submit-job")
    assert submit.stdin == _MANIFEST
    assert submit.argv == (
        GATES_WRAPPER,
        "kubectl",
        "--namespace",
        "gates",
        "create",
        "--output",
        "json",
        "--filename",
        "-",
    )


def test_every_later_step_names_the_job_the_cluster_assigned() -> None:
    """The name is an OUTPUT of the submit, so nothing may predict it.

    The manifest asks for a `generateName` — which is what lets a tree be
    re-gated inside a finished Job's TTL instead of being refused
    `AlreadyExists` — so the Job's name does not exist until the API server has
    made one. A client that kept deriving the old `gate-<repo>-<tree[:12]>` name
    would then poll, read and stream a DIFFERENT Job: inside that TTL window it
    is the PREVIOUS run's Job, which already carries a terminal condition, so a
    verdict about another run would come back immediately and nothing would
    error. The assigned name here deliberately shares nothing with the tree
    hash, so a derivation cannot accidentally match it.
    """
    assigned = "gate-widget-x9k2v"
    cluster = _StubCluster(created_payload=json.dumps({"metadata": {"name": assigned}}))

    outcome = run_gate(request=_REQUEST, runner=cluster, sleeper=cluster.sleep)

    assert is_successful(outcome)
    assert outcome.unwrap().job_name == assigned
    assert cluster.only(kind="get-job").argv[-4:] == ("job", assigned, "--output", "json")
    assert f"job/{assigned}" in cluster.only(kind="stream-logs").argv


def test_the_outcome_names_the_tree_the_created_job_reports() -> None:
    """The outcome's tree is the created Job's own label, not the tree that was asked for.

    A caller that compares the outcome's tree to the tree it staged can only catch a Job
    gating another tree if the outcome carries what the Job reports. Echoing the request
    back would make that comparison vacuous.
    """
    other = "c" * 40
    created = json.dumps({"metadata": {"name": _JOB, "labels": {"livespec.gate/tree-hash": other}}})
    cluster = _StubCluster(created_payload=created)
    request = dataclasses.replace(_REQUEST, tree_hash=_TREE)

    outcome = run_gate(request=request, runner=cluster, sleeper=cluster.sleep)

    assert is_successful(outcome)
    assert outcome.unwrap().reported_tree_hash == other
    assert outcome.unwrap().tree_hash == _TREE


def test_a_created_job_without_a_tree_label_reports_no_tree() -> None:
    """A submit answer that omits the label reports no tree; the request is never echoed back."""
    cluster = _StubCluster()
    request = dataclasses.replace(_REQUEST, tree_hash=_TREE)

    outcome = run_gate(request=request, runner=cluster, sleeper=cluster.sleep)

    assert is_successful(outcome)
    assert outcome.unwrap().reported_tree_hash == ""
    assert outcome.unwrap().tree_hash == _TREE


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param("not json at all", id="unreadable"),
        pytest.param(json.dumps({"metadata": {}}), id="no-name"),
        pytest.param(json.dumps({"metadata": {"name": ""}}), id="empty-name"),
    ],
)
def test_a_submit_that_names_no_job_fails_the_run_rather_than_guessing(*, payload: str) -> None:
    """Fail closed: a Job nothing can find is not a gate that can be judged.

    Falling back to the renderer's old derived name is the one thing this must
    not do — that name is precisely the value whose reuse made a re-gate
    impossible, and inside the TTL window it names the previous run's Job. The
    step is reported as incomplete instead, which reaches `GATE_NO_VERDICT` and
    refuses the push: the Job may well be running, and this run can no longer
    tell.
    """
    cluster = _StubCluster(created_payload=payload)

    outcome = run_gate(request=_REQUEST, runner=cluster, sleeper=cluster.sleep)

    assert isinstance(outcome, Failure)
    assert outcome.failure().step == "submit-gate-job"
    assert "get-job" not in cluster.kinds
    # The server may have created the Job despite a malformed reply. Without a
    # terminal observation, deleting its input would make that Job fail later.
    assert "delete-ref" not in cluster.kinds


def test_every_cluster_command_runs_through_the_credential_wrapper() -> None:
    """The INVARIANT, asserted over the whole run rather than one command at a time.

    Each cluster argv is asserted whole elsewhere; this says why none of them may
    be spelled any other way. A bare `kubectl` authenticates with whatever
    `KUBECONFIG` the pushing user's shell carries — on the VPS login user, none
    at all — and, worse, never reaches the wrapper's refresh-on-rejection path,
    so the FIRST call after a control-plane boot fails 401 with nothing to fix
    it. Neither symptom names the missing prefix, and a client that wrapped two
    of its three cluster commands would look entirely healthy until the gate ran
    on a host whose token had just been recreated.

    The `git` steps are deliberately NOT wrapped: the mirror is reached over ssh
    with the pushing user's own tailnet identity, which the gates credential has
    nothing to do with.
    """
    cluster = _StubCluster()
    _ = run_gate(request=_REQUEST, runner=cluster, sleeper=cluster.sleep)

    cluster_calls = [call for call in cluster.calls if "kubectl" in call.argv]
    assert [call.kind for call in cluster_calls] == ["submit-job", "get-job", "stream-logs"]
    assert all(call.argv[0] == GATES_WRAPPER for call in cluster_calls)
    assert not [call for call in cluster.calls if call.argv[0] == "kubectl"]
    assert all(call.argv[0] == "git" for call in cluster.calls if call not in cluster_calls)


def test_the_terminal_state_is_awaited_before_the_logs_are_streamed() -> None:
    """A gate is polled until it finishes; the wait is what bounds the return."""
    cluster = _StubCluster(job_states=("Suspended", "Suspended", "Complete"))
    outcome = run_gate(request=_REQUEST, runner=cluster, sleeper=cluster.sleep)
    assert is_successful(outcome)
    assert cluster.kinds == [
        "read-tree",
        "push-ref",
        "submit-job",
        "get-job",
        "get-job",
        "get-job",
        "stream-logs",
        "delete-ref",
    ]
    assert cluster.naps == [_REQUEST.poll_interval_seconds, _REQUEST.poll_interval_seconds]
    assert outcome.unwrap().terminal_state == "Complete"


def test_a_suspended_job_keeps_its_full_poll_budget_after_kueue_admits_it() -> None:
    """Admission polls are distinct from the Job's terminal-state poll budget."""
    cluster = _StubCluster(
        job_states=(
            "Suspended",
            "Suspended",
            "Suspended",
            "Active",
            "Active",
            "Active",
            "Complete",
        )
    )
    request = dataclasses.replace(_REQUEST, poll_timeout_seconds=30.0)

    outcome = run_gate(request=request, runner=cluster, sleeper=cluster.sleep)

    assert is_successful(outcome)
    assert cluster.kinds.count("get-job") == 7
    assert cluster.naps == [request.poll_interval_seconds] * 5


def test_the_admission_waiter_is_a_cohesive_module() -> None:
    """The polling concern is extracted from the client that submits and streams Jobs."""
    module_path = Path(__file__).parents[2] / "livespec_dev_tooling/gate_remote_admission.py"

    assert module_path.is_file()
    module = importlib.import_module("livespec_dev_tooling.gate_remote_admission")
    assert callable(module.await_terminal_state)


@pytest.mark.parametrize(
    "status",
    [
        {"spec": {"suspend": False}, "status": {}},
        {
            "spec": {"suspend": True},
            "status": {"conditions": [{"type": "Admitted", "status": "True"}]},
        },
        {"spec": {"suspend": True}, "status": {"startTime": "2026-11-07T15:00:00Z"}},
    ],
)
def test_kueue_admission_signals_start_the_terminal_poll_budget(
    *, status: dict[str, object]
) -> None:
    """Unsuspension, Kueue admission and a start time all release the terminal wait."""
    cluster = _StubCluster(job_status_payloads=(json.dumps(status), _job_status(state="Complete")))
    request = dataclasses.replace(_REQUEST, poll_timeout_seconds=10.0)

    outcome = run_gate(request=request, runner=cluster, sleeper=cluster.sleep)

    assert is_successful(outcome)
    assert cluster.kinds.count("get-job") == 2


def test_an_unadmitted_job_reports_its_admission_wait_bound() -> None:
    """The admission bound is a no-verdict result that names this Job."""
    cluster = _StubCluster(job_states=("Suspended",))
    request = dataclasses.replace(_REQUEST, admission_timeout_seconds=30.0)

    outcome = run_gate(request=request, runner=cluster, sleeper=cluster.sleep)

    assert isinstance(outcome, Failure)
    assert outcome.failure().detail == (
        f"admission wait for {_JOB} exceeded {request.admission_timeout_seconds:g}s without admission"
    )
    assert cluster.kinds.count("get-job") == 3


def test_a_stale_refused_read_does_not_replace_the_admission_wait_bound() -> None:
    """A later successful read showing the Job still suspended supersedes an earlier refusal."""
    cluster = _StubCluster(job_states=("Suspended",), refused_gets=1)
    request = dataclasses.replace(_REQUEST, admission_timeout_seconds=30.0)

    outcome = run_gate(request=request, runner=cluster, sleeper=cluster.sleep)

    assert isinstance(outcome, Failure)
    assert outcome.failure().detail == (
        f"admission wait for {_JOB} exceeded {request.admission_timeout_seconds:g}s without admission"
    )


def test_a_refused_job_read_is_retried_before_its_refs_are_collected() -> None:
    """A transient API refusal must not abandon the still-queued Job it created.

    The first get is refused, but the second reports completion inside the
    request's poll budget. The ref delete follows that terminal observation,
    rather than the refused read: otherwise the Job can later be admitted and
    fail its fetch-tree init container because its input disappeared.
    """
    cluster = _StubCluster(refused_gets=1)
    request = dataclasses.replace(_REQUEST, poll_timeout_seconds=20.0)

    outcome = run_gate(request=request, runner=cluster, sleeper=cluster.sleep)

    assert is_successful(outcome)
    assert cluster.kinds == [
        "read-tree",
        "push-ref",
        "submit-job",
        "get-job",
        "get-job",
        "stream-logs",
        "delete-ref",
    ]
    assert cluster.naps == [request.poll_interval_seconds]


def test_the_logs_are_streamed_rather_than_captured() -> None:
    """Capturing is exactly what would swallow the log the operator is owed.

    A captured child writes into this process instead of the terminal, so the
    property the log step exists for would be silently absent while every
    assertion about "the command ran" still passed.
    """
    cluster = _StubCluster()
    _ = run_gate(request=_REQUEST, runner=cluster, sleeper=cluster.sleep)
    logs = cluster.only(kind="stream-logs")
    assert logs.stream is True
    assert logs.argv == (
        GATES_WRAPPER,
        "kubectl",
        "--namespace",
        "gates",
        "logs",
        f"job/{_JOB}",
        "--all-containers",
        "--follow",
    )


def test_a_capturing_request_checksums_the_job_output_and_still_shows_it(
    *, capsys: pytest.CaptureFixture[str]
) -> None:
    """A commit-time replay must carry evidence of the output its Job produced."""
    output = "1 passed\n"
    cluster = _StubCluster(log_output=output)
    request = dataclasses.replace(_REQUEST, capture_output=True)

    outcome = run_gate(request=request, runner=cluster, sleeper=cluster.sleep)

    assert cluster.only(kind="stream-logs").stream is False
    assert outcome.unwrap().output_checksum == (
        f"sha256:{hashlib.sha256(output.encode('utf-8')).hexdigest()}"
    )
    assert capsys.readouterr().out == output


def test_a_streaming_request_retains_no_output_checksum() -> None:
    """An uncaptured stream reached the terminal only, so nothing can be checksummed."""
    cluster = _StubCluster(log_output="1 passed\n")

    outcome = run_gate(request=_REQUEST, runner=cluster, sleeper=cluster.sleep)

    assert outcome.unwrap().output_checksum == ""


def test_a_failed_gate_comes_back_as_a_raw_terminal_state_rather_than_a_verdict() -> None:
    """S7b decides pass from fail; this slice reports what the cluster said."""
    cluster = _StubCluster(job_states=("Failed",))
    outcome = run_gate(request=_REQUEST, runner=cluster, sleeper=cluster.sleep)
    assert is_successful(outcome)
    assert outcome.unwrap().terminal_state == "Failed"
    assert outcome.unwrap().job_name == _JOB


def test_a_non_zero_log_stream_exit_does_not_fail_the_run() -> None:
    """The log stream's exit code is OBSERVATIONAL — it echoes the gate's own."""
    cluster = _StubCluster(fails=("stream-logs",))
    outcome = run_gate(request=_REQUEST, runner=cluster, sleeper=cluster.sleep)
    assert is_successful(outcome)
    assert outcome.unwrap().logs_returncode == 1


def test_the_gate_ref_is_deleted_on_the_success_path() -> None:
    """The client is the FIRST collector; the mirror's sweep is the second.

    BOTH refs the push created are collected. The `.base` companion is the same
    kind of litter as the tree ref and grows at the same rate, so a delete that
    named only the tree ref would halve the collection while looking complete.

    The collection runs HOOKLESS for the same reason the publish does: git fires
    `pre-push` for a `--delete` push too, so a collection spelled with hooks live
    re-enters the hook that started this gate and delegates another one.
    """
    cluster = _StubCluster()
    _ = run_gate(request=_REQUEST, runner=cluster, sleeper=cluster.sleep)
    assert cluster.kinds[-1] == "delete-ref"
    assert cluster.only(kind="delete-ref").argv == (
        "git",
        "-c",
        "core.hooksPath=/dev/null",
        "push",
        "--delete",
        _MIRROR,
        _GATE_REF,
        f"{_GATE_REF}.base",
    )


def test_the_run_never_touches_the_tree_named_ref_a_concurrent_gate_might_hold() -> None:
    """The collision that cost TWO gates their verdicts, read off the argv.

    Both refs used to be named `refs/gates/<tree hash>` alone, and the
    collection above runs in a `finally` — so when two gates of one tree
    overlapped, whichever reached its cleanup first deleted the ref the other
    run's pod had not fetched yet. Measured 2026-10-19: two post-merge janitors
    gated master tree 228727afbe95 five seconds apart, the losing run's
    collection removed the winner's input, that pod died with `couldn't find
    remote ref`, and a correct merged tree read as a RED janitor.

    THE ABSENCE IS WHAT IS ASSERTED, not merely the presence of the per-run ref.
    A client that pushed its own ref and ALSO collected the tree-named one would
    satisfy every other assertion here and still reach into a concurrent run's
    input — and it would do so silently, because deleting a ref that is not
    there succeeds just as quietly as deleting one that is.
    """
    cluster = _StubCluster()

    _ = run_gate(request=_REQUEST, runner=cluster, sleeper=cluster.sleep)

    shared = f"refs/gates/{_TREE}"
    published = cluster.only(kind="push-ref").argv
    collected = cluster.only(kind="delete-ref").argv
    assert [arg for arg in collected if arg.startswith("refs/")] == [
        _GATE_REF,
        f"{_GATE_REF}.base",
    ]
    assert shared not in collected
    assert f"{shared}.base" not in collected
    assert f"HEAD:{shared}" not in published


def test_the_gate_ref_is_deleted_when_a_step_fails() -> None:
    """A refused submit still owns the ref it pushed a moment earlier."""
    cluster = _StubCluster(fails=("submit-job",))
    outcome = run_gate(request=_REQUEST, runner=cluster, sleeper=cluster.sleep)
    assert isinstance(outcome, Failure)
    assert outcome.failure().step == "submit-gate-job"
    assert outcome.failure().returncode == 1
    assert "delete-ref" in cluster.kinds


def test_the_gate_ref_is_retained_when_a_get_raises() -> None:
    """A Job may still run when its terminal state could not be read."""
    cluster = _StubCluster(raises="get-job")
    with pytest.raises(RuntimeError):
        _ = run_gate(request=_REQUEST, runner=cluster, sleeper=cluster.sleep)
    assert "delete-ref" not in cluster.kinds


def test_a_gate_that_never_reaches_a_terminal_state_deletes_its_job() -> None:
    """Giving up deletes the submitted Job before returning no verdict."""
    cluster = _StubCluster(job_states=("Suspended",))
    request = dataclasses.replace(
        _REQUEST, admission_timeout_seconds=30.0, poll_timeout_seconds=30.0
    )
    outcome = run_gate(request=request, runner=cluster, sleeper=cluster.sleep)
    assert isinstance(outcome, Failure)
    assert outcome.failure().step == "await-gate-terminal"
    assert outcome.failure().returncode is None
    assert cluster.kinds.count("get-job") == 3
    assert cluster.only(kind="delete-job").argv == (
        GATES_WRAPPER,
        "kubectl",
        "--namespace",
        "gates",
        "delete",
        "job",
        _JOB,
    )
    assert "delete-ref" not in cluster.kinds


def test_failed_abandoned_job_cleanup_is_reported_without_changing_no_verdict(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A cleanup fault is visible but does not invent a gate verdict."""
    cluster = _StubCluster(job_states=("Suspended",), fails=("delete-job",))
    request = dataclasses.replace(_REQUEST, poll_timeout_seconds=10.0)
    outcome = run_gate(request=request, runner=cluster, sleeper=cluster.sleep)
    assert isinstance(outcome, Failure)
    assert outcome.failure().step == "await-gate-terminal"
    assert (
        capsys.readouterr().err
        == f"could not delete abandoned gate Job {_JOB}: delete-job refused\n"
    )


def test_a_refused_private_sibling_secret_deletes_the_submitted_job() -> None:
    """A Job left unmountable by a failed Secret delivery is abandoned, so it is deleted."""
    cluster = _StubCluster(
        created_payload=json.dumps({"kind": "Job", "metadata": {"name": _JOB, "uid": "uid-1"}})
    )
    request = dataclasses.replace(
        _REQUEST,
        private_sibling_token="ghs_token",  # noqa: S106 — public fixture token.
        private_sibling_secret="gate-secret",  # noqa: S106 — public fixture secret name.
    )

    def runner(
        *, argv: list[str], cwd: Path, stdin: str | None = None, stream: bool = False
    ) -> GateCommandOutcome:
        if stdin is not None and '"kind": "Secret"' in stdin:
            return Success(GateCommandResult(returncode=1, stdout="", stderr="secret refused\n"))
        return cluster(argv=argv, cwd=cwd, stdin=stdin, stream=stream)

    outcome = run_gate(request=request, runner=runner, sleeper=cluster.sleep)
    assert isinstance(outcome, Failure)
    assert outcome.failure().step == "create-private-sibling-token-secret"
    assert cluster.only(kind="delete-job").argv == (
        GATES_WRAPPER,
        "kubectl",
        "--namespace",
        "gates",
        "delete",
        "job",
        _JOB,
    )
    assert "get-job" not in cluster.kinds


def test_a_job_the_cluster_will_not_report_on_is_retried_then_retains_its_ref() -> None:
    """A read refusal is retried, but never authorizes deleting a live Job's ref."""
    cluster = _StubCluster(fails=("get-job",))
    request = dataclasses.replace(
        _REQUEST, admission_timeout_seconds=20.0, poll_timeout_seconds=20.0
    )
    outcome = run_gate(request=request, runner=cluster, sleeper=cluster.sleep)
    assert isinstance(outcome, Failure)
    assert outcome.failure().step == "await-gate-terminal"
    assert outcome.failure().detail == "get-job refused\n"
    assert cluster.kinds.count("get-job") == 2
    assert "delete-ref" not in cluster.kinds


def test_a_refused_post_admission_read_exhausts_the_terminal_budget() -> None:
    """A refusal after admission remains the terminal wait's no-verdict result."""
    cluster = _StubCluster(job_states=("Active",))
    request = dataclasses.replace(_REQUEST, poll_timeout_seconds=20.0)
    read_count = 0

    def runner(
        *, argv: list[str], cwd: Path, stdin: str | None = None, stream: bool = False
    ) -> GateCommandOutcome:
        nonlocal read_count
        if _kind_of(argv=argv) == "get-job":
            read_count += 1
            if read_count == 2:
                return Success(
                    GateCommandResult(returncode=1, stdout="", stderr="get-job refused\n")
                )
        return cluster(argv=argv, cwd=cwd, stdin=stdin, stream=stream)

    outcome = run_gate(request=request, runner=runner, sleeper=cluster.sleep)

    assert isinstance(outcome, Failure)
    assert outcome.failure().detail == "get-job refused\n"


def test_an_unreadable_post_admission_status_ends_the_terminal_wait() -> None:
    """Admission does not let a malformed later Job status be guessed."""
    cluster = _StubCluster(
        job_status_payloads=(
            _job_status(state="Active"),
            "<html>gateway timeout</html>",
        )
    )

    outcome = run_gate(request=_REQUEST, runner=cluster, sleeper=cluster.sleep)

    assert isinstance(outcome, Failure)
    assert "unreadable job status" in outcome.failure().detail


def test_an_unreadable_job_status_fails_the_wait_rather_than_being_guessed() -> None:
    """Neither "finished" nor "still running" may be inferred from nonsense."""
    cluster = _StubCluster(job_status_payload="<html>gateway timeout</html>")
    outcome = run_gate(request=_REQUEST, runner=cluster, sleeper=cluster.sleep)
    assert isinstance(outcome, Failure)
    assert outcome.failure().step == "await-gate-terminal"
    assert "unreadable job status" in outcome.failure().detail
    assert "delete-ref" not in cluster.kinds


def test_the_run_fails_when_its_own_ref_cannot_be_deleted() -> None:
    """An orphan ref is reported rather than swallowed by a successful gate."""
    cluster = _StubCluster(fails=("delete-ref",))
    outcome = run_gate(request=_REQUEST, runner=cluster, sleeper=cluster.sleep)
    assert isinstance(outcome, Failure)
    assert outcome.failure().step == "delete-gate-ref"


def test_nothing_is_submitted_when_the_ref_could_not_be_pushed() -> None:
    """No ref was created, so there is nothing to collect and nothing to gate."""
    cluster = _StubCluster(fails=("push-ref",))
    outcome = run_gate(request=_REQUEST, runner=cluster, sleeper=cluster.sleep)
    assert isinstance(outcome, Failure)
    assert outcome.failure().step == "push-gate-ref"
    assert cluster.kinds == ["read-tree", "push-ref"]


def test_a_tree_hash_that_cannot_be_read_stops_before_the_mirror_is_touched() -> None:
    """`returncode=None` is what says there was no exit code at all."""
    cluster = _StubCluster(never_runs=("read-tree",))
    outcome = run_gate(request=_REQUEST, runner=cluster, sleeper=cluster.sleep)
    assert isinstance(outcome, Failure)
    assert outcome.failure().step == "read-tree-hash"
    assert outcome.failure().returncode is None
    assert cluster.kinds == ["read-tree"]
