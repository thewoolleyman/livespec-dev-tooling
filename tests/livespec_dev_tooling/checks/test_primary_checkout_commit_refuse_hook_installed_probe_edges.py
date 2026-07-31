"""Green-leg edges for `primary_checkout_commit_refuse_hook_installed` — git-probe arms.

A `*_edges.py` sibling of `test_primary_checkout_commit_refuse_hook_installed.py`
per the repo's Green-leg convention: the Red-recorded test file of a
Red→Green pair is byte-identity-bound, so tests authored at the Green amend
land here. `check_coverage_incremental` selects `test_<stem>_*.py` siblings
alongside the paired test, so these count toward the parent impl's coverage.

WHAT THESE PIN — livespec-dev-tooling-qndn, epic 8o8e. Every verdict the
parent check reports rests on six git probes. Until the probes went on the
`IOResult` railway, a probe that did not ANSWER was spelled the same as an
answer: `is_git_repo_at_all` returned a bare `False` whether git said "not a
repository" or never ran, and that `False` took the SKIP path — exit 0, a pass
the run never earned. `git_common_dir` and `work_tree_root` raised
`CalledProcessError` instead, which at least did not go green but produced a
traceback rather than a structured finding.

Each arm below drives ONE probe's failure and asserts the CHECK's disposition;
the probe-level success/failure split has its own mirror-paired test in
`test_primary_checkout_git_probes.py`.

`main()` is called IN-PROCESS (`monkeypatch.chdir` + `capsys`) rather than
spawned, per `check-tests-no-subprocess-spawn` — the paired file predates that
rule and sits on the migrate-away-from allowlist, which a new file must not
join. The git subprocesses the fixtures and the check itself run are
unaffected: that check governs PYTHON children, which are the ones that
self-instrument under `--cov` and race.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from livespec_dev_tooling.checks.primary_checkout_commit_refuse_hook_installed import main

__all__: list[str] = []


# Vars git sets when invoking hooks (lefthook pre-commit / pre-push). Under a
# hook these would redirect the check's probes at the SURROUNDING repo instead
# of the tmp_path fixture.
_GIT_ENV_PASSTHROUGH_VARS: tuple[str, ...] = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_COMMON_DIR",
    "GIT_NAMESPACE",
    "GIT_LITERAL_PATHSPECS",
    "GIT_PREFIX",
)

# The check's fail exit; `0` is pass-or-skip and is what these arms must NOT be.
_FAIL_EXIT = 4

# An exit code no probe treats as an answer (`git config --get` uses 1 for an
# unset key, and that one IS an answer).
_SYNTHETIC_GIT_EXIT = 66


def _git_init(*, cwd: Path) -> None:
    """Initialize a git repo at `cwd` with local user.name/user.email."""
    env = {k: v for k, v in os.environ.items() if k not in _GIT_ENV_PASSTHROUGH_VARS}
    for args in (
        ["init", "--quiet"],
        ["config", "--local", "user.name", "Test User"],
        ["config", "--local", "user.email", "test@example.com"],
    ):
        _ = subprocess.run(["git", *args], cwd=str(cwd), check=True, env=env)


def _repo_at(*, tmp_path: Path) -> Path:
    """A real git repo, initialized while the REAL git is still on PATH."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    _git_init(cwd=project_root)
    return project_root


def _unexecutable_git_bin(*, tmp_path: Path) -> str:
    """A directory whose `git` passes `shutil.which` but cannot be exec'd.

    `shutil.which` asks only for an existing, executable, non-directory file,
    so a shim whose interpreter does not resolve satisfies the check's ONE git
    guard and then makes `subprocess.run` raise `FileNotFoundError`. That is
    exactly the gap between "git is unavailable" (a documented skip) and "git
    does not answer" (a finding), and it is reachable in the field: a
    truncated install, a wrapper pointing at a removed toolchain.

    ⛔ The caller MUST use this directory as the WHOLE PATH, never as a
    prefix. An unresolvable interpreter makes `execve` fail with `ENOENT`, and
    `subprocess`'s own PATH search reads that as "not here" and CONTINUES to
    the next directory — so a real git further along the path silently
    services the call and the arm never fires. Measured, not assumed: the
    first version of this fixture appended `os.environ["PATH"]` and the check
    ran to completion against the real git.
    """
    bin_dir = tmp_path / "unexecutable-bin"
    bin_dir.mkdir()
    shim = bin_dir / "git"
    _ = shim.write_text("#!/nonexistent/interpreter\n", encoding="utf-8")
    shim.chmod(0o755)
    return str(bin_dir)


def _git_bin_failing_on(*, tmp_path: Path, name: str, argv: str) -> str:
    """A directory whose `git` exits non-zero for exactly `argv`, else delegates.

    One shim per scenario rather than one switched by an env var, so each arm
    isolates a single probe. The delegation target is the REAL git resolved
    absolutely, so every OTHER probe in the run answers normally — which is
    what makes the asserted `probe` field meaningful rather than incidental.
    """
    real_git = shutil.which("git")
    assert real_git is not None, "the suite needs a real git to delegate to"
    bin_dir = tmp_path / name
    bin_dir.mkdir()
    shim = bin_dir / "git"
    _ = shim.write_text(
        "#!/bin/sh\n"
        f'if [ "$*" = "{argv}" ]; then\n'
        "  printf 'fatal: synthetic git failure\\n' >&2\n"
        f"  exit {_SYNTHETIC_GIT_EXIT}\n"
        "fi\n"
        f'exec {real_git} "$@"\n',
        encoding="utf-8",
    )
    shim.chmod(0o755)
    return str(bin_dir)


