"""Tests for how `.claude/settings.json` registers the two agent-session guards.

Per work-item livespec-dev-tooling-skcqrx, the `PreToolUse` Bash guard and
the `SubagentStop` guard run on the checkout's own virtualenv interpreter
when it is executable, so a tool call does not pay a `mise` plus `uv`
cold start, and fall back to `mise exec -- uv run --no-sync python -m`
when it is not. The guards' decisions are unchanged.

Each test runs the REGISTERED command string through `sh`, exactly as the
harness does, with fake `mise` and `uv` executables first on `PATH` that
record every start. The fake virtualenv interpreter and the fake `mise`
both hand over to the real test interpreter, so the guard itself runs.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import cast

import pytest

__all__: list[str] = []

_SETTINGS = Path(__file__).resolve().parents[3] / ".claude" / "settings.json"
_PRETOOLUSE_MODULE = "livespec_dev_tooling.agent_hooks.pretooluse_background_guard"
_SUBAGENT_STOP_MODULE = "livespec_dev_tooling.agent_hooks.subagent_stop_guard"


def _registered_command(*, event: str, module: str) -> str:
    settings = cast("dict[str, object]", json.loads(_SETTINGS.read_text(encoding="utf-8")))
    hooks = cast("dict[str, list[dict[str, list[dict[str, str]]]]]", settings["hooks"])
    commands = [
        hook["command"]
        for group in hooks[event]
        for hook in group["hooks"]
        if module in hook["command"]
    ]
    assert len(commands) == 1
    return commands[0]


def _executable(*, path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(f"#!/bin/sh\n{body}", encoding="utf-8")
    path.chmod(0o755)


def _fake_toolchain(*, root: Path, with_venv: bool) -> tuple[Path, dict[str, str]]:
    """Return (project dir, env): fake mise/uv on PATH; optional fake venv python."""
    project = root / "project"
    project.mkdir()
    log = root / "starts.log"
    bin_dir = root / "bin"
    _executable(
        path=bin_dir / "mise",
        body=(
            f'echo "mise $*" >> "{log}"\n'
            'while [ "$1" != python ]; do shift; done\nshift\n'
            f'exec "{sys.executable}" "$@"\n'
        ),
    )
    _executable(path=bin_dir / "uv", body=f'echo "uv $*" >> "{log}"\nexit 1\n')
    if with_venv:
        _executable(
            path=project / ".venv" / "bin" / "python",
            body=f'echo "venv-python $*" >> "{log}"\nexec "{sys.executable}" "$@"\n',
        )
    env = {key: value for key, value in os.environ.items() if not key.startswith("COVERAGE_")}
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    env["CLAUDE_PROJECT_DIR"] = str(project)
    return project, env


def _starts(*, root: Path) -> list[str]:
    log = root / "starts.log"
    return log.read_text(encoding="utf-8").splitlines() if log.exists() else []


def _run_registered(
    *, command: str, env: dict[str, str], cwd: Path, stdin: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/bin/sh", "-c", command],
        env=env,
        cwd=cwd,
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
    )


def _refusal_without_timestamp(*, stderr: str) -> dict[str, object]:
    """The guard's refusal event minus its wall-clock `timestamp`, the one field that varies."""
    event = cast("dict[str, object]", json.loads(stderr.strip().splitlines()[-1]))
    _ = event.pop("timestamp")
    return event


@pytest.mark.parametrize(
    ("event", "module"),
    [
        pytest.param("PreToolUse", _PRETOOLUSE_MODULE, id="pretooluse"),
        pytest.param("SubagentStop", _SUBAGENT_STOP_MODULE, id="subagent-stop"),
    ],
)
def test_a_present_virtualenv_python_runs_the_guard_and_starts_no_mise_or_uv(
    tmp_path: Path, event: str, module: str
) -> None:
    project, env = _fake_toolchain(root=tmp_path, with_venv=True)
    command = _registered_command(event=event, module=module)
    result = _run_registered(command=command, env=env, cwd=project, stdin="{}")
    assert result.returncode == 0, result.stderr
    assert _starts(root=tmp_path) == [f"venv-python -m {module}"]


@pytest.mark.parametrize(
    ("event", "module"),
    [
        pytest.param("PreToolUse", _PRETOOLUSE_MODULE, id="pretooluse"),
        pytest.param("SubagentStop", _SUBAGENT_STOP_MODULE, id="subagent-stop"),
    ],
)
def test_an_absent_virtualenv_python_falls_back_to_mise_exec_uv_run(
    tmp_path: Path, event: str, module: str
) -> None:
    project, env = _fake_toolchain(root=tmp_path, with_venv=False)
    command = _registered_command(event=event, module=module)
    result = _run_registered(command=command, env=env, cwd=project, stdin="{}")
    assert result.returncode == 0, result.stderr
    assert _starts(root=tmp_path) == [f"mise exec -- uv run --no-sync python -m {module}"]


@pytest.mark.integration
def test_the_foreground_hook_running_git_refusal_text_is_the_same_on_either_interpreter(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = subprocess.run(["git", "init", "--quiet"], cwd=repo, check=True)
    hook = repo / ".git" / "hooks" / "pre-commit"
    _ = hook.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    hook.chmod(0o755)
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}})
    command = _registered_command(event="PreToolUse", module=_PRETOOLUSE_MODULE)
    results: list[subprocess.CompletedProcess[str]] = []
    for with_venv in (True, False):
        root = tmp_path / f"venv-{with_venv}"
        root.mkdir()
        _, env = _fake_toolchain(root=root, with_venv=with_venv)
        results.append(_run_registered(command=command, env=env, cwd=repo, stdin=payload))
    with_venv_result, without_venv_result = results
    assert with_venv_result.returncode == 2
    assert without_venv_result.returncode == 2
    assert "gate-start" in with_venv_result.stderr
    assert _refusal_without_timestamp(stderr=with_venv_result.stderr) == (
        _refusal_without_timestamp(stderr=without_venv_result.stderr)
    )
