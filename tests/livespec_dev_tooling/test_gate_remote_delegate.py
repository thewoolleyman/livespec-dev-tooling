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
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from returns.result import Failure, Success

from livespec_dev_tooling.gate_remote_delegate import (
    GATE_MIRROR_ROOT,
    GATE_RENDERER_IN_REPO,
    GATE_RENDERER_INSTALLED,
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
_MANIFEST = "apiVersion: batch/v1\nkind: Job\nmetadata:\n  name: gate-widget-4b825dc642cb\n"


# ---------------------------------------------------------------------------
# The switch — OFF unless the repository says exactly `true`
# ---------------------------------------------------------------------------


def _write_pyproject(*, repo_root: Path, body: str) -> None:
    _ = (repo_root / "pyproject.toml").write_text(body, encoding="utf-8")


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


def test_this_repository_has_not_opted_in() -> None:
    """Default OFF until the slice is proven — asserted of the real tree.

    The rollout is per repository and this slice wires the CLIENT, not the
    opt-in. A future commit that flips this repository has to change this test
    deliberately, which is the review the flip is owed.
    """
    assert delegated_gate_enabled(repo_root=_REPO_ROOT) is False


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
exit 0
"""


def _run_pre_push(
    *,
    tmp_path: Path,
    green_probe_exit: str = "1",
    switch_exit: str = "1",
    gate_run_exit: str = "0",
) -> tuple[int, list[str]]:
    """Run the real `check-pre-push.sh` against stub `uv` and `just`.

    Returns the script's exit code and every command it invoked, in order.
    """
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    for name, body in (("uv", _UV_STUB), ("just", _JUST_STUB)):
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
    return completed.returncode, invoked


def test_the_switch_off_takes_the_local_aggregate_fall_through(*, tmp_path: Path) -> None:
    """A token miss with the switch OFF runs `just hook_gate=1 check`, as before.

    This is the acceptance property of the whole slice: with nothing opted in,
    the fall-through is byte-for-byte the local aggregate it has always been, and
    the delegated client is never asked to gate anything.
    """
    code, invoked = _run_pre_push(tmp_path=tmp_path, switch_exit="1")

    assert code == 0
    assert "just hook_gate=1 check" in invoked
    assert not [line for line in invoked if "gate_remote_delegate run" in line]


def test_the_switch_on_delegates_instead_of_running_the_aggregate(*, tmp_path: Path) -> None:
    """With the switch ON the SAME fall-through reaches the client instead."""
    code, invoked = _run_pre_push(tmp_path=tmp_path, switch_exit="0")

    assert code == 0
    assert [line for line in invoked if "gate_remote_delegate run" in line]
    assert not [line for line in invoked if line.startswith("just ")]


def test_a_refused_delegated_gate_refuses_the_push(*, tmp_path: Path) -> None:
    """The client's exit code IS the hook's — a refusal stops the push."""
    code, _invoked = _run_pre_push(tmp_path=tmp_path, switch_exit="0", gate_run_exit="1")

    assert code == 1


def test_the_green_token_skip_path_is_untouched(*, tmp_path: Path) -> None:
    """A matching token still exits 0 without consulting the switch at all."""
    code, invoked = _run_pre_push(tmp_path=tmp_path, green_probe_exit="0", switch_exit="0")

    assert code == 0
    assert not [line for line in invoked if "gate_remote_delegate" in line]
    assert not [line for line in invoked if line.startswith("just ")]


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


def _kind_of(*, argv: list[str]) -> str:
    """Name the step one argv belongs to, for the canned answers below."""
    if "rev-parse" in argv:
        return "read-tree"
    if argv[0] == str(_RENDERER):
        return "render"
    if "get" in argv:
        return "get-job"
    return "other"


_STDOUT = {
    "read-tree": f"{_TREE}\n",
    "render": _MANIFEST,
    "other": "",
}


class _StubWorld:
    """Every command a delegated push issues, canned.

    `refuse` names the ONE step that answers non-zero; everything else succeeds,
    so each refusal test differs from the happy path by exactly one command.

    The polls are answered in sequence rather than from one canned payload, so a
    run has to WAIT at least once before it sees a verdict. That is the realistic
    shape — no gate is terminal on its first poll — and it is the only way the
    sleeper seam is reached at all.
    """

    def __init__(self, *, refuse: str | None = None) -> None:
        self.argvs: list[tuple[str, ...]] = []
        self._refuse = refuse
        self._polls = 0

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
        if kind == self._refuse:
            return Success(GateCommandResult(returncode=1, stdout="", stderr=f"{kind} refused"))
        stdout = self._poll() if kind == "get-job" else _STDOUT[kind]
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
    assert request.job_name == f"gate-widget-{_TREE[:12]}"
    assert request.manifest == _MANIFEST


def test_the_renderer_is_told_the_name_the_run_will_wait_on(*, tmp_path: Path) -> None:
    """The job name is passed, not parsed back out of the rendered YAML."""
    repo_root = tmp_path / "widget"
    repo_root.mkdir()
    runner = _StubWorld()
    _ = gate_remote_request(repo_root=repo_root, renderer=_RENDERER, runner=runner)

    render = next(argv for argv in runner.argvs if argv[0] == str(_RENDERER))
    assert "--job-name" in render
    assert f"gate-widget-{_TREE[:12]}" in render
    assert _TREE in render


def test_a_tree_that_cannot_be_read_assembles_nothing(*, tmp_path: Path) -> None:
    """No tree hash means no ref, no Job and no request."""
    built = gate_remote_request(
        repo_root=tmp_path, renderer=_RENDERER, runner=_StubWorld(refuse="read-tree")
    )

    assert isinstance(built, Failure)
    assert built.failure().step == "read-tree-hash"


def test_a_manifest_that_cannot_be_rendered_assembles_nothing(*, tmp_path: Path) -> None:
    """A renderer that refuses is a gate that cannot be submitted."""
    built = gate_remote_request(
        repo_root=tmp_path, renderer=_RENDERER, runner=_StubWorld(refuse="render")
    )

    assert isinstance(built, Failure)
    assert built.failure().step == "render-gate-job"


def test_a_run_that_could_not_be_assembled_reaches_no_verdict(*, tmp_path: Path) -> None:
    """Nothing was submitted, so nothing was decided — and no token is written."""
    verdict = run_delegated_gate(
        repo_root=tmp_path,
        renderer=_RENDERER,
        runner=_StubWorld(refuse="render"),
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
    assert (
        f"{GATE_MIRROR_ROOT}/widget.git",
        f"HEAD:refs/gates/{_TREE}",
        f"origin/master:refs/gates/{_TREE}.base",
    ) == (next(argv for argv in runner.argvs if argv[:2] == ("git", "push"))[-3:])
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
    """The same probe, on the far side of the opt-in."""
    _write_pyproject(
        repo_root=tmp_path,
        body="[tool.livespec_dev_tooling]\ndelegated_gate = true\n",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["gate_remote_delegate", "enabled"])

    assert main() == 0


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
