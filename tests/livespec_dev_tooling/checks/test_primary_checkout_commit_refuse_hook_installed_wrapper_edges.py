"""Foreign-lefthook-wrapper arm of `primary_checkout_commit_refuse_hook_installed`.

A third `*_edges.py` sibling of
`test_primary_checkout_commit_refuse_hook_installed.py`, alongside
`*_probe_edges.py` (unanswered inputs) and `*_scan_edges.py` (the vendored-copy
tree walk). `check_coverage_incremental` selects every `test_<stem>_*.py`
sibling, so all of them count toward the parent impl's coverage.

WHAT THIS PINS — livespec-dev-tooling-x2ju4a. Until this arm existed the check
inspected exactly THREE NAMES in the shared hooks directory and nothing else,
so a FOURTH file there was invisible to it however dangerous. On 2026-09-06
`/data/projects/livespec/.git/hooks/prepare-commit-msg` was exactly that: not
the canonical commit-refuse body but lefthook's stock `call_lefthook` wrapper,
mtime 2026-06-20 — three months older than the canonical hooks sitting beside
it. It fires on every `git commit` and (verified the same day in a scratch
repo) on every `git cherry-pick`; it does not `unset GIT_DIR GIT_INDEX_FILE
GIT_WORK_TREE GIT_PREFIX`; and it calls `lefthook run` WITHOUT
`--no-auto-install` — the shape li-iroguc proved can write `core.bare=true`
into the shared `.git/config` when a hook fires inside a linked worktree. The
check reported three green byte-identity verdicts and said nothing about it.

⛔ THE ARM MATCHES ON SHAPE, NOT ON NAME, and the tests below are written to
that. `prepare-commit-msg` is the observed instance, not the rule: no name list
could cover the hook names lefthook has been asked to install across the
fleet's histories. What convicts a file is that it reaches lefthook and does
not first clear the GIT_DIR family — which is also exactly why the canonical
three, which carry that line by construction, keep passing.

`main()` is called IN-PROCESS (`monkeypatch.chdir` + `capsys`) rather than
spawned, per `check-tests-no-subprocess-spawn`. The git subprocesses the
fixtures run are unaffected: that rule governs PYTHON children.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

from livespec_dev_tooling.checks.primary_checkout_commit_refuse_hook_installed import main
from livespec_dev_tooling.install_commit_refuse_hooks import CANONICAL_HOOK_BODY

__all__: list[str] = []


# Vars git sets when invoking hooks; under a lefthook run they would redirect
# the check's probes at the SURROUNDING repo instead of the tmp_path fixture.
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

_FAIL_EXIT = 4

_HOOK_NAMES: tuple[str, ...] = ("pre-commit", "pre-push", "commit-msg")

# lefthook's stock wrapper, abridged to the shape that makes it a hazard: it
# reaches `lefthook` (so it IS an entry point), it dispatches `lefthook run
# <name>` with no `--no-auto-install`, and it never clears the GIT_DIR family.
# The real article is ~70 lines of interpreter-hunting `elif`s; none of them
# change the verdict, and reproducing them here would only invite the reader to
# think the arm greps for one of them.
_STOCK_LEFTHOOK_WRAPPER = """#!/bin/sh

if [ "$LEFTHOOK" = "0" ]; then
  exit 0
fi

call_lefthook()
{
  if test -n "$LEFTHOOK_BIN"
  then
    "$LEFTHOOK_BIN" "$@"
  elif lefthook -h >/dev/null 2>&1
  then
    lefthook "$@"
  else
    echo "Can't find lefthook in PATH"
  fi
}

call_lefthook run "prepare-commit-msg" "$@"
"""

# An ordinary local hook that has nothing to do with lefthook. Executable, and
# it must SURVIVE: this arm's subject is lefthook entry points, and a check
# that swept every executable in the hooks directory would be asserting an
# ownership claim nothing ratifies.
_UNRELATED_LOCAL_HOOK = """#!/bin/sh
# A repo-local hook that predates livespec and delegates to nothing.
exit 0
"""


def _git_init(*, cwd: Path) -> None:
    """Initialize a git repo at `cwd` with local user.name/user.email."""
    env = {k: v for k, v in os.environ.items() if k not in _GIT_ENV_PASSTHROUGH_VARS}
    for args in (
        ["init", "--quiet"],
        ["config", "--local", "user.name", "Test User"],
        ["config", "--local", "user.email", "test@example.com"],
    ):
        _ = subprocess.run(["git", *args], cwd=str(cwd), check=True, env=env)


def _repo_with_canonical_hooks(*, tmp_path: Path) -> Path:
    """A real git repo whose three canonical hooks are byte-perfect and executable.

    The three are correct so the ONLY thing the check can report is this arm; a
    fixture with drifted hooks would produce a fail these tests would happily
    mistake for their own.
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    _git_init(cwd=project_root)
    hooks_dir = project_root / ".git" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    for hook_name in _HOOK_NAMES:
        hook = hooks_dir / hook_name
        _ = hook.write_bytes(CANONICAL_HOOK_BODY.encode("utf-8"))
        hook.chmod(0o755)
    return project_root


