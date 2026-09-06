"""The incremental coverage gate's `git diff` read is on the `IOResult` railway.

`check_coverage_incremental` derives the ENTIRE gated set from one
`git diff --name-only --diff-filter=d origin/master...HEAD`. That invocation
ran with `check=False` and its `returncode` was NEVER READ — only `.stdout`
was taken — so every failure of the diff produced an empty string, which the
filter turned into an empty path list, which `main()` reported as

    no changed impl .py paths derived from git diff; nothing to gate

and returned 0 on. The per-file 100% coverage gate passed VACUOUSLY on a read
that never happened, while stating in as many words that it had looked and
there was nothing there. **A failed enumeration does not go quiet; it
manufactures a confident empty answer** — the same class as `8o8e.5`'s
`ruff --show-files` outcome, and the FAIL-OPEN counterpart to the fail-closed
collapse `8o8e.9` converted in `_docs_only_change.py` one frame in.

It is reachable rather than theoretical: `origin/master` is a REMOTE-TRACKING
ref, absent from a shallow clone, from a fresh clone that has not fetched it,
from a checkout whose remote is named anything but `origin`, and from any CI
job cloning at `fetch-depth: 1`.

The load-bearing pair here is
`test_a_base_ref_that_cannot_be_diffed_fails_the_check` beside
`test_a_successful_empty_diff_still_exits_zero`: both exited 0 before, and
they are on OPPOSITE tracks now. The second is the ruling this unit turns on —
exit 0 with empty stdout is the one exit of `git diff <range>` that
legitimately answers "this branch changed nothing", so it stays a PASS.

Filed as livespec-dev-tooling-rav3.
"""

from __future__ import annotations

import importlib
import subprocess
import sys
import types
from pathlib import Path

import pytest
from returns.io import IOFailure, IOSuccess
from returns.unsafe import unsafe_perform_io

from livespec_dev_tooling.checks.check_coverage_incremental import main

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[3]
_BRANCH_DIFF_PATH = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "_branch_diff.py"
_DIFF_RANGE = "origin/master...HEAD"
_PYPROJECT = '[tool.livespec_dev_tooling]\nsource_tree_prefixes = ["livespec_dev_tooling/"]\n'


def _branch_diff_module() -> types.ModuleType:
    """The module owning the diff read, asserted to EXIST before it is imported.

    A top-level `import` would make the Red moment a COLLECTION error, which
    proves only that the module is unimportable rather than that the behavior
    is unimplemented. Asserting the file's presence first makes the Red a
    genuine assertion failure.
    """
    assert _BRANCH_DIFF_PATH.is_file(), f"the diff read must live at {_BRANCH_DIFF_PATH}"
    return importlib.import_module("livespec_dev_tooling.checks._branch_diff")


def _git(*, cwd: Path, args: list[str]) -> None:
    """Run `git` hermetically: no global config, no ambient `GIT_*` inheritance."""
    # S603/S607: argv is a fixed list (literal git binary + test-controlled
    # args); bare `git` is the canonical invocation per system PATH.
    _ = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
        env={"HOME": str(cwd), "GIT_CONFIG_GLOBAL": "/dev/null", "PATH": "/usr/bin:/bin"},
    )


def _repo_without_the_base_ref(*, tmp_path: Path) -> Path:
    """A committed repo that has NO `origin/master` — the shallow-clone shape."""
    _git(cwd=tmp_path, args=["init", "-q"])
    _ = (tmp_path / "pyproject.toml").write_text(_PYPROJECT, encoding="utf-8")
    _git(cwd=tmp_path, args=["add", "-A"])
    _git(cwd=tmp_path, args=["-c", "user.email=t@e", "-c", "user.name=T", "commit", "-qm", "base"])
    return tmp_path


def _repo_with_the_base_ref(*, tmp_path: Path) -> Path:
    """The same repo with `refs/remotes/origin/master` pointed at HEAD."""
    _ = _repo_without_the_base_ref(tmp_path=tmp_path)
    _git(cwd=tmp_path, args=["update-ref", "refs/remotes/origin/master", "HEAD"])
    return tmp_path


