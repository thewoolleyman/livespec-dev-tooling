"""Behaviour tests for the pack member `worktree_pack/gate-run.sh`.

Two behaviors are under test and both were bought by production incidents:

Scope A covers run-directory durability and the config write-watch. The
run directory must outlive the worktree that started it, and the watcher
around `.git/config` must record flips without changing the gate verdict.

Scope B covers `status`'s evidence probe and the zero-target NOTE it
guards. The probe must count evidenced green runs from both emitters, on
both the direct and lefthook-buffered paths, while still warning when a
completed run produced no per-target evidence at all.

Every subprocess is `git` (fixture setup) or `bash` (the script under
test); nothing touches the fleet ledger, the network, or the developer's
own repositories. `HOME`, the git env family and `COVERAGE_PROCESS_START`
/ `COV_CORE_*` are scrubbed so the children are hermetic and never
self-instrument under `pytest --cov`.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from livespec_dev_tooling.install_worktree_pack import CANONICAL_GATE_RUN_BODY

__all__: list[str] = []

_SCRIPT = "gate-run.sh"
_STORE = Path("tmp") / "gate-runs"
_RUN_ID = "20260821T095508Z-3605372"
_NOTE = "NOTE: zero check targets completed"
_VERDICT_TIMEOUT_S = 90.0
_POLL_INTERVAL_S = 0.1
_GATE_EXIT_CODE = 7

# git sets these in a hook's environment when it fires inside a worktree;
# under a lefthook pre-commit they leak in from the surrounding repo.
# Scrubbing them confines every git invocation to the tmp_path fixture.
_GIT_ENV_VARS: tuple[str, ...] = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_COMMON_DIR",
    "GIT_NAMESPACE",
    "GIT_LITERAL_PATHSPECS",
    "GIT_PREFIX",
)

# What the parallel dispatcher writes: one line per COMPLETED target,
# carrying the target's status inside the bracket.
_PARALLEL_LOG = (
    "\n::: just check-lint [ok, wall: 1.4s]\n"
    "ruff: all checks passed\n"
    "\n::: just check-types [ok, wall: 9.1s]\n"
    "\n::: just check-vendor-manifest (skipped)\n"
    "\nAll 2 targets passed.\n"
)

# What the serial `check:` justfile loop writes: one line per STARTED
# target, with NO bracket suffix and no status of any kind.
_SERIAL_LOG = (
    "\n::: just check-lint\n"
    "ruff: all checks passed\n"
    "\n::: just check-types\n"
    "\n::: just check-vendor-manifest (skipped)\n"
    "\nAll 2 targets passed.\n"
)

# A serial aggregate that reached a real verdict and REFUSED. Its
# per-target lines carry no status, so the summary is the only failure
# evidence in the capture.
_SERIAL_FAILED_LOG = (
    "\n::: just check-lint\n"
    "\n::: just check-types\n"
    "pyright: 3 errors\n"
    "\nFailed targets (1):\n  - check-types\n"
)

# A run that completed having executed nothing at all: lefthook's own
# banner and summary, and not one `::: just` line. This is the case the
# NOTE was built for and it must keep firing.
_VACUOUS_LOG = (
    "╭─────────────────────────────────────╮\n"
    "│ 🥊 lefthook v1.13.6  hook: pre-push │\n"
    "╰─────────────────────────────────────╯\n"
    "sync hooks: ✔️ (pre-push)\n"
    "summary: (skip) no matching files\n"
)


def _as_lefthook_pty_capture(*, text: str) -> str:
    """Return `text` as lefthook replays it: every line CRLF-terminated."""
    return text.replace("\n", "\r\n")


def _write(*, path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(text, encoding="utf-8")


def _init_repo(*, tmp_path: Path) -> Path:
    """A throwaway repository carrying the canonical body under `dev-tooling/`."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = subprocess.run(
        ["git", "init", "--quiet", "--initial-branch=master"],
        cwd=str(repo),
        check=True,
        capture_output=True,
        text=True,
    )
    script = repo / "dev-tooling" / _SCRIPT
    _write(path=script, text=CANONICAL_GATE_RUN_BODY)
    script.chmod(0o755)
    return repo