def _run_check(
    *,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    cwd: Path,
    path_override: str,
) -> tuple[int, str]:
    """Call `main()` in-process under `cwd` and `path_override`, returning (rc, stderr)."""
    for var in _GIT_ENV_PASSTHROUGH_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.chdir(cwd)
    monkeypatch.setenv("PATH", path_override)
    rc = main()
    return rc, capsys.readouterr().err


def _assert_probe_failure(*, rc: int, stderr: str, probe: str) -> None:
    """The run FAILED, named `git_probe_failed`, and named WHICH probe.

    All four assertions carry weight. The exit code alone would not
    distinguish this from a hook-drift fail; the failure mode alone would not
    tell the operator which command to rerun; the argv is what makes the
    finding actionable rather than merely correct.
    """
    assert rc == _FAIL_EXIT, f"expected the fail exit; got {rc}"
    assert '"failure_mode": "git_probe_failed"' in stderr, stderr
    assert f'"probe": "{probe}"' in stderr, stderr
    assert '"argv": "git ' in stderr, stderr


def test_fails_when_git_is_on_path_but_cannot_be_executed(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An unexecutable `git` is a FINDING, not the `git unavailable` skip.

    The first probe the check runs is `is_git_repo_at_all`, and its bare
    `False` used to route this environment to "cwd is not a git repository;
    skipping check" — exit 0. The two states are now distinct: no git at all
    still skips (`test_skipped_when_git_unavailable` in the paired file), a
    git that does not answer fails.
    """
    project_root = _repo_at(tmp_path=tmp_path)
    rc, stderr = _run_check(
        monkeypatch=monkeypatch,
        capsys=capsys,
        cwd=project_root,
        path_override=_unexecutable_git_bin(tmp_path=tmp_path),
    )
    _assert_probe_failure(rc=rc, stderr=stderr, probe="is_git_repo_at_all")


def test_fails_when_the_core_bare_probe_cannot_read_config(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`git config --get core.bare` failing is a finding, not git's default `false`.

    Exit 1 means the key is UNSET and stays an answer; this exercises the
    other non-zero codes, which used to reach the caller as the same empty
    stdout and therefore the same `False`.
    """
    project_root = _repo_at(tmp_path=tmp_path)
    bin_dir = _git_bin_failing_on(
        tmp_path=tmp_path, name="shim-core-bare", argv="config --get core.bare"
    )
    rc, stderr = _run_check(
        monkeypatch=monkeypatch, capsys=capsys, cwd=project_root, path_override=bin_dir
    )
    _assert_probe_failure(rc=rc, stderr=stderr, probe="core_bare_is_true")


def test_fails_when_the_inside_work_tree_probe_does_not_answer(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A non-zero `rev-parse --is-inside-work-tree` is a finding, not "not a work tree"."""
    project_root = _repo_at(tmp_path=tmp_path)
    bin_dir = _git_bin_failing_on(
        tmp_path=tmp_path,
        name="shim-inside-work-tree",
        argv="rev-parse --is-inside-work-tree",
    )
    rc, stderr = _run_check(
        monkeypatch=monkeypatch, capsys=capsys, cwd=project_root, path_override=bin_dir
    )
    _assert_probe_failure(rc=rc, stderr=stderr, probe="is_inside_work_tree")


def test_fails_when_the_common_dir_probe_does_not_answer(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The converted `check=True` raise: a structured finding, not a traceback."""
    project_root = _repo_at(tmp_path=tmp_path)
    bin_dir = _git_bin_failing_on(
        tmp_path=tmp_path, name="shim-common-dir", argv="rev-parse --git-common-dir"
    )
    rc, stderr = _run_check(
        monkeypatch=monkeypatch, capsys=capsys, cwd=project_root, path_override=bin_dir
    )
    _assert_probe_failure(rc=rc, stderr=stderr, probe="git_common_dir")


def test_fails_when_the_work_tree_root_probe_does_not_answer(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The work-tree root anchors the no-vendored-copy scan.

    An unresolved root must not reach that scan as any path at all: `rglob`
    over the wrong tree finds no vendored copy and the arm passes silently.
    """
    project_root = _repo_at(tmp_path=tmp_path)
    bin_dir = _git_bin_failing_on(
        tmp_path=tmp_path, name="shim-toplevel", argv="rev-parse --show-toplevel"
    )
    rc, stderr = _run_check(
        monkeypatch=monkeypatch, capsys=capsys, cwd=project_root, path_override=bin_dir
    )
    _assert_probe_failure(rc=rc, stderr=stderr, probe="work_tree_root")


def test_fails_when_the_sandbox_exempt_probe_cannot_read_config(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An unreadable exemption marker fails rather than silently NOT exempting.

    A failed read collapsing onto `False` is the SAFE direction here — the
    pack arm just stays armed — which is exactly why it survived: a fail-safe
    that is indistinguishable from an answer still hides a broken environment.
    """
    project_root = _repo_at(tmp_path=tmp_path)
    bin_dir = _git_bin_failing_on(
        tmp_path=tmp_path,
        name="shim-sandbox-exempt",
        argv="config --get livespec.sandboxExempt",
    )
    rc, stderr = _run_check(
        monkeypatch=monkeypatch, capsys=capsys, cwd=project_root, path_override=bin_dir
    )
    _assert_probe_failure(rc=rc, stderr=stderr, probe="sandbox_exempt_is_true")
