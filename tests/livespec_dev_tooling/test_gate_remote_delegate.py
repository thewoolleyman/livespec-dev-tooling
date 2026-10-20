"""The delegated gate's per-repo opt-in and its recipe wiring — R4.S7c.

Nothing here reaches a cluster, a mirror or a host. The client's only door to the
world is its `GateCommandRunner` seam, so a canned runner is the whole cluster;
the switch is read out of a `pyproject.toml` written into `tmp_path`; and the
pre-push recipe is exercised against stub `uv` and `just` executables on `PATH`
that record their argv and return a scripted exit code.

THE SUBJECT IS THE OFF PATH. The switch defaults OFF and this repository has not
opted in, so the behaviour that has to be proven is the one every push takes
today: green token first, and on a miss the local `just hook_gate=1 check`
aggregate, unchanged. The three recipe tests below assert that as a property of
what the script INVOKES rather than of what it prints — a fall-through that
quietly started delegating would still print something, just not this.

The ON path is asserted the same way, from the same script, so the pair reads as
one statement: the switch is the only thing that moves between them.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from returns.result import Failure, Success

from livespec_dev_tooling.gate_group_repair import (
    GATE_MODULE,
    GATES_GROUP_REEXEC_ENV,
    SG,
    GateGroupFacts,
)
from livespec_dev_tooling.gate_remote_delegate import (
    GATE_CHECK_SUITE_FALL_THROUGH,
    GATE_MIRROR_ROOT,
    GATE_RENDERER_IN_REPO,
    GATE_RENDERER_INSTALLED,
    declared_gate_check_suite,
    delegated_gate_enabled,
    gate_remote_request,
    main,
    resolve_renderer,
    run_delegated_gate,
)
from livespec_dev_tooling.gate_remote_invocation import GateCommandOutcome, GateCommandResult
from livespec_dev_tooling.gate_remote_verdict import GATE_NO_VERDICT, GATE_PASSED, GateVerdict

if TYPE_CHECKING:
    import pytest

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[2]
_PRE_PUSH = _REPO_ROOT / "scripts" / "just" / "check-pre-push.sh"

_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
_RENDERER = Path("/opt/gates/render-gate-job.sh")
_MANIFEST = "apiVersion: batch/v1\nkind: Job\nmetadata:\n  generateName: gate-widget-\n"
# The name the API SERVER assigns, in the shape its `generateName` suffix takes.
# Neither this suite nor the client predicts it: that it cannot be predicted is
# precisely what lets one tree be gated twice (livespec-dev-tooling-44fglo).
_JOB = "gate-widget-7f2qd"
_CREATED = json.dumps({"apiVersion": "batch/v1", "kind": "Job", "metadata": {"name": _JOB}})

# The canned clone's identity: an origin naming `widget` and a `--git-common-dir`
# answer of a primary checkout's own `.git`, which is what git prints there.
_ORIGIN_URL = "git@github.com:acme/widget.git"
_COMMON_DIR = ".git"

# The two names a delegated push has to keep apart, and the one shape that
# separates them. A linked worktree's DIRECTORY is its branch; the REPOSITORY it
# is a checkout of is what the mirror, the Job and the renderer are named after.
# Measured 2026-10-11 on the VPS: a push from the worktree below was refused
# because `proof-delegated-gate-green.git` is not a repository on the mirror.
_WORKTREE_DIR = "proof-delegated-gate-green"
_REPOSITORY = "livespec-dev-tooling"
_REPOSITORY_ORIGIN = f"git@github.com:thewoolleyman/{_REPOSITORY}.git"


# ---------------------------------------------------------------------------
# The switch — OFF unless the repository says exactly `true`
# ---------------------------------------------------------------------------


def _write_pyproject(*, repo_root: Path, body: str) -> None:
    _ = (repo_root / "pyproject.toml").write_text(body, encoding="utf-8")


def _a_readable_credential(*, root: Path) -> Path:
    """A stand-in gates kubeconfig this user can read — never a real credential.

    Eligibility is asserted on PRESENCE-AND-READABILITY rather than on a
    permission bit because this suite runs as root in the factory sandbox, where
    a mode-0000 fixture is still perfectly readable: a bit-based fixture would
    answer one way under root and the other under a login user.
    """
    credential = root / "gates.kubeconfig"
    _ = credential.write_text("kind: Config\napiVersion: v1\n", encoding="utf-8")
    return credential


def test_the_switch_is_off_when_nothing_declares_it(*, tmp_path: Path) -> None:
    """No `pyproject.toml` at all is the default every repository is at."""
    assert delegated_gate_enabled(repo_root=tmp_path) is False


def test_the_switch_is_off_when_the_block_omits_the_key(*, tmp_path: Path) -> None:
    """A configured repository that has not opted in is still OFF."""
    _write_pyproject(
        repo_root=tmp_path,
        body='[tool.livespec_dev_tooling]\nsource_trees = ["widget"]\n',
    )
    assert delegated_gate_enabled(repo_root=tmp_path) is False


def test_the_switch_is_off_when_declared_false(*, tmp_path: Path) -> None:
    """An explicit opt-out reads the same as an absent key."""
    _write_pyproject(
        repo_root=tmp_path,
        body="[tool.livespec_dev_tooling]\ndelegated_gate = false\n",
    )
    assert delegated_gate_enabled(repo_root=tmp_path) is False


def test_the_switch_is_on_only_when_declared_true(*, tmp_path: Path) -> None:
    """The one shape that delegates a gate."""
    _write_pyproject(
        repo_root=tmp_path,
        body="[tool.livespec_dev_tooling]\ndelegated_gate = true\n",
    )
    assert delegated_gate_enabled(repo_root=tmp_path) is True


def test_an_unreadable_switch_is_off(*, tmp_path: Path) -> None:
    """A non-boolean value must not delegate — it must fall back to local.

    The loader raises on it; this reader turns that into the strict answer,
    because the caller's alternative branch is the full local aggregate and a
    repository whose config cannot be read is one that should run its checks.
    """
    _write_pyproject(
        repo_root=tmp_path,
        body='[tool.livespec_dev_tooling]\ndelegated_gate = "yes"\n',
    )
    assert delegated_gate_enabled(repo_root=tmp_path) is False


def test_this_repository_has_opted_in() -> None:
    """The first repository to opt in — asserted of the real tree.

    This test was `..._has_not_opted_in` and asserted `False` until
    livespec-dev-tooling-pj7q4m; flipping it IS the deliberate review the
    rollout is owed, which is why it was written as an assertion about the real
    `pyproject.toml` rather than left implicit.

    The flip is only safe because the switch is no longer the whole answer: a
    push delegates only where the pushing user can read the gates credential, so
    this repository gates on the cluster from the VPS and locally everywhere
    else — this suite's own host included.
    """
    assert delegated_gate_enabled(repo_root=_REPO_ROOT) is True


# ---------------------------------------------------------------------------
# The pre-push recipe — what the fall-through actually invokes
# ---------------------------------------------------------------------------

_UV_STUB = """#!/usr/bin/env bash
printf 'uv %s\\n' "$*" >> "${STUB_LOG}"
case "$*" in
    *green_token*)                       exit "${GREEN_TOKEN_EXIT}" ;;
    *"gate_remote_delegate enabled")     exit "${SWITCH_EXIT}" ;;
    *"gate_remote_delegate run")         exit "${GATE_RUN_EXIT}" ;;
