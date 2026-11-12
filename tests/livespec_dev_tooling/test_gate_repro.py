"""The operator reproduction route: one diagnosed gate Job on a named lane.

`livespec_dev_tooling.gate_repro` submits ONE gate Job through the normal gate
client, onto the LocalQueue the operator names, with the renderer's stack
diagnostics switched on, and reports how that Job ended (livespec-dev-tooling-
pkmxgu, the reproduction route for livespec-dev-tooling-ddy5xu).

What these tests hold it to, through the same command seam the client uses:

- the rendered Job is put on the named queue with the diagnostics interval;
- a Job that reaches a terminal condition is reported with its name and its
  condition, and NO green token is written: a reproduction is a measurement of
  a node, never a pass a later push of that checkout could spend;
- a Job that reaches no terminal condition is reported as such, with the
  client's own reason, and the abandoned Job is deleted by the client.
"""

from __future__ import annotations

import json
from itertools import pairwise
from pathlib import Path

import pytest
from returns.result import Success

from livespec_dev_tooling.gate_remote_invocation import GateCommandOutcome, GateCommandResult
from livespec_dev_tooling.gate_repro import (
    REPRO_ENDED_COMPLETE,
    REPRO_ENDED_NO_TERMINAL_CONDITION,
    REPRO_QUEUE,
    main,
    run_repro_gate,
)

_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
_RENDERER = Path("/opt/gates/render-gate-job.sh")
_MANIFEST = "apiVersion: batch/v1\nkind: Job\nmetadata:\n  generateName: gate-widget-\n"
_JOB = "gate-widget-7f2qd"
_CREATED = json.dumps({"apiVersion": "batch/v1", "kind": "Job", "metadata": {"name": _JOB}})
_ADMITTED = json.dumps({"spec": {"suspend": False}, "status": {}})
_COMPLETE = json.dumps({"status": {"conditions": [{"type": "Complete", "status": "True"}]}})
_CLUSTER_REFUSAL = "the API server refused the read"

# Marker token -> step, tried IN ORDER; the first marker present in an argv
# names the step. `--git-common-dir` must precede `rev-parse`, because both
# identity probes and the tree read are spelled `git rev-parse`.
_STEP_MARKERS: tuple[tuple[str, str], ...] = (
    ("--git-common-dir", "read-common-dir"),
    ("rev-parse", "read-tree"),
    ("get-url", "read-origin"),
    ("create", "submit-job"),
    ("await-gate-terminal-watch", "read-job"),
    ("get", "read-job"),
)


class _StubWorld:
    """Every command one reproduction issues, canned.

    The Job is READ IN SEQUENCE: the first `kubectl get job` answers that the Job
    is admitted, and every later read answers `ending`, a Complete Job or a
    refusal. The client's terminal wait is the client's own business. It has
    been a poll and, briefly, a watch (livespec-dev-tooling-ie7fas, reverted by
    livespec-dev-tooling#4177). This suite asserts only how the reproduction
    reports the ending the client reads. Keying the ending to one wait's argv
    made the suite pass on its branch and fail on master once that revert
    landed. `answers` overrides any other named step.
    """

    def __init__(
        self,
        *,
        ending: GateCommandResult,
        answers: dict[str, GateCommandResult] | None = None,
    ) -> None:
        self.argvs: list[tuple[str, ...]] = []
        self._ending = ending
        self._answers = answers or {}
        self._job_reads = 0
        self._stdout = {
            "read-common-dir": ".git\n",
            "read-tree": f"{_TREE}\n",
            "read-origin": "git@github.com:acme/widget.git\n",
            "submit-job": _CREATED,
            "render": _MANIFEST,
            "other": "",
        }

    def _read_job(self) -> GateCommandResult:
        """Admitted on the first read, then the scenario's ending on every later one."""
        self._job_reads += 1
        admitted = GateCommandResult(returncode=0, stdout=_ADMITTED, stderr="")
        return admitted if self._job_reads == 1 else self._ending

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
        kind = "render" if argv[0] == str(_RENDERER) else "other"
        for marker, step in _STEP_MARKERS:
            if kind == "other" and marker in argv:
                kind = step
        if kind in self._answers:
            return Success(self._answers[kind])
        if kind == "read-job":
            return Success(self._read_job())
        return Success(GateCommandResult(returncode=0, stdout=self._stdout[kind], stderr=""))


def _no_sleep(*, seconds: float) -> None:
    """The poll wait, canned."""
    _ = seconds


def _completing() -> _StubWorld:
    return _StubWorld(ending=GateCommandResult(returncode=0, stdout=_COMPLETE, stderr=""))


