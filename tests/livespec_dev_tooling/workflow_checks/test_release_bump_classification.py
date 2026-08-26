"""Outside-in test for `livespec_dev_tooling/workflow_checks/release_bump_classification.py`.

Per `SPECIFICATION/contracts.md` section "`release_bump_classification`
check" (a release-workflow check, per section "Shared check inventory"),
the check compares the `__all__` inventory between the last release tag
and `HEAD` against the semver classification the Conventional-Commit
types over that range declare, refusing when the declared classification
is strictly weaker than the delta requires.

Test scenarios:

- No `v[0-9]*` tag at all → exit 0 (graceful skip).
- Equal inventories, only `chore:` commits since the tag → exit 0. This
  is the regression guard for the `patch`-floor defect: an earlier draft
  required `patch` on equal inventories, which refused every repository
  whose public surface had not changed.
- A name ADDED with only `fix:` commits → exit 4 (required minor,
  declared patch).
- A name ADDED with a `feat:` commit → exit 0.
- A name REMOVED with a `feat:` commit → exit 4 (required major,
  declared minor).
- A name REMOVED with a `feat!:` commit → exit 0.
- A `BREAKING CHANGE:` footer on a `fix:` commit lifts the declaration
  to major → exit 0 even with a removal.
- A name added in a file OUTSIDE the declared `source_trees` is not
  inventoried → exit 0.
- The `HEAD` inventory reads the COMMITTED tree, not the working tree:
  an uncommitted `__all__` addition does not trigger a refusal.
- `--help` exits 0 with usage on stdout.

The check is invoked IN-PROCESS (`main()` under `monkeypatch.chdir`),
not by spawning a Python child: a spawned child races
`COVERAGE_PROCESS_START` and is banned by the `tests_no_subprocess_spawn`
check. The real git subprocesses the check itself makes are unaffected,
and the fixtures below build genuine git repos under `tmp_path` so the
check exercises real git plumbing end-to-end.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

from livespec_dev_tooling.workflow_checks import release_bump_classification

__all__: list[str] = []


# Vars git sets when invoking hooks. Inherited by subprocess children unless
# scrubbed, which would redirect the fixture's `git` calls to the SURROUNDING
# repo instead of the tmp_path mini-repo the test constructs.
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

_PYPROJECT = """\
[tool.livespec_dev_tooling]
source_trees = ["pkg"]
io_trees = []
commands_trees = []
covered_trees = []
supervisor_entry_files = []
dataclasses_tree = { not_applicable = "fixture" }
pure_trees = { not_applicable = "fixture" }
source_tree_prefixes = { not_applicable = "fixture" }
"""


@dataclass(frozen=True, kw_only=True)
class _Result:
    """The in-process equivalent of a CompletedProcess for this check."""

    returncode: int
    stderr: str


def _scrubbed_environ() -> dict[str, str]:
    """Return a copy of `os.environ` with GIT_* hook vars removed."""
    return {k: v for k, v in os.environ.items() if k not in _GIT_ENV_PASSTHROUGH_VARS}


def _git(*, cwd: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    """Invoke git with a hermetic env so tmp_path fixtures stay isolated."""
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
        env=_scrubbed_environ(),
    )


def _commit(*, repo: Path, subject: str, body: str = "") -> None:
    """Stage everything and commit with the given subject (and optional body)."""
    _git(cwd=repo, args=["add", "-A"])
    args = ["commit", "-m", subject]
    if body:
        args.extend(["-m", body])
    _git(cwd=repo, args=args)


def _init_repo(*, repo: Path) -> None:
    """Create a git repo with identity configured and a pyproject fixture."""
    repo.mkdir(parents=True, exist_ok=True)
    _git(cwd=repo, args=["init", "-b", "master"])
    _git(cwd=repo, args=["config", "user.email", "test@example.com"])
    _git(cwd=repo, args=["config", "user.name", "Test"])
    _git(cwd=repo, args=["config", "commit.gpgsign", "false"])
    (repo / "pyproject.toml").write_text(_PYPROJECT, encoding="utf-8")
    (repo / "pkg").mkdir(exist_ok=True)


def _write_module(*, repo: Path, name: str, exports: list[str]) -> None:
    """Write `pkg/<name>.py` declaring `exports` in its `__all__`."""
    body = ", ".join(f'"{e}"' for e in exports)
    defs = "\n".join(f"def {e}() -> None:\n    return None\n" for e in exports)
    (repo / "pkg" / f"{name}.py").write_text(
        f"__all__: list[str] = [{body}]\n\n\n{defs}", encoding="utf-8"
    )


def _baseline_repo(*, tmp_path: Path) -> Path:
    """A repo tagged v1.0.0 exporting one name from `pkg/mod.py`."""
    repo = tmp_path / "repo"
    _init_repo(repo=repo)
    _write_module(repo=repo, name="mod", exports=["alpha"])
    _commit(repo=repo, subject="feat: initial")
    _git(cwd=repo, args=["tag", "v1.0.0"])
    return repo


def _run(
    *,
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> _Result:
    """Invoke the check IN-PROCESS with `repo` as cwd."""
    monkeypatch.chdir(repo)
    monkeypatch.setattr(sys, "argv", ["release-bump-classification"])
    returncode = release_bump_classification.main()
    return _Result(returncode=returncode, stderr=capsys.readouterr().err)


def test_no_release_tag_skips_gracefully(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo=repo)
    _write_module(repo=repo, name="mod", exports=["alpha"])
    _commit(repo=repo, subject="feat: initial")
    result = _run(repo=repo, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0, result.stderr


def test_equal_inventory_with_chore_commits_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Regression guard: an earlier draft required `patch` here and refused."""
    repo = _baseline_repo(tmp_path=tmp_path)
    (repo / "README.md").write_text("docs\n", encoding="utf-8")
    _commit(repo=repo, subject="chore: unrelated housekeeping")
    result = _run(repo=repo, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0, result.stderr


def test_added_name_with_only_fix_commit_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _baseline_repo(tmp_path=tmp_path)
    _write_module(repo=repo, name="mod", exports=["alpha", "beta"])
    _commit(repo=repo, subject="fix: tweak")
    result = _run(repo=repo, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 4, result.stderr
    assert "required_classification" in result.stderr
    assert "pkg/mod.py:beta" in result.stderr


def test_added_name_with_feat_commit_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _baseline_repo(tmp_path=tmp_path)
    _write_module(repo=repo, name="mod", exports=["alpha", "beta"])
    _commit(repo=repo, subject="feat: add beta")
    result = _run(repo=repo, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0, result.stderr


def test_removed_name_with_feat_commit_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _baseline_repo(tmp_path=tmp_path)
    _write_module(repo=repo, name="mod", exports=["gamma"])
    _commit(repo=repo, subject="feat: replace alpha with gamma")
    result = _run(repo=repo, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 4, result.stderr
    assert "pkg/mod.py:alpha" in result.stderr


def test_removed_name_with_breaking_subject_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _baseline_repo(tmp_path=tmp_path)
    _write_module(repo=repo, name="mod", exports=["gamma"])
    _commit(repo=repo, subject="feat!: replace alpha with gamma")
    result = _run(repo=repo, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0, result.stderr


def test_breaking_change_footer_lifts_declaration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _baseline_repo(tmp_path=tmp_path)
    _write_module(repo=repo, name="mod", exports=["gamma"])
    _commit(repo=repo, subject="fix: swap", body="BREAKING CHANGE: alpha is gone")
    result = _run(repo=repo, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0, result.stderr


def test_file_outside_source_trees_is_not_inventoried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _baseline_repo(tmp_path=tmp_path)
    (repo / "other").mkdir(exist_ok=True)
    (repo / "other" / "mod.py").write_text('__all__: list[str] = ["zeta"]\n', encoding="utf-8")
    _commit(repo=repo, subject="fix: unrelated tree")
    result = _run(repo=repo, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0, result.stderr


def test_head_inventory_reads_committed_tree_not_working_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A dirty working tree must not manufacture a refusal at a pre-push gate."""
    repo = _baseline_repo(tmp_path=tmp_path)
    (repo / "README.md").write_text("docs\n", encoding="utf-8")
    _commit(repo=repo, subject="chore: housekeeping")
    # Uncommitted surface addition — invisible to the check by design.
    _write_module(repo=repo, name="mod", exports=["alpha", "delta"])
    result = _run(repo=repo, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0, result.stderr


def test_help_exits_zero_with_usage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _baseline_repo(tmp_path=tmp_path)
    monkeypatch.chdir(repo)
    monkeypatch.setattr(sys, "argv", ["release-bump-classification", "--help"])
    with pytest.raises(SystemExit) as excinfo:
        release_bump_classification.main()
    assert excinfo.value.code == 0
    assert "usage:" in capsys.readouterr().out


# --- Edge and failure paths -------------------------------------------------
#
# These exercise the defensive branches the end-to-end scenarios above cannot
# reach: git invocations that fail (the check degrades rather than crashing),
# and `__all__` shapes the ratified section says contribute nothing without
# being errors. They call module privates directly, which is permitted because
# `tests/` sits outside the declared `source_trees` the `private_calls` check
# walks.


def test_baseline_tag_returns_none_outside_a_repo(tmp_path: Path) -> None:
    assert release_bump_classification._baseline_tag(cwd=tmp_path) is None  # noqa: SLF001  — private helper under test


def test_tracked_python_files_returns_empty_outside_a_repo(tmp_path: Path) -> None:
    assert (
        release_bump_classification._tracked_python_files(cwd=tmp_path, rev="HEAD", trees=("pkg",))  # noqa: SLF001  — private helper under test
        == ()
    )


def test_declared_classification_returns_none_outside_a_repo(tmp_path: Path) -> None:
    assert (
        release_bump_classification._declared_classification(cwd=tmp_path, tag="v1.0.0") == "none"  # noqa: SLF001  — private helper under test
    )


def test_non_conventional_subject_declares_nothing() -> None:
    assert release_bump_classification._subject_classification(subject="tidied things up") == "none"  # noqa: SLF001  — private helper under test


def test_all_that_is_not_a_literal_sequence_contributes_nothing() -> None:
    names = release_bump_classification._exported_names(  # noqa: SLF001  — private helper under test
        source='__all__ = "alpha"\n', rel_path="pkg/mod.py"
    )
    assert names == frozenset()


def test_non_string_all_elements_are_ignored() -> None:
    names = release_bump_classification._exported_names(  # noqa: SLF001  — private helper under test
        source='__all__ = [1, "alpha"]\n', rel_path="pkg/mod.py"
    )
    assert names == frozenset({"pkg/mod.py:alpha"})


def test_plain_assignment_form_of_all_is_recognized() -> None:
    """`__all__ = [...]` (ast.Assign) as well as `__all__: list[str] = [...]`."""
    names = release_bump_classification._exported_names(  # noqa: SLF001  — private helper under test
        source='__all__ = ["alpha"]\n', rel_path="pkg/mod.py"
    )
    assert names == frozenset({"pkg/mod.py:alpha"})


def test_unreadable_blob_is_skipped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A file listed by ls-tree whose blob cannot be shown is skipped, not fatal."""
    repo = _baseline_repo(tmp_path=tmp_path)
    real_git = release_bump_classification._git  # noqa: SLF001  — private helper under test

    def _failing_show(*, cwd: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
        _ = cwd
        if args and args[0] == "show":
            return subprocess.CompletedProcess(args=["git", *args], returncode=1, stdout="")
        return real_git(cwd=cwd, args=args)

    monkeypatch.setattr(release_bump_classification, "_git", _failing_show)
    assert (
        release_bump_classification._inventory_at(cwd=repo, rev="HEAD", trees=("pkg",))  # noqa: SLF001  — private helper under test
        == frozenset()
    )


def test_blank_lines_in_tag_output_are_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A blank first line in `git tag --list` output does not become the tag."""
    repo = _baseline_repo(tmp_path=tmp_path)

    def _padded_tags(*, cwd: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
        _ = cwd
        return subprocess.CompletedProcess(
            args=["git", *args], returncode=0, stdout="\n  \nv1.0.0\n"
        )

    monkeypatch.setattr(release_bump_classification, "_git", _padded_tags)
    assert release_bump_classification._baseline_tag(cwd=repo) == "v1.0.0"  # noqa: SLF001  — private helper under test