esac
exit 0
"""

_JUST_STUB = """#!/usr/bin/env bash
printf 'just %s\\n' "$*" >> "${STUB_LOG}"
if [ "$*" = "hook_gate=1 check" ]; then
    printf '%s\\n' "${CHECK_OUTPUT:-}"
    exit "${CHECK_EXIT:-0}"
fi
exit 0
"""

_GH_STUB = """#!/usr/bin/env bash
printf 'gh %s\\n' "$*" >> "${STUB_LOG}"
printf '%s\\n' "${GREEN_RUN:-17\\t0123456789abcdef}"
"""

_GIT_STUB = """#!/usr/bin/env bash
printf 'git %s\\n' "$*" >> "${STUB_LOG}"
if [ "$1 $2" = "worktree add" ]; then
    mkdir -p "$4"
fi
if [ "$1 $2" = "worktree remove" ]; then
    rm -rf "$4"
fi
"""


def _run_pre_push(
    *,
    tmp_path: Path,
    green_probe_exit: str = "1",
    switch_exit: str = "1",
    gate_run_exit: str = "0",
    check_exit: str = "0",
    check_output: str = "",
) -> tuple[int, str, list[str]]:
    """Run the real `check-pre-push.sh` against stub `uv` and `just`.

    Returns the script's exit code and every command it invoked, in order.
    """
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    for name, body in (
        ("uv", _UV_STUB),
        ("just", _JUST_STUB),
        ("gh", _GH_STUB),
        ("git", _GIT_STUB),
    ):
        stub = stub_dir / name
        _ = stub.write_text(body, encoding="utf-8")
        stub.chmod(0o755)
    log = tmp_path / "invocations.log"
    env = dict(os.environ)
    env.update(
        {
            "PATH": f"{stub_dir}{os.pathsep}{env['PATH']}",
            "STUB_LOG": str(log),
            "GREEN_TOKEN_EXIT": green_probe_exit,
            "SWITCH_EXIT": switch_exit,
            "GATE_RUN_EXIT": gate_run_exit,
            "CHECK_EXIT": check_exit,
            "CHECK_OUTPUT": check_output,
        }
    )
    completed = subprocess.run(
        ["bash", str(_PRE_PUSH)],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    invoked = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    return completed.returncode, completed.stdout, invoked


def test_the_switch_off_takes_the_local_aggregate_fall_through(*, tmp_path: Path) -> None:
    """A token miss with the switch OFF runs `just hook_gate=1 check`, as before.

    This is the acceptance property of the whole slice: with nothing opted in,
    the fall-through is byte-for-byte the local aggregate it has always been, and
    the delegated client is never asked to gate anything.
    """
    code, _stdout, invoked = _run_pre_push(tmp_path=tmp_path, switch_exit="1")

    assert code == 0
    assert "just hook_gate=1 check" in invoked
    assert not [line for line in invoked if "gate_remote_delegate run" in line]


def test_the_switch_on_delegates_instead_of_running_the_aggregate(*, tmp_path: Path) -> None:
    """With the switch ON the SAME fall-through reaches the client instead."""
    code, _stdout, invoked = _run_pre_push(tmp_path=tmp_path, switch_exit="0")

    assert code == 0
    assert [line for line in invoked if "gate_remote_delegate run" in line]
    assert not [line for line in invoked if line.startswith("just ")]


def test_a_refused_delegated_gate_refuses_the_push(*, tmp_path: Path) -> None:
    """The client's exit code IS the hook's — a refusal stops the push."""
    code, _stdout, _invoked = _run_pre_push(tmp_path=tmp_path, switch_exit="0", gate_run_exit="1")

    assert code == 1


def test_the_green_token_skip_path_is_untouched(*, tmp_path: Path) -> None:
    """A matching token still exits 0 without consulting the switch at all."""
    code, _stdout, invoked = _run_pre_push(tmp_path=tmp_path, green_probe_exit="0", switch_exit="0")

    assert code == 0
    assert not [line for line in invoked if "gate_remote_delegate" in line]
    assert not [line for line in invoked if line.startswith("just ")]


def test_a_failed_local_gate_reruns_exactly_its_failing_pytest_node_ids(*, tmp_path: Path) -> None:
    """A local pytest failure is replayed against the selected green master tree."""
    first = "tests/widget_test.py::test_one"
    second = "tests/widget_test.py::test_two[param]"

    code, _stdout, invoked = _run_pre_push(
        tmp_path=tmp_path,
        check_exit="1",
        check_output=f"FAILED {first} - host-only failure\\nFAILED {second} - host-only failure",
    )

    assert code == 1
    assert f"uv run pytest {first} {second}" in invoked, invoked


# ---------------------------------------------------------------------------
# Which renderer a run uses
# ---------------------------------------------------------------------------


def test_a_repository_carrying_the_renderer_uses_its_own(*, tmp_path: Path) -> None:
    """A checkout of this repository gates through the renderer it is changing."""
    in_repo = tmp_path / GATE_RENDERER_IN_REPO
    in_repo.parent.mkdir(parents=True)
    _ = in_repo.write_text("#!/usr/bin/env bash\n", encoding="utf-8")

    assert resolve_renderer(repo_root=tmp_path) == in_repo


def test_every_other_repository_uses_the_converged_host_copy(*, tmp_path: Path) -> None:
    """No in-tree renderer falls back to the path the converge installs."""
    assert resolve_renderer(repo_root=tmp_path) == GATE_RENDERER_INSTALLED


# ---------------------------------------------------------------------------
# Assembling the request, and running the gate behind it
# ---------------------------------------------------------------------------


# The two `kubectl get job --output json` payloads a run sees, in order: a Job
# that has reported no condition yet — what a real poll gets while Kueue is still
# admitting the gate — and then the one condition that means the aggregate exited
# zero inside the pod.
_JOB_ADMITTING = json.dumps({"status": {}})
_JOB_COMPLETE = json.dumps({"status": {"conditions": [{"type": "Complete", "status": "True"}]}})


# Marker token → step name, tried IN ORDER: the first marker present in an argv
# names the step, and `other` is what is left when none matches. The order is
# load-bearing — `--git-common-dir` must be matched BEFORE `rev-parse`, because
# the two identity probes and the tree read are all spelled `git rev-parse`.
_STEP_MARKERS: tuple[tuple[str, str], ...] = (
    ("--git-common-dir", "read-common-dir"),
    ("rev-parse", "read-tree"),
    ("get-url", "read-origin"),
    ("create", "submit-job"),
    ("get", "get-job"),
)


def _kind_of(*, argv: list[str]) -> str:
    """Name the step one argv belongs to, for the canned answers below.

    The renderer is recognised by its PATH rather than by a token, because it is
    the one step that is not a `git` or `kubectl` subcommand at all.
    """
    if argv[0] == str(_RENDERER):
        return "render"
    for marker, kind in _STEP_MARKERS:
        if marker in argv:
            return kind
    return "other"


class _StubWorld:
    """Every command a delegated push issues, canned.

    `refuse` names the steps that answer non-zero; everything else succeeds, so
    each refusal test differs from the happy path by exactly the commands it
    names. `origin` and `common_dir` are the clone's two identity answers, so a
    linked worktree is expressed as a `repo_root` whose directory name differs
    from the repository those two name.

    The polls are answered in sequence rather than from one canned payload, so a
    run has to WAIT at least once before it sees a verdict. That is the realistic
    shape — no gate is terminal on its first poll — and it is the only way the
    sleeper seam is reached at all.
    """

    def __init__(
        self,
        *,
        refuse: tuple[str, ...] = (),
        origin: str = _ORIGIN_URL,
        common_dir: str = _COMMON_DIR,
    ) -> None:
        self.argvs: list[tuple[str, ...]] = []
        self._refuse = refuse
        self._polls = 0
        self._stdout = {
            "read-tree": f"{_TREE}\n",
            "read-origin": f"{origin}\n",
            "read-common-dir": f"{common_dir}\n",
            "render": _MANIFEST,
            # `kubectl create --output json` answers with the created object,
            # which is where the Job's ASSIGNED name — the one the manifest's
            # `generateName` asked the API server for — comes from.
            "submit-job": _CREATED,
            "other": "",
        }

    def _poll(self) -> str:
        """Not admitted yet, then complete."""
        self._polls += 1
        return _JOB_ADMITTING if self._polls == 1 else _JOB_COMPLETE

    def __call__(
        self,
        *,
        argv: list[str],
        cwd: Path,
        stdin: str | None = None,
        stream: bool = False,
    ) -> GateCommandOutcome:
        _ = (cwd, stdin, stream)
        self.argvs.append(tuple(argv))
        kind = _kind_of(argv=argv)
        if kind in self._refuse:
            return Success(GateCommandResult(returncode=1, stdout="", stderr=f"{kind} refused"))
        stdout = self._poll() if kind == "get-job" else self._stdout[kind]
        return Success(GateCommandResult(returncode=0, stdout=stdout, stderr=""))


def _no_sleep(*, seconds: float) -> None:
    """The poll wait, canned — the run's only source of time."""
    _ = seconds