def _never_ending() -> _StubWorld:
    return _StubWorld(ending=GateCommandResult(returncode=1, stdout="", stderr=_CLUSTER_REFUSAL))


def _repo(*, tmp_path: Path) -> Path:
    repo_root = tmp_path / "widget"
    repo_root.mkdir()
    return repo_root


def test_the_job_is_rendered_onto_the_named_queue_with_stack_diagnostics(*, tmp_path: Path) -> None:
    """The renderer is told the repro queue and the diagnostics interval, adjacent to each flag."""
    world = _completing()
    _ = run_repro_gate(
        repo_root=_repo(tmp_path=tmp_path),
        renderer=_RENDERER,
        queue=REPRO_QUEUE,
        stack_interval_seconds=300,
        runner=world,
        sleeper=_no_sleep,
    )

    render = next(argv for argv in world.argvs if argv[0] == str(_RENDERER))
    pairs = set(pairwise(render))
    facts = [
        ("--queue", REPRO_QUEUE) in pairs,
        ("--repro-stack-interval", "300") in pairs,
    ]
    assert all(facts), (facts, render)


def test_a_job_that_ends_is_reported_by_name_and_condition_with_no_green_token(
    *, tmp_path: Path
) -> None:
    """A terminal Job is the reproduction's answer, and nothing is written to the checkout."""
    world = _completing()
    outcome = run_repro_gate(
        repo_root=_repo(tmp_path=tmp_path),
        renderer=_RENDERER,
        queue=REPRO_QUEUE,
        stack_interval_seconds=300,
        runner=world,
        sleeper=_no_sleep,
    )

    token_writes = [argv for argv in world.argvs if "livespec_dev_tooling.green_token" in argv]
    facts = [
        outcome.ended == REPRO_ENDED_COMPLETE,
        outcome.job_name == _JOB,
        token_writes == [],
    ]
    assert all(facts), (facts, outcome)


def test_a_job_that_never_ends_is_reported_with_the_clients_reason_and_deleted(
    *, tmp_path: Path
) -> None:
    """No terminal condition is its own ending, carrying the step's own detail."""
    world = _never_ending()
    outcome = run_repro_gate(
        repo_root=_repo(tmp_path=tmp_path),
        renderer=_RENDERER,
        queue=REPRO_QUEUE,
        stack_interval_seconds=300,
        runner=world,
        sleeper=_no_sleep,
    )

    deletes = [argv for argv in world.argvs if "delete" in argv and _JOB in argv]
    facts = [
        outcome.ended == REPRO_ENDED_NO_TERMINAL_CONDITION,
        _CLUSTER_REFUSAL in outcome.detail,
        deletes != [],
    ]
    assert all(facts), (facts, outcome, deletes)


def test_main_reports_the_ending_and_exits_by_it(
    *, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The CLI prints one `gate-repro:` line naming the ending and exits 0 only on Complete."""
    repo_root = _repo(tmp_path=tmp_path)
    argv = ["--repo-root", str(repo_root), "--renderer", str(_RENDERER)]
    ended_code = main(argv=argv, runner=_completing(), sleeper=_no_sleep)
    hung_code = main(argv=argv, runner=_never_ending(), sleeper=_no_sleep)

    printed = capsys.readouterr().out
    facts = [
        ended_code == 0,
        hung_code != 0,
        f"gate-repro: ended={REPRO_ENDED_COMPLETE} job={_JOB}" in printed,
        f"gate-repro: ended={REPRO_ENDED_NO_TERMINAL_CONDITION}" in printed,
    ]
    assert all(facts), (facts, printed)


def test_a_job_the_renderer_refuses_is_never_submitted_and_names_that_step(
    *, tmp_path: Path
) -> None:
    """An assembly that fails submits nothing, and its ending names the render step."""
    refused = GateCommandResult(
        returncode=2, stdout="", stderr="FATAL: --queue 'X' is not a LocalQueue name"
    )
    world = _StubWorld(ending=refused, answers={"render": refused})
    outcome = run_repro_gate(
        repo_root=_repo(tmp_path=tmp_path),
        renderer=_RENDERER,
        queue="X",
        stack_interval_seconds=300,
        runner=world,
        sleeper=_no_sleep,
    )

    submits = [argv for argv in world.argvs if "create" in argv]
    facts = [
        outcome.ended == REPRO_ENDED_NO_TERMINAL_CONDITION,
        "render-gate-job" in outcome.detail,
        "is not a LocalQueue name" in outcome.detail,
        submits == [],
    ]
    assert all(facts), (facts, outcome)
