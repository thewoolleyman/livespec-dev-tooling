"""The reproduction route's command form.

`main` takes a command after `--` and hands the renderer one `--repro-command`
flag carrying that command base64-encoded, so no quoting survives to the
renderer; with no command the flag is absent and the Job runs the repository's
whole gate (livespec-dev-tooling-z66x7t).
"""

from __future__ import annotations

import base64
import json
import shlex
from itertools import pairwise
from pathlib import Path

from returns.result import Success

from livespec_dev_tooling.gate_remote_invocation import GateCommandOutcome, GateCommandResult
from livespec_dev_tooling.gate_repro import main

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


def test_a_command_after_the_separator_reaches_the_renderer_encoded(*, tmp_path: Path) -> None:
    """The words after `--` are rendered as one base64 `--repro-command` flag."""
    repo_root = tmp_path / "widget"
    repo_root.mkdir()
    world = _World()
    command = ["pytest", "tests/test_a.py::test_one", "-k", "a b"]
    code = main(
        argv=["--repo-root", str(repo_root), "--renderer", str(_RENDERER), "--", *command],
        runner=world,
        sleeper=_no_sleep,
    )

    render = _render_argv(world=world)
    flag = dict(pairwise(render)).get("--repro-command", "")
    decoded = base64.b64decode(flag).decode("utf-8") if flag else ""
    facts = [code == 0, decoded == shlex.join(command)]
    assert all(facts), (facts, render)


def test_no_command_flag_is_rendered_without_a_command(*, tmp_path: Path) -> None:
    """With nothing after `--` the Job runs the whole gate, so the flag is absent."""
    repo_root = tmp_path / "widget"
    repo_root.mkdir()
    world = _World()
    code = main(
        argv=["--repo-root", str(repo_root), "--renderer", str(_RENDERER)],
        runner=world,
        sleeper=_no_sleep,
    )

    render = _render_argv(world=world)
    assert code == 0, code
    assert "--repro-command" not in render, render
