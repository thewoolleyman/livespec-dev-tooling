"""The reproduction route's image and node parameters.

`run_repro_gate` and `main` hand the renderer `--image` (a reference by digest)
and `--node` (one gate node) beside the queue and diagnostics flags, and leave
both out when the operator names neither (livespec-dev-tooling-cwrg3v).
"""

from __future__ import annotations

import json
from itertools import pairwise
from pathlib import Path

from returns.result import Success

from livespec_dev_tooling.gate_remote_invocation import GateCommandOutcome, GateCommandResult
from livespec_dev_tooling.gate_repro import REPRO_QUEUE, main, run_repro_gate

_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
_RENDERER = Path("/opt/gates/render-gate-job.sh")
_DIGEST = "ghcr.io/livespec-ai/livespec-fabro-sandbox@sha256:" + "a" * 64
_JOB = "gate-widget-7f2qd"
_STDOUT = {
    "read-common-dir": "/work/widget/.git\n",
    "read-tree": _TREE + "\n",
    "read-origin": "git@github.com:livespec-ai/widget.git\n",
    "render": "apiVersion: batch/v1\nkind: Job\nmetadata:\n  generateName: gate-widget-\n",
    "submit-job": json.dumps({"metadata": {"name": _JOB}}),
}
_COMPLETE = json.dumps({"status": {"conditions": [{"type": "Complete", "status": "True"}]}})
_ADMITTED = json.dumps({"spec": {"suspend": False}, "status": {}})


class _World:
    """Every command one reproduction issues, canned; records each argv."""

    def __init__(self) -> None:
        self.argvs: list[tuple[str, ...]] = []
        self._reads = 0

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
        if argv[0] == str(_RENDERER):
            return Success(GateCommandResult(returncode=0, stdout=_STDOUT["render"], stderr=""))
        for marker, step in (
            ("--git-common-dir", "read-common-dir"),
            ("rev-parse", "read-tree"),
            ("get-url", "read-origin"),
            ("create", "submit-job"),
        ):
            if marker in argv:
                return Success(GateCommandResult(returncode=0, stdout=_STDOUT[step], stderr=""))
        self._reads += 1
        body = _ADMITTED if self._reads == 1 else _COMPLETE
        return Success(GateCommandResult(returncode=0, stdout=body, stderr=""))


def _no_sleep(*, seconds: float) -> None:
    _ = seconds


def _render_argv(*, world: _World) -> tuple[str, ...]:
    return next(argv for argv in world.argvs if argv[0] == str(_RENDERER))


def test_image_and_node_reach_the_renderer_beside_the_queue(*, tmp_path: Path) -> None:
    """Named image and node become adjacent `--image` and `--node` renderer flags."""
    repo_root = tmp_path / "widget"
    repo_root.mkdir()
    world = _World()
    _ = run_repro_gate(
        repo_root=repo_root,
        renderer=_RENDERER,
        queue=REPRO_QUEUE,
        stack_interval_seconds=300,
        image=_DIGEST,
        node="hp-xubuntu",
        runner=world,
        sleeper=_no_sleep,
    )

    pairs = set(pairwise(_render_argv(world=world)))
    facts = [("--image", _DIGEST) in pairs, ("--node", "hp-xubuntu") in pairs]
    assert all(facts), (facts, _render_argv(world=world))


def test_neither_flag_is_rendered_when_the_operator_names_neither(*, tmp_path: Path) -> None:
    """The default route carries no `--image` and no `--node`, so it is the pkmxgu route."""
    repo_root = tmp_path / "widget"
    repo_root.mkdir()
    world = _World()
    _ = run_repro_gate(
        repo_root=repo_root,
        renderer=_RENDERER,
        queue=REPRO_QUEUE,
        stack_interval_seconds=300,
        image=None,
        node=None,
        runner=world,
        sleeper=_no_sleep,
    )

    render = _render_argv(world=world)
    assert "--image" not in render, render
    assert "--node" not in render, render


def test_main_parses_image_and_node_flags(*, tmp_path: Path) -> None:
    """The CLI's `--image` and `--node` arguments reach the renderer."""
    repo_root = tmp_path / "widget"
    repo_root.mkdir()
    world = _World()
    code = main(
        argv=[
            "--repo-root",
            str(repo_root),
            "--renderer",
            str(_RENDERER),
            "--image",
            _DIGEST,
            "--node",
            "gmktec-xubuntu",
        ],
        runner=world,
        sleeper=_no_sleep,
    )

    pairs = set(pairwise(_render_argv(world=world)))
    facts = [code == 0, ("--image", _DIGEST) in pairs, ("--node", "gmktec-xubuntu") in pairs]
    assert all(facts), (facts, _render_argv(world=world))