def test_a_base_ref_that_cannot_be_diffed_is_a_failure(*, tmp_path: Path) -> None:
    """A missing `origin/master` is a NON-READ, and the detail names the range."""
    module = _branch_diff_module()
    _ = _repo_without_the_base_ref(tmp_path=tmp_path)

    read = module.name_only_diff(diff_range=_DIFF_RANGE, cwd=tmp_path)

    assert isinstance(read, IOFailure), f"an undiffable range must fail; got {read!r}"
    unavailable = unsafe_perform_io(read.failure())
    assert unavailable.reason == "diff-failed"
    assert _DIFF_RANGE in unavailable.detail


def test_git_absent_from_path_is_not_run(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`git` missing from PATH is an `OSError`, lifted rather than propagated.

    Unguarded, it raised straight out of a function whose caller was typed to
    receive a list of paths — the arm the old `check=False` spelling did not
    merely mis-answer, it crashed on.
    """
    module = _branch_diff_module()
    _ = _repo_with_the_base_ref(tmp_path=tmp_path)
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    monkeypatch.setenv("PATH", str(empty_bin))

    read = module.name_only_diff(diff_range=_DIFF_RANGE, cwd=tmp_path)

    assert isinstance(read, IOFailure), f"an unrunnable git must fail; got {read!r}"
    assert unsafe_perform_io(read.failure()).reason == "git-not-run"


def test_a_range_with_no_changed_paths_answers_an_empty_diff(*, tmp_path: Path) -> None:
    """Exit 0 with empty stdout is an ANSWER `git` gave, not a failure."""
    module = _branch_diff_module()
    _ = _repo_with_the_base_ref(tmp_path=tmp_path)

    read = module.name_only_diff(diff_range=_DIFF_RANGE, cwd=tmp_path)

    assert isinstance(read, IOSuccess), f"an empty range is an answer; got {read!r}"
    assert unsafe_perform_io(read.unwrap()) == ""


def test_a_range_with_a_changed_path_answers_it(*, tmp_path: Path) -> None:
    """The success track carries the raw `--name-only` blob `git` printed."""
    module = _branch_diff_module()
    _ = _repo_with_the_base_ref(tmp_path=tmp_path)
    impl = tmp_path / "livespec_dev_tooling" / "checks" / "derived_mod.py"
    impl.parent.mkdir(parents=True)
    _ = impl.write_text("from __future__ import annotations\n", encoding="utf-8")
    _git(cwd=tmp_path, args=["add", "-A"])
    _git(cwd=tmp_path, args=["-c", "user.email=t@e", "-c", "user.name=T", "commit", "-qm", "add"])

    read = module.name_only_diff(diff_range=_DIFF_RANGE, cwd=tmp_path)

    assert isinstance(read, IOSuccess), f"a readable range must succeed; got {read!r}"
    assert "livespec_dev_tooling/checks/derived_mod.py" in unsafe_perform_io(read.unwrap())


def _main_in(*, cwd: Path, monkeypatch: pytest.MonkeyPatch) -> int:
    """Invoke the check's `main()` IN-PROCESS with `cwd` as the repo root."""
    monkeypatch.setattr(sys, "argv", ["check-coverage-incremental"])
    monkeypatch.chdir(cwd)
    return main()


def test_a_base_ref_that_cannot_be_diffed_fails_the_check(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The gate REFUSES rather than reporting an empty changed set.

    This is the fail-open the work-item names: without the returncode read the
    check logged "nothing to gate" and returned 0 on a diff that exited 128.
    """
    _ = _repo_without_the_base_ref(tmp_path=tmp_path)

    exit_code = _main_in(cwd=tmp_path, monkeypatch=monkeypatch)

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert exit_code != 0, f"an unreadable diff must fail the gate; got {exit_code}, {combined!r}"
    assert _DIFF_RANGE in combined, f"the diagnostic must name the range; got {combined!r}"
    assert "nothing to gate" not in combined, f"a non-read must not answer as empty; {combined!r}"


def test_a_successful_empty_diff_still_exits_zero(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The one exit that legitimately says "this branch changed nothing" still PASSES.

    Paired with the test above so the fix cannot over-reach into refusing a
    genuinely empty branch — which would red every commit whose HEAD matches
    `origin/master`.
    """
    _ = _repo_with_the_base_ref(tmp_path=tmp_path)

    exit_code = _main_in(cwd=tmp_path, monkeypatch=monkeypatch)

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert exit_code == 0, f"an empty-but-read diff is a PASS; got {exit_code}, {combined!r}"
    assert "nothing to gate" in combined, f"the no-op diagnostic must survive; got {combined!r}"
