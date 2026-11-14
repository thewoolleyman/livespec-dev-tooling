"""Behaviour tests for the pack member `worktree_pack/local-gate-scope.sh`.

The script is how a gate launch uses the host's gate memory slice, as the
local gate concurrency limit in SPECIFICATION/non-functional-requirements.md
requires in its Gate memory slice paragraph. Where the login's service manager
loads `local-gate.slice` and a probe scope can be created there, the command
runs in a transient scope in that slice with OOMPolicy=continue and, through
`choom`, an oom_score_adj of 500. Anywhere else it runs unchanged.

No case touches the real service manager. `uname`, `systemctl`,
`systemd-run` and `choom` are fakes on a private `PATH` that record their
argv to a log. The fake `systemd-run` and `choom` then run what follows
their `--`, the way the real ones exec it. The only real tools on that `PATH`
are `bash`, `grep` and `env`.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from livespec_dev_tooling.install_worktree_pack import (
    CANONICAL_WORKTREE_JUST_BODY,
    WORKTREE_PACK_FILES,
)

__all__: list[str] = []

_SCRIPT_NAME = "local-gate-scope.sh"
_REPO_ROOT = Path(__file__).resolve().parents[3]
_SLICE = "local-gate.slice"
_SCOPED_PREFIX = (
    "systemd-run --user --scope --quiet --collect " f"--slice={_SLICE} -p OOMPolicy=continue --"
)
_PROBE = f"systemd-run --user --scope --quiet --collect --slice={_SLICE} -- true"
_REAL_TOOLS: tuple[str, ...] = ("bash", "grep", "env")

_FAKE_UNAME = '#!/bin/sh\necho "uname $*" >> "$FAKE_LOG"\necho "${FAKE_OS:-Linux}"\n'
_FAKE_SYSTEMCTL = (
    '#!/bin/sh\necho "systemctl $*" >> "$FAKE_LOG"\necho "${FAKE_LOAD_STATE:-loaded}"\n'
)
_FAKE_SYSTEMD_RUN = """#!/bin/bash
echo "systemd-run $*" >> "$FAKE_LOG"
if [ "${@: -1}" = "true" ] && [ "${@: -2:1}" = "--" ]; then
  exit "${FAKE_PROBE_RC:-0}"
fi
while [ "$#" -gt 0 ] && [ "$1" != "--" ]; do shift; done
shift
exec "$@"
"""
_FAKE_CHOOM = """#!/bin/bash
echo "choom $*" >> "$FAKE_LOG"
while [ "$#" -gt 0 ] && [ "$1" != "--" ]; do shift; done
shift
exec "$@"
"""
_FAKE_GATE = """#!/bin/bash
echo "gate-cmd $* scope=${LIVESPEC_LOCAL_GATE_SCOPE:-unset}" >> "$FAKE_LOG"
exit "${FAKE_GATE_RC:-0}"
"""


def _pack_entry() -> tuple[str, bool]:
    """The pack's body and executable bit for the script, or a failed assertion."""
    entries = [entry for entry in WORKTREE_PACK_FILES if entry.name == _SCRIPT_NAME]
    assert len(entries) == 1, f"the worktree pack must ship exactly one {_SCRIPT_NAME}"
    return entries[0].body, entries[0].executable


def _write_tool(*, directory: Path, name: str, body: str) -> None:
    path = directory / name
    _ = path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def _world(*, tmp_path: Path, fakes: tuple[str, ...]) -> tuple[Path, Path]:
    """Install the script and a private PATH; return (script, bin dir)."""
    body, _ = _pack_entry()
    script = tmp_path / "dev-tooling" / _SCRIPT_NAME
    script.parent.mkdir(parents=True)
    _ = script.write_text(body, encoding="utf-8")
    script.chmod(0o755)
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for tool in _REAL_TOOLS:
        real = shutil.which(tool)
        assert real is not None, f"the test needs a real {tool}"
        (bindir / tool).symlink_to(real)
    bodies = {
        "uname": _FAKE_UNAME,
        "systemctl": _FAKE_SYSTEMCTL,
        "systemd-run": _FAKE_SYSTEMD_RUN,
        "choom": _FAKE_CHOOM,
    }
    for name in fakes:
        _write_tool(directory=bindir, name=name, body=bodies[name])
    _write_tool(directory=bindir, name="gate-cmd", body=_FAKE_GATE)
    return script, bindir


