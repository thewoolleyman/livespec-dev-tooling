"""Outside-in test for `dev-tooling/checks/check_coverage_incremental.py`.

The path-scoped fast-feedback variant of `check-coverage` is
authored as `dev-tooling/checks/check_coverage_incremental.py`
+ a `check-coverage-incremental:` recipe in the justfile.
Invocation contract: take `--paths <impl_path> [<impl_path>...]`,
resolve each impl's mirror-paired test, run pytest with full
`--cov` (no path filter — path-scoped `--cov=<dir>` filters
break under subprocess instrumentation), then apply the per-file
100% line+branch gate via `coverage report
--include=<impl_paths> --fail-under=100`.

Wall-clock target: under 10 seconds for a typical single-file
pair. NOT a replacement for `check-coverage` — the full-tree
run remains the load-bearing pre-commit gate. The fast-feedback
role is to surface coverage gaps proactively during the v039 D4
Red→Green authoring loop, before the Green amend triggers a
multi-minute aggregate retry on a missed defensive branch.

This module pins the public-API surface via spec-loading the
not-yet-existing impl module, asserting `main` and the
mirror-pair-resolution helper exist, and exercising the
mirror-pair mapping for each of the three impl-tree shapes.
The end-to-end path is exercised via subprocess invocation in
the repo's actual cwd (no tmp_path fixture: the script's
contract is to read repo-root-relative paths and run pytest
against the real test tree).

Output discipline: per spec, the test scaffolding may use
`subprocess.run` and stdlib imports freely. The check itself
is exempt from the dev-tooling/checks/ "no CLI flags" guidance
documented in `dev-tooling/checks/CLAUDE.md` — the v039 D3
contract REQUIRES a `--paths` flag to scope the per-file gate.
The exemption mirrors `red_green_replay.py` which takes
`argv[1]` as the COMMIT_EDITMSG path.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import types
from pathlib import Path

import pytest

from livespec_dev_tooling.config import MirrorPairing, load_config

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECK_PATH = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "check_coverage_incremental.py"


def _core_pairings() -> tuple[MirrorPairing, ...]:
    """The livespec-core historical mirror pairings (no-block fallback)."""
    return load_config(repo_root=Path("/livespec-dev-tooling-nonexistent-root")).mirror_pairings


def _load_check_module() -> types.ModuleType:
    """Import the check module via spec loading.

    The module lives outside any package (`dev-tooling/checks/`
    is on no `sys.path` package root), so a normal `import` would
    fail. `spec_from_file_location` loads it from the absolute
    path. At HEAD (Red moment) the file does not exist, so
    `spec` is None; the assertion below fires the Red signal.
    """
    spec = importlib.util.spec_from_file_location(
        "check_coverage_incremental_under_test",
        str(_CHECK_PATH),
    )
    assert spec is not None and spec.loader is not None, f"check module not found at {_CHECK_PATH}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_check_module_exports_main_callable() -> None:
    """Module exists and exports a callable `main` per dev-tooling/checks contract."""
    module = _load_check_module()
    assert callable(
        module.main
    ), "check_coverage_incremental.main must be callable per the dev-tooling/checks/ contract"


def test_resolve_mirror_test_for_livespec_dev_tooling_checks_pair() -> None:
    """`livespec_dev_tooling/checks/foo.py` resolves to `tests/livespec_dev_tooling/checks/test_foo.py`.

    Mirror-pairing per v033 D1, applied to this library's own
    source-tree layout: `livespec_dev_tooling/checks/` mirrors to
    `tests/livespec_dev_tooling/checks/` with the standard
    `test_<name>.py` filename convention. The mapping is
    additive — livespec-core's pre-existing mappings remain
    so the migrated check still applies to consumers using the
    original layout.
    """
    module = _load_check_module()
    impl_path = Path("livespec_dev_tooling") / "checks" / "foo.py"
    expected_test = Path("tests") / "livespec_dev_tooling" / "checks" / "test_foo.py"
    actual_test = module._resolve_mirror_test_path(  # noqa: SLF001
        impl_path=impl_path, mirror_pairings=_core_pairings()
    )
    assert actual_test == expected_test, (
        f"mirror-pair resolution mismatch for {impl_path}: "
        f"expected {expected_test}, got {actual_test}"
    )


def test_resolve_mirror_test_for_livespec_subdir_pair() -> None:
    """`.claude-plugin/scripts/livespec/sub/foo.py` resolves to `tests/livespec/sub/test_foo.py`.

    Mirror-pairing per v033 D1: the livespec package tree
    rooted at `.claude-plugin/scripts/livespec/` mirrors to
    `tests/livespec/`, preserving subdirectory structure.
    """
    module = _load_check_module()
    impl_path = Path(".claude-plugin") / "scripts" / "livespec" / "validate" / "finding.py"
    expected_test = Path("tests") / "livespec" / "validate" / "test_finding.py"
    actual_test = module._resolve_mirror_test_path(  # noqa: SLF001
        impl_path=impl_path, mirror_pairings=_core_pairings()
    )
    assert actual_test == expected_test, (
        f"mirror-pair resolution mismatch for {impl_path}: "
        f"expected {expected_test}, got {actual_test}"
    )


def test_resolve_mirror_test_for_bin_wrapper_pair() -> None:
    """`.claude-plugin/scripts/bin/seed.py` resolves to `tests/bin/test_seed.py`.

    Mirror-pairing per v033 D1: the bin wrapper tree rooted at
    `.claude-plugin/scripts/bin/` mirrors to `tests/bin/`.
    """
    module = _load_check_module()
    impl_path = Path(".claude-plugin") / "scripts" / "bin" / "seed.py"
    expected_test = Path("tests") / "bin" / "test_seed.py"
    actual_test = module._resolve_mirror_test_path(  # noqa: SLF001
        impl_path=impl_path, mirror_pairings=_core_pairings()
    )
    assert actual_test == expected_test, (
        f"mirror-pair resolution mismatch for {impl_path}: "
        f"expected {expected_test}, got {actual_test}"
    )


def test_resolve_mirror_test_for_private_helper_strips_leading_underscore() -> None:
    """`_seed_helpers.py` resolves to `test_seed_helpers.py` (matches tests_mirror_pairing.py).

    Per `dev-tooling/checks/tests_mirror_pairing.py`'s
    `_expected_paired_test_path`, leading-underscore module
    names are stripped before the `test_` prefix is added —
    `_seed_helpers.py` → `test_seed_helpers.py`. This pinning
    ensures `check-coverage-incremental` matches the same
    mapping rule (deviation would silently miss tests that
    DO exist in the standard convention).
    """
    module = _load_check_module()
    impl_path = Path(".claude-plugin") / "scripts" / "livespec" / "commands" / "_seed_helpers.py"
    expected_test = Path("tests") / "livespec" / "commands" / "test_seed_helpers.py"
    actual_test = module._resolve_mirror_test_path(  # noqa: SLF001
        impl_path=impl_path, mirror_pairings=_core_pairings()
    )
    assert actual_test == expected_test, (
        f"private-helper mirror-pair resolution mismatch for {impl_path}: "
        f"expected {expected_test}, got {actual_test}"
    )


def test_resolve_mirror_test_raises_on_unknown_impl_tree() -> None:
    """Path under no recognized impl tree raises `ValueError` with diagnostic.

    The mapping table covers exactly three impl trees:
    `.claude-plugin/scripts/livespec/`,
    `.claude-plugin/scripts/bin/`, `dev-tooling/checks/`. A
    path under any other tree (e.g., `tests/`, `sandbox/`,
    a top-level script) is unmappable and must surface a clear
    error rather than silently producing a bogus test path.
    """
    module = _load_check_module()
    impl_path = Path("sandbox") / "scratch" / "foo.py"
    with pytest.raises(ValueError, match=r"sandbox/scratch/foo\.py|sandbox.scratch.foo\.py"):
        _ = module._resolve_mirror_test_path(impl_path=impl_path, mirror_pairings=_core_pairings())  # noqa: SLF001


def test_resolve_test_paths_returns_empty_list_for_empty_impl_paths() -> None:
    """`_resolve_test_paths(impl_paths=[])` returns `[]` (loop-not-taken branch).

    The argparse `--paths` flag uses `nargs="+"` (required, at
    least one), so the script's `main` never invokes
    `_resolve_test_paths` with an empty list. This unit test
    exercises the loop-not-taken branch directly so per-file
    branch coverage hits 100% — coverage.py treats `for X in
    Y:` as a branch (body taken vs body not taken when Y is
    empty), and the not-taken branch is otherwise unreachable
    from the main entry path.
    """
    module = _load_check_module()
    log = module._configure_logger()  # noqa: SLF001
    test_paths = module._resolve_test_paths(  # noqa: SLF001
        impl_paths=[], mirror_pairings=_core_pairings(), log=log
    )
    assert (
        test_paths == []
    ), f"empty impl_paths should resolve to empty test_paths; got {test_paths!r}"


def test_main_fails_on_unknown_impl_tree(*, tmp_path: Path) -> None:
    """`--paths` under no recognized impl tree → exit non-zero, ValueError logged.

    The path `sandbox/scratch/foo.py` is under no
    mirror-paired source tree (livespec/, bin/, dev-tooling/checks/),
    so `_resolve_mirror_test_path` raises ValueError. The
    script's `main` catches that, logs the diagnostic with
    `check_id` semantics implicit in the structlog event name,
    and returns 1. Pins the ValueError-catch branch in the
    helper.
    """
    _ = tmp_path
    result = subprocess.run(
        [sys.executable, str(_CHECK_PATH), "--paths", "sandbox/scratch/foo.py"],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0, (
        f"check_coverage_incremental should exit non-zero on unknown impl tree; "
        f"got returncode={result.returncode} stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert "could not resolve" in combined or "not under" in combined, (
        f"diagnostic does not surface the resolution failure; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_main_fails_when_mirror_test_does_not_exist(*, tmp_path: Path) -> None:
    """`--paths` whose mirror-pair points at a non-existent test file → exit non-zero.

    Uses a synthetic impl path under `livespec_dev_tooling/checks/`
    (the source tree this library declares in its own
    `[tool.livespec_dev_tooling].mirror_pairings`) that does NOT
    have a corresponding test file at
    `tests/livespec_dev_tooling/checks/test_<name>.py`. Mirror-pair
    resolution succeeds (the path is under the configured tree),
    but `test_path.is_file()` returns False because no such test
    exists in the real repo. Pins the `if not test_path.is_file()`
    branch.
    """
    _ = tmp_path
    result = subprocess.run(
        [
            sys.executable,
            str(_CHECK_PATH),
            "--paths",
            "livespec_dev_tooling/checks/synthesized_nonexistent_xyz.py",
        ],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0, (
        f"check_coverage_incremental should exit non-zero when mirror test missing; "
        f"got returncode={result.returncode} stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert "mirror" in combined.lower() and "does not exist" in combined.lower(), (
        f"diagnostic does not surface the missing-mirror message; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_main_passes_against_fully_covered_real_repo_pair(*, tmp_path: Path) -> None:
    """End-to-end: invoke the check against `livespec_dev_tooling/checks/all_declared.py`.

    `livespec_dev_tooling/checks/all_declared.py` +
    `tests/livespec_dev_tooling/checks/test_all_declared.py` is a
    known-fully-covered real-repo mirror pair. The check is
    invoked with cwd=_REPO_ROOT (the script reads
    `<cwd>/<impl_path>` so cwd MUST be the repo root) and
    `--paths livespec_dev_tooling/checks/all_declared.py`.
    Expected: exit 0 and no error diagnostics in stderr.

    The `tmp_path` fixture is unused for the assertion but
    accepted to keep the signature consistent with the rest
    of the test suite (and to avoid pytest's
    `pytest_configure` complaining about unused fixtures).
    """
    _ = tmp_path  # signature parity; cwd MUST be the real repo root for the pytest run

    result = subprocess.run(
        [
            sys.executable,
            str(_CHECK_PATH),
            "--paths",
            "livespec_dev_tooling/checks/all_declared.py",
        ],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, (
        f"check_coverage_incremental should pass against fully-covered all_declared pair; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


# ---------------------------------------------------------------------------
# Epic li-cvaudit (cvnoarg): with NO --paths, the check derives the changed
# impl-file list from `git diff --name-only origin/master...HEAD` (filtered
# to `.py` files under the configured source-tree prefixes) and runs against
# them, instead of no-op'ing. An explicit --paths still behaves as before.
# ---------------------------------------------------------------------------


def test_changed_py_impl_paths_filters_to_source_prefixes() -> None:
    """`_changed_py_impl_paths` keeps only `.py` files under a source-tree prefix."""
    module = _load_check_module()
    diff_output = "\n".join(
        [
            "livespec_dev_tooling/checks/foo.py",  # kept
            "livespec_dev_tooling/checks/bar.py",  # kept
            "tests/livespec_dev_tooling/checks/test_foo.py",  # dropped (not a source prefix)
            "README.md",  # dropped (not .py)
            "livespec_dev_tooling/checks/baz.txt",  # dropped (not .py)
            "",  # dropped (blank line)
        ]
    )
    result = module._changed_py_impl_paths(  # noqa: SLF001
        diff_output=diff_output,
        source_tree_prefixes=("livespec_dev_tooling/",),
    )
    assert result == [
        Path("livespec_dev_tooling/checks/foo.py"),
        Path("livespec_dev_tooling/checks/bar.py"),
    ], f"unexpected filtered set: {result!r}"


def test_changed_py_impl_paths_empty_when_no_match() -> None:
    """No `.py` impl file in the diff → empty list (the no-op-after-derive case)."""
    module = _load_check_module()
    diff_output = "README.md\ndocs/guide.md\n"
    result = module._changed_py_impl_paths(  # noqa: SLF001
        diff_output=diff_output,
        source_tree_prefixes=("livespec_dev_tooling/",),
    )
    assert result == [], f"expected empty list; got {result!r}"


def _isolated_git_env() -> dict[str, str]:
    """Inherited env with every `GIT_*` var stripped.

    pytest may be launched with `GIT_DIR`/`GIT_INDEX_FILE`/`GIT_WORK_TREE`
    set (notably when the suite runs inside a git commit hook). If those
    leak into a `subprocess.run(["git", ...], cwd=tmp_path)` call, git
    targets the OUTER worktree's index instead of the tmp repo's,
    corrupting the real checkout's staging area. Stripping `GIT_*` keeps
    each tmp-repo operation scoped to its own `cwd`.
    """
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


def _git_in(*, tmp_path: Path, args: tuple[str, ...]) -> None:
    subprocess.run(
        ["git", *args],
        cwd=str(tmp_path),
        check=True,
        capture_output=True,
        text=True,
        env=_isolated_git_env(),
    )


def _init_tmp_repo(*, tmp_path: Path, with_mirror_pairing: bool) -> None:
    """Init a tmp git repo + baseline commit + `origin/master` tracking ref."""
    _git_in(tmp_path=tmp_path, args=("init", "-q"))
    _git_in(tmp_path=tmp_path, args=("config", "user.email", "test@example.com"))
    _git_in(tmp_path=tmp_path, args=("config", "user.name", "Test"))
    _git_in(tmp_path=tmp_path, args=("config", "commit.gpgsign", "false"))
    pairing = (
        'mirror_pairings = [{ source_tree = "livespec_dev_tooling", '
        'test_tree = "tests/livespec_dev_tooling" }]\n'
        if with_mirror_pairing
        else ""
    )
    (tmp_path / "pyproject.toml").write_text(
        '[tool.livespec_dev_tooling]\nsource_tree_prefixes = ["livespec_dev_tooling/"]\n' + pairing,
        encoding="utf-8",
    )
    _git_in(tmp_path=tmp_path, args=("add", "-A"))
    _git_in(tmp_path=tmp_path, args=("commit", "-qm", "baseline"))
    # Simulate the remote tracking ref without a real remote.
    _git_in(tmp_path=tmp_path, args=("update-ref", "refs/remotes/origin/master", "HEAD"))


def _commit_changed_impl(*, tmp_path: Path, with_mirror_test: bool) -> None:
    """Add a changed impl `.py` (and optionally its mirror test) on a feature commit."""
    impl = tmp_path / "livespec_dev_tooling" / "checks" / "derived_mod.py"
    impl.parent.mkdir(parents=True, exist_ok=True)
    impl.write_text(
        "from __future__ import annotations\n\n__all__ = ['v']\n\nv = 1\n",
        encoding="utf-8",
    )
    if with_mirror_test:
        test = tmp_path / "tests" / "livespec_dev_tooling" / "checks" / "test_derived_mod.py"
        test.parent.mkdir(parents=True, exist_ok=True)
        test.write_text(
            "from __future__ import annotations\n\n__all__: list[str] = []\n",
            encoding="utf-8",
        )
    _git_in(tmp_path=tmp_path, args=("add", "-A"))
    _git_in(tmp_path=tmp_path, args=("commit", "-qm", "add derived_mod"))


def test_derive_paths_from_git_surfaces_changed_impl(*, tmp_path: Path) -> None:
    """`_derive_paths_from_git` reads the git diff and returns the changed impl path."""
    _init_tmp_repo(tmp_path=tmp_path, with_mirror_pairing=True)
    _commit_changed_impl(tmp_path=tmp_path, with_mirror_test=True)
    module = _load_check_module()
    derived = module._derive_paths_from_git(  # noqa: SLF001
        source_tree_prefixes=("livespec_dev_tooling/",),
        cwd=tmp_path,
    )
    assert derived == [
        Path("livespec_dev_tooling/checks/derived_mod.py")
    ], f"expected the changed impl path; got {derived!r}"


def test_main_no_args_no_changed_impl_exits_zero(*, tmp_path: Path) -> None:
    """No `--paths` and an empty derived set → exit 0 (nothing to gate).

    A fresh git repo whose HEAD == origin/master has no diff, so the
    derived impl-path list is empty and the check no-ops with a
    diagnostic, exiting 0.
    """
    _init_tmp_repo(tmp_path=tmp_path, with_mirror_pairing=False)

    result = subprocess.run(
        [sys.executable, str(_CHECK_PATH)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
        env=_isolated_git_env(),
    )
    assert result.returncode == 0, (
        f"no-arg derive with empty diff should exit 0; "
        f"got returncode={result.returncode} stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert (
        "no changed" in combined.lower()
    ), f"empty-derive path should log a 'no changed' diagnostic; stderr={result.stderr!r}"


def test_main_no_args_nonempty_derive_runs_gate(*, tmp_path: Path) -> None:
    """No `--paths` + a non-empty derived set → falls through to the per-file gate.

    The derived impl `livespec_dev_tooling/checks/derived_mod.py` has NO
    mirror test in this tmp repo, so `_resolve_test_paths` returns None and
    the check exits 1 — proving the no-arg path fell through past the
    empty-derive short-circuit into the downstream gate (the `253->260`
    fall-through branch in `main`).
    """
    _init_tmp_repo(tmp_path=tmp_path, with_mirror_pairing=True)
    _commit_changed_impl(tmp_path=tmp_path, with_mirror_test=False)

    result = subprocess.run(
        [sys.executable, str(_CHECK_PATH)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
        env=_isolated_git_env(),
    )
    assert result.returncode != 0, (
        f"no-arg derive with a changed impl lacking a mirror test should exit non-zero; "
        f"got returncode={result.returncode} stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert (
        "does not exist" in combined.lower()
    ), f"fall-through should reach the missing-mirror diagnostic; stderr={result.stderr!r}"