def test_the_request_is_assembled_out_of_the_repository(*, tmp_path: Path) -> None:
    """One tree hash names the mirror ref, the Job and the manifest."""
    repo_root = tmp_path / "widget"
    repo_root.mkdir()
    built = gate_remote_request(repo_root=repo_root, renderer=_RENDERER, runner=_StubWorld())

    assert isinstance(built, Success)
    request = built.unwrap()
    assert request.mirror_url == f"{GATE_MIRROR_ROOT}/widget.git"
    assert request.manifest == _MANIFEST


def test_the_renderer_is_told_the_tree_and_asked_for_no_job_name(*, tmp_path: Path) -> None:
    """The gated tree is passed; the Job's NAME is the cluster's to assign.

    A name used to be computed here and handed to the renderer so the run would
    wait on the name it asked for. That name was derived from the tree, and the
    rendered Job survives its own run for `ttlSecondsAfterFinished` — so for an
    hour after a tree's gate ended, every further gate of that tree was refused
    at submit with `AlreadyExists` and reported NO_VERDICT, the state reserved
    for a lost cluster (livespec-dev-tooling-44fglo). The manifest asks for a
    `generateName` now, and the client reads the assigned name back off its own
    submit — so a flag carrying a predicted name is not merely unused here, it
    is the defect, and its absence is asserted.
    """
    repo_root = tmp_path / "widget"
    repo_root.mkdir()
    runner = _StubWorld()
    _ = gate_remote_request(repo_root=repo_root, renderer=_RENDERER, runner=runner)

    render = next(argv for argv in runner.argvs if argv[0] == str(_RENDERER))
    assert _TREE in render
    assert "--job-name" not in render


