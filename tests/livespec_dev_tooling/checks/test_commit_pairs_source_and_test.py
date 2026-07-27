"""Outside-in test for `dev-tooling/checks/commit_pairs_source_and_test.py` — commit-pair gate.

Every commit modifying any `.claude-plugin/scripts/livespec/**`,
`.claude-plugin/scripts/bin/**`, or `<repo-root>/dev-tooling/
checks/**` source file MUST also modify a `tests/**` file in the
same commit. Lefthook pre-commit gate, NOT in `just check`
aggregate.

Pre-commit hooks run BEFORE the commit lands and inspect the
STAGED state. The check therefore reads `git diff --cached
--name-only` (or equivalent) to enumerate files staged for the
imminent commit, applies the source-file filter, and verifies
the test-file co-staging.

Cycle 1 pins the bare rejection: a synthetic git repo with a
staged `.claude-plugin/scripts/livespec/foo/bar.py` change but
NO staged `tests/**` change makes the check exit non-zero with
the offending source path surfaced. Subsequent cycles will
pin the carve-outs (refactor: prefix, ## Type: lines, config-
only filenames, deletion-only) and the accept case (source +
test co-staged).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[3]
_COMMIT_PAIRS_SOURCE_AND_TEST = (
    _REPO_ROOT / "livespec_dev_tooling" / "checks" / "commit_pairs_source_and_test.py"
)


# Vars git sets when invoking hooks (lefthook pre-commit / pre-push /
# commit-msg). Inherited by subprocess children unless scrubbed, which
# would otherwise redirect the check script's internal `git diff
# --cached` to the SURROUNDING repo instead of the tmp_path mini-repo
# the test constructs. Mirrors the discipline already established in
# `test_primary_checkout_commit_refuse_hook_installed.py`.
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


def _scrubbed_env() -> dict[str, str]:
    """Return a copy of `os.environ` with GIT_* hook vars removed."""
    return {k: v for k, v in os.environ.items() if k not in _GIT_ENV_PASSTHROUGH_VARS}


def _git(*, cwd: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    # S603/S607: argv is a fixed list (literal git binary + repo-controlled
    # args); bare `git` is the canonical invocation per system PATH;
    # no untrusted shell input.
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
        env={"HOME": str(cwd), "GIT_CONFIG_GLOBAL": "/dev/null", "PATH": "/usr/bin:/bin"},
    )


def test_commit_pairs_rejects_staged_source_without_staged_test(*, tmp_path: Path) -> None:
    """A staged `livespec/foo/bar.py` with no staged tests/ change fails the check.

    Fixture: a fresh git repo with one baseline commit (so HEAD
    exists). A `livespec/foo/bar.py` source file is created and
    staged for the next commit. NO `tests/**` file is staged.
    The check, invoked with `cwd=tmp_path`, inspects the staged
    state, detects a source-file change without a paired
    test-file change, exits non-zero, and surfaces the offending
    source path in its diagnostic.
    """
    _git(cwd=tmp_path, args=["init", "-q"])
    _git(cwd=tmp_path, args=["config", "user.email", "test@example.com"])
    _git(cwd=tmp_path, args=["config", "user.name", "Test"])
    # Baseline commit so HEAD exists.
    (tmp_path / "README.md").write_text("baseline\n", encoding="utf-8")
    _git(cwd=tmp_path, args=["add", "README.md"])
    _git(cwd=tmp_path, args=["commit", "-m", "baseline"])

    # Stage a source file change without staging any tests.
    package_dir = tmp_path / ".claude-plugin" / "scripts" / "livespec" / "foo"
    package_dir.mkdir(parents=True)
    source = package_dir / "bar.py"
    source.write_text(
        "from __future__ import annotations\n__all__: list[str] = []\nx = 0\n",
        encoding="utf-8",
    )
    _git(cwd=tmp_path, args=["add", ".claude-plugin/scripts/livespec/foo/bar.py"])

    # S603: argv is a fixed list (sys.executable + repo-controlled
    # script path); no untrusted shell input.
    result = subprocess.run(
        [sys.executable, str(_COMMIT_PAIRS_SOURCE_AND_TEST)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
        env=_scrubbed_env(),
    )

    assert result.returncode != 0, (
        f"commit_pairs_source_and_test should reject staged source without staged test "
        f"with non-zero exit; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    expected_token = ".claude-plugin/scripts/livespec/foo/bar.py"
    assert expected_token in combined, (
        f"commit_pairs_source_and_test diagnostic does not surface offending source path "
        f"`{expected_token}`; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_commit_pairs_skips_when_head_has_unpaired_red_trailers(
    *,
    tmp_path: Path,
) -> None:
    """A staged source-only commit with HEAD carrying unpaired Red trailers passes the check.

    Per v034 D2-D3 amend-pattern coexistence (cycle 2.7): when
    HEAD's commit message contains `TDD-Red-Test-File-Checksum:`
    WITHOUT `TDD-Green-Verified-At:`, the next operation is
    structurally guaranteed to be `git commit --amend` adding the
    impl. During that amend, `git diff --cached --name-only`
    shows only the impl (the Red commit's test is in HEAD,
    unchanged). The check skips itself; pairing is enforced by
    v034 D3's replay hook at the commit-msg stage.

    Fixture: fresh git repo with HEAD's commit message carrying a
    Red trailer (mocking the Red commit's state). A
    source file is staged WITHOUT a test file. The check, invoked
    with `cwd=tmp_path`, detects HEAD's amend-pending state and
    exits 0 (skip).
    """
    _git(cwd=tmp_path, args=["init", "-q"])
    _git(cwd=tmp_path, args=["config", "user.email", "test@example.com"])
    _git(cwd=tmp_path, args=["config", "user.name", "Test"])
    # Baseline + a Red commit (its message carries the Red trailer).
    (tmp_path / "README.md").write_text("baseline\n", encoding="utf-8")
    _git(cwd=tmp_path, args=["add", "README.md"])
    _git(cwd=tmp_path, args=["commit", "-m", "baseline"])
    test_dir = tmp_path / "tests" / "livespec" / "foo"
    test_dir.mkdir(parents=True)
    (test_dir / "test_bar.py").write_text(
        "from __future__ import annotations\n__all__: list[str] = []\n"
        "def test_bar() -> None:\n    assert True\n",
        encoding="utf-8",
    )
    _git(cwd=tmp_path, args=["add", "tests/livespec/foo/test_bar.py"])
    red_commit_message = (
        "feat: foo bar\n\nRed commit body.\n\n"
        "TDD-Red-Test: tests/livespec/foo/test_bar.py\n"
        "TDD-Red-Test-File-Checksum: sha256:0000000000000000000000000000000000000000000000000000000000000000\n"
    )
    _git(cwd=tmp_path, args=["commit", "-m", red_commit_message])

    # Now stage an impl file (the Green amend's content).
    package_dir = tmp_path / ".claude-plugin" / "scripts" / "livespec" / "foo"
    package_dir.mkdir(parents=True)
    (package_dir / "bar.py").write_text(
        "from __future__ import annotations\n__all__: list[str] = []\nx = 0\n",
        encoding="utf-8",
    )
    _git(cwd=tmp_path, args=["add", ".claude-plugin/scripts/livespec/foo/bar.py"])

    # S603: argv is a fixed list (sys.executable + repo-controlled script path).
    result = subprocess.run(
        [sys.executable, str(_COMMIT_PAIRS_SOURCE_AND_TEST)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
        env=_scrubbed_env(),
    )

    assert result.returncode == 0, (
        f"commit_pairs should skip when HEAD has unpaired Red trailers; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_commit_pairs_applies_when_head_has_paired_red_and_green_trailers(
    *,
    tmp_path: Path,
) -> None:
    """A staged source-only commit with HEAD carrying Red+Green trailers fails the check.

    After a Green amend lands, HEAD carries BOTH `TDD-Red-*` and
    `TDD-Green-*` trailers — the "complete" state. The next
    commit isn't an amend; it's a fresh top-of-branch commit. The
    check resumes normal enforcement: source-without-paired-test
    is rejected.
    """
    _git(cwd=tmp_path, args=["init", "-q"])
    _git(cwd=tmp_path, args=["config", "user.email", "test@example.com"])
    _git(cwd=tmp_path, args=["config", "user.name", "Test"])
    (tmp_path / "README.md").write_text("baseline\n", encoding="utf-8")
    _git(cwd=tmp_path, args=["add", "README.md"])
    _git(cwd=tmp_path, args=["commit", "-m", "baseline"])
    test_dir = tmp_path / "tests" / "livespec" / "foo"
    test_dir.mkdir(parents=True)
    (test_dir / "test_bar.py").write_text(
        "from __future__ import annotations\n__all__: list[str] = []\n"
        "def test_bar() -> None:\n    assert True\n",
        encoding="utf-8",
    )
    _git(cwd=tmp_path, args=["add", "tests/livespec/foo/test_bar.py"])
    paired_commit_message = (
        "feat: foo bar\n\nRed+Green pair body.\n\n"
        "TDD-Red-Test: tests/livespec/foo/test_bar.py\n"
        "TDD-Red-Test-File-Checksum: sha256:0000000000000000000000000000000000000000000000000000000000000000\n"
        "TDD-Green-Verified-At: 2026-05-02T00:00:00Z\n"
    )
    _git(cwd=tmp_path, args=["commit", "-m", paired_commit_message])

    # Now stage a source-only change for a NEW commit (not an amend).
    package_dir = tmp_path / ".claude-plugin" / "scripts" / "livespec" / "foo"
    package_dir.mkdir(parents=True)
    (package_dir / "bar.py").write_text(
        "from __future__ import annotations\n__all__: list[str] = []\nx = 0\n",
        encoding="utf-8",
    )
    _git(cwd=tmp_path, args=["add", ".claude-plugin/scripts/livespec/foo/bar.py"])

    # S603: argv is a fixed list (sys.executable + repo-controlled script path).
    result = subprocess.run(
        [sys.executable, str(_COMMIT_PAIRS_SOURCE_AND_TEST)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
        env=_scrubbed_env(),
    )

    assert result.returncode != 0, (
        f"commit_pairs should reject source-only when HEAD has paired Red+Green trailers; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_commit_pairs_skips_on_empty_repo_with_no_head() -> None:
    """On a fresh repo with zero commits, the head-message lookup falls back gracefully.

    Drives the `result.returncode != 0` early-return in
    `_head_has_unpaired_red_trailers`: `git log -1`
    exits non-zero on a repo with no commits, the function
    returns False (no Red trailers), and the check applies its
    normal source-vs-test enforcement.

    Fixture: fresh git repo with NO commits AND no staged files
    in the source/test trees. The check exits 0 (no source
    changes = passes the existing source-vs-test logic).
    """
    import tempfile

    with tempfile.TemporaryDirectory() as raw_dir:
        empty_repo = Path(raw_dir)
        _git(cwd=empty_repo, args=["init", "-q"])
        _git(cwd=empty_repo, args=["config", "user.email", "test@example.com"])
        _git(cwd=empty_repo, args=["config", "user.name", "Test"])
        # Stage a non-source file so `_staged_files` has something
        # to enumerate but the source-tree filter returns an empty
        # list (no rejection).
        (empty_repo / "README.md").write_text("seed\n", encoding="utf-8")
        _git(cwd=empty_repo, args=["add", "README.md"])

        # S603: argv is a fixed list (sys.executable + repo-controlled
        # script path); no untrusted shell input.
        result = subprocess.run(
            [sys.executable, str(_COMMIT_PAIRS_SOURCE_AND_TEST)],
            cwd=str(empty_repo),
            capture_output=True,
            text=True,
            check=False,
            env=_scrubbed_env(),
        )

    assert result.returncode == 0, (
        f"commit_pairs should accept empty repo with no source changes; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_commit_pairs_module_importable_without_running_main() -> None:
    """The check module imports cleanly without invoking main().

    Closes two branch-coverage gaps in
    `commit_pairs_source_and_test.py`:
      - 100->exit: when the module is imported (not run as
        `python3 dev-tooling/checks/commit_pairs_source_and_test.py`),
        `__name__` is the module-qualified path, NOT `"__main__"`,
        so the `raise SystemExit(main())` line is skipped — the
        else-arm of `if __name__ == "__main__":` is taken.
      - 42->45: the `if str(_VENDOR_DIR) not in sys.path:` guard
        is taken on second import (the test runner already added
        _VENDOR_DIR via pytest's pythonpath config), so the body
        (`sys.path.insert(...)`) is skipped — the
        already-present branch is exercised.

    Pins the invocation contract that this script is BOTH usable
    as a CLI (`python3 dev-tooling/checks/commit_pairs_source_and_test.py`)
    AND importable for testing without running its main(). Tests
    of the rejection / accept cases above invoke via subprocess to
    pin the CLI path; this test pins the import path.
    """
    import importlib.util

    module_path = (
        Path(__file__).resolve().parents[3]
        / "livespec_dev_tooling"
        / "checks"
        / "commit_pairs_source_and_test.py"
    )
    spec = importlib.util.spec_from_file_location(
        "commit_pairs_source_and_test_for_import_test",
        str(module_path),
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module.main), "main should be importable without invocation"


def test_commit_pairs_accepts_staged_source_with_staged_test(*, tmp_path: Path) -> None:
    """A staged source change paired with a staged tests/ change passes the check.

    Pass-case companion to the rejection test. Fixture: fresh git
    repo with one baseline commit. A source file under
    `.claude-plugin/scripts/livespec/foo/bar.py` AND a paired
    test under `tests/livespec/foo/test_bar.py` are co-staged. The
    check, invoked with `cwd=tmp_path`, inspects the staged state,
    finds both a source-tree file AND a tests/-tree file in the
    same commit, and exits 0 (success).

    Drives the success-path return on (`return 0`) and
    closes the load-bearing branch coverage gap: only the
    rejection arm has been exercised; the accept arm has been
    silently unreachable from the test suite.
    """
    _git(cwd=tmp_path, args=["init", "-q"])
    _git(cwd=tmp_path, args=["config", "user.email", "test@example.com"])
    _git(cwd=tmp_path, args=["config", "user.name", "Test"])
    (tmp_path / "README.md").write_text("baseline\n", encoding="utf-8")
    _git(cwd=tmp_path, args=["add", "README.md"])
    _git(cwd=tmp_path, args=["commit", "-m", "baseline"])

    # Stage source AND test together — the canonical Red→Green
    # pair pattern this gate is designed to enforce.
    package_dir = tmp_path / ".claude-plugin" / "scripts" / "livespec" / "foo"
    package_dir.mkdir(parents=True)
    source = package_dir / "bar.py"
    source.write_text(
        "from __future__ import annotations\n__all__: list[str] = []\nx = 0\n",
        encoding="utf-8",
    )
    test_dir = tmp_path / "tests" / "livespec" / "foo"
    test_dir.mkdir(parents=True)
    test_file = test_dir / "test_bar.py"
    test_file.write_text(
        "from __future__ import annotations\n__all__: list[str] = []\n"
        "def test_bar() -> None:\n    assert True\n",
        encoding="utf-8",
    )
    _git(cwd=tmp_path, args=["add", ".claude-plugin/scripts/livespec/foo/bar.py"])
    _git(cwd=tmp_path, args=["add", "tests/livespec/foo/test_bar.py"])

    # S603: argv is a fixed list (sys.executable + repo-controlled script path).
    result = subprocess.run(
        [sys.executable, str(_COMMIT_PAIRS_SOURCE_AND_TEST)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
        env=_scrubbed_env(),
    )

    assert result.returncode == 0, (
        f"commit_pairs_source_and_test should accept staged source + paired test "
        f"with exit 0; got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


_CARRIER_PYPROJECT = """\
[tool.livespec_dev_tooling]
source_tree_prefixes = [".claude-plugin/hooks/"]
neutral_hook_body_path = ".claude-plugin/hooks/no_shadow_ledger.py"
"""


def _init_carrier_repo(*, tmp_path: Path) -> None:
    """A mini-repo whose source tree CONTAINS the declared carrier body.

    Both role keys are declared deliberately. `load_config` uses a flat
    `Config()` baseline once a `[tool.livespec_dev_tooling]` block is
    present, so a fixture declaring `neutral_hook_body_path` ALONE would
    leave `source_tree_prefixes` empty — the carrier would not be
    classified as a source file at all and the exemption assertion would
    pass VACUOUSLY, proving nothing. Declaring the prefix too is what
    makes the carrier a genuine source-tree member that the check must
    exempt on purpose rather than overlook.
    """
    _git(cwd=tmp_path, args=["init", "-q"])
    _git(cwd=tmp_path, args=["config", "user.email", "test@example.com"])
    _git(cwd=tmp_path, args=["config", "user.name", "Test"])
    (tmp_path / "pyproject.toml").write_text(_CARRIER_PYPROJECT, encoding="utf-8")
    (tmp_path / "README.md").write_text("baseline\n", encoding="utf-8")
    _git(cwd=tmp_path, args=["add", "pyproject.toml", "README.md"])
    _git(cwd=tmp_path, args=["commit", "-m", "baseline"])
    (tmp_path / ".claude-plugin" / "hooks").mkdir(parents=True)


def test_commit_pairs_exempts_the_declared_neutral_hook_body(*, tmp_path: Path) -> None:
    """The declared carrier body may be re-rendered with no paired test change.

    The neutral no-shadow-ledger body is a GENERATED carrier: it is
    installed verbatim from the packaged
    `CANONICAL_NO_SHADOW_LEDGER_BODY` by `just
    install-no-shadow-ledger`, never hand-authored in the consumer, and
    already gated for byte-identity by
    `check-no-shadow-ledger-body-identical`.

    When the producer changes that constant, every consumer MUST
    re-render its copy in the SAME commit that moves the dev-tooling pin
    (the body alone would be compared against the old canonical, the pin
    alone against the new one). Such a commit touches no `tests/**` file
    BY CONSTRUCTION, so the unexempted pairing rule refused it and the
    carrier change could be propagated neither by the pin-only fan-out
    NOR by hand — livespec-driver-claude and livespec-driver-codex were
    both stalled on exactly this at dev-tooling v0.54.0.

    Staging ONLY the declared carrier, with no `tests/` companion, must
    therefore exit 0.
    """
    _init_carrier_repo(tmp_path=tmp_path)
    carrier = tmp_path / ".claude-plugin" / "hooks" / "no_shadow_ledger.py"
    carrier.write_text(
        "from __future__ import annotations\n__all__: list[str] = []\nx = 1\n",
        encoding="utf-8",
    )
    _git(cwd=tmp_path, args=["add", ".claude-plugin/hooks/no_shadow_ledger.py"])

    # S603: argv is a fixed list (sys.executable + repo-controlled script path).
    result = subprocess.run(
        [sys.executable, str(_COMMIT_PAIRS_SOURCE_AND_TEST)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
        env=_scrubbed_env(),
    )

    assert result.returncode == 0, (
        f"commit_pairs_source_and_test must exempt the declared "
        f"neutral_hook_body_path and exit 0; got "
        f"returncode={result.returncode} stdout={result.stdout!r} "
        f"stderr={result.stderr!r}"
    )


def test_commit_pairs_exemption_does_not_widen_to_the_carrier_sibling(*, tmp_path: Path) -> None:
    """The exemption is path-scoped, NOT prefix-wide — a sibling still fails.

    Non-vacuity guard for the test above. The carrier lives INSIDE a
    declared source-tree prefix, so an exemption implemented as "skip the
    prefix" (rather than "skip exactly the declared path") would also pass
    that test while silently disarming the pairing gate for every
    hand-authored hook beside it.

    A DIFFERENT `.py` under the SAME prefix, staged with no `tests/`
    companion, must therefore still be rejected with exit 1.
    """
    _init_carrier_repo(tmp_path=tmp_path)
    sibling = tmp_path / ".claude-plugin" / "hooks" / "block_auto_memory.py"
    sibling.write_text(
        "from __future__ import annotations\n__all__: list[str] = []\ny = 2\n",
        encoding="utf-8",
    )
    _git(cwd=tmp_path, args=["add", ".claude-plugin/hooks/block_auto_memory.py"])

    # S603: argv is a fixed list (sys.executable + repo-controlled script path).
    result = subprocess.run(
        [sys.executable, str(_COMMIT_PAIRS_SOURCE_AND_TEST)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
        env=_scrubbed_env(),
    )

    assert result.returncode == 1, (
        f"a non-carrier sibling under the same source prefix must still be "
        f"rejected with exit 1; got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


# A source module carrying a module docstring, an inline comment, a class with
# a method docstring, and a plain function with NO docstring — the fixture the
# docs-only carve-out (livespec-dev-tooling-5eow) tests re-stage with edits.
_CARVEOUT_HEAD_SOURCE = (
    '"""Module docstring — original."""\n'
    "from __future__ import annotations\n\n"
    "__all__: list[str] = []\n\n"
    "X = 1  # original inline comment\n\n\n"
    "class Foo:\n"
    '    """Class docstring — original."""\n\n'
    "    def method(self) -> int:\n"
    '        """Method docstring — original."""\n'
    "        return X\n\n\n"
    "def bare() -> int:\n"
    "    return X + 1\n"
)
_CARVEOUT_SOURCE_REL = ".claude-plugin/scripts/livespec/foo/bar.py"


def _init_repo_with_committed_source(*, tmp_path: Path, body: str) -> Path:
    """Init a repo, commit `body` at `_CARVEOUT_SOURCE_REL`, and return its abs path."""
    _git(cwd=tmp_path, args=["init", "-q"])
    _git(cwd=tmp_path, args=["config", "user.email", "test@example.com"])
    _git(cwd=tmp_path, args=["config", "user.name", "Test"])
    package_dir = tmp_path / ".claude-plugin" / "scripts" / "livespec" / "foo"
    package_dir.mkdir(parents=True)
    source = package_dir / "bar.py"
    source.write_text(body, encoding="utf-8")
    _git(cwd=tmp_path, args=["add", _CARVEOUT_SOURCE_REL])
    _git(cwd=tmp_path, args=["commit", "-m", "baseline with source"])
    return source


def _run_check(*, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    """Invoke the commit-pairs check as a CLI with `cwd=tmp_path`."""
    # S603: argv is a fixed list (sys.executable + repo-controlled script path).
    return subprocess.run(
        [sys.executable, str(_COMMIT_PAIRS_SOURCE_AND_TEST)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
        env=_scrubbed_env(),
    )


def test_commit_pairs_carveout_allows_docs_only_source_change(*, tmp_path: Path) -> None:
    """A comments+docstring-only source edit with no staged test passes (5eow carve-out).

    Fixture: a source file committed to HEAD, then re-staged with ONLY its
    module, class, and method docstrings and its inline comment changed (and a
    method docstring grown to several lines) — no logical-code change — and NO
    `tests/` file co-staged. The check reads both the HEAD and the staged
    (index) versions, strips every module/class/function docstring from each,
    finds the docstring-stripped ASTs identical, and waives the pairing
    requirement, exiting 0. Comments never reach the AST; docstrings do, so
    stripping them is what makes a docstring-only edit compare equal.
    """
    source = _init_repo_with_committed_source(tmp_path=tmp_path, body=_CARVEOUT_HEAD_SOURCE)

    staged_body = (
        '"""Module docstring — REWORDED for clarity."""\n'
        "from __future__ import annotations\n\n"
        "__all__: list[str] = []\n\n"
        "X = 1  # a different inline comment\n\n\n"
        "class Foo:\n"
        '    """Class docstring — REWORDED."""\n\n'
        "    def method(self) -> int:\n"
        '        """Method docstring — REWORDED, now spanning\n\n'
        "        several lines of prose that live only in the\n"
        "        docstring and change no logical code.\n"
        '        """\n'
        "        return X\n\n\n"
        "def bare() -> int:\n"
        "    return X + 1\n"
    )
    source.write_text(staged_body, encoding="utf-8")
    _git(cwd=tmp_path, args=["add", _CARVEOUT_SOURCE_REL])

    result = _run_check(tmp_path=tmp_path)

    assert result.returncode == 0, (
        f"docs-only source change (comments + docstrings only) should pass the "
        f"carve-out with exit 0; got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_commit_pairs_carveout_rejects_real_source_change(*, tmp_path: Path) -> None:
    """A real (logical-code) source edit with no staged test is still rejected.

    The carve-out is content-keyed: a change touching anything beyond comments
    and docstrings re-arms the pairing requirement. Fixture: the source file in
    HEAD re-staged with a changed constant (`X = 1` → `X = 2`) and no `tests/`
    co-stage. The docstring-stripped ASTs differ, so the check rejects with
    exit 1 and surfaces the offending source path.
    """
    source = _init_repo_with_committed_source(tmp_path=tmp_path, body=_CARVEOUT_HEAD_SOURCE)
    source.write_text(_CARVEOUT_HEAD_SOURCE.replace("X = 1", "X = 2"), encoding="utf-8")
    _git(cwd=tmp_path, args=["add", _CARVEOUT_SOURCE_REL])

    result = _run_check(tmp_path=tmp_path)

    assert result.returncode != 0, (
        f"a real code change should re-arm the pairing requirement (exit non-zero); "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert _CARVEOUT_SOURCE_REL in combined, (
        f"the rejection diagnostic should surface the offending source path "
        f"`{_CARVEOUT_SOURCE_REL}`; stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_commit_pairs_carveout_fails_closed_on_staged_deletion(*, tmp_path: Path) -> None:
    """A staged deletion of a source file falls back to the pairing requirement.

    A deletion has no staged (index, stage-0) blob, so `_git_blob(":<path>")`
    fails and `_is_docs_only_change` returns False (fail closed). Fixture: the
    source file committed to HEAD, then `git rm`'d (staging the deletion) with
    no `tests/` co-stage. The check rejects with exit 1 rather than treating a
    removed file as a docs-only edit.
    """
    _init_repo_with_committed_source(tmp_path=tmp_path, body=_CARVEOUT_HEAD_SOURCE)
    _git(cwd=tmp_path, args=["rm", "-q", _CARVEOUT_SOURCE_REL])

    result = _run_check(tmp_path=tmp_path)

    assert result.returncode != 0, (
        f"a staged deletion should fail closed to the pairing requirement (exit "
        f"non-zero); got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_commit_pairs_carveout_fails_closed_when_staged_unparseable(*, tmp_path: Path) -> None:
    """A staged version that does not parse falls back to the pairing requirement.

    `_dump_without_docstrings` returns None when `ast.parse` raises, so
    `_is_docs_only_change` returns False (fail closed). Fixture: a valid source
    file in HEAD re-staged with syntactically broken Python and no `tests/`
    co-stage. The check rejects with exit 1.
    """
    source = _init_repo_with_committed_source(tmp_path=tmp_path, body=_CARVEOUT_HEAD_SOURCE)
    source.write_text("def broken( this is not valid python\n", encoding="utf-8")
    _git(cwd=tmp_path, args=["add", _CARVEOUT_SOURCE_REL])

    result = _run_check(tmp_path=tmp_path)

    assert result.returncode != 0, (
        f"an unparseable staged version should fail closed (exit non-zero); "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_commit_pairs_carveout_fails_closed_when_head_unparseable(*, tmp_path: Path) -> None:
    """A HEAD version that does not parse falls back to the pairing requirement.

    Mirror of the staged-unparseable case for the HEAD side: `_is_docs_only_change`
    parses the HEAD blob first and returns False (fail closed) when it does not
    parse, before it even reads the staged blob. Fixture: syntactically broken
    Python committed to HEAD, re-staged with a valid version and no `tests/`
    co-stage. The check rejects with exit 1.
    """
    source = _init_repo_with_committed_source(
        tmp_path=tmp_path, body="def broken( this is not valid python\n"
    )
    source.write_text(_CARVEOUT_HEAD_SOURCE, encoding="utf-8")
    _git(cwd=tmp_path, args=["add", _CARVEOUT_SOURCE_REL])

    result = _run_check(tmp_path=tmp_path)

    assert result.returncode != 0, (
        f"an unparseable HEAD version should fail closed (exit non-zero); "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_commit_pairs_ignores_non_python_source_tree_file(*, tmp_path: Path) -> None:
    """A Markdown file under a source tree needs no paired test.

    The pairing contract is defined on Python: the mirror transform
    maps `<name>.py` to `test_<name>.py`, so a non-`.py` file has no
    paired test that could exist, and demanding one is unsatisfiable.
    The docs-only carve-out cannot rescue it either — that carve-out
    compares docstring-stripped ASTs, and a Markdown file does not
    parse as Python, so it fails closed into the very requirement it
    can never meet. Fixture: a `CLAUDE.md` under the source tree,
    staged alone with no `tests/` co-stage.
    """
    _init_repo_with_committed_source(tmp_path=tmp_path, body=_CARVEOUT_HEAD_SOURCE)
    doc = tmp_path / ".claude-plugin" / "scripts" / "livespec" / "foo" / "CLAUDE.md"
    doc.write_text("# orientation\n\nProse only — no behavior to test.\n", encoding="utf-8")
    _git(cwd=tmp_path, args=["add", ".claude-plugin/scripts/livespec/foo/CLAUDE.md"])

    result = _run_check(tmp_path=tmp_path)

    assert result.returncode == 0, (
        f"a non-Python file under a source tree should not require a paired test; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_commit_pairs_ignores_vendored_python_under_a_source_tree(*, tmp_path: Path) -> None:
    """A vendored `.py` under a source tree needs no paired test.

    `_vendor` exclusion is the fleet-wide first-party rule, not a
    local courtesy: `config.filter_first_party_py` — the canonical
    predicate behind `resolve_check_universe` — excludes any path
    carrying a `_vendor` segment, and `pyproject.toml` excludes
    `**/_vendor/**` from both ruff and pyright. Vendored code is
    upstream source the repo does not author and must not mirror
    into `tests/`, so demanding a paired test is unsatisfiable in
    exactly the way the non-Python case above is.

    Regression: vendoring `dry-python/returns` produced 115 of these
    errors, one per vendored file, making the commit unmakeable
    (livespec-dev-tooling-hh4d).
    """
    _init_repo_with_committed_source(tmp_path=tmp_path, body=_CARVEOUT_HEAD_SOURCE)
    vendored = (
        tmp_path / ".claude-plugin" / "scripts" / "livespec" / "_vendor" / "somelib" / "core.py"
    )
    vendored.parent.mkdir(parents=True, exist_ok=True)
    vendored.write_text("def upstream_helper():\n    return 1\n", encoding="utf-8")
    _git(
        cwd=tmp_path,
        args=["add", ".claude-plugin/scripts/livespec/_vendor/somelib/core.py"],
    )

    result = _run_check(tmp_path=tmp_path)

    assert result.returncode == 0, (
        f"a vendored `.py` under a source tree should not require a paired test; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_commit_pairs_vendor_exclusion_does_not_widen_to_authored_siblings(
    *, tmp_path: Path
) -> None:
    """The `_vendor` exclusion must not leak onto hand-authored source.

    Paired with the test above so the exclusion cannot silently widen
    into a hole: a file whose name merely CONTAINS the substring
    `_vendor` — but which carries no `_vendor` path SEGMENT — is
    authored source and stays gated. Without this, a substring match
    would exempt `vendor_update.py` and every sibling like it.
    """
    _init_repo_with_committed_source(tmp_path=tmp_path, body=_CARVEOUT_HEAD_SOURCE)
    authored = tmp_path / ".claude-plugin" / "scripts" / "livespec" / "_vendor_update.py"
    authored.write_text("def authored_helper():\n    return 2\n", encoding="utf-8")
    _git(cwd=tmp_path, args=["add", ".claude-plugin/scripts/livespec/_vendor_update.py"])

    result = _run_check(tmp_path=tmp_path)

    assert result.returncode == 1, (
        f"authored source merely NAMED like the vendor tree must stay gated; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
