"""Mirror-paired test for `livespec_dev_tooling/checks/_primary_checkout_git_probes.py`.

The private sibling module carries the git rev-parse / git config
probes extracted from `primary_checkout_commit_refuse_hook_installed.py`
at the fleet-check-coverage LLOC-reduction split. The probes' end-to-end
coverage lives in `test_primary_checkout_commit_refuse_hook_installed.py`
(they are exercised outside-in through the parent check's subprocess
contract); THIS file unit-tests each probe directly against a real
tmp-path git repo, pinning the module boundary and both branches of
`git_common_dir` (relative common-dir at the repo root, absolute
common-dir from a linked worktree).

EVERY PROBE IS ON THE `IOResult` RAILWAY (livespec-dev-tooling-qndn,
epic 8o8e), so this file also pins the split the conversion exists to
make: an invocation that COMPLETES and answers is `IOSuccess` whatever
it answers, and only git failing to answer at all is `IOFailure`. The
two are asserted separately per probe, because collapsing them is the
defect — `is_git_repo_at_all` returning a bare `False` for a broken
environment routed the parent check to SKIP (exit 0), and
`git_common_dir` raised `CalledProcessError` out of a function whose
docstring advertised the raise as a feature.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from returns.io import IOFailure, IOSuccess
from returns.unsafe import unsafe_perform_io

from livespec_dev_tooling.checks._primary_checkout_git_probes import (
    GitProbeFailed,
    core_bare_is_true,
    git_common_dir,
    is_git_repo_at_all,
    is_inside_work_tree,
    sandbox_exempt_is_true,
    work_tree_root,
)

if TYPE_CHECKING:
    from collections.abc import Callable

__all__: list[str] = []


# Vars git sets when invoking hooks (lefthook pre-commit / pre-push).
# The probes' internal `git` subprocesses inherit the test process env;
# under a hook, GIT_DIR / GIT_INDEX_FILE would redirect those probes at
# the SURROUNDING repo instead of the tmp_path mini-repo.
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

# An exit code `git config --get` never uses for "the key is unset" (which is
# 1) — the probes must read anything else as a FAILURE rather than as `False`.
_ODD_CONFIG_EXIT = 66


@pytest.fixture(autouse=True)
def _scrub_git_hook_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in _GIT_ENV_PASSTHROUGH_VARS:
        monkeypatch.delenv(var, raising=False)


def _git(*, cwd: Path, args: list[str]) -> None:
    _ = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
        env={
            "HOME": str(cwd),
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_SYSTEM": "/dev/null",
            "PATH": "/usr/bin:/bin",
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.com",
        },
    )


def _make_repo(*, tmp_path: Path) -> Path:
    """Initialize a normal work-tree repo at `tmp_path/repo` with one commit."""
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    _git(cwd=repo, args=["init", "--quiet", "-b", "work"])
    _git(cwd=repo, args=["commit", "--quiet", "--allow-empty", "-m", "seed"])
    return repo


def _succeeded(result: object) -> object:
    """Unwrap an `IOSuccess`, asserting the railway took the success track."""
    assert isinstance(result, IOSuccess), f"expected IOSuccess; got {result!r}"
    return unsafe_perform_io(result.unwrap())


def _failed(result: object) -> GitProbeFailed:
    """Unwrap an `IOFailure`, asserting the railway took the failure track."""
    assert isinstance(result, IOFailure), f"expected IOFailure; got {result!r}"
    failure = unsafe_perform_io(result.failure())
    assert isinstance(failure, GitProbeFailed)
    return failure


def _refuse_to_run(*, monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every `subprocess.run` raise `OSError`, as an unexecutable git does.

    The failure track the four `bool` probes could not previously express:
    `git` present per `shutil.which` but impossible to exec (a shim whose
    interpreter does not resolve, a fork failure). Before the conversion this
    propagated out of the probe uncaught.
    """

    def _boom(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise OSError(2, "No such file or directory: 'git'")

    monkeypatch.setattr(subprocess, "run", _boom)


def _fake_exit(*, monkeypatch: pytest.MonkeyPatch, returncode: int) -> None:
    """Make every `subprocess.run` return a completed process with `returncode`."""

    def _completed(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=["git"], returncode=returncode, stdout="", stderr="fatal: synthetic\n"
        )

    monkeypatch.setattr(subprocess, "run", _completed)


def test_is_git_repo_at_all_true_in_repo_false_outside(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path=tmp_path)
    plain = tmp_path / "plain"
    plain.mkdir()
    assert _succeeded(is_git_repo_at_all(cwd=repo)) is True
    # `git rev-parse --git-dir` exiting non-zero IS the answer "not a
    # repository", not a failure — the one non-zero exit this probe accepts.
    assert _succeeded(is_git_repo_at_all(cwd=plain)) is False


def test_is_inside_work_tree_true_in_repo_false_in_git_dir(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path=tmp_path)
    assert _succeeded(is_inside_work_tree(cwd=repo)) is True
    # Inside the `.git` directory is a git context that is NOT a work tree.
    assert _succeeded(is_inside_work_tree(cwd=repo / ".git")) is False


def test_core_bare_is_true_false_for_normal_repo_true_for_bare(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path=tmp_path)
    # `core.bare` unset — `git config --get` exits 1 and prints nothing. That
    # is an ANSWER (git's default `false`), so it stays on the success track.
    assert _succeeded(core_bare_is_true(cwd=repo)) is False
    bare = tmp_path / "bare.git"
    bare.mkdir()
    _git(cwd=bare, args=["init", "--bare", "--quiet"])
    assert _succeeded(core_bare_is_true(cwd=bare)) is True


def test_sandbox_exempt_is_true_only_for_the_literal_true(tmp_path: Path) -> None:
    """Only the literal `true` exempts; the marker is a declaration, not a key."""
    repo = _make_repo(tmp_path=tmp_path)
    assert _succeeded(sandbox_exempt_is_true(cwd=repo)) is False
    _git(cwd=repo, args=["config", "--local", "livespec.sandboxExempt", "yes"])
    assert _succeeded(sandbox_exempt_is_true(cwd=repo)) is False
    _git(cwd=repo, args=["config", "--local", "livespec.sandboxExempt", "true"])
    assert _succeeded(sandbox_exempt_is_true(cwd=repo)) is True


def test_git_common_dir_relative_from_repo_root(tmp_path: Path) -> None:
    """From the repo root `git --git-common-dir` is relative (`.git`) → resolved branch."""
    repo = _make_repo(tmp_path=tmp_path)
    result = _succeeded(git_common_dir(cwd=repo))
    assert isinstance(result, Path)
    assert result == (repo / ".git").resolve()
    assert result.is_absolute()
    assert result.is_dir()


def test_git_common_dir_absolute_from_linked_worktree(tmp_path: Path) -> None:
    """From a linked worktree `git --git-common-dir` is absolute → returned verbatim."""
    repo = _make_repo(tmp_path=tmp_path)
    linked = tmp_path / "linked"
    _git(cwd=repo, args=["worktree", "add", "--quiet", str(linked), "-b", "wt"])
    result = _succeeded(git_common_dir(cwd=linked))
    assert isinstance(result, Path)
    assert result.is_absolute()
    assert result.name == ".git"
    assert result.is_dir()


def test_work_tree_root_returns_toplevel(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path=tmp_path)
    result = _succeeded(work_tree_root(cwd=repo))
    assert isinstance(result, Path)
    assert result.is_dir()
    assert (result / ".git").exists()
    assert result.name == "repo"


def test_work_tree_root_outside_a_repo_is_a_failure_not_a_path(tmp_path: Path) -> None:
    """A non-zero `git rev-parse --show-toplevel` is a FAILURE, never a Path.

    This is the `check=True` raise the conversion replaced: the docstring
    advertised "raises rather than silently returning a sentinel", which is an
    inhabited, uncaught failure track stated in prose. It is now on the
    railway, and the diagnostic names the probe, the argv and the cwd so the
    operator can rerun the exact command.
    """
    plain = tmp_path / "plain"
    plain.mkdir()
    failure = _failed(work_tree_root(cwd=plain))
    assert failure.probe == "work_tree_root"
    assert failure.argv == "git rev-parse --show-toplevel"
    assert failure.cwd == str(plain)
    assert "not a git repository" in failure.detail


def test_git_common_dir_outside_a_repo_is_a_failure_not_a_path(tmp_path: Path) -> None:
    """Same `check=True` raise-by-design as `work_tree_root`, same conversion."""
    plain = tmp_path / "plain"
    plain.mkdir()
    failure = _failed(git_common_dir(cwd=plain))
    assert failure.probe == "git_common_dir"
    assert failure.argv == "git rev-parse --git-common-dir"


def test_is_inside_work_tree_outside_a_repo_is_a_failure_not_false(tmp_path: Path) -> None:
    """`False` means "a git context that is not a work tree", never "git failed".

    The parent check calls this only after `is_git_repo_at_all` has confirmed a
    surrounding repo, so a non-zero exit here contradicts the probe's own
    precondition. Reporting it as `False` made a broken environment
    indistinguishable from a bare repo.
    """
    plain = tmp_path / "plain"
    plain.mkdir()
    failure = _failed(is_inside_work_tree(cwd=plain))
    assert failure.probe == "is_inside_work_tree"
    assert failure.argv == "git rev-parse --is-inside-work-tree"


@pytest.mark.parametrize(
    ("probe", "name"),
    [
        (is_git_repo_at_all, "is_git_repo_at_all"),
        (is_inside_work_tree, "is_inside_work_tree"),
        (core_bare_is_true, "core_bare_is_true"),
        (sandbox_exempt_is_true, "sandbox_exempt_is_true"),
        (git_common_dir, "git_common_dir"),
        (work_tree_root, "work_tree_root"),
    ],
)
def test_every_probe_reports_an_unexecutable_git_as_a_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    probe: Callable[..., object],
    name: str,
) -> None:
    """`git` that cannot be exec'd is a FAILURE for all six, not a bare answer.

    `shutil.which("git")` — the parent check's only guard — passes for a file
    that exists and carries the exec bit but whose interpreter does not
    resolve. `subprocess.run` then raises, and before the conversion that
    exception either escaped the probe uncaught or, for the four `bool`
    probes, could not be expressed in the return type at all.
    """
    _refuse_to_run(monkeypatch=monkeypatch)
    failure = _failed(probe(cwd=tmp_path))
    assert failure.probe == name
    assert failure.cwd == str(tmp_path)
    assert "No such file or directory" in failure.detail


@pytest.mark.parametrize(
    ("probe", "name"),
    [
        (core_bare_is_true, "core_bare_is_true"),
        (sandbox_exempt_is_true, "sandbox_exempt_is_true"),
    ],
)
def test_config_probes_separate_an_unset_key_from_a_failed_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    probe: Callable[..., object],
    name: str,
) -> None:
    """Exit 1 is "key unset" (an answer); any OTHER non-zero exit is a failure.

    The collapse the triage recorded: "git-failed and key-unset both yield
    empty stdout → False". `sandbox_exempt_is_true` gates an EXEMPTION, so its
    silent `False` was the safe direction — and still indistinguishable, which
    is what makes it a defect rather than a preference.
    """
    _fake_exit(monkeypatch=monkeypatch, returncode=_ODD_CONFIG_EXIT)
    failure = _failed(probe(cwd=tmp_path))
    assert failure.probe == name
    assert "synthetic" in failure.detail
    assert str(_ODD_CONFIG_EXIT) in failure.detail