# ---------------------------------------------------------------------------
# What the gate RUNS — the gated repository's own declaration
# ---------------------------------------------------------------------------


def test_a_repository_that_declares_nothing_gets_its_local_fall_through_recipe(
    *, tmp_path: Path
) -> None:
    """The documented default, and the one every repository but this one is at.

    It is the SHARED pre-push sequence a consumer's own local fall-through runs
    — the pack install the `pre-push` hook runs, the commit-refuse-hook install,
    and the ONE recipe that hook then calls, `check-pre-push` (freeze-driver
    rulings R92 and R100, 2026-10-17). It is never this repository's
    `warm-typecheck` nor its own `hook_gate=1 check`: `hook_gate` is a `just`
    variable only this justfile declares, and `just` refuses a command-line
    override of an undeclared variable, so R92's spelling killed every other
    consumer's Job before its aggregate ran. The sequence is pinned to
    `lefthook.yml` by tests.consumer.test_delegated_gate_declared_recipe_scenarios,
    which reads each step back out of the file that owns it; this is the
    unit-tier statement that the suite a repository declaring nothing gets IS
    that sequence, and that no entry in it carries a variable override.
    """
    declared = declared_gate_check_suite(repo_root=tmp_path)

    assert isinstance(declared, Success)
    assert declared.unwrap() == GATE_CHECK_SUITE_FALL_THROUGH
    assert GATE_CHECK_SUITE_FALL_THROUGH == (
        "install-worktree-pack",
        "install-commit-refuse-hooks",
        "check-pre-push",
    )
    assert [entry for entry in GATE_CHECK_SUITE_FALL_THROUGH if "=" in entry] == []


def test_a_declared_suite_is_read_in_its_declaration_order(*, tmp_path: Path) -> None:
    """Order is the gate's run order, so the declaration is a sequence."""
    _write_pyproject(
        repo_root=tmp_path,
        body=(
            "[tool.livespec_dev_tooling]\n"
            'gate_check_suite = ["install-pack", "hook_gate=1 check"]\n'
        ),
    )
    declared = declared_gate_check_suite(repo_root=tmp_path)

    assert isinstance(declared, Success)
    assert declared.unwrap() == ("install-pack", "hook_gate=1 check")


def test_an_empty_declaration_falls_through_rather_than_gating_on_nothing(
    *, tmp_path: Path
) -> None:
    """An empty array would be a Job that runs no check and reports green."""
    _write_pyproject(
        repo_root=tmp_path,
        body="[tool.livespec_dev_tooling]\ngate_check_suite = []\n",
    )
    declared = declared_gate_check_suite(repo_root=tmp_path)

    assert isinstance(declared, Success)
    assert declared.unwrap() == GATE_CHECK_SUITE_FALL_THROUGH


def test_an_unreadable_declaration_fails_the_step_rather_than_falling_back(
    *, tmp_path: Path
) -> None:
    """The OPPOSITE disposition from the opt-in above, and deliberately so.

    The opt-in resolves a doubt to "run the full local aggregate", which is
    strict. By the time the suite is read the run has already delegated, so the
    only thing a fallback could do is gate the tree on a recipe the repository
    did not declare — which the contract forbids in as many words.
    """
    _write_pyproject(
        repo_root=tmp_path,
        body='[tool.livespec_dev_tooling]\ngate_check_suite = "check"\n',
    )
    declared = declared_gate_check_suite(repo_root=tmp_path)

    assert isinstance(declared, Failure)
    assert declared.failure().step == "read-gate-check-suite"


def test_the_renderer_is_told_the_repositorys_own_check_suite(*, tmp_path: Path) -> None:
    """The flags the renderer turns into the pod's command, one per invocation.

    Repeated rather than one delimited value: a `just` invocation may carry
    spaces, so any single-argument spelling would need a separator the entries
    are then forbidden to contain.
    """
    repo_root = tmp_path / "widget"
    repo_root.mkdir()
    _write_pyproject(
        repo_root=repo_root,
        body='[tool.livespec_dev_tooling]\ngate_check_suite = ["verify", "hook_gate=1 check"]\n',
    )
    runner = _StubWorld()
    _ = gate_remote_request(repo_root=repo_root, renderer=_RENDERER, runner=runner)

    render = list(next(argv for argv in runner.argvs if argv[0] == str(_RENDERER)))
    flags = [render[index + 1] for index, arg in enumerate(render) if arg == "--check-suite"]
    assert flags == ["verify", "hook_gate=1 check"]


def test_an_unreadable_check_suite_submits_no_gate_at_all(*, tmp_path: Path) -> None:
    """Fail closed: nothing was decided, so the push is refused, not completed."""
    repo_root = tmp_path / "widget"
    repo_root.mkdir()
    _write_pyproject(
        repo_root=repo_root,
        body="[tool.livespec_dev_tooling]\ngate_check_suite = [1]\n",
    )
    verdict = run_delegated_gate(
        repo_root=repo_root, renderer=_RENDERER, runner=_StubWorld(), sleeper=_no_sleep
    )

    assert verdict.state == GATE_NO_VERDICT
    assert verdict.refuses_push is True
    assert "no gate was submitted" in verdict.detail


def test_this_repository_declares_the_four_recipes_its_gate_runs() -> None:
    """The first repository to declare one — asserted of the real tree.

    These four are livespec-dev-tooling's OWN. They lived in the shared
    `gate-job-template.yaml` as a constant until livespec-dev-tooling-saxz, and
    moving them HERE is what stops another repository's Job from running them.
    """
    declared = declared_gate_check_suite(repo_root=_REPO_ROOT)

    assert isinstance(declared, Success)
    assert declared.unwrap() == (
        "install-worktree-pack",
        "install-commit-refuse-hooks",
        "warm-typecheck",
        "hook_gate=1 check",
    )