def _record_run(*, repo: Path, output_log: str, exit_code: str, run_id: str = _RUN_ID) -> None:
    """Hand-write one run record exactly as the detached child leaves it."""
    run_dir = repo / "tmp" / "gate-runs" / run_id
    _write(path=run_dir / "label", text="consensus-valve\n")
    _write(path=run_dir / "started_at", text="2026-08-21T09:55:08Z\n")
    _write(path=run_dir / "finished_at", text="2026-08-21T10:12:41Z\n")
    _write(path=run_dir / "cwd", text=f"{repo}\n")
    _write(path=run_dir / "branch", text="master\n")
    _write(path=run_dir / "head", text="0123456789abcdef\n")
    _write(path=run_dir / "command", text="just\ncheck\n")
    _write(path=run_dir / "output.log", text=output_log)
    _write(path=run_dir / "exit_code", text=f"{exit_code}\n")


def _run_status(*, repo: Path, run_id: str = _RUN_ID) -> subprocess.CompletedProcess[str]:
    """Run `gate-run.sh status <run-id>` from the repo root, as the recipe does."""
    env = {key: value for key, value in os.environ.items() if key not in _GIT_ENV_VARS}
    return subprocess.run(
        ["bash", str(Path("dev-tooling") / _SCRIPT), "status", run_id],
        cwd=str(repo),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def _child_env(*, home: Path) -> dict[str, str]:
    env = dict(os.environ)
    for name in (*_GIT_ENV_VARS, "COVERAGE_PROCESS_START"):
        _ = env.pop(name, None)
    for name in [key for key in env if key.startswith("COV_CORE_")]:
        _ = env.pop(name, None)
    home.mkdir(parents=True, exist_ok=True)
    env["HOME"] = str(home)
    env["XDG_STATE_HOME"] = str(home / "state")
    return env


def _run_git(*, args: list[str], cwd: Path, env: dict[str, str]) -> None:
    _ = subprocess.run(
        ["git", *args], cwd=str(cwd), env=env, check=True, capture_output=True, text=True
    )


def _install_runner(*, root: Path) -> None:
    """Materialize the canonical body under `dev-tooling/`, as a consumer would."""
    pack = root / "dev-tooling"
    pack.mkdir(parents=True, exist_ok=True)
    _ = (pack / "worktree-lib.sh").write_text("# stub\n", encoding="utf-8")
    script = pack / _SCRIPT
    _ = script.write_text(CANONICAL_GATE_RUN_BODY, encoding="utf-8")
    script.chmod(0o755)


@pytest.fixture
def fixture_repo(tmp_path: Path) -> tuple[Path, Path, dict[str, str]]:
    """A primary checkout plus a linked worktree, both carrying the runner."""
    env = _child_env(home=tmp_path / "home")
    primary = tmp_path / "primary"
    primary.mkdir()
    _run_git(args=["init", "--quiet", "--initial-branch=master"], cwd=primary, env=env)
    _run_git(args=["config", "--local", "user.name", "Test User"], cwd=primary, env=env)
    _run_git(args=["config", "--local", "user.email", "test@example.com"], cwd=primary, env=env)
    _ = (primary / "README.md").write_text("# fixture\n", encoding="utf-8")
    _run_git(args=["add", "--all"], cwd=primary, env=env)
    _run_git(args=["commit", "--quiet", "-m", "base"], cwd=primary, env=env)

    worktree = tmp_path / "wt"
    _run_git(
        args=["worktree", "add", "--quiet", "-b", "feature/wip", str(worktree)],
        cwd=primary,
        env=env,
    )
    _install_runner(root=primary)
    _install_runner(root=worktree)
    return primary, worktree, env


def _gate(*, cwd: Path, env: dict[str, str], args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(cwd / "dev-tooling" / _SCRIPT), *args],
        cwd=str(cwd),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def _start(*, cwd: Path, env: dict[str, str], command: list[str]) -> str:
    started = _gate(cwd=cwd, env=env, args=["start", "--", *command])
    assert started.returncode == 0, started.stderr
    return started.stdout.strip()


def _wait_for_file(*, path: Path, timeout_s: float) -> bool:
    """True as soon as `path` appears; False once `timeout_s` has elapsed."""
    deadline = time.monotonic() + timeout_s
    while not path.is_file():
        if time.monotonic() >= deadline:
            return False
        time.sleep(_POLL_INTERVAL_S)
    return True


def _await_verdict(*, primary: Path, run_id: str) -> Path:
    """Block until the detached child records a verdict; return its run dir."""
    run_dir = primary / _STORE / run_id
    assert _wait_for_file(
        path=run_dir / "exit_code", timeout_s=_VERDICT_TIMEOUT_S
    ), f"gate run {run_id} never recorded a verdict under {run_dir}"
    return run_dir


def test_the_verdict_poll_helper_gives_up_rather_than_blocking_forever(*, tmp_path: Path) -> None:
    """The arm every other case in this file must NOT take."""
    assert not _wait_for_file(path=tmp_path / "never-appears", timeout_s=0.05)
    present = tmp_path / "present"
    _ = present.write_text("", encoding="utf-8")
    assert _wait_for_file(path=present, timeout_s=0.05)


def _flip_writer(*, tmp_path: Path, primary: Path) -> Path:
    """A gate command that writes the PRIMARY's shared config, then lingers."""
    writer = tmp_path / "flip-writer.sh"
    config = primary / ".git" / "config"
    _ = writer.write_text(
        "#!/usr/bin/env bash\n"
        f'git config --file "{config}" core.bare true\n'
        f"deadline=$((SECONDS + {int(_VERDICT_TIMEOUT_S) // 2}))\n"
        'while [ "$SECONDS" -lt "$deadline" ]; do\n'
        f'    grep -qs . "{primary / _STORE}"/*/config-writes.log && break\n'
        "    sleep 0.1\n"
        "done\n"
        f"exit {_GATE_EXIT_CODE}\n",
        encoding="utf-8",
    )
    writer.chmod(0o755)
    return writer


def test_run_started_in_a_worktree_is_readable_after_the_worktree_is_removed(
    *, fixture_repo: tuple[Path, Path, dict[str, str]]
) -> None:
    """SCOPE A: `git worktree remove` no longer destroys the run record."""
    primary, worktree, env = fixture_repo
    run_id = _start(cwd=worktree, env=env, command=["bash", "-c", "echo ran-in-worktree"])
    run_dir = _await_verdict(primary=primary, run_id=run_id)
    assert run_dir.is_dir()

    _run_git(args=["worktree", "remove", "--force", str(worktree)], cwd=primary, env=env)
    assert not worktree.exists()

    status = _gate(cwd=primary, env=env, args=["status", run_id])
    assert status.returncode == 0, status.stderr
    assert "PASSED" in status.stdout
    assert "ran-in-worktree" in (run_dir / "output.log").read_text(encoding="utf-8")


def test_gate_list_is_the_same_from_the_primary_and_from_a_linked_worktree(
    *, fixture_repo: tuple[Path, Path, dict[str, str]]
) -> None:
    """SCOPE A: one store per repository, not one per worktree."""
    primary, worktree, env = fixture_repo
    from_worktree = _start(cwd=worktree, env=env, command=["bash", "-c", "true"])
    from_primary = _start(cwd=primary, env=env, command=["bash", "-c", "true"])
    _ = _await_verdict(primary=primary, run_id=from_worktree)
    _ = _await_verdict(primary=primary, run_id=from_primary)

    listed_at_worktree = _gate(cwd=worktree, env=env, args=["list"])
    listed_at_primary = _gate(cwd=primary, env=env, args=["list"])
    assert listed_at_worktree.stdout == listed_at_primary.stdout
    assert from_worktree in listed_at_primary.stdout
    assert from_primary in listed_at_worktree.stdout


def test_the_run_record_names_the_worktree_and_the_command_line(
    *, fixture_repo: tuple[Path, Path, dict[str, str]]
) -> None:
    """SCOPE A: a shared store must say WHERE a run ran, not only WHAT ran."""
    primary, worktree, env = fixture_repo
    command = ["bash", "-c", "echo recorded"]
    run_id = _start(cwd=worktree, env=env, command=command)
    run_dir = _await_verdict(primary=primary, run_id=run_id)

    recorded_worktree = (run_dir / "worktree").read_text(encoding="utf-8").strip()
    assert Path(recorded_worktree).resolve() == worktree.resolve()
    assert (run_dir / "command").read_text(encoding="utf-8").splitlines() == command

    status = _gate(cwd=primary, env=env, args=["status", run_id])
    assert recorded_worktree in status.stdout
    assert "echo recorded" in status.stdout


@pytest.mark.integration
def test_a_config_flip_during_the_gate_marks_the_run_and_names_the_writer(
    *, tmp_path: Path, fixture_repo: tuple[Path, Path, dict[str, str]]
) -> None:
    """SCOPE B (a): the marker fires, the write is attributed, the verdict is untouched."""
    primary, worktree, env = fixture_repo
    writer = _flip_writer(tmp_path=tmp_path, primary=primary)
    run_id = _start(cwd=worktree, env=env, command=["bash", str(writer)])
    run_dir = _await_verdict(primary=primary, run_id=run_id)

    assert (run_dir / "exit_code").read_text(encoding="utf-8").strip() == str(_GATE_EXIT_CODE)
    marker = run_dir / "CORE_BARE_FLIP"
    assert marker.is_file()
    marker_text = marker.read_text(encoding="utf-8")
    assert "core.bare: false -> true" in marker_text

    writes = (run_dir / "config-writes.log").read_text(encoding="utf-8")
    assert writes.strip() != ""
    assert "core.bare now: true" in writes
    assert writer.name in writes

    status = _gate(cwd=primary, env=env, args=["status", run_id])
    # Non-fatal: the gate's own exit code is transported unchanged, and the
    # marker is surfaced alongside the verdict rather than instead of it.
    assert status.returncode == _GATE_EXIT_CODE
    assert "CORE_BARE_FLIP" in status.stdout


def test_a_run_with_no_config_write_records_matching_core_state_and_no_marker(
    *, fixture_repo: tuple[Path, Path, dict[str, str]]
) -> None:
    """SCOPE B (b): the happy path is silent — an observer that always fires is noise."""
    primary, worktree, env = fixture_repo
    run_id = _start(cwd=worktree, env=env, command=["bash", "-c", "sleep 0.5"])
    run_dir = _await_verdict(primary=primary, run_id=run_id)

    before = _core_fields(path=run_dir / "core_before")
    after = _core_fields(path=run_dir / "core_after")
    assert before == after
    assert before["core.bare"] == "false"
    assert not (run_dir / "CORE_BARE_FLIP").exists()
    assert (run_dir / "config-writes.log").read_text(encoding="utf-8") == ""


def test_the_watch_artifacts_survive_removal_of_the_worktree_that_ran_the_gate(
    *, tmp_path: Path, fixture_repo: tuple[Path, Path, dict[str, str]]
) -> None:
    """SCOPE B (c): the watch writes into Scope A's durable directory, not the worktree's."""
    primary, worktree, env = fixture_repo
    writer = _flip_writer(tmp_path=tmp_path, primary=primary)
    run_id = _start(cwd=worktree, env=env, command=["bash", str(writer)])
    run_dir = _await_verdict(primary=primary, run_id=run_id)

    _run_git(args=["worktree", "remove", "--force", str(worktree)], cwd=primary, env=env)
    assert not worktree.exists()
    for artifact in ("core_before", "core_after", "config-writes.log", "CORE_BARE_FLIP"):
        assert (run_dir / artifact).is_file(), artifact

    status = _gate(cwd=primary, env=env, args=["status", run_id])
    assert "CORE_BARE_FLIP" in status.stdout
    assert writer.name in status.stdout


@pytest.mark.parametrize(
    "output_log",
    [
        pytest.param(_SERIAL_LOG, id="serial-emitter"),
        pytest.param(_PARALLEL_LOG, id="parallel-emitter"),
        pytest.param(
            _as_lefthook_pty_capture(text=_SERIAL_LOG), id="serial-emitter-under-lefthook"
        ),
        pytest.param(
            _as_lefthook_pty_capture(text=_PARALLEL_LOG), id="parallel-emitter-under-lefthook"
        ),
    ],
)
def test_status_counts_every_target_of_an_evidenced_green_run(
    tmp_path: Path, output_log: str
) -> None:
    """An evidenced green run reports its target count and never prints the NOTE."""
    repo = _init_repo(tmp_path=tmp_path)
    _record_run(repo=repo, output_log=output_log, exit_code="0")

    result = _run_status(repo=repo)

    assert result.returncode == 0, f"{result.stdout}{result.stderr}"
    assert "targets completed : 2 (failed: 0)" in result.stdout
    assert _NOTE not in result.stdout
    assert "the gate RAN TO COMPLETION and PASSED" in result.stdout


@pytest.mark.parametrize(
    "output_log",
    [
        pytest.param(_SERIAL_FAILED_LOG, id="serial-emitter"),
        pytest.param(
            _as_lefthook_pty_capture(text=_SERIAL_FAILED_LOG), id="serial-emitter-under-lefthook"
        ),
    ],
)
def test_status_reads_the_serial_emitters_only_failure_evidence(
    tmp_path: Path, output_log: str
) -> None:
    """A refusing serial aggregate reports its failed count from the summary."""
    repo = _init_repo(tmp_path=tmp_path)
    _record_run(repo=repo, output_log=output_log, exit_code="1")

    result = _run_status(repo=repo)

    assert result.returncode == 1, f"{result.stdout}{result.stderr}"
    assert "targets completed : 2 (failed: 1)" in result.stdout
    assert _NOTE not in result.stdout
    assert "RAN TO COMPLETION and REFUSED" in result.stdout


def test_status_still_warns_when_a_completed_run_executed_no_target(tmp_path: Path) -> None:
    """The case the NOTE exists for: a green run with no per-target evidence at all."""
    repo = _init_repo(tmp_path=tmp_path)
    _record_run(repo=repo, output_log=_VACUOUS_LOG, exit_code="0")

    result = _run_status(repo=repo)

    assert result.returncode == 0, f"{result.stdout}{result.stderr}"
    assert "targets completed : 0 (failed: 0)" in result.stdout
    assert _NOTE in result.stdout


def test_status_still_warns_when_the_run_captured_nothing(tmp_path: Path) -> None:
    """An empty capture is the emptiest vacuous run there is; the NOTE must fire."""
    repo = _init_repo(tmp_path=tmp_path)
    _record_run(repo=repo, output_log="", exit_code="0")

    result = _run_status(repo=repo)

    assert result.returncode == 0, f"{result.stdout}{result.stderr}"
    assert "targets completed : 0 (failed: 0)" in result.stdout
    assert _NOTE in result.stdout


def _core_fields(*, path: Path) -> dict[str, str]:
    """The comparable half of a core digest — `captured_at` differs by design."""
    fields: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key, _, value = line.partition(": ")
        if key in {"core.bare", "core_sha256"}:
            fields[key] = value
    return fields


# Every external command the runner reaches for. A shim in front of each one
# logs its exec, so a process spawned on a watch tick or a wait poll shows up
# as a line in the log.
_SHIMMED_COMMANDS: tuple[str, ...] = (
    "cat",
    "date",
    "find",
    "git",
    "grep",
    "ls",
    "readlink",
    "sha256sum",
    "sleep",
    "stat",
    "tr",
)
_IDLE_GATE_S = 4
_IDLE_SETTLE_S = 0.7
_IDLE_WINDOW_S = 1.5
_WAIT_RETURN_BUDGET_S = 5.0


def _shim_dir(*, root: Path) -> Path:
    """A PATH directory whose entries log their own exec to `$GATE_SHIM_LOG`, then run the real one."""
    shims = root / "shims"
    shims.mkdir()
    for name in _SHIMMED_COMMANDS:
        real = shutil.which(name)
        assert real is not None, name
        shim = shims / name
        _ = shim.write_text(
            f'#!/bin/sh\nprintf \'%s\\n\' "{name}" >> "$GATE_SHIM_LOG"\nexec {real} "$@"\n',
            encoding="utf-8",
        )
        shim.chmod(0o755)
    return shims


def _shimmed_env(*, env: dict[str, str], shims: Path, log: Path) -> dict[str, str]:
    shimmed = dict(env)
    shimmed["PATH"] = f"{shims}{os.pathsep}{env['PATH']}"
    shimmed["GATE_SHIM_LOG"] = str(log)
    return shimmed


def _spawn_count(*, log: Path) -> int:
    return len(log.read_text(encoding="utf-8").splitlines()) if log.is_file() else 0


@pytest.mark.integration
def test_an_idle_detached_gate_run_and_an_idle_waiter_spawn_no_per_tick_process(
    *, tmp_path: Path, fixture_repo: tuple[Path, Path, dict[str, str]]
) -> None:
    """The cost of doing nothing: no exec per watch tick, none per wait poll."""
    primary, worktree, env = fixture_repo
    shims = _shim_dir(root=tmp_path)
    runner_log = tmp_path / "runner-spawns.log"
    waiter_log = tmp_path / "waiter-spawns.log"
    ready = tmp_path / "gate-is-idle"
    idle_gate = f"touch {ready}; exec 3<> <(:); read -t {_IDLE_GATE_S} -u 3; exit {_GATE_EXIT_CODE}"
    run_id = _start(
        cwd=worktree,
        env=_shimmed_env(env=env, shims=shims, log=runner_log),
        command=["bash", "-c", idle_gate],
    )
    waiter = subprocess.Popen(
        [str(primary / "dev-tooling" / _SCRIPT), "wait", run_id],
        cwd=str(primary),
        env=_shimmed_env(env=env, shims=shims, log=waiter_log),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert _wait_for_file(path=ready, timeout_s=_VERDICT_TIMEOUT_S)
    time.sleep(_IDLE_SETTLE_S)
    # Control arm: the shims are live, so a silent log means silence, not blindness.
    assert _spawn_count(log=runner_log) > 0
    assert _spawn_count(log=waiter_log) > 0
    runner_before = _spawn_count(log=runner_log)
    waiter_before = _spawn_count(log=waiter_log)

    time.sleep(_IDLE_WINDOW_S)

    assert _spawn_count(log=runner_log) == runner_before
    assert _spawn_count(log=waiter_log) == waiter_before

    _ = _await_verdict(primary=primary, run_id=run_id)
    verdict_at = time.monotonic()
    stdout, _stderr = waiter.communicate(timeout=_VERDICT_TIMEOUT_S)
    assert time.monotonic() - verdict_at < _WAIT_RETURN_BUDGET_S
    assert waiter.returncode == _GATE_EXIT_CODE
    assert "FAILED" in stdout


@pytest.mark.integration
def test_gate_wait_reports_the_gates_own_exit_code_for_a_finished_detached_run(
    *, fixture_repo: tuple[Path, Path, dict[str, str]]
) -> None:
    """Scenario: the gate outlives the launching shell and its code is the verdict."""
    primary, worktree, env = fixture_repo
    run_id = _start(
        cwd=worktree, env=env, command=["bash", "-c", f"sleep 0.3; exit {_GATE_EXIT_CODE}"]
    )
    waited = _gate(cwd=primary, env=env, args=["wait", run_id])

    run_dir = primary / _STORE / run_id
    assert (run_dir / "exit_code").read_text(encoding="utf-8").strip() == str(_GATE_EXIT_CODE)
    assert waited.returncode == _GATE_EXIT_CODE
    assert "FAILED" in waited.stdout


@pytest.mark.integration
def test_a_run_whose_process_died_without_a_verdict_exits_75_and_is_not_a_pass(
    *, fixture_repo: tuple[Path, Path, dict[str, str]]
) -> None:
    """Scenario: a recorded pid, no exit_code, and a pid that is gone."""
    primary, _worktree, env = fixture_repo
    gone = subprocess.Popen(["true"])
    _ = gone.wait()
    run_dir = primary / _STORE / "20260101T000000Z-1"
    _write(path=run_dir / "pid", text=f"{gone.pid}\n")
    _write(path=run_dir / "command", text="just\ncheck\n")
    _write(path=run_dir / "output.log", text="")

    for subcommand in ("wait", "status"):
        result = _gate(cwd=primary, env=env, args=[subcommand, run_dir.name])

        assert result.returncode == 75, subcommand
        assert "DIED_WITHOUT_VERDICT" in result.stdout, subcommand
        assert "PASSED" not in result.stdout, subcommand
