"""Behaviour tests for the pack member `worktree_pack/gate-run.sh`.

Two properties are under test, and both were bought by the same incident
(livespec-dev-tooling-trfzkw, folding in livespec-p32m6d):

SCOPE A — the run directory must OUTLIVE the worktree that started the
run. It used to resolve under the invoked worktree, so routine post-merge
`git worktree remove` deleted the only record of what a gate was executing
when it failed. Every case here therefore builds a real primary checkout
plus a real linked worktree, starts a real detached run from the worktree,
and reads the record back from the PRIMARY — in one case after the
worktree is gone.

SCOPE B — the runner arms a `.git/config` write-watch around the gate. The
flip that refused two detached runs at 03:00:09Z on 2026-09-06 happened
INSIDE a gate child, so the watch lives here and writes into Scope A's
durable directory. The watch is an OBSERVER: the flip case asserts the
gate's own exit code (7) is passed through unchanged even though the
marker fires.

Every subprocess is `git` (fixture setup) or `bash` (the script under
test); nothing touches the fleet ledger, the network, or the developer's
own repositories. `HOME`, the git env family and `COVERAGE_PROCESS_START`
/ `COV_CORE_*` are scrubbed so the children are hermetic and never
self-instrument under `pytest --cov`.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import pytest

from livespec_dev_tooling.install_worktree_pack import CANONICAL_GATE_RUN_BODY

__all__: list[str] = []

_SCRIPT = "gate-run.sh"
# The store the runner resolves from the SHARED git dir, relative to the
# PRIMARY checkout. Spelled out here so a regression that silently moves it
# back under the worktree fails on the path, not just on a missing file.
_STORE = Path("tmp") / "gate-runs"
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
    """Materialize the canonical body under `dev-tooling/`, as a consumer would.

    The stub `worktree-lib.sh` beside it satisfies the runner's own
    pack preflight, which would otherwise shell out to
    `just install-worktree-pack` inside the fixture.
    """
    pack = root / "dev-tooling"
    pack.mkdir(parents=True, exist_ok=True)
    _ = (pack / "worktree-lib.sh").write_text("# stub\n", encoding="utf-8")
    script = pack / _SCRIPT
    _ = script.write_text(CANONICAL_GATE_RUN_BODY, encoding="utf-8")
    script.chmod(0o755)


@pytest.fixture
def fixture_repo(tmp_path: Path) -> tuple[Path, Path, dict[str, str]]:
    """A primary checkout plus a linked worktree, both carrying the runner.

    Returns `(primary, worktree, env)`. Both checkouts get their own
    `dev-tooling/` because a `git worktree add` never inherits the
    primary's gitignored pack.
    """
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
    """True as soon as `path` appears; False once `timeout_s` has elapsed.

    Split out of `_await_verdict` and given its own test rather than left
    inline, because the give-up arm of a poll loop only runs when the system
    under test is broken — inline it would be the one line in this file that
    a green run can never reach, and the repo gates on 100% per-file
    coverage. Extracting it makes the timeout genuinely exercised instead of
    merely annotated away.
    """
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
    """The arm every other case in this file must NOT take.

    A gate that never records a verdict has to fail the suite, not hang it —
    `_await_verdict` turns this `False` into a named assertion failure.
    """
    assert not _wait_for_file(path=tmp_path / "never-appears", timeout_s=0.05)
    present = tmp_path / "present"
    _ = present.write_text("", encoding="utf-8")
    assert _wait_for_file(path=present, timeout_s=0.05)


def _flip_writer(*, tmp_path: Path, primary: Path) -> Path:
    """A gate command that writes the PRIMARY's shared config, then lingers.

    It lives outside both checkouts so removing the worktree cannot take it
    with it, and it stays alive after the write so the watcher's
    descendant-tree snapshot can still NAME it — which is the whole point of
    the instrument.

    It lingers until the watcher has actually recorded, rather than for a
    fixed sleep, so the assertion is on the WATCH and not on the scheduler:
    a fixed sleep turns a loaded host into a red build. The wait is capped,
    so a watch that never fires still fails the test rather than hanging it.
    A real gate outlives any config write it makes by minutes, which is the
    situation this reproduces.
    """
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


def _core_fields(*, path: Path) -> dict[str, str]:
    """The comparable half of a core digest — `captured_at` differs by design."""
    fields: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key, _, value = line.partition(": ")
        if key in {"core.bare", "core_sha256"}:
            fields[key] = value
    return fields
