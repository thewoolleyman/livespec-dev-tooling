"""Tests for livespec_dev_tooling/red_leg_scope.py.

`red_leg_scope` computes the set of `just check` aggregate targets to
SKIP at the Red-commit pre-commit gate, given the staged paths and the
repo's full target list. The Red gate already skips the coverage gates
(coverage is verified at the Green amend); this module additionally
trims check legs that a staged unit-test change cannot affect
(structurally orthogonal legs such as livespec's e2e-mock / prompts /
doctor-static), keyed by staged-path CLASS. Per work-item
livespec-dev-tooling-7us.6 and the just-check-performance research
(archive/research/justcheck-performance/baseline-and-research.md §(2),
proposed item #4).

HARD INVARIANT this module preserves: it NEVER touches the
red_green_replay commit-msg hook. The staged-test-MUST-fail semantics
and the recorded TDD-Red-* trailer evidence are produced entirely by
livespec_dev_tooling/checks/red_green_replay.py + _red_green_replay_modes.py,
which this changeset leaves byte-for-byte unmodified. The scope
reduction only trims orthogonal aggregate legs at the pre-commit gate;
it changes nothing about whether the staged test runs or how its
failure is recorded. test_red_green_replay_hook_unmodified pins that.

Pure-function tests import red_mode_skip_targets directly; the CLI
`main()` path is exercised via a subprocess against a throwaway git
repo (mirroring the green_token / parallel_check_dispatcher test
style).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from livespec_dev_tooling.red_leg_scope import (
    _COVERAGE_GATES,
    _ORTHOGONAL_LEGS,
    red_mode_skip_targets,
)

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MODULE = _REPO_ROOT / "livespec_dev_tooling" / "red_leg_scope.py"

# The two coverage gates the Red leg has always skipped (verified at the
# Green amend). Kept as the byte-identical floor of the skip set.
_DEVTOOLING_TARGETS = (
    "check-lint",
    "check-types",
    "check-coverage",
    "check-per-file-coverage",
)

# A representative livespec target list carrying the three orthogonal
# legs the item names (e2e-mock / prompts / doctor-static). dev-tooling
# itself has none of these targets, so this is the cross-repo (post
# pin-bump) consumer's shape.
_LIVESPEC_TARGETS = (
    "check-types",
    "check-coverage",
    "check-per-file-coverage",
    "check-doctor-static",
    "check-prompts",
    "e2e-test-claude-code-mock",
)


# ---------------------------------------------------------------------------
# Table well-formedness
# ---------------------------------------------------------------------------


def test_orthogonal_legs_table_is_nonempty_and_prefix_keyed() -> None:
    """_ORTHOGONAL_LEGS maps target names to non-empty input-prefix tuples."""
    assert _ORTHOGONAL_LEGS, "orthogonal-legs table must not be empty"
    for target, prefixes in _ORTHOGONAL_LEGS.items():
        assert target.startswith(("check-", "e2e-")), target
        assert prefixes, f"{target} must declare at least one input prefix"
        assert all(isinstance(p, str) and p for p in prefixes), target


def test_coverage_gates_are_the_existing_floor() -> None:
    """The coverage gates the Red leg has always skipped are preserved."""
    assert _COVERAGE_GATES == ("check-coverage", "check-per-file-coverage")


# ---------------------------------------------------------------------------
# red_mode_skip_targets — coverage floor (existing behavior preserved)
# ---------------------------------------------------------------------------


def test_coverage_gates_always_skipped_when_present() -> None:
    """Both coverage gates present in the target list are always skipped."""
    skip = red_mode_skip_targets(
        staged_paths=["tests/livespec_dev_tooling/test_config.py"],
        available_targets=list(_DEVTOOLING_TARGETS),
    )
    assert "check-coverage" in skip
    assert "check-per-file-coverage" in skip


def test_devtooling_unit_test_skips_only_coverage_gates() -> None:
    """In a repo with NO orthogonal legs, the skip set is exactly the coverage gates."""
    skip = red_mode_skip_targets(
        staged_paths=["tests/livespec_dev_tooling/checks/test_no_inheritance.py"],
        available_targets=list(_DEVTOOLING_TARGETS),
    )
    assert set(skip) == {"check-coverage", "check-per-file-coverage"}


def test_absent_coverage_gate_not_added_to_skip_set() -> None:
    """A coverage gate absent from the target list is not invented into the skip set."""
    skip = red_mode_skip_targets(
        staged_paths=["tests/livespec_dev_tooling/test_config.py"],
        available_targets=["check-lint", "check-types", "check-per-file-coverage"],
    )
    assert "check-coverage" not in skip
    assert "check-per-file-coverage" in skip


# ---------------------------------------------------------------------------
# red_mode_skip_targets — orthogonal-leg trimming by staged-path class
# ---------------------------------------------------------------------------


def test_unit_test_staged_skips_orthogonal_livespec_legs() -> None:
    """A staged unit test trims e2e-mock / prompts / doctor-static on livespec."""
    skip = red_mode_skip_targets(
        staged_paths=["tests/livespec/validate/test_front_matter.py"],
        available_targets=list(_LIVESPEC_TARGETS),
    )
    assert "check-doctor-static" in skip
    assert "check-prompts" in skip
    assert "e2e-test-claude-code-mock" in skip
    # coverage floor still present
    assert {"check-coverage", "check-per-file-coverage"} <= set(skip)
    # the leg a unit test CAN affect is never skipped
    assert "check-types" not in skip


def test_staged_path_under_e2e_tree_keeps_e2e_leg() -> None:
    """A staged tests/e2e/ file does NOT skip the e2e-mock leg (it can affect it)."""
    skip = red_mode_skip_targets(
        staged_paths=["tests/e2e/test_claude_code_mock_flow.py"],
        available_targets=list(_LIVESPEC_TARGETS),
    )
    assert "e2e-test-claude-code-mock" not in skip
    # but the unrelated orthogonal legs are still trimmed
    assert "check-prompts" in skip
    assert "check-doctor-static" in skip


def test_staged_path_under_prompts_tree_keeps_prompts_leg() -> None:
    """A staged tests/prompts/ file keeps the prompts leg but trims the others."""
    skip = red_mode_skip_targets(
        staged_paths=["tests/prompts/test_seed_prompt.py"],
        available_targets=list(_LIVESPEC_TARGETS),
    )
    assert "check-prompts" not in skip
    assert "e2e-test-claude-code-mock" in skip
    assert "check-doctor-static" in skip


def test_orthogonal_leg_absent_from_targets_not_skipped() -> None:
    """An orthogonal leg not present in the target list is not invented into the skip set."""
    skip = red_mode_skip_targets(
        staged_paths=["tests/livespec/validate/test_front_matter.py"],
        available_targets=["check-types", "check-coverage", "check-per-file-coverage"],
    )
    assert "check-doctor-static" not in skip
    assert "check-prompts" not in skip
    assert "e2e-test-claude-code-mock" not in skip


def test_skip_set_is_sorted_and_deduplicated() -> None:
    """The returned skip list is sorted and carries no duplicates."""
    skip = red_mode_skip_targets(
        staged_paths=["tests/livespec/validate/test_front_matter.py"],
        available_targets=list(_LIVESPEC_TARGETS),
    )
    assert skip == sorted(skip)
    assert len(skip) == len(set(skip))


def test_skip_set_is_a_strict_subset_of_targets() -> None:
    """Every skipped target is a member of available_targets (no phantoms)."""
    available = list(_LIVESPEC_TARGETS)
    skip = red_mode_skip_targets(
        staged_paths=["tests/livespec/validate/test_front_matter.py"],
        available_targets=available,
    )
    assert set(skip) <= set(available)
    assert set(skip) != set(available)


# ---------------------------------------------------------------------------
# Fail-fast — the HAZARD #2 guard: empty / over-broad selection MUST error
# ---------------------------------------------------------------------------


def test_empty_target_list_raises() -> None:
    """An empty available_targets list fails fast (never yields an empty run)."""
    with pytest.raises(ValueError, match="empty"):
        _ = red_mode_skip_targets(
            staged_paths=["tests/livespec_dev_tooling/test_config.py"],
            available_targets=[],
        )


def test_skipping_every_target_raises() -> None:
    """A skip set covering the entire target list fails fast (empty selection)."""
    # A target list consisting ONLY of skippable legs would leave nothing
    # to run at Red — that is the wedge the hazard section warns about.
    with pytest.raises(ValueError, match="empty selection|every target"):
        _ = red_mode_skip_targets(
            staged_paths=["tests/livespec/validate/test_front_matter.py"],
            available_targets=["check-coverage", "check-per-file-coverage"],
        )


def test_empty_staged_paths_raises() -> None:
    """No staged paths at the Red gate is malformed and fails fast."""
    with pytest.raises(ValueError, match="staged"):
        _ = red_mode_skip_targets(
            staged_paths=[],
            available_targets=list(_DEVTOOLING_TARGETS),
        )


# ---------------------------------------------------------------------------
# HARD INVARIANT pin — the red_green_replay hook is untouched
# ---------------------------------------------------------------------------


def test_red_green_replay_hook_unmodified() -> None:
    """This changeset must not alter the Red-trailer-producing hook code.

    The staged-test-must-fail semantics and TDD-Red-* trailer evidence
    live in red_green_replay.py + _red_green_replay_modes.py. The
    scope-reduction work touches NEITHER. Pin the exact substrings that
    encode the Red contract so a future edit there fails this test.
    """
    hook = (_REPO_ROOT / "livespec_dev_tooling" / "checks" / "red_green_replay.py").read_text(
        encoding="utf-8"
    )
    modes = (
        _REPO_ROOT / "livespec_dev_tooling" / "checks" / "_red_green_replay_modes.py"
    ).read_text(encoding="utf-8")
    # The staged-test pytest invocation that decides Red pass/fail.
    assert '"-m",\n            "pytest",' in hook or '"-m", "pytest"' in modes
    # The five TDD-Red-* trailer keys recorded as Red evidence.
    for trailer_key in (
        "TDD-Red-Test",
        "TDD-Red-Failure-Reason",
        "TDD-Red-Test-File-Checksum",
        "TDD-Red-Output-Checksum",
        "TDD-Red-Captured-At",
    ):
        assert trailer_key in modes, f"Red trailer key {trailer_key!r} missing from hook"
    # The test-passed-at-red gate that proves the staged test must fail.
    assert "test-passed-at-red" in modes


# ---------------------------------------------------------------------------
# CLI main() — invoked IN-PROCESS (monkeypatch argv + cwd, capsys for stdout).
#
# Deliberately NOT a `python red_leg_scope.py` subprocess: the
# check-coverage-incremental gate runs this test file's mirror under
# `pytest --cov`, which sets COVERAGE_PROCESS_START so any spawned Python
# child self-instruments and writes parallel-mode `.coverage.*` data
# files. Under the parallel check dispatcher that pollution races with
# the concurrent full-suite `pytest -n auto --cov` and intermittently
# leaves the per-file gate's data file empty ("No data to report"). An
# in-process main() keeps coverage of the CLI in the parent process and
# spawns no instrumented children, so the gate is deterministic.
# ---------------------------------------------------------------------------

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
    return {k: v for k, v in os.environ.items() if k not in _GIT_ENV_PASSTHROUGH_VARS}


def _init_repo(*, repo: Path) -> None:
    env = _scrubbed_env()
    subprocess.run(["git", "init", "-q"], cwd=str(repo), check=True, env=env)
    subprocess.run(
        ["git", "config", "user.email", "test@test.test"], cwd=str(repo), check=True, env=env
    )
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=str(repo), check=True, env=env)
    (repo / "README.md").write_text("baseline\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=str(repo), check=True, env=env)
    subprocess.run(
        ["git", "commit", "-q", "-m", "chore: baseline"], cwd=str(repo), check=True, env=env
    )


def _stage_test_file(*, repo: Path, rel: str) -> None:
    env = _scrubbed_env()
    target = repo / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("def test_x() -> None:\n    assert True\n", encoding="utf-8")
    subprocess.run(["git", "add", rel], cwd=str(repo), check=True, env=env)


def _invoke_main(
    *,
    monkeypatch: pytest.MonkeyPatch,
    cwd: Path,
    argv_tail: list[str],
) -> int:
    """Invoke red_leg_scope.main() in-process with a patched argv and cwd."""
    from livespec_dev_tooling import red_leg_scope

    monkeypatch.chdir(cwd)
    monkeypatch.setattr(sys, "argv", ["red_leg_scope", *argv_tail])
    return red_leg_scope.main()


def test_cli_emits_space_separated_skip_list_on_stdout(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """main() prints the computed skip set as a single space-separated stdout line."""
    rc = _invoke_main(
        monkeypatch=monkeypatch,
        cwd=tmp_path,
        argv_tail=[
            "--staged",
            "tests/livespec/validate/test_front_matter.py",
            "--targets",
            "check-types",
            "check-coverage",
            "check-per-file-coverage",
            "check-doctor-static",
            "check-prompts",
            "e2e-test-claude-code-mock",
        ],
    )
    assert rc == 0
    emitted = set(capsys.readouterr().out.split())
    assert {
        "check-coverage",
        "check-per-file-coverage",
        "check-doctor-static",
        "check-prompts",
        "e2e-test-claude-code-mock",
    } == emitted


def test_cli_fails_fast_when_every_target_skippable(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """main() returns 1 (not 0, never hangs) when the selection would be empty."""
    rc = _invoke_main(
        monkeypatch=monkeypatch,
        cwd=tmp_path,
        argv_tail=[
            "--staged",
            "tests/livespec/validate/test_front_matter.py",
            "--targets",
            "check-coverage",
            "check-per-file-coverage",
        ],
    )
    assert rc == 1
    captured = capsys.readouterr()
    # Empty stdout (no skip line emitted) and a fail-fast diagnostic on stderr.
    assert captured.out.strip() == ""
    assert "empty selection" in captured.err or "every target" in captured.err


def test_cli_emits_only_coverage_gates_for_devtooling_unit_test(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A dev-tooling unit test (no orthogonal legs) emits exactly the coverage gates."""
    rc = _invoke_main(
        monkeypatch=monkeypatch,
        cwd=tmp_path,
        argv_tail=[
            "--staged",
            "tests/livespec_dev_tooling/checks/test_no_inheritance.py",
            "--targets",
            "check-lint",
            "check-types",
            "check-coverage",
            "check-per-file-coverage",
        ],
    )
    assert rc == 0
    assert set(capsys.readouterr().out.split()) == {"check-coverage", "check-per-file-coverage"}


def test_cli_reads_staged_from_git_when_staged_omitted(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """With --staged omitted, main() derives the staged paths from `git diff --cached`.

    Git is the only subprocess here (not a coverage-instrumented Python
    child), so it does not pollute the parallel-mode coverage data files.
    """
    _init_repo(repo=tmp_path)
    _stage_test_file(repo=tmp_path, rel="tests/livespec/validate/test_front_matter.py")
    rc = _invoke_main(
        monkeypatch=monkeypatch,
        cwd=tmp_path,
        argv_tail=[
            "--targets",
            "check-types",
            "check-coverage",
            "check-per-file-coverage",
            "check-doctor-static",
            "check-prompts",
            "e2e-test-claude-code-mock",
        ],
    )
    assert rc == 0
    emitted = set(capsys.readouterr().out.split())
    assert {"check-doctor-static", "check-prompts", "e2e-test-claude-code-mock"} <= emitted
    assert "check-types" not in emitted