def test_a_push_from_a_linked_worktree_publishes_to_the_repositorys_mirror(
    *, tmp_path: Path
) -> None:
    """The mirror is named after the REPOSITORY, not the directory pushed from.

    The gate mirror holds one bare repository per repository, so a worktree
    directory in the URL is a path that does not exist there. Measured
    2026-10-11 on the VPS: the first delegated push from a worktree was refused
    NO_VERDICT with `'proof-delegated-gate-green.git' does not appear to be a
    git repository`, and since the primary checkout refuses pushes outright, no
    delegated push could succeed at all.
    """
    repo_root = tmp_path / _WORKTREE_DIR
    repo_root.mkdir()
    built = gate_remote_request(
        repo_root=repo_root,
        renderer=_RENDERER,
        runner=_StubWorld(origin=_REPOSITORY_ORIGIN),
    )

    assert isinstance(built, Success)
    assert built.unwrap().mirror_url == f"{GATE_MIRROR_ROOT}/{_REPOSITORY}.git"


def test_one_repository_identity_covers_the_primary_checkout_and_a_worktree_alike(
    *, tmp_path: Path
) -> None:
    """Two directories, one repository — so one mirror and one rendered `--repo`.

    A directory-derived name made these two differ, which is a second identity
    for the same gate: the mirror a push reaches, and the name the Job carries
    in its labels and its in-cluster source URL, both followed the checkout
    directory rather than the repository. A linked worktree's directory is its
    BRANCH, so a push from one was refused with
    `'<branch>.git' does not appear to be a git repository`.

    The Job's own NAME is no longer part of that statement, because it is no
    longer derived from anything here: the manifest asks the API server for a
    `generateName` so that a re-gate of one tree is a new measurement rather
    than an `AlreadyExists` refusal. What has to be stable across the two
    checkouts is the REPOSITORY identity, which is what is asserted.
    """
    identities: list[tuple[str, str]] = []
    for directory in (_REPOSITORY, _WORKTREE_DIR):
        repo_root = tmp_path / directory
        repo_root.mkdir()
        runner = _StubWorld(origin=_REPOSITORY_ORIGIN)
        built = gate_remote_request(repo_root=repo_root, renderer=_RENDERER, runner=runner)
        assert isinstance(built, Success)
        render = next(argv for argv in runner.argvs if argv[0] == str(_RENDERER))
        identities.append((built.unwrap().mirror_url, render[render.index("--repo") + 1]))

    expected = (f"{GATE_MIRROR_ROOT}/{_REPOSITORY}.git", _REPOSITORY)
    assert identities == [expected, expected]


def test_each_gate_of_one_tree_is_given_its_own_mirror_ref(*, tmp_path: Path) -> None:
    """Two gates of ONE tree must not share the ref either of them deletes.

    The ref was `refs/gates/<tree hash>` for every gate of a tree, and the
    client deletes the refs it created in a `finally` — so when two gates of one
    tree overlapped, whichever reached its cleanup first deleted the ref the
    other run's pod had not fetched yet. Measured 2026-10-19: two post-merge
    janitors gated master tree 228727afbe95 five seconds apart, the losing run's
    collection removed the winner's input, that pod died with `couldn't find
    remote ref`, and a correct merged tree read as a RED janitor. ONE collision
    cost BOTH gates their verdicts (livespec-dev-tooling-44fglo).

    ASSERTED THROUGH THE RENDERER, because the ref has to be ONE value in TWO
    places: the client pushes to it and the POD fetches whatever the manifest
    was rendered with. A per-run ref the renderer was not told about would leave
    every pod looking for a ref nothing pushed.

    Two different checkout directories of ONE repository is the cheapest way to
    drive two assemblies of the same tree; the ref must differ even though the
    repository, the tree and therefore the mirror are identical.
    """
    rendered: list[str] = []
    for directory in (_REPOSITORY, _WORKTREE_DIR):
        repo_root = tmp_path / directory
        repo_root.mkdir()
        runner = _StubWorld(origin=_REPOSITORY_ORIGIN)
        built = gate_remote_request(repo_root=repo_root, renderer=_RENDERER, runner=runner)
        assert isinstance(built, Success)
        render = next(argv for argv in runner.argvs if argv[0] == str(_RENDERER))
        assert "--gate-ref" in render, "the renderer is told no per-run gate ref"
        rendered.append(render[render.index("--gate-ref") + 1])

    assert all(ref.startswith(f"refs/gates/{_TREE}-") for ref in rendered)
    assert rendered[0] != rendered[1]


def test_the_renderer_is_told_the_repository_not_the_worktree(*, tmp_path: Path) -> None:
    """`--repo` is the name the manifest itself carries, so it is passed too.

    The renderer DEFAULTS it to the basename of `--repo-root`, which is the same
    directory-derived name this fix exists to stop using. Leaving it off would
    therefore put the worktree's name back inside the Job — its labels and its
    in-cluster source URL — even with the mirror URL and the Job name correct.
    """
    repo_root = tmp_path / _WORKTREE_DIR
    repo_root.mkdir()
    runner = _StubWorld(origin=_REPOSITORY_ORIGIN)
    _ = gate_remote_request(repo_root=repo_root, renderer=_RENDERER, runner=runner)

    render = next(argv for argv in runner.argvs if argv[0] == str(_RENDERER))
    assert render[render.index("--repo") + 1] == _REPOSITORY


def test_a_clone_with_no_origin_is_named_by_its_primary_checkout(*, tmp_path: Path) -> None:
    """The fallback, and why it is not the checkout directory either.

    `--git-common-dir` answers the PRIMARY checkout's `.git` from inside a
    linked worktree, so its parent is the repository directory even there —
    which is exactly what the directory name is not.
    """
    repo_root = tmp_path / _WORKTREE_DIR
    repo_root.mkdir()
    built = gate_remote_request(
        repo_root=repo_root,
        renderer=_RENDERER,
        runner=_StubWorld(refuse=("read-origin",), common_dir=str(tmp_path / _REPOSITORY / ".git")),
    )

    assert isinstance(built, Success)
    assert built.unwrap().mirror_url == f"{GATE_MIRROR_ROOT}/{_REPOSITORY}.git"