def _run(
    *,
    tmp_path: Path,
    script: Path,
    bindir: Path,
    extra_env: dict[str, str],
    cgroup: str = "0::/user.slice/user-1000.slice/session-1.scope\n",
) -> tuple[int, list[str]]:
    """Run the script on `gate-cmd a b`; return (exit code, logged lines)."""
    log = tmp_path / "calls.log"
    cgroup_file = tmp_path / "cgroup"
    _ = cgroup_file.write_text(cgroup, encoding="utf-8")
    env = {
        "PATH": str(bindir),
        "HOME": str(tmp_path),
        "FAKE_LOG": str(log),
        "LIVESPEC_LOCAL_GATE_CGROUP_FILE": str(cgroup_file),
        **extra_env,
    }
    completed = subprocess.run(
        [str(bindir / "bash"), str(script), "gate-cmd", "a", "b"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    lines = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    return completed.returncode, lines


_ALL_FAKES: tuple[str, ...] = ("uname", "systemctl", "systemd-run", "choom")


def test_the_pack_ships_the_script_executable() -> None:
    body, executable = _pack_entry()
    assert executable
    assert body.startswith("#!/usr/bin/env bash\n")


def test_gate_start_launches_the_runner_through_the_script() -> None:
    _ = _pack_entry()
    recipe = CANONICAL_WORKTREE_JUST_BODY.split("\ngate-start *args:\n", 1)[1].split("\n\n", 1)[0]
    assert [line.strip() for line in recipe.splitlines()] == [
        './dev-tooling/local-gate-scope.sh ./dev-tooling/gate-run.sh start "$@"'
    ]


def test_this_repository_check_recipe_runs_itself_through_the_script() -> None:
    _ = _pack_entry()
    justfile = (_REPO_ROOT / "justfile").read_text(encoding="utf-8")
    recipe = justfile.split("\ncheck:\n", 1)[1].split("\n\n", 1)[0]
    # The aggregate itself runs through the script, so every exported caller
    # variable (hook_gate, token_match, skip) reaches it unchanged.
    assert 'dev-tooling/local-gate-scope.sh scripts/just/check.sh "${targets[@]}"' in recipe


def test_a_host_with_the_slice_runs_the_command_in_a_scope_with_a_raised_oom_score(
    tmp_path: Path,
) -> None:
    script, bindir = _world(tmp_path=tmp_path, fakes=_ALL_FAKES)
    code, lines = _run(tmp_path=tmp_path, script=script, bindir=bindir, extra_env={})
    assert code == 0
    assert _PROBE in lines
    assert f"{_SCOPED_PREFIX} choom -n 500 -- gate-cmd a b" in lines
    assert "choom -n 500 -- gate-cmd a b" in lines
    assert lines[-1] == "gate-cmd a b scope=1"


def test_without_choom_the_scope_still_runs_the_command(tmp_path: Path) -> None:
    script, bindir = _world(tmp_path=tmp_path, fakes=("uname", "systemctl", "systemd-run"))
    code, lines = _run(tmp_path=tmp_path, script=script, bindir=bindir, extra_env={})
    assert code == 0
    assert f"{_SCOPED_PREFIX} gate-cmd a b" in lines
    assert lines[-1] == "gate-cmd a b scope=1"


def test_a_host_whose_manager_does_not_load_the_slice_runs_the_command_unchanged(
    tmp_path: Path,
) -> None:
    script, bindir = _world(tmp_path=tmp_path, fakes=_ALL_FAKES)
    code, lines = _run(
        tmp_path=tmp_path,
        script=script,
        bindir=bindir,
        extra_env={"FAKE_LOAD_STATE": "not-found"},
    )
    assert code == 0
    assert not [line for line in lines if line.startswith("systemd-run")]
    assert lines[-1] == "gate-cmd a b scope=1"


def test_a_refused_probe_scope_falls_back_to_the_unscoped_launch(tmp_path: Path) -> None:
    script, bindir = _world(tmp_path=tmp_path, fakes=_ALL_FAKES)
    code, lines = _run(
        tmp_path=tmp_path,
        script=script,
        bindir=bindir,
        extra_env={"FAKE_PROBE_RC": "1"},
    )
    assert code == 0
    assert [line for line in lines if line.startswith("systemd-run")] == [_PROBE]
    assert lines[-1] == "gate-cmd a b scope=1"


def test_a_launch_already_inside_the_slice_is_not_scoped_again(tmp_path: Path) -> None:
    script, bindir = _world(tmp_path=tmp_path, fakes=_ALL_FAKES)
    code, lines = _run(
        tmp_path=tmp_path,
        script=script,
        bindir=bindir,
        extra_env={},
        cgroup=f"0::/user.slice/user-1000.slice/user@1000.service/local.slice/{_SLICE}/run-p1.scope\n",
    )
    assert code == 0
    assert lines == ["gate-cmd a b scope=1"]


def test_a_non_linux_host_runs_the_command_unchanged(tmp_path: Path) -> None:
    script, bindir = _world(tmp_path=tmp_path, fakes=_ALL_FAKES)
    code, lines = _run(
        tmp_path=tmp_path,
        script=script,
        bindir=bindir,
        extra_env={"FAKE_OS": "Darwin"},
    )
    assert code == 0
    assert not [line for line in lines if line.startswith(("systemd-run", "systemctl"))]
    assert lines[-1] == "gate-cmd a b scope=1"


def test_a_host_without_a_scope_launcher_runs_the_command_unchanged(tmp_path: Path) -> None:
    script, bindir = _world(tmp_path=tmp_path, fakes=("uname", "systemctl", "choom"))
    code, lines = _run(tmp_path=tmp_path, script=script, bindir=bindir, extra_env={})
    assert code == 0
    assert lines[-1] == "gate-cmd a b scope=1"
    assert not [line for line in lines if line.startswith("choom")]


def test_the_command_exit_code_is_the_script_exit_code_scoped_and_unscoped(
    tmp_path: Path,
) -> None:
    scoped_dir = tmp_path / "scoped"
    scoped_dir.mkdir()
    script, bindir = _world(tmp_path=scoped_dir, fakes=_ALL_FAKES)
    code, _ = _run(
        tmp_path=scoped_dir, script=script, bindir=bindir, extra_env={"FAKE_GATE_RC": "3"}
    )
    assert code == 3
    plain_dir = tmp_path / "plain"
    plain_dir.mkdir()
    script, bindir = _world(tmp_path=plain_dir, fakes=_ALL_FAKES)
    code, _ = _run(
        tmp_path=plain_dir,
        script=script,
        bindir=bindir,
        extra_env={"FAKE_GATE_RC": "3", "FAKE_LOAD_STATE": "not-found"},
    )
    assert code == 3


def test_no_command_is_a_usage_error(tmp_path: Path) -> None:
    script, bindir = _world(tmp_path=tmp_path, fakes=_ALL_FAKES)
    completed = subprocess.run(
        [str(bindir / "bash"), str(script)],
        env={"PATH": str(bindir), "FAKE_LOG": str(tmp_path / "calls.log")},
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert completed.returncode == 64
    assert "usage: local-gate-scope.sh" in completed.stderr


def test_the_environment_reaches_the_command_unchanged(tmp_path: Path) -> None:
    script, bindir = _world(tmp_path=tmp_path, fakes=_ALL_FAKES)
    probe = tmp_path / "bin" / "gate-cmd"
    _ = probe.write_text(
        '#!/bin/bash\necho "gate-cmd marker=${CALLER_MARKER:-unset}" >> "$FAKE_LOG"\n',
        encoding="utf-8",
    )
    code, lines = _run(
        tmp_path=tmp_path,
        script=script,
        bindir=bindir,
        extra_env={"CALLER_MARKER": "kept"},
    )
    assert code == 0
    assert lines[-1] == "gate-cmd marker=kept"