def _seed(*, hooks_dir: Path, name: str, body: str, executable: bool) -> Path:
    """Write `body` into `<hooks_dir>/<name>` with or without the execute bits."""
    path = hooks_dir / name
    _ = path.write_text(body, encoding="utf-8")
    path.chmod(0o755 if executable else 0o644)
    return path


def _run_check(
    *, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], cwd: Path
) -> tuple[int, str]:
    """Call `main()` in-process under `cwd`, returning `(rc, stderr)`."""
    for var in _GIT_ENV_PASSTHROUGH_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.chdir(cwd)
    rc = main()
    return rc, capsys.readouterr().err


def test_fails_naming_a_stock_lefthook_wrapper_beside_canonical_hooks(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The observed defect, reproduced: three green hooks and a fourth live entry point.

    Every assertion carries weight. The exit code alone would not distinguish
    this from hook drift; the failure mode alone would not tell the operator
    WHICH file to look at, and this arm has no hook name to fall back on
    because it found the file by walking the directory; the remedy is asserted
    because a finding that names no installer leaves the operator to guess.
    """
    project_root = _repo_with_canonical_hooks(tmp_path=tmp_path)
    wrapper = _seed(
        hooks_dir=project_root / ".git" / "hooks",
        name="prepare-commit-msg",
        body=_STOCK_LEFTHOOK_WRAPPER,
        executable=True,
    )

    rc, stderr = _run_check(monkeypatch=monkeypatch, capsys=capsys, cwd=project_root)

    assert rc == _FAIL_EXIT, f"expected the fail exit; got {rc}\n{stderr}"
    assert '"failure_mode": "foreign_lefthook_wrapper"' in stderr, stderr
    assert f'"path": "{wrapper}"' in stderr, stderr
    assert '"hook": "prepare-commit-msg"' in stderr, stderr
    assert "just install-commit-refuse-hooks" in stderr, stderr


def test_canonical_three_alone_still_pass(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The canonical hooks ARE lefthook entry points and must never match this arm.

    They dispatch `lefthook run --no-auto-install "$hook_name"` — so a
    shape-matcher keyed on "invokes lefthook" alone would convict all three and
    make the check permanently red. The unset line is what tells them apart,
    and this is the test that says so.
    """
    project_root = _repo_with_canonical_hooks(tmp_path=tmp_path)

    rc, stderr = _run_check(monkeypatch=monkeypatch, capsys=capsys, cwd=project_root)

    assert rc == 0, f"expected a pass; got {rc}\n{stderr}"
    assert "foreign_lefthook_wrapper" not in stderr, stderr


def test_ignores_a_non_lefthook_hook_a_non_executable_wrapper_and_a_subdirectory(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Three things in the hooks dir that CANNOT fire as a lefthook entry point.

    A repo-local hook that never mentions lefthook is not this arm's business.
    A wrapper without the execute bit is inert — git runs a hook only when it
    is an executable regular file — and reporting it would send an operator
    after a file that does nothing. A subdirectory is not a hook at all; it is
    here because the predicate's `is_file` guard is otherwise unexercised, and
    an unexercised guard is one refactor away from an `IsADirectoryError` out
    of the check.
    """
    project_root = _repo_with_canonical_hooks(tmp_path=tmp_path)
    hooks_dir = project_root / ".git" / "hooks"
    _ = _seed(hooks_dir=hooks_dir, name="post-commit", body=_UNRELATED_LOCAL_HOOK, executable=True)
    _ = _seed(
        hooks_dir=hooks_dir,
        name="prepare-commit-msg",
        body=_STOCK_LEFTHOOK_WRAPPER,
        executable=False,
    )
    (hooks_dir / "multi").mkdir()

    rc, stderr = _run_check(monkeypatch=monkeypatch, capsys=capsys, cwd=project_root)

    assert rc == 0, f"expected a pass; got {rc}\n{stderr}"
    assert "foreign_lefthook_wrapper" not in stderr, stderr


def test_absent_hooks_directory_is_reported_as_missing_hooks_not_as_a_read_failure(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A hooks dir that is not there is already fully described by the byte-identity arm.

    It reports three `missing` hooks, which is the whole truth and routes to
    the installer. Letting this arm's `iterdir` raise `FileNotFoundError` into
    `hook_unreadable` would add a second, WRONGER sentence about the same
    state — "fix the access fault and re-run rather than reinstalling
    anything" — over a directory nothing is denying access to.
    """
    project_root = _repo_with_canonical_hooks(tmp_path=tmp_path)
    shutil.rmtree(project_root / ".git" / "hooks")

    rc, stderr = _run_check(monkeypatch=monkeypatch, capsys=capsys, cwd=project_root)

    assert rc == _FAIL_EXIT, f"expected the fail exit; got {rc}\n{stderr}"
    assert '"failure_mode": "missing"' in stderr, stderr
    assert "foreign_lefthook_wrapper" not in stderr, stderr
    assert "hook_unreadable" not in stderr, stderr


def test_fails_when_the_hooks_directory_cannot_be_listed(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A listing that did not happen is not an empty directory.

    This arm's PASS is an empty list, so a walk that raised part-way and
    unwound to `[]` would be a silent green on the arm whose entire job is to
    notice a file that should not be there — the same asymmetry that put the
    vendored-copy scan on the railway.

    ⛔ The fixture patches `iterdir` rather than removing the directory's read
    bit, because this suite runs as ROOT: a `chmod 000` hooks directory is
    still listed, the arm still returns `[]`, and the assertion would never
    fire — a green proving nothing.
    """
    project_root = _repo_with_canonical_hooks(tmp_path=tmp_path)
    hooks_dir = project_root / ".git" / "hooks"
    real_iterdir = Path.iterdir

    def _iterdir(self: Path) -> Iterator[Path]:
        if self == hooks_dir:
            raise OSError(13, "synthetic listing failure")
        return real_iterdir(self)

    monkeypatch.setattr(Path, "iterdir", _iterdir)
    # The patch is SCOPED to the hooks directory — every other listing still
    # delegates to the real `iterdir`. Asserted rather than assumed: a fixture
    # that raised for EVERY directory would drive the same three assertions
    # below green while proving something weaker than they claim, since the
    # failure could then have come from any listing the check happens to make.
    assert project_root / ".git" in set(project_root.iterdir())

    rc, stderr = _run_check(monkeypatch=monkeypatch, capsys=capsys, cwd=project_root)

    assert rc == _FAIL_EXIT, f"expected the fail exit; got {rc}\n{stderr}"
    assert '"failure_mode": "hook_unreadable"' in stderr, stderr
    assert f'"path": "{hooks_dir}"' in stderr, stderr
    assert "synthetic listing failure" in stderr, stderr
    assert "foreign_lefthook_wrapper" not in stderr, stderr


def test_fails_naming_the_hooks_dir_entry_that_could_not_be_read(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An unread candidate is neither a wrapper nor a clean directory.

    The three canonical hooks read successfully — which also proves the patch
    is scoped to one path rather than failing everything — and only the fourth
    file declines. Classifying it either way would be a verdict about bytes
    this run never saw; `hook_unreadable` says what actually happened and names
    the file.
    """
    project_root = _repo_with_canonical_hooks(tmp_path=tmp_path)
    wrapper = _seed(
        hooks_dir=project_root / ".git" / "hooks",
        name="prepare-commit-msg",
        body=_STOCK_LEFTHOOK_WRAPPER,
        executable=True,
    )
    real_read_bytes = Path.read_bytes

    def _read_bytes(self: Path) -> bytes:
        if self == wrapper:
            raise OSError(5, "synthetic read failure")
        return real_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", _read_bytes)

    rc, stderr = _run_check(monkeypatch=monkeypatch, capsys=capsys, cwd=project_root)

    assert rc == _FAIL_EXIT, f"expected the fail exit; got {rc}\n{stderr}"
    assert '"failure_mode": "hook_unreadable"' in stderr, stderr
    assert f'"path": "{wrapper}"' in stderr, stderr
    assert "synthetic read failure" in stderr, stderr
    assert "foreign_lefthook_wrapper" not in stderr, stderr