def test_a_clone_that_names_no_repository_assembles_nothing(*, tmp_path: Path) -> None:
    """Fail closed rather than guess: a mirror is never named from a directory."""
    built = gate_remote_request(
        repo_root=tmp_path,
        renderer=_RENDERER,
        runner=_StubWorld(refuse=("read-origin", "read-common-dir")),
    )

    assert isinstance(built, Failure)
    assert built.failure().step == "derive-repo-name"


def test_a_tree_that_cannot_be_read_assembles_nothing(*, tmp_path: Path) -> None:
    """No tree hash means no ref, no Job and no request."""
    built = gate_remote_request(
        repo_root=tmp_path, renderer=_RENDERER, runner=_StubWorld(refuse=("read-tree",))
    )

    assert isinstance(built, Failure)
    assert built.failure().step == "read-tree-hash"


def test_a_manifest_that_cannot_be_rendered_assembles_nothing(*, tmp_path: Path) -> None:
    """A renderer that refuses is a gate that cannot be submitted."""
    built = gate_remote_request(
        repo_root=tmp_path, renderer=_RENDERER, runner=_StubWorld(refuse=("render",))
    )

    assert isinstance(built, Failure)
    assert built.failure().step == "render-gate-job"


def test_a_run_that_could_not_be_assembled_reaches_no_verdict(*, tmp_path: Path) -> None:
    """Nothing was submitted, so nothing was decided — and no token is written."""
    verdict = run_delegated_gate(
        repo_root=tmp_path,
        renderer=_RENDERER,
        runner=_StubWorld(refuse=("render",)),
        sleeper=_no_sleep,
    )

    assert verdict.state == GATE_NO_VERDICT
    assert verdict.token_written is False
    assert verdict.refuses_push is True
    assert "no gate was submitted" in verdict.detail


def test_a_complete_gate_over_the_pushed_tree_authorises_the_push(*, tmp_path: Path) -> None:
    """The whole delegated path, end to end, against a canned cluster."""
    repo_root = tmp_path / "widget"
    repo_root.mkdir()
    runner = _StubWorld()

    verdict = run_delegated_gate(
        repo_root=repo_root, renderer=_RENDERER, runner=runner, sleeper=_no_sleep
    )

    assert verdict.state == GATE_PASSED
    assert verdict.token_written is True
    assert verdict.refuses_push is False
    # The push carries the mirror URL and BOTH refspecs — the tree under test
    # and the `.base` companion the pod fetches as its diff base — so the tail
    # is read rather than a fixed slice, which `--atomic` would have shifted.
    # The push is found by "a git that pushes" rather than by a fixed prefix,
    # because the client sets `core.hooksPath` on that invocation: a `git push`
    # from inside a `pre-push` hook fires that same hook and delegates again.
    #
    # The REF is matched by its `refs/gates/<tree hash>` stem rather than
    # literally: it carries a per-run component, so that two gates of one tree
    # cannot delete each other's input, and which component this run minted is
    # not what this scenario is about. That the ref pushed here is the ref the
    # POD was told to fetch is asserted end to end in
    # tests.consumer.test_delegated_pre_push_gate_scenarios.
    mirror, published, base = next(
        argv for argv in runner.argvs if argv[0] == "git" and "push" in argv
    )[-3:]
    assert mirror == f"{GATE_MIRROR_ROOT}/widget.git"
    assert published.startswith(f"HEAD:refs/gates/{_TREE}")
    assert base == f"origin/master:{published.removeprefix('HEAD:')}.base"
    # Two polls: the run waited through a Job that had not been admitted yet
    # rather than reading a verdict off the first answer it got.
    assert len([argv for argv in runner.argvs if "get" in argv]) == 2


# ---------------------------------------------------------------------------
# The entry point the recipe calls
# ---------------------------------------------------------------------------


def test_enabled_exits_non_zero_for_a_repository_that_has_not_opted_in(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The exit code the recipe branches on, from the default repository."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["gate_remote_delegate", "enabled"])

    assert main() == 1


def test_enabled_exits_zero_for_a_repository_that_has(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same probe, on the far side of the opt-in — from an ELIGIBLE host.

    The credential has to be there for the answer to be yes, which is the half
    the switch alone never said: `delegated_gate` travels with the code and
    describes no host.
    """
    _write_pyproject(
        repo_root=tmp_path,
        body="[tool.livespec_dev_tooling]\ndelegated_gate = true\n",
    )
    monkeypatch.setenv("GATES_KUBECONFIG", str(_a_readable_credential(root=tmp_path)))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["gate_remote_delegate", "enabled"])

    assert main() == 0


def test_an_opted_in_repository_on_a_host_without_the_credential_gates_locally(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The host-eligibility rule, from the two things the recipe reads.

    THE EXIT CODE IS THE FALL-THROUGH. The recipe branches on it and on nothing
    else, so a non-zero answer here IS "run the local `just check` aggregate",
    and the paired recipe test above proves that branch invokes
    `just hook_gate=1 check` and submits no gate Job.

    THE LINE IS THE OTHER HALF, and it is why this is not simply the switch-off
    path. Without it a push from a sandbox or a fresh laptop in an opted-in
    repository would silently run a different gate than the maintainer
    configured — silently being the whole problem, because a locally-gated push
    and a cluster-gated one look identical afterwards.

    Before this, an opted-in repository delegated from EVERY host that cloned
    it: the push then failed closed on a host with no credential, blocking the
    factory with no statement of why.
    """
    _write_pyproject(
        repo_root=tmp_path,
        body="[tool.livespec_dev_tooling]\ndelegated_gate = true\n",
    )
    monkeypatch.setenv("GATES_KUBECONFIG", str(tmp_path / "absent.kubeconfig"))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["gate_remote_delegate", "enabled"])

    code = main()

    assert code == 1
    assert "gating locally" in capsys.readouterr().err


def test_a_repository_that_has_not_opted_in_says_nothing_about_the_credential(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The default repository's probe stays SILENT, credential or no credential.

    Every repository is here today, so this is the path a push actually takes:
    the host's eligibility is not its business and must not be narrated at it.
    """
    monkeypatch.setenv("GATES_KUBECONFIG", str(tmp_path / "absent.kubeconfig"))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["gate_remote_delegate", "enabled"])

    code = main()

    assert code == 1
    assert capsys.readouterr().err == ""


# ---------------------------------------------------------------------------
# The ELIGIBLE host whose pushing process lacks the credential's group
# ---------------------------------------------------------------------------

# The group the VPS credential is owned by. Named here rather than inlined
# because every assertion below is about whether this exact name reaches the
# operator.
_GATES_GROUP = "gates-client"


def _facts_at(*, monkeypatch: pytest.MonkeyPatch, facts: GateGroupFacts) -> None:
    """Make the host-and-process probes answer `facts`.

    Injected at the FACTS seam rather than built on disk because the state the
    repair exists for CANNOT be built here: it needs a credential the current
    process cannot read, and this suite runs as root in the factory sandbox,
    where a mode-0000 file is still perfectly readable.
    """

    def _answer() -> GateGroupFacts:
        return facts

    monkeypatch.setattr("livespec_dev_tooling.gate_group_repair.gate_group_facts", _answer)


_ELIGIBLE_BUT_UNGROUPED = GateGroupFacts(
    readable=False,
    owning_group=_GATES_GROUP,
    user_is_a_member=True,
    process_carries_it=False,
)

# A genuinely ineligible host: the credential is there, and the group database
# does not list this user in the group that owns it. `sg` would refuse them, so
# there is nothing to repair.
_NOT_IN_THE_GROUP_DATABASE = GateGroupFacts(
    readable=False,
    owning_group=_GATES_GROUP,
    user_is_a_member=False,
    process_carries_it=False,
)


def _an_opted_in_repo_on_an_unreadable_credential(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An opted-in repository whose gates kubeconfig this process cannot read.

    The kubeconfig path is pointed at an absent file so the readability probe
    the client calls DIRECTLY agrees with the injected record: the two have to
    say the same thing, or the fixture is asserting against a state no host has.
    """
    _write_pyproject(
        repo_root=tmp_path,
        body="[tool.livespec_dev_tooling]\ndelegated_gate = true\n",
    )
    monkeypatch.setenv("GATES_KUBECONFIG", str(tmp_path / "unreadable.kubeconfig"))
    monkeypatch.chdir(tmp_path)


def test_an_eligible_host_whose_process_lacks_the_group_is_told_the_gate_runs_under_it(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The defect, from the probe the recipe branches on — measured on the VPS 2026-10-18.

    There `/etc/ci-runner/gates.kubeconfig` is `0640 root:gates-client` and the
    group database lists the login user in `gates-client`, so the HOST is
    eligible — but a login session started before that membership was granted
    does not carry the group. The read failed, this probe exited non-zero, and
    the push ran the full local aggregate (about 17 minutes for
    livespec-orchestrator-beads-fabro) behind the ordinary `GATED_LOCALLY` line.
    Nothing said the host was eligible and nothing named the remedy; the same
    push under `/usr/bin/sg gates-client` reached a verdict in 95 seconds.

    So the probe now answers YES, because the host IS eligible, and says which
    group the gate will run under. ONE line: this is a git hook's output, and
    the operator reads it in the middle of a push.
    """
    _an_opted_in_repo_on_an_unreadable_credential(tmp_path=tmp_path, monkeypatch=monkeypatch)
    _facts_at(monkeypatch=monkeypatch, facts=_ELIGIBLE_BUT_UNGROUPED)
    monkeypatch.setattr(sys, "argv", ["gate_remote_delegate", "enabled"])

    code = main()
    printed = capsys.readouterr().err

    assert code == 0
    assert len(printed.strip().splitlines()) == 1
    assert _GATES_GROUP in printed
    assert "will run under" in printed
    assert "gating locally" not in printed


def test_a_host_the_group_database_does_not_vouch_for_keeps_its_current_output(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The two shapes the repair must NOT reach, each left exactly as it was.

    An ABSENT credential is the factory-sandbox and fresh-laptop case. A
    credential whose owning group the group database does not list this user in
    is a genuinely ineligible host — `sg` would refuse them there, so there is
    nothing to repair and nothing new to say. Both keep the `GATED_LOCALLY`
    line and the non-zero exit that IS the local fall-through.
    """
    _an_opted_in_repo_on_an_unreadable_credential(tmp_path=tmp_path, monkeypatch=monkeypatch)
    monkeypatch.setattr(sys, "argv", ["gate_remote_delegate", "enabled"])

    absent = main()
    on_absent = capsys.readouterr().err
    _facts_at(monkeypatch=monkeypatch, facts=_NOT_IN_THE_GROUP_DATABASE)
    ineligible = main()
    on_ineligible = capsys.readouterr().err

    assert (absent, ineligible) == (1, 1)
    assert "gating locally" in on_absent
    assert "gating locally" in on_ineligible
    assert "will run under" not in on_absent
    assert "will run under" not in on_ineligible


def _sg_at(monkeypatch: pytest.MonkeyPatch, *, resolved: str | None) -> None:
    """Make `shutil.which` answer for `/usr/bin/sg` the way the host under test would."""

    def _answer(_program: str) -> str | None:
        return resolved

    monkeypatch.setattr(shutil, "which", _answer)


def _a_local_gate_that_would_pass(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    """Stub the gate this client runs HERE, and record whether it was reached.

    It answers PASSED rather than raising, so a test that expected a
    re-execution fails on the exit status it asserted — a genuine assertion
    about the behaviour — rather than on a stub's own exception.
    """
    reached: list[object] = []

    def _passed(**kwargs: object) -> GateVerdict:
        reached.append(kwargs)
        return GateVerdict(state=GATE_PASSED, detail="gated here", token_written=True)

    monkeypatch.setattr("livespec_dev_tooling.gate_remote_delegate.run_delegated_gate", _passed)
    return reached


def _spawns_recorded(
    monkeypatch: pytest.MonkeyPatch, *, returncode: int
) -> list[dict[str, object]]:
    """Record every re-execution spawn, answering `returncode` to each.

    ONE recorder for the tests that expect a spawn and the tests that must prove
    none happened: a recorder written separately for the second kind is never
    called, so it asserts its own absence with a body nothing ever ran.
    """
    spawned: list[dict[str, object]] = []

    def _fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        spawned.append({**kwargs, "argv": argv})
        return subprocess.CompletedProcess(args=argv, returncode=returncode)

    monkeypatch.setattr(subprocess, "run", _fake_run)
    return spawned


def test_run_re_executes_itself_under_sg_and_answers_with_that_runs_exit_status(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The repair itself: the gate re-runs under the group and the CHILD's verdict is the answer.

    The re-executed run is the one that reads the kubeconfig and submits the
    Job, so its exit status is the push's — this process must not also gate
    locally, and must not translate the child's answer into one of its own.

    ONCE is asserted two ways, because a re-executing gate that could re-execute
    again is an infinite push: exactly one spawn happens, and the child is handed
    the sentinel naming the group that was tried, which is what makes it able to
    tell that it IS the re-executed run.
    """
    _an_opted_in_repo_on_an_unreadable_credential(tmp_path=tmp_path, monkeypatch=monkeypatch)
    _facts_at(monkeypatch=monkeypatch, facts=_ELIGIBLE_BUT_UNGROUPED)
    monkeypatch.delenv(GATES_GROUP_REEXEC_ENV, raising=False)
    monkeypatch.setattr(sys, "argv", ["gate_remote_delegate", "run"])
    gated_here = _a_local_gate_that_would_pass(monkeypatch)
    _sg_at(monkeypatch, resolved=SG)
    spawned = _spawns_recorded(monkeypatch, returncode=7)

    assert main() == 7
    assert gated_here == []
    assert len(spawned) == 1
    assert spawned[0]["argv"] == [SG, _GATES_GROUP, "-c", f"{sys.executable} -m {GATE_MODULE} run"]
    handed = spawned[0]["env"]
    assert isinstance(handed, dict)
    assert handed[GATES_GROUP_REEXEC_ENV] == _GATES_GROUP


def test_a_group_re_execution_that_decides_nothing_refuses_the_push_and_names_the_remedy(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The two ways the repair can fail, and the one thing neither may do: fall through.

    A re-execution that NEVER STARTED (`sg` is not installed on this host) and
    one that ran and STILL could not read the credential are different events,
    and both leave this process holding no verdict. Falling through to the local
    aggregate here is precisely the defect being fixed, one layer out: the push
    would complete on a gate nobody chose, after the operator was told the gate
    would run under a group. So each refuses, and each names the group that was
    tried and the remedy — a fresh login session — because the diagnostic is the
    only thing standing between the operator and the 17-minute local run.
    """
    _an_opted_in_repo_on_an_unreadable_credential(tmp_path=tmp_path, monkeypatch=monkeypatch)
    _facts_at(monkeypatch=monkeypatch, facts=_ELIGIBLE_BUT_UNGROUPED)
    monkeypatch.delenv(GATES_GROUP_REEXEC_ENV, raising=False)
    monkeypatch.setattr(sys, "argv", ["gate_remote_delegate", "run"])
    gated_here = _a_local_gate_that_would_pass(monkeypatch)
    _sg_at(monkeypatch, resolved=None)

    never_started = main()
    on_never_started = capsys.readouterr().err
    monkeypatch.setenv(GATES_GROUP_REEXEC_ENV, _GATES_GROUP)
    still_unreadable = main()
    on_still_unreadable = capsys.readouterr().err

    assert (never_started, still_unreadable) == (1, 1)
    assert gated_here == []
    for printed in (on_never_started, on_still_unreadable):
        assert GATE_NO_VERDICT in printed
        assert _GATES_GROUP in printed
        assert "fresh login session" in printed


def test_a_credential_this_process_can_read_never_reaches_sg_on_either_command(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The path every delegating push already took, left untouched by the repair.

    A process that can read the credential is missing no group, so there is
    nothing to repair and nothing to narrate: `enabled` exits zero in silence
    and `run` gates through the client it always did. The spawn recorder is the
    load-bearing assertion — a repair that fired here would re-run every
    delegated push inside a second process for no reason.
    """
    _write_pyproject(
        repo_root=tmp_path,
        body="[tool.livespec_dev_tooling]\ndelegated_gate = true\n",
    )
    monkeypatch.setenv("GATES_KUBECONFIG", str(_a_readable_credential(root=tmp_path)))
    monkeypatch.delenv(GATES_GROUP_REEXEC_ENV, raising=False)
    monkeypatch.chdir(tmp_path)
    gated_here = _a_local_gate_that_would_pass(monkeypatch)
    _sg_at(monkeypatch, resolved=SG)
    spawned = _spawns_recorded(monkeypatch, returncode=0)

    monkeypatch.setattr(sys, "argv", ["gate_remote_delegate", "enabled"])
    assert main() == 0
    assert capsys.readouterr().err == ""

    monkeypatch.setattr(sys, "argv", ["gate_remote_delegate", "run"])
    assert main() == 0
    assert len(gated_here) == 1
    assert spawned == []


def test_run_exits_zero_only_on_a_verdict_that_authorises_the_push(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A passed gate whose token was written completes the push."""

    def _passed(**kwargs: object) -> GateVerdict:
        _ = kwargs
        return GateVerdict(state=GATE_PASSED, detail="gated", token_written=True)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["gate_remote_delegate", "run"])
    monkeypatch.setattr("livespec_dev_tooling.gate_remote_delegate.run_delegated_gate", _passed)

    assert main() == 0


def test_run_exits_non_zero_on_every_other_verdict(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A gate that decided nothing refuses the push, exactly as S7b does."""

    def _undecided(**kwargs: object) -> GateVerdict:
        _ = kwargs
        return GateVerdict(state=GATE_NO_VERDICT, detail="nothing decided", token_written=False)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["gate_remote_delegate", "run"])
    monkeypatch.setattr("livespec_dev_tooling.gate_remote_delegate.run_delegated_gate", _undecided)

    assert main() == 1
