"""Outside-in test for `dev-tooling/checks/red_green_replay.py` — replay-based TDD enforcement.

Content is the trigger; the subject prefix NEVER rejects a commit for
containing product code (user design correction 2026-06-11, follow-up
to work-item livespec-dev-tooling-eld — changing product code as part
of a chore is legitimate; it is simply subject to the same TDD
discipline). The commit-msg decision tree (argv[1] = commit-message
file path):

1. nothing staged / no `.py` in the tests or impl buckets ⇒ pass
   immediately, any prefix (machine checkpoint subjects such as
   `fabro(<run_id>): <node> (<status>)`, docs, and empty commits);
2. tests-only `.py` staged + pytest on the staged tests FAILS ⇒ the
   Red leg records `TDD-Red-*` trailers — ANY prefix may author a
   Red (a behavior-changing chore does Red->Green like a feature);
3. tests-only `.py` staged + pytest PASSES ⇒ `feat:`/`fix:` keeps the
   loud `test-passed-at-red` reject (the author DECLARED a behavior
   change, so their test must fail first); any other prefix is a
   test-only cleanup and takes the green-verified leg;
4. product impl `.py` staged WITH `TDD-Red-*` trailers at HEAD (the
   amend shape) ⇒ the Green leg, unchanged: byte-identical test
   re-run must pass, `TDD-Green-*` recorded;
5. product impl `.py` staged WITHOUT Red trailers (pure refactor /
   behavior-preserving chore / any prefix incl. feat:/fix:) ⇒ the
   green-verified leg: the FULL pytest suite must pass against the
   staged tree; `TDD-Suite-Green-*` trailers (scope, output
   checksum, captured-at) are recorded; a failing suite rejects
   actionably (`suite-red`).

With NO argv (the canonical-aggregate / `just check` invocation) the
hook validates the COMMIT RANGE `origin/master..HEAD`: every
non-merge commit touching product impl `.py` must carry EITHER the
TDD-Red-*/TDD-Green-* pair shape OR the TDD-Suite-Green-* shape,
regardless of prefix.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[3]
_RED_GREEN_REPLAY = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "red_green_replay.py"


# When this test suite runs inside a git hook (lefthook pre-commit /
# pre-push / commit-msg), git sets GIT_DIR / GIT_WORK_TREE /
# GIT_INDEX_FILE / friends pointing at the SURROUNDING repo. These
# vars are inherited by subprocess children and would redirect every
# `git ...` call (and every check-script-internal `git` call) to the
# outer repo instead of the tmp_path mini-repo the test constructs.
# Scrubbing them at every subprocess boundary confines git to the
# tmp_path fixture's `.git` directory regardless of how the test
# suite is invoked. Mirrors the discipline already established in
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


def test_chore_commit_subject_exits_zero(*, tmp_path: Path) -> None:
    """A `chore:` commit subject with no product impl `.py` staged exits 0.

    Fixture: a tmp_path COMMIT_EDITMSG file containing
    `chore: codify v034`. The hook is invoked as a `commit-msg`
    git hook (the v034 D2-D3 design): argv[1] is the path to
    the commit message file. Content is the trigger: with no
    product impl `.py` staged (here: no repo at all, so the
    staged list is empty), the hook MUST exit 0 without running
    any test or computing any checksum.
    """
    msg_path = tmp_path / "COMMIT_EDITMSG"
    msg_path.write_text("chore: codify v034\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(_RED_GREEN_REPLAY), str(msg_path)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
        env=_scrubbed_env(),
    )

    assert result.returncode == 0, (
        f"red_green_replay should exit 0 for chore: subject; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_docs_commit_subject_exits_zero(*, tmp_path: Path) -> None:
    """A `docs:` commit subject with no product impl `.py` staged exits 0.

    Fixture: a tmp_path COMMIT_EDITMSG file containing
    `docs: clarify proposal`. Under the content-trigger design
    the historical exempt-type list (chore, docs, build, ci,
    style, test, refactor, perf, revert) is retired: ANY prefix
    passes when no product impl `.py` is staged.
    """
    msg_path = tmp_path / "COMMIT_EDITMSG"
    msg_path.write_text("docs: clarify proposal\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(_RED_GREEN_REPLAY), str(msg_path)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
        env=_scrubbed_env(),
    )

    assert result.returncode == 0, (
        f"red_green_replay should exit 0 for docs: subject; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


@pytest.mark.parametrize(
    "type_token",
    ["build", "ci", "style", "test", "refactor", "perf", "revert"],
)
def test_remaining_exempt_commit_subjects_exit_zero(
    *,
    type_token: str,
    tmp_path: Path,
) -> None:
    """Each remaining historical exempt Conventional Commit type exits 0.

    Under the content-trigger design these prefixes are no
    longer special-cased: they pass here because no product
    impl `.py` is staged (config/meta changesets produce no
    test/impl pairing), not because of a prefix allowlist.
    The parameterized test pins that none of them regressed
    when the exempt-list fallthrough was retired.
    """
    msg_path = tmp_path / "COMMIT_EDITMSG"
    msg_path.write_text(f"{type_token}: minor change\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(_RED_GREEN_REPLAY), str(msg_path)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
        env=_scrubbed_env(),
    )

    assert result.returncode == 0, (
        f"red_green_replay should exit 0 for {type_token}: subject; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_feat_commit_subject_with_nothing_staged_exits_zero(*, tmp_path: Path) -> None:
    """A `feat:` commit subject with nothing staged at all exits 0.

    Fixture: a tmp_path COMMIT_EDITMSG file containing
    `feat: add new feature` and no git repo (the staged list is
    empty). An empty commit cannot change product code, so there
    is nothing for the ritual to verify; under the content-trigger
    design the hook MUST exit 0 (the old design rejected with an
    `empty-staged` diagnostic, which broke `--allow-empty` machine
    checkpoint commits).
    """
    msg_path = tmp_path / "COMMIT_EDITMSG"
    msg_path.write_text("feat: add new feature\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(_RED_GREEN_REPLAY), str(msg_path)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
        env=_scrubbed_env(),
    )

    assert result.returncode == 0, (
        f"red_green_replay should exit 0 for feat: with nothing staged; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_feat_in_git_repo_with_no_staged_files_exits_zero(*, tmp_path: Path) -> None:
    """A feat: subject in a git repo with NO staged files exits 0 (empty commit).

    An empty staging area means the commit changes no repo state,
    so the Red/Green ritual has nothing to verify and the hook
    passes immediately — `git commit --allow-empty` (e.g. machine
    checkpoint commits) must not be blocked. The old `empty-staged`
    rejection branch is retired; its diagnostic MUST NOT fire.
    """
    subprocess.run(
        ["git", "init", "-q"],
        cwd=str(tmp_path),
        check=True,
        env=_scrubbed_env(),
    )
    msg_path = tmp_path / "COMMIT_EDITMSG"
    msg_path.write_text("feat: add new feature\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(_RED_GREEN_REPLAY), str(msg_path)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
        env=_scrubbed_env(),
    )

    assert result.returncode == 0, (
        f"feat: with empty staged tree must pass (empty commits are inert); "
        f"got returncode={result.returncode} stderr={result.stderr!r}"
    )
    assert "empty-staged" not in result.stderr, (
        f"the retired empty-staged rejection must not fire; " f"got stderr={result.stderr!r}"
    )


def test_feat_in_git_repo_with_staged_files_skips_no_staged_diagnostic(
    *,
    tmp_path: Path,
) -> None:
    """A feat: subject in a git repo WITH staged tests dispatches into the ritual.

    Paired test for the empty-staging pass: with a staged tests-tree
    `.py`, the hook enters Red mode instead of the empty-staging
    early exit (here the staged test PASSES, so Red mode rejects
    with `test-passed-at-red` — a ritual-path rejection, proving
    dispatch happened). No empty-staging diagnostic may appear.
    """
    subprocess.run(
        ["git", "init", "-q"],
        cwd=str(tmp_path),
        check=True,
        env=_scrubbed_env(),
    )
    (tmp_path / "tests").mkdir()
    test_file = tmp_path / "tests" / "test_dummy.py"
    test_file.write_text(
        "def test_x() -> None:\n    assert True\n",
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "add", "tests/test_dummy.py"],
        cwd=str(tmp_path),
        check=True,
        env=_scrubbed_env(),
    )

    msg_path = tmp_path / "COMMIT_EDITMSG"
    msg_path.write_text("feat: add new feature\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(_RED_GREEN_REPLAY), str(msg_path)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
        env=_scrubbed_env(),
    )

    assert result.returncode != 0, (
        f"feat: with staged files still rejects (full replay logic not yet implemented); "
        f"got returncode={result.returncode}"
    )
    assert "no staged files" not in result.stderr.lower(), (
        f"no-staged-files diagnostic must NOT fire when files ARE staged; "
        f"got stderr={result.stderr!r}"
    )


def test_feat_with_tests_only_staged_emits_red_mode_candidate(
    *,
    tmp_path: Path,
) -> None:
    """A feat: subject with tests-only staged is a Red-mode candidate.

    Cycle 178 drives the test/impl classification step. Per Plan
    §"Per-commit Red→Green replay discipline (v034 D2-D3)", Red mode
    is triggered when the staged tree carries test files but no
    implementation files. This test pins the True branch of
    "tests_paths AND NOT impl_paths" — staging a single file under
    `tests/` qualifies the commit as a Red-mode candidate; the hook
    emits a structured `red-mode-candidate` structlog event identifying
    the discriminator. The hook still exits non-zero (pytest invocation
    + Red-trailer authoring come in subsequent cycles).
    """
    subprocess.run(
        ["git", "init", "-q"],
        cwd=str(tmp_path),
        check=True,
        env=_scrubbed_env(),
    )
    (tmp_path / "tests").mkdir()
    test_file = tmp_path / "tests" / "test_dummy.py"
    test_file.write_text(
        "def test_x() -> None:\n    assert True\n",
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "add", "tests/test_dummy.py"],
        cwd=str(tmp_path),
        check=True,
        env=_scrubbed_env(),
    )

    msg_path = tmp_path / "COMMIT_EDITMSG"
    msg_path.write_text("feat: add new feature\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(_RED_GREEN_REPLAY), str(msg_path)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
        env=_scrubbed_env(),
    )

    assert result.returncode != 0, (
        f"feat: with tests-only staged still rejects (full Red replay not yet implemented); "
        f"got returncode={result.returncode}"
    )
    assert "red-mode-candidate" in result.stderr.lower(), (
        f"expected 'red-mode-candidate' diagnostic in stderr for tests-only feat:; "
        f"got stderr={result.stderr!r}"
    )


def test_feat_with_impl_only_staged_skips_red_mode_candidate(
    *,
    tmp_path: Path,
) -> None:
    """A feat: subject with impl-only staged is NOT a Red-mode candidate.

    With one file staged under `livespec/` (impl bucket) and zero
    files under `tests/`, the Red-mode-candidate diagnostic MUST NOT
    fire — impl staging dispatches to the Green leg (with HEAD Red
    trailers) or the green-verified suite leg (without). Here the
    fixture repo has no collectable tests, so the suite leg rejects
    (non-zero) — but never via the Red path. Together with the
    True-branch test above, this pins the dispatch discriminator.
    """
    subprocess.run(
        ["git", "init", "-q"],
        cwd=str(tmp_path),
        check=True,
        env=_scrubbed_env(),
    )
    impl_dir = tmp_path / "livespec"
    impl_dir.mkdir()
    impl_file = impl_dir / "foo.py"
    impl_file.write_text("VALUE: int = 1\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "livespec/foo.py"],
        cwd=str(tmp_path),
        check=True,
        env=_scrubbed_env(),
    )

    msg_path = tmp_path / "COMMIT_EDITMSG"
    msg_path.write_text("feat: add new feature\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(_RED_GREEN_REPLAY), str(msg_path)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
        env=_scrubbed_env(),
    )

    assert result.returncode != 0, (
        f"feat: with impl-only staged in a test-less repo rejects via the suite leg; "
        f"got returncode={result.returncode}"
    )
    assert "red-mode-candidate" not in result.stderr.lower(), (
        f"red-mode-candidate diagnostic must NOT fire when impl is staged; "
        f"got stderr={result.stderr!r}"
    )


def test_feat_with_single_test_file_staged_emits_sha256_checksum(
    *,
    tmp_path: Path,
) -> None:
    """A feat: subject with one staged test file surfaces a SHA-256 checksum.

    Cycle 179 wires SHA-256 computation of the staged test file. Per and the trailer schema (`TDD-Red-Test-File-Checksum:
    sha256:<hex>`), the Red-mode hook computes the test file's SHA-256
    so the Green-mode amend can verify the test file is unchanged. This
    test pins: a tests-only-staged commit with exactly one path under
    `tests/` carries a `test_file_checksum` field on the
    red-mode-candidate event whose value is the literal `sha256:` prefix
    followed by the 64-character lowercase hex digest of the staged
    file's bytes. The exact hex digest is asserted against
    `hashlib.sha256(file_bytes).hexdigest()` to make the contract
    mechanical.
    """
    subprocess.run(
        ["git", "init", "-q"],
        cwd=str(tmp_path),
        check=True,
        env=_scrubbed_env(),
    )
    (tmp_path / "tests").mkdir()
    test_file = tmp_path / "tests" / "test_dummy.py"
    test_bytes = b"def test_x() -> None:\n    assert True\n"
    test_file.write_bytes(test_bytes)
    subprocess.run(
        ["git", "add", "tests/test_dummy.py"],
        cwd=str(tmp_path),
        check=True,
        env=_scrubbed_env(),
    )

    msg_path = tmp_path / "COMMIT_EDITMSG"
    msg_path.write_text("feat: add new feature\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(_RED_GREEN_REPLAY), str(msg_path)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
        env=_scrubbed_env(),
    )

    expected_digest = hashlib.sha256(test_bytes).hexdigest()
    expected_checksum_token = f"sha256:{expected_digest}"

    assert result.returncode != 0, (
        f"feat: with single test file staged still rejects "
        f"(full Red replay not yet implemented); "
        f"got returncode={result.returncode}"
    )
    assert "test_file_checksum" in result.stderr, (
        f"expected 'test_file_checksum' field in red-mode-candidate event; "
        f"got stderr={result.stderr!r}"
    )
    assert expected_checksum_token in result.stderr, (
        f"expected sha256:<hex> token {expected_checksum_token!r} in stderr; "
        f"got stderr={result.stderr!r}"
    )


def test_feat_with_multiple_test_files_staged_rejects_with_multi_test_file_diagnostic(
    *,
    tmp_path: Path,
) -> None:
    """A feat: subject with multiple staged test files is not a valid Red moment.

    Cycle 179 paired test: pins the False branch of the
    "len(tests_paths) > 1" rejection. Per the v034 D2 trailer schema,
    `TDD-Red-Test:` and `TDD-Red-Test-File-Checksum:` are singular
    fields — Red mode is per-file (one staged test file per Red commit),
    so multi-test-file staged trees must be rejected with a clear
    `multi-test-file` diagnostic. The hook returns non-zero without
    emitting a checksum (no single canonical test file to checksum).
    Together with the True-branch test above, this guarantees per-file
    100% branch coverage on the new conditional.
    """
    subprocess.run(
        ["git", "init", "-q"],
        cwd=str(tmp_path),
        check=True,
        env=_scrubbed_env(),
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text(
        "def test_a() -> None:\n    assert True\n",
        encoding="utf-8",
    )
    (tmp_path / "tests" / "test_b.py").write_text(
        "def test_b() -> None:\n    assert True\n",
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "add", "tests/test_a.py", "tests/test_b.py"],
        cwd=str(tmp_path),
        check=True,
        env=_scrubbed_env(),
    )

    msg_path = tmp_path / "COMMIT_EDITMSG"
    msg_path.write_text("feat: add new feature\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(_RED_GREEN_REPLAY), str(msg_path)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
        env=_scrubbed_env(),
    )

    assert result.returncode != 0, (
        f"feat: with multiple test files staged must reject; " f"got returncode={result.returncode}"
    )
    assert "multi-test-file" in result.stderr.lower(), (
        f"expected 'multi-test-file' diagnostic in stderr; " f"got stderr={result.stderr!r}"
    )
    assert "test_file_checksum" not in result.stderr, (
        f"checksum field must NOT fire when multiple test files are staged; "
        f"got stderr={result.stderr!r}"
    )


def test_feat_with_failing_test_staged_emits_red_pytest_result(
    *,
    tmp_path: Path,
) -> None:
    """A feat: subject with a single failing staged test file pins a valid Red moment.

    Cycle 180 invokes pytest on the staged test file. Per Plan
    §"Per-commit Red→Green replay discipline (v034 D2-D3)", a Red
    moment requires the staged test to fail (non-zero pytest exit
    code). This test stages a `tests/test_failing.py` whose body
    asserts a falsy expression, then invokes the hook; the hook
    runs pytest, observes a non-zero returncode, and emits a
    structured `red-green-replay-red-pytest-result` info event
    carrying `pytest_returncode=<non-zero-int>`. Pins the False
    branch of `pytest_result.returncode == 0`.
    """
    subprocess.run(
        ["git", "init", "-q"],
        cwd=str(tmp_path),
        check=True,
        env=_scrubbed_env(),
    )
    (tmp_path / "tests").mkdir()
    test_file = tmp_path / "tests" / "test_failing.py"
    test_file.write_text(
        "def test_failing() -> None:\n" "    assert False, 'staged red test fails as required'\n",
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "add", "tests/test_failing.py"],
        cwd=str(tmp_path),
        check=True,
        env=_scrubbed_env(),
    )

    msg_path = tmp_path / "COMMIT_EDITMSG"
    msg_path.write_text("feat: add new feature\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(_RED_GREEN_REPLAY), str(msg_path)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
        env=_scrubbed_env(),
    )

    assert result.returncode == 0, (
        f"after cycle 181, Red-moment-confirmed exits 0 (commit proceeds); "
        f"got returncode={result.returncode} stderr={result.stderr!r}"
    )
    assert "red-pytest-result" in result.stderr, (
        f"expected 'red-pytest-result' event in stderr for failing test; "
        f"got stderr={result.stderr!r}"
    )
    assert "pytest_returncode" in result.stderr, (
        f"expected 'pytest_returncode' field in red-pytest-result event; "
        f"got stderr={result.stderr!r}"
    )
    assert "test-passed-at-red" not in result.stderr, (
        f"test-passed-at-red rejection MUST NOT fire when pytest fails; "
        f"got stderr={result.stderr!r}"
    )


def test_feat_with_passing_test_staged_rejects_with_test_passed_at_red(
    *,
    tmp_path: Path,
) -> None:
    """A feat: subject with a single passing staged test file is NOT a Red moment.

    Cycle 180 paired test: pins the True branch of
    `pytest_result.returncode == 0`. If the staged test PASSES when
    run, the commit is not a valid Red moment (Red mode requires
    the test to fail so that the subsequent Green amend has
    something to make pass). The hook MUST reject with a
    structured `red-green-replay-test-passed-at-red` error and
    surface a `pytest_returncode=0` field. The
    `red-green-replay-red-pytest-result` info event MUST NOT
    fire on this path.
    """
    subprocess.run(
        ["git", "init", "-q"],
        cwd=str(tmp_path),
        check=True,
        env=_scrubbed_env(),
    )
    (tmp_path / "tests").mkdir()
    test_file = tmp_path / "tests" / "test_passing.py"
    test_file.write_text(
        "def test_passing() -> None:\n    assert True\n",
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "add", "tests/test_passing.py"],
        cwd=str(tmp_path),
        check=True,
        env=_scrubbed_env(),
    )

    msg_path = tmp_path / "COMMIT_EDITMSG"
    msg_path.write_text("feat: add new feature\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(_RED_GREEN_REPLAY), str(msg_path)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
        env=_scrubbed_env(),
    )

    assert result.returncode != 0, (
        f"hook must reject when staged test passes; " f"got returncode={result.returncode}"
    )
    assert "test-passed-at-red" in result.stderr, (
        f"expected 'test-passed-at-red' rejection in stderr for passing test; "
        f"got stderr={result.stderr!r}"
    )
    assert "red-pytest-result" not in result.stderr, (
        f"red-pytest-result event MUST NOT fire when pytest passes; "
        f"got stderr={result.stderr!r}"
    )


def test_feat_with_failing_test_writes_full_red_trailer_schema(
    *,
    tmp_path: Path,
) -> None:
    """Red-moment confirmed → COMMIT_EDITMSG gains the v034 D2 trailer schema.

    Cycle 181 wires Red trailer authoring via `git interpret-trailers
    --in-place`. Per, the full set of
    Red trailers required at the Red commit boundary is:

      TDD-Red-Test: <pytest-node-id>
      TDD-Red-Failure-Reason: <one-line failure summary>
      TDD-Red-Test-File-Checksum: sha256:<hex>
      TDD-Red-Output-Checksum: sha256:<hex>
      TDD-Red-Captured-At: <UTC ISO 8601>

    This test stages a single failing test, runs the hook, then
    re-reads the COMMIT_EDITMSG file and asserts each trailer key is
    present. The hook returns 0 (the new happy-path exit — Red moment
    fully verified, commit proceeds).
    """
    subprocess.run(
        ["git", "init", "-q"],
        cwd=str(tmp_path),
        check=True,
        env=_scrubbed_env(),
    )
    (tmp_path / "tests").mkdir()
    test_file = tmp_path / "tests" / "test_red.py"
    test_file.write_text(
        "def test_red() -> None:\n" "    assert False, 'red-trailer-test'\n",
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "add", "tests/test_red.py"],
        cwd=str(tmp_path),
        check=True,
        env=_scrubbed_env(),
    )

    msg_path = tmp_path / "COMMIT_EDITMSG"
    msg_path.write_text("feat: add new feature\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(_RED_GREEN_REPLAY), str(msg_path)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
        env=_scrubbed_env(),
    )

    assert result.returncode == 0, (
        f"Red-moment-confirmed must exit 0 (commit proceeds); "
        f"got returncode={result.returncode} stderr={result.stderr!r}"
    )

    final_msg = msg_path.read_text(encoding="utf-8")
    for trailer_key in (
        "TDD-Red-Test:",
        "TDD-Red-Failure-Reason:",
        "TDD-Red-Test-File-Checksum:",
        "TDD-Red-Output-Checksum:",
        "TDD-Red-Captured-At:",
    ):
        assert trailer_key in final_msg, (
            f"expected trailer {trailer_key!r} in COMMIT_EDITMSG; " f"got final_msg={final_msg!r}"
        )
    assert "sha256:" in final_msg, (
        f"expected sha256: prefix in trailers (Test-File-Checksum + Output-Checksum); "
        f"got final_msg={final_msg!r}"
    )


def test_feat_with_impl_staged_and_head_has_red_trailers_emits_green_mode_candidate(
    *,
    tmp_path: Path,
) -> None:
    """Green-mode-candidate detection: HEAD~0 has Red trailers + impl staged.

    Cycle 182 wires the Green-mode dispatch counterpart to Red mode.
    Per, Green mode
    is triggered when the HEAD~0 commit message carries Red trailers
    AND the new staged tree adds implementation files. This test
    fixtures a Red commit by manually authoring a commit body with
    the v034 D2 trailer schema, then stages an impl file under
    `livespec/`, then invokes the hook. The hook MUST detect the
    Green-mode-candidate condition and emit a structured
    `red-green-replay-green-mode-candidate` info event. Returns 1
    (full Green replay logic — checksum re-verification, pytest
    invocation, Green trailer authoring — lands in subsequent
    cycles).
    """
    subprocess.run(
        ["git", "init", "-q"],
        cwd=str(tmp_path),
        check=True,
        env=_scrubbed_env(),
    )
    subprocess.run(
        ["git", "config", "user.email", "test@test.test"],
        cwd=str(tmp_path),
        check=True,
        env=_scrubbed_env(),
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=str(tmp_path),
        check=True,
        env=_scrubbed_env(),
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_red.py").write_text(
        "def test_red() -> None:\n    assert False\n",
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "add", "tests/test_red.py"],
        cwd=str(tmp_path),
        check=True,
        env=_scrubbed_env(),
    )
    red_commit_msg = (
        "feat: add new feature\n"
        "\n"
        "TDD-Red-Test: tests/test_red.py\n"
        "TDD-Red-Failure-Reason: AssertionError\n"
        "TDD-Red-Test-File-Checksum: sha256:0000000000000000000000000000000000000000000000000000000000000000\n"
        "TDD-Red-Output-Checksum: sha256:1111111111111111111111111111111111111111111111111111111111111111\n"
        "TDD-Red-Captured-At: 2026-05-02T05:00:00Z\n"
    )
    subprocess.run(
        ["git", "commit", "-m", red_commit_msg],
        cwd=str(tmp_path),
        check=True,
        env=_scrubbed_env(),
    )

    (tmp_path / "livespec").mkdir()
    (tmp_path / "livespec" / "foo.py").write_text(
        "VALUE: int = 1\n",
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "add", "livespec/foo.py"],
        cwd=str(tmp_path),
        check=True,
        env=_scrubbed_env(),
    )

    msg_path = tmp_path / "COMMIT_EDITMSG"
    msg_path.write_text("feat: add green impl\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(_RED_GREEN_REPLAY), str(msg_path)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
        env=_scrubbed_env(),
    )

    assert result.returncode != 0, (
        f"Green-mode-candidate detection still rejects until full Green replay lands; "
        f"got returncode={result.returncode}"
    )
    assert "green-mode-candidate" in result.stderr.lower(), (
        f"expected 'green-mode-candidate' diagnostic in stderr; " f"got stderr={result.stderr!r}"
    )


def test_feat_green_amend_with_unchanged_test_and_passing_pytest_writes_green_trailers(
    *,
    tmp_path: Path,
) -> None:
    """Full Green-mode replay success: Green trailers written, hook returns 0.

    Green-mode replay verification: the hook must recompute the
    test file SHA-256 from working tree (rejects on mismatch), run
    pytest (expects exit zero), then add `TDD-Green-Verified-At:`
    and `TDD-Green-Parent-Reflog:` trailers and let the commit land.
    This test fixtures a Red commit with the REAL SHA-256 of a
    passing test (cosmetically Red — the body still uses `assert
    True` since the actual Red→Green author flow is out of scope
    for this unit), stages an impl file, and verifies returncode==0
    plus Green trailer presence in COMMIT_EDITMSG.
    """
    subprocess.run(
        ["git", "init", "-q"],
        cwd=str(tmp_path),
        check=True,
        env=_scrubbed_env(),
    )
    subprocess.run(
        ["git", "config", "user.email", "test@test.test"],
        cwd=str(tmp_path),
        check=True,
        env=_scrubbed_env(),
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=str(tmp_path),
        check=True,
        env=_scrubbed_env(),
    )

    (tmp_path / "tests").mkdir()
    test_bytes = b"def test_x() -> None:\n    assert True\n"
    test_file = tmp_path / "tests" / "test_x.py"
    test_file.write_bytes(test_bytes)
    real_checksum = f"sha256:{hashlib.sha256(test_bytes).hexdigest()}"
    subprocess.run(
        ["git", "add", "tests/test_x.py"],
        cwd=str(tmp_path),
        check=True,
        env=_scrubbed_env(),
    )
    red_commit_msg = (
        "feat: red commit\n"
        "\n"
        "TDD-Red-Test: tests/test_x.py\n"
        "TDD-Red-Failure-Reason: stub-failure-reason\n"
        f"TDD-Red-Test-File-Checksum: {real_checksum}\n"
        "TDD-Red-Output-Checksum: sha256:abc\n"
        "TDD-Red-Captured-At: 2026-05-02T05:00:00Z\n"
    )
    subprocess.run(
        ["git", "commit", "-m", red_commit_msg],
        cwd=str(tmp_path),
        check=True,
        env=_scrubbed_env(),
    )

    (tmp_path / "livespec").mkdir()
    (tmp_path / "livespec" / "foo.py").write_text(
        "VALUE: int = 1\n",
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "add", "livespec/foo.py"],
        cwd=str(tmp_path),
        check=True,
        env=_scrubbed_env(),
    )

    msg_path = tmp_path / "COMMIT_EDITMSG"
    msg_path.write_text("feat: green impl\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(_RED_GREEN_REPLAY), str(msg_path)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
        env=_scrubbed_env(),
    )

    assert result.returncode == 0, (
        f"Green replay confirmed must exit 0; got returncode={result.returncode} "
        f"stderr={result.stderr!r}"
    )
    final_msg = msg_path.read_text(encoding="utf-8")
    for trailer_key in ("TDD-Green-Verified-At:", "TDD-Green-Parent-Reflog:"):
        assert (
            trailer_key in final_msg
        ), f"expected {trailer_key!r} in COMMIT_EDITMSG; got final_msg={final_msg!r}"


def test_feat_green_amend_with_test_still_failing_rejects(
    *,
    tmp_path: Path,
) -> None:
    """Green-mode replay rejection: pytest still fails at Green moment.

    Cycle 183 paired test for the pytest-fail branch. Fixtures a
    Red commit with the REAL checksum of a test that asserts False;
    after staging impl, the hook re-runs pytest, observes a
    non-zero returncode, and rejects with
    `red-green-replay-test-still-failing`. Pins the True branch of
    `green_pytest_result.returncode != 0`.
    """
    subprocess.run(
        ["git", "init", "-q"],
        cwd=str(tmp_path),
        check=True,
        env=_scrubbed_env(),
    )
    subprocess.run(
        ["git", "config", "user.email", "test@test.test"],
        cwd=str(tmp_path),
        check=True,
        env=_scrubbed_env(),
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=str(tmp_path),
        check=True,
        env=_scrubbed_env(),
    )

    (tmp_path / "tests").mkdir()
    test_bytes = (
        b"def test_still_failing() -> None:\n" b"    assert False, 'still-failing-at-green'\n"
    )
    test_file = tmp_path / "tests" / "test_still_failing.py"
    test_file.write_bytes(test_bytes)
    real_checksum = f"sha256:{hashlib.sha256(test_bytes).hexdigest()}"
    subprocess.run(
        ["git", "add", "tests/test_still_failing.py"],
        cwd=str(tmp_path),
        check=True,
        env=_scrubbed_env(),
    )
    red_commit_msg = (
        "feat: red commit\n"
        "\n"
        "TDD-Red-Test: tests/test_still_failing.py\n"
        "TDD-Red-Failure-Reason: stub\n"
        f"TDD-Red-Test-File-Checksum: {real_checksum}\n"
        "TDD-Red-Output-Checksum: sha256:abc\n"
        "TDD-Red-Captured-At: 2026-05-02T05:00:00Z\n"
    )
    subprocess.run(
        ["git", "commit", "-m", red_commit_msg],
        cwd=str(tmp_path),
        check=True,
        env=_scrubbed_env(),
    )

    (tmp_path / "livespec").mkdir()
    (tmp_path / "livespec" / "foo.py").write_text(
        "VALUE: int = 1\n",
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "add", "livespec/foo.py"],
        cwd=str(tmp_path),
        check=True,
        env=_scrubbed_env(),
    )

    msg_path = tmp_path / "COMMIT_EDITMSG"
    msg_path.write_text("feat: green impl\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(_RED_GREEN_REPLAY), str(msg_path)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
        env=_scrubbed_env(),
    )

    assert result.returncode != 0, (
        f"hook must reject when Green-mode pytest still fails; "
        f"got returncode={result.returncode}"
    )
    assert "test-still-failing-at-green" in result.stderr.lower(), (
        f"expected 'test-still-failing-at-green' diagnostic in stderr; "
        f"got stderr={result.stderr!r}"
    )


@pytest.mark.parametrize(
    "subject_token",
    [
        "chore!: codify v034",
        "docs!: revise terminology",
        "chore(deps): bump returns",
        "chore(deps)!: bump returns major",
        "refactor(io)!: rename io facades",
    ],
)
def test_conventional_commit_breaking_and_scope_variants_exit_zero(
    *,
    subject_token: str,
    tmp_path: Path,
) -> None:
    """Conventional Commits `<type>[(<scope>)][!]:` variants resolve as exempt.

    Discovered at activation time: cycles 173-176 used a literal
    `subject.startswith(("chore:", ...))` check that fails to match
    `chore!:` (the `!` breaking-change marker) and `chore(deps):`
    (the optional scope). The activation commit itself (subject
    `chore!: ...`) was rejected by the live commit-msg hook on first
    attempt. The fix replaces the startswith tuple with a regex
    matching the full Conventional Commits format
    `^<type>(\\(<scope>\\))?!?:`. Pins the breaking-change marker
    and scope-notation variants for every exempt type.
    """
    msg_path = tmp_path / "COMMIT_EDITMSG"
    msg_path.write_text(f"{subject_token}\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(_RED_GREEN_REPLAY), str(msg_path)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
        env=_scrubbed_env(),
    )

    assert result.returncode == 0, (
        f"Conventional-Commits exempt variant {subject_token!r} should exit 0; "
        f"got returncode={result.returncode} stderr={result.stderr!r}"
    )


def test_classify_staged_recognizes_production_claude_plugin_scripts_paths() -> None:
    """`_classify_staged` buckets `.claude-plugin/scripts/{livespec,bin}/...` paths as impl.

    The `_IMPL_PREFIXES` enumeration recognizes both production
    paths (`.claude-plugin/scripts/livespec/...` and
    `.claude-plugin/scripts/bin/...`) and bare `livespec/`/`bin/`
    legacy prefixes (kept for paired-test fixture compatibility —
    the test fixtures synthesize paths like `livespec/foo.py` in
    tmp repos rather than full production paths). This test pins
    both forms of impl-tree match.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "red_green_replay_for_classify_test",
        str(_RED_GREEN_REPLAY),
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    paths = [
        ".claude-plugin/scripts/livespec/validate/finding.py",
        ".claude-plugin/scripts/bin/seed.py",
        "dev-tooling/checks/foo.py",
        "tests/livespec/test_foo.py",
        "docs/STATUS.md",
        "dev-tooling/checks/data.json",
        "tests/livespec/fixture.json",
    ]
    tests_paths, impl_paths = module._classify_staged(paths=paths)  # noqa: SLF001
    assert "dev-tooling/checks/data.json" not in impl_paths, (
        f"non-.py file under an impl prefix should NOT be in impl bucket "
        f"(content trigger is product .py); got impl_paths={impl_paths}"
    )
    assert "tests/livespec/fixture.json" not in tests_paths, (
        f"non-.py file under tests/ should NOT be in tests bucket "
        f"(content trigger is .py); got tests_paths={tests_paths}"
    )
    assert ".claude-plugin/scripts/livespec/validate/finding.py" in impl_paths, (
        f"production `.claude-plugin/scripts/livespec/...` path should be in impl bucket; "
        f"got impl_paths={impl_paths}"
    )
    assert ".claude-plugin/scripts/bin/seed.py" in impl_paths, (
        f"production `.claude-plugin/scripts/bin/...` path should be in impl bucket; "
        f"got impl_paths={impl_paths}"
    )
    assert "dev-tooling/checks/foo.py" in impl_paths, (
        f"`dev-tooling/...` path should be in impl bucket; " f"got impl_paths={impl_paths}"
    )
    assert "tests/livespec/test_foo.py" in tests_paths, (
        f"`tests/...` path should be in tests bucket; " f"got tests_paths={tests_paths}"
    )
    assert "docs/STATUS.md" not in impl_paths, (
        f"path under no recognized prefix should NOT be in impl bucket; "
        f"got impl_paths={impl_paths}"
    )
    assert "docs/STATUS.md" not in tests_paths, (
        f"path under no recognized prefix should NOT be in tests bucket; "
        f"got tests_paths={tests_paths}"
    )


def test_classify_staged_recognizes_sibling_library_impl_paths() -> None:
    """`_classify_staged` buckets sibling-library impl paths correctly.

    Per the cross-repo coordination contract in
    `livespec/SPECIFICATION/contracts.md` §"Cross-repo coordination —
    pin-and-bump", the dev-tooling repo's RGR check is consumed by
    every livespec-governed sibling repo: livespec-runtime,
    livespec-impl-git-jsonl, livespec-dev-tooling itself, and future
    livespec-impl-<X> plugins. Each repo's impl tree lives at a
    repo-specific prefix:

      - `livespec_runtime/`                          (livespec-runtime)
      - `livespec_dev_tooling/`                     (livespec-dev-tooling, self)
      - `.claude-plugin/scripts/livespec_impl_git_jsonl/`
                                                    (livespec-impl-git-jsonl)

    Without these prefixes in `_IMPL_PREFIXES`, `feat:` / `fix:`
    commits in those repos that touch the package source classify as
    test-only (no impl bucket), which incorrectly trips the
    Red-without-Green diagnostic and forces consumers onto a `chore:`
    workaround. This test pins recognition of all three.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "red_green_replay_for_sibling_classify_test",
        str(_RED_GREEN_REPLAY),
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    paths = [
        "livespec_runtime/cross_repo/resolve.py",
        "livespec_dev_tooling/checks/red_green_replay.py",
        ".claude-plugin/scripts/livespec_impl_git_jsonl/commands/list_memos.py",
        "tests/livespec_runtime/test_smoke.py",
        "README.md",
    ]
    _tests_paths, impl_paths = module._classify_staged(paths=paths)  # noqa: SLF001
    assert "livespec_runtime/cross_repo/resolve.py" in impl_paths, (
        f"`livespec_runtime/...` path should be in impl bucket; " f"got impl_paths={impl_paths}"
    )
    assert "livespec_dev_tooling/checks/red_green_replay.py" in impl_paths, (
        f"`livespec_dev_tooling/...` path should be in impl bucket; " f"got impl_paths={impl_paths}"
    )
    assert ".claude-plugin/scripts/livespec_impl_git_jsonl/commands/list_memos.py" in impl_paths, (
        f"`.claude-plugin/scripts/livespec_impl_git_jsonl/...` path should be in impl bucket; "
        f"got impl_paths={impl_paths}"
    )
    assert (
        "README.md" not in impl_paths
    ), f"top-level docs path should NOT be in impl bucket; got impl_paths={impl_paths}"


def test_classify_staged_recognizes_impl_beads_path() -> None:
    """`_classify_staged` buckets `livespec-impl-beads` impl paths as impl.

    Per the cross-repo coordination contract in
    `livespec/SPECIFICATION/contracts.md` §"Cross-repo coordination —
    pin-and-bump", the `livespec-impl-beads` plugin's impl tree lives
    at `.claude-plugin/scripts/livespec_impl_beads/`, mirroring the
    `livespec-impl-git-jsonl` sibling. Without that prefix in
    `_IMPL_PREFIXES`, every `feat:` / `fix:` commit touching the
    plugin's package source classifies as test-only (no impl bucket),
    which incorrectly trips the Red-without-Green diagnostic and blocks
    the plugin from committing ANY product `.py` via the RGR ritual.
    This test pins recognition of the beads impl prefix and that it
    pairs with a `tests/livespec_impl_beads/...` test path.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "red_green_replay_for_impl_beads_classify_test",
        str(_RED_GREEN_REPLAY),
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    paths = [
        ".claude-plugin/scripts/livespec_impl_beads/_beads_client.py",
        "tests/livespec_impl_beads/test_beads_client.py",
        "README.md",
    ]
    tests_paths, impl_paths = module._classify_staged(paths=paths)  # noqa: SLF001
    assert ".claude-plugin/scripts/livespec_impl_beads/_beads_client.py" in impl_paths, (
        f"`.claude-plugin/scripts/livespec_impl_beads/...` path should be in impl bucket; "
        f"got impl_paths={impl_paths}"
    )
    assert "tests/livespec_impl_beads/test_beads_client.py" in tests_paths, (
        f"`tests/livespec_impl_beads/...` path should be in tests bucket; "
        f"got tests_paths={tests_paths}"
    )
    assert (
        ".claude-plugin/scripts/livespec_impl_beads/_beads_client.py" not in tests_paths
    ), f"beads impl path should NOT be in tests bucket; got tests_paths={tests_paths}"
    assert (
        "README.md" not in impl_paths
    ), f"top-level docs path should NOT be in impl bucket; got impl_paths={impl_paths}"


def test_red_green_replay_module_importable_without_running_main() -> None:
    """The check module imports cleanly without invoking main().

    Structural test mirroring the project convention (see e.g.
    `test_check_tools.py::test_check_tools_module_importable_without_running_main`):
    importing the module exercises the `if __name__ == "__main__":`
    False branch so per-file coverage hits 100% line+branch.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "red_green_replay_for_import_test",
        str(_RED_GREEN_REPLAY),
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module.main), "main should be importable without invocation"


def test_feat_with_neither_tests_nor_impl_staged_exits_zero(
    *,
    tmp_path: Path,
) -> None:
    """A feat: subject with staged paths that are neither tests nor impl exits 0.

    Pins the content-trigger pass where `_classify_staged` returns
    `(tests_paths=[], impl_paths=[])` — staged files are config,
    docs, templates, top-level scripts, or any path that doesn't
    start with `tests/` or one of the `_IMPL_PREFIXES`. No product
    impl `.py` is staged, so there is nothing for the ritual to
    verify and the hook passes regardless of prefix (the old
    `staged-not-classifiable` rejection — which forced a
    chore(template): workaround for feat:-worthy non-Python
    changes — is retired).
    """
    subprocess.run(
        ["git", "init", "-q"],
        cwd=str(tmp_path),
        check=True,
        env=_scrubbed_env(),
    )
    (tmp_path / "templates").mkdir()
    config_file = tmp_path / "templates" / "foo.yml"
    config_file.write_text("key: value\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "templates/foo.yml"],
        cwd=str(tmp_path),
        check=True,
        env=_scrubbed_env(),
    )

    msg_path = tmp_path / "COMMIT_EDITMSG"
    msg_path.write_text("feat: add new template\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(_RED_GREEN_REPLAY), str(msg_path)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
        env=_scrubbed_env(),
    )

    assert result.returncode == 0, (
        f"feat: with neither-tests-nor-impl staged must pass (content trigger absent); "
        f"got returncode={result.returncode} stderr={result.stderr!r}"
    )
    assert "staged-not-classifiable" not in result.stderr, (
        f"the retired 'staged-not-classifiable' rejection must not fire; "
        f"got stderr={result.stderr!r}"
    )


@pytest.mark.parametrize(
    "subject_token",
    [
        "chore: tidy the impl tree",
        "fabro(run-7f3k): worker-node (failed)",
        "refactor: reorganize helpers",
        "feat: refactor with no new test",
    ],
)
def test_any_subject_staging_impl_without_red_takes_suite_green_leg(
    *,
    subject_token: str,
    tmp_path: Path,
) -> None:
    """Product impl `.py` staged without Red trailers takes the green-verified leg, any prefix.

    User design correction 2026-06-11: changing product code as part
    of a chore (or under a machine checkpoint subject, or as a
    behavior-preserving feat:/fix: refactor) is LEGITIMATE — the
    prefix never rejects a commit for containing product code. The
    commit is instead green-verified: the FULL pytest suite must pass
    against the staged tree, and the hook records the
    `TDD-Suite-Green-*` trailer shape as evidence. (The prior
    `product-mislabel` reject from the first eld iteration is
    retired.)
    """
    subprocess.run(
        ["git", "init", "-q"],
        cwd=str(tmp_path),
        check=True,
        env=_scrubbed_env(),
    )
    impl_dir = tmp_path / "livespec"
    impl_dir.mkdir()
    (impl_dir / "foo.py").write_text("VALUE: int = 1\n", encoding="utf-8")
    # A passing test on disk: the green-verified leg runs the FULL
    # suite in the repo, which must collect and pass.
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_ok.py").write_text(
        "def test_ok() -> None:\n    assert True\n",
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "add", "livespec/foo.py"],
        cwd=str(tmp_path),
        check=True,
        env=_scrubbed_env(),
    )

    msg_path = tmp_path / "COMMIT_EDITMSG"
    msg_path.write_text(f"{subject_token}\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(_RED_GREEN_REPLAY), str(msg_path)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
        env=_scrubbed_env(),
    )

    assert result.returncode == 0, (
        f"{subject_token!r} staging product impl .py with a passing suite must "
        f"take the green-verified leg and exit 0; "
        f"got returncode={result.returncode} stderr={result.stderr!r}"
    )
    assert (
        "product-mislabel" not in result.stderr
    ), f"the retired product-mislabel reject must not fire; got stderr={result.stderr!r}"
    final_msg = msg_path.read_text(encoding="utf-8")
    assert "TDD-Suite-Green-Captured-At:" in final_msg, (
        f"green-verified leg must record TDD-Suite-Green-* trailers; "
        f"got final_msg={final_msg!r}"
    )


def test_impl_staged_without_red_and_failing_suite_rejects_suite_red(
    *,
    tmp_path: Path,
) -> None:
    """The green-verified leg REJECTS when the full suite fails against the staged tree.

    A failing suite means the change is NOT behavior-preserving as
    far as the tests can observe; the actionable `suite-red` reject
    tells the author to either fix the breakage or author the change
    via the Red->Green ritual if the behavior change is intended.
    """
    subprocess.run(
        ["git", "init", "-q"],
        cwd=str(tmp_path),
        check=True,
        env=_scrubbed_env(),
    )
    impl_dir = tmp_path / "livespec"
    impl_dir.mkdir()
    (impl_dir / "foo.py").write_text("VALUE: int = 2\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_broken.py").write_text(
        "def test_broken() -> None:\n    assert False, 'suite fails'\n",
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "add", "livespec/foo.py"],
        cwd=str(tmp_path),
        check=True,
        env=_scrubbed_env(),
    )

    msg_path = tmp_path / "COMMIT_EDITMSG"
    msg_path.write_text("chore: behavior-preserving cleanup (allegedly)\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(_RED_GREEN_REPLAY), str(msg_path)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
        env=_scrubbed_env(),
    )

    assert result.returncode != 0, (
        f"a failing suite must reject the green-verified leg; "
        f"got returncode={result.returncode} stderr={result.stderr!r}"
    )
    assert (
        "suite-red" in result.stderr
    ), f"expected 'suite-red' check_id in stderr; got stderr={result.stderr!r}"
    final_msg = msg_path.read_text(encoding="utf-8")
    assert "TDD-Suite-Green-Captured-At:" not in final_msg, (
        f"no suite trailers may be written on a suite-red reject; " f"got final_msg={final_msg!r}"
    )


def test_impl_staged_without_red_and_no_collectable_tests_rejects_suite_red(
    *,
    tmp_path: Path,
) -> None:
    """The green-verified leg REJECTS when the repo has no collectable tests at all.

    pytest exits 5 when zero tests are collected; only exit 0 counts
    as a green suite. A vacuously-empty suite proves nothing about
    behavior preservation, so the leg fails actionably rather than
    waving the product change through.
    """
    subprocess.run(
        ["git", "init", "-q"],
        cwd=str(tmp_path),
        check=True,
        env=_scrubbed_env(),
    )
    impl_dir = tmp_path / "livespec"
    impl_dir.mkdir()
    (impl_dir / "foo.py").write_text("VALUE: int = 3\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "livespec/foo.py"],
        cwd=str(tmp_path),
        check=True,
        env=_scrubbed_env(),
    )

    msg_path = tmp_path / "COMMIT_EDITMSG"
    msg_path.write_text("chore: cleanup in an untested repo\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(_RED_GREEN_REPLAY), str(msg_path)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
        env=_scrubbed_env(),
    )

    assert result.returncode != 0, (
        f"an empty (uncollectable) suite must reject the green-verified leg; "
        f"got returncode={result.returncode} stderr={result.stderr!r}"
    )
    assert (
        "suite-red" in result.stderr
    ), f"expected 'suite-red' check_id in stderr; got stderr={result.stderr!r}"


def test_suite_green_trailer_schema_is_complete(*, tmp_path: Path) -> None:
    """The green-verified leg writes the full TDD-Suite-Green-* trailer schema.

    Mirrors the Red-trailer schema test: scope, output checksum
    (sha256-prefixed), and captured-at must all land in
    COMMIT_EDITMSG so the commit-range validation (and any later
    audit) can recognize the suite-green evidence shape.
    """
    subprocess.run(
        ["git", "init", "-q"],
        cwd=str(tmp_path),
        check=True,
        env=_scrubbed_env(),
    )
    impl_dir = tmp_path / "livespec"
    impl_dir.mkdir()
    (impl_dir / "foo.py").write_text("VALUE: int = 4\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_ok.py").write_text(
        "def test_ok() -> None:\n    assert True\n",
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "add", "livespec/foo.py"],
        cwd=str(tmp_path),
        check=True,
        env=_scrubbed_env(),
    )

    msg_path = tmp_path / "COMMIT_EDITMSG"
    msg_path.write_text("refactor: behavior-preserving cleanup\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(_RED_GREEN_REPLAY), str(msg_path)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
        env=_scrubbed_env(),
    )

    assert result.returncode == 0, (
        f"green-verified leg with a passing suite must exit 0; "
        f"got returncode={result.returncode} stderr={result.stderr!r}"
    )
    final_msg = msg_path.read_text(encoding="utf-8")
    for trailer_key in (
        "TDD-Suite-Green-Scope:",
        "TDD-Suite-Green-Output-Checksum:",
        "TDD-Suite-Green-Captured-At:",
    ):
        assert (
            trailer_key in final_msg
        ), f"expected trailer {trailer_key!r} in COMMIT_EDITMSG; got final_msg={final_msg!r}"
    assert (
        "sha256:" in final_msg
    ), f"expected sha256: prefix on the suite output checksum; got final_msg={final_msg!r}"


def test_fabro_checkpoint_subject_with_non_product_staged_exits_zero(
    *,
    tmp_path: Path,
) -> None:
    """A machine checkpoint subject staging non-product paths exits 0.

    `fabro(<run_id>): <node> (<status>)` is not a Conventional
    Commit type at all; under the old prefix-fallthrough design it
    fell into the feat:/fix: ritual path and was rejected. Content
    is now the trigger: with only non-product paths staged the
    checkpoint commit passes the hook naturally (no
    `skip_git_hooks` carve-out needed).
    """
    subprocess.run(
        ["git", "init", "-q"],
        cwd=str(tmp_path),
        check=True,
        env=_scrubbed_env(),
    )
    (tmp_path / "notes.md").write_text("checkpoint payload\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "notes.md"],
        cwd=str(tmp_path),
        check=True,
        env=_scrubbed_env(),
    )

    msg_path = tmp_path / "COMMIT_EDITMSG"
    msg_path.write_text("fabro(run-7f3k): worker-node (ok)\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(_RED_GREEN_REPLAY), str(msg_path)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
        env=_scrubbed_env(),
    )

    assert result.returncode == 0, (
        f"machine checkpoint subject with non-product staging must pass; "
        f"got returncode={result.returncode} stderr={result.stderr!r}"
    )


def test_chore_with_passing_tests_only_staged_takes_suite_green_leg(*, tmp_path: Path) -> None:
    """A `chore:` subject staging tests-only `.py` that PASS takes the green-verified leg.

    A non-ritual prefix staging a passing test-only change (e.g.
    renaming a test) is a test-only cleanup: it must remain
    committable (the test passes by construction, so the Red leg
    cannot apply), and it is green-verified — the full suite runs
    and the `TDD-Suite-Green-*` evidence lands in the message.
    Only a `feat:`/`fix:` subject staging a PASSING test rejects
    (`test-passed-at-red`): that prefix declares a behavior change.
    """
    subprocess.run(
        ["git", "init", "-q"],
        cwd=str(tmp_path),
        check=True,
        env=_scrubbed_env(),
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_renamed.py").write_text(
        "def test_renamed() -> None:\n    assert True\n",
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "add", "tests/test_renamed.py"],
        cwd=str(tmp_path),
        check=True,
        env=_scrubbed_env(),
    )

    msg_path = tmp_path / "COMMIT_EDITMSG"
    msg_path.write_text("chore: rename a test\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(_RED_GREEN_REPLAY), str(msg_path)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
        env=_scrubbed_env(),
    )

    assert result.returncode == 0, (
        f"chore: staging passing tests-only .py must take the green-verified leg; "
        f"got returncode={result.returncode} stderr={result.stderr!r}"
    )
    final_msg = msg_path.read_text(encoding="utf-8")
    assert "TDD-Suite-Green-Captured-At:" in final_msg, (
        f"test-only cleanup must be green-verified with TDD-Suite-Green-* trailers; "
        f"got final_msg={final_msg!r}"
    )


def test_chore_with_failing_test_staged_alone_authors_a_red(*, tmp_path: Path) -> None:
    """A `chore:` subject staging a single FAILING test takes the Red leg (any prefix).

    ANY prefix may author a Red: a behavior-changing chore is
    allowed to do Red->Green exactly like a feature. The hook must
    record the full `TDD-Red-*` trailer schema and exit 0 so the
    subsequent amend can take the Green leg.
    """
    subprocess.run(
        ["git", "init", "-q"],
        cwd=str(tmp_path),
        check=True,
        env=_scrubbed_env(),
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_red.py").write_text(
        "def test_red() -> None:\n    assert False, 'chore-authored red'\n",
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "add", "tests/test_red.py"],
        cwd=str(tmp_path),
        check=True,
        env=_scrubbed_env(),
    )

    msg_path = tmp_path / "COMMIT_EDITMSG"
    msg_path.write_text("chore: tighten behavior via red-green\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(_RED_GREEN_REPLAY), str(msg_path)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
        env=_scrubbed_env(),
    )

    assert result.returncode == 0, (
        f"chore: staging a failing test alone must author a Red and exit 0; "
        f"got returncode={result.returncode} stderr={result.stderr!r}"
    )
    final_msg = msg_path.read_text(encoding="utf-8")
    assert "TDD-Red-Test-File-Checksum:" in final_msg, (
        f"a chore-authored Red must record the TDD-Red-* trailers; " f"got final_msg={final_msg!r}"
    )


def test_feat_staging_only_non_py_under_impl_prefix_exits_zero(*, tmp_path: Path) -> None:
    """A feat: subject staging only a non-`.py` file under an impl prefix exits 0.

    The content trigger is product impl `.py` — `_classify_staged`
    filters on the `.py` extension, so a data/config file under an
    impl prefix (e.g. `livespec/data.json`) does not enter the impl
    bucket and the ritual does not apply.
    """
    subprocess.run(
        ["git", "init", "-q"],
        cwd=str(tmp_path),
        check=True,
        env=_scrubbed_env(),
    )
    impl_dir = tmp_path / "livespec"
    impl_dir.mkdir()
    (impl_dir / "data.json").write_text('{"k": 1}\n', encoding="utf-8")
    subprocess.run(
        ["git", "add", "livespec/data.json"],
        cwd=str(tmp_path),
        check=True,
        env=_scrubbed_env(),
    )

    msg_path = tmp_path / "COMMIT_EDITMSG"
    msg_path.write_text("feat: ship a data file\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(_RED_GREEN_REPLAY), str(msg_path)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
        env=_scrubbed_env(),
    )

    assert result.returncode == 0, (
        f"feat: staging only non-.py under an impl prefix must pass; "
        f"got returncode={result.returncode} stderr={result.stderr!r}"
    )


def test_feat_with_tests_and_impl_staged_together_takes_suite_green_leg(
    *,
    tmp_path: Path,
) -> None:
    """A feat: subject with tests AND impl staged together (no prior Red) is green-verified.

    The old `mixed-buckets` reject is retired: product impl `.py`
    staged without Red trailers takes the green-verified leg
    regardless of co-staged tests. The full suite (including the
    co-staged test) must pass; the `TDD-Suite-Green-*` evidence
    lands in the message.
    """
    subprocess.run(
        ["git", "init", "-q"],
        cwd=str(tmp_path),
        check=True,
        env=_scrubbed_env(),
    )
    (tmp_path / "tests").mkdir()
    test_file = tmp_path / "tests" / "test_dummy.py"
    test_file.write_text("def test_x() -> None:\n    assert True\n", encoding="utf-8")
    (tmp_path / "livespec").mkdir()
    impl_file = tmp_path / "livespec" / "foo.py"
    impl_file.write_text("VALUE: int = 1\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "tests/test_dummy.py", "livespec/foo.py"],
        cwd=str(tmp_path),
        check=True,
        env=_scrubbed_env(),
    )

    msg_path = tmp_path / "COMMIT_EDITMSG"
    msg_path.write_text("feat: add mixed change\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(_RED_GREEN_REPLAY), str(msg_path)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
        env=_scrubbed_env(),
    )

    assert result.returncode == 0, (
        f"feat: with mixed buckets and a passing suite must be green-verified; "
        f"got returncode={result.returncode} stderr={result.stderr!r}"
    )
    assert (
        "mixed-buckets" not in result.stderr
    ), f"the retired mixed-buckets reject must not fire; got stderr={result.stderr!r}"
    final_msg = msg_path.read_text(encoding="utf-8")
    assert "TDD-Suite-Green-Captured-At:" in final_msg, (
        f"green-verified leg must record TDD-Suite-Green-* trailers; "
        f"got final_msg={final_msg!r}"
    )


def test_feat_with_impl_only_staged_no_prior_red_takes_suite_green_leg(
    *,
    tmp_path: Path,
) -> None:
    """A feat: subject with impl-only staged and no Red trailers takes the suite leg.

    The old `green-without-red` reject is retired: even a
    `feat:`/`fix:` subject may stage product impl `.py` without a
    prior Red (a behavior-preserving refactor shipped under a
    feature subject) — it is green-verified instead of rejected
    for its SHAPE. Here the fixture repo has no collectable tests,
    so the suite leg itself rejects with `suite-red` (exit 5 from
    pytest is not a green suite) — proving the dispatch went to
    the suite leg, not to a shape reject.
    """
    subprocess.run(
        ["git", "init", "-q"],
        cwd=str(tmp_path),
        check=True,
        env=_scrubbed_env(),
    )
    (tmp_path / "livespec").mkdir()
    impl_file = tmp_path / "livespec" / "foo.py"
    impl_file.write_text("VALUE: int = 1\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "livespec/foo.py"],
        cwd=str(tmp_path),
        check=True,
        env=_scrubbed_env(),
    )

    msg_path = tmp_path / "COMMIT_EDITMSG"
    msg_path.write_text("feat: add impl-only change\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(_RED_GREEN_REPLAY), str(msg_path)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
        env=_scrubbed_env(),
    )

    assert result.returncode != 0, (
        f"impl-only staged in a repo with no collectable tests must reject via "
        f"suite-red; got returncode={result.returncode}"
    )
    assert (
        "green-without-red" not in result.stderr
    ), f"the retired green-without-red reject must not fire; got stderr={result.stderr!r}"
    assert "suite-red" in result.stderr, (
        f"expected the suite-red check_id (dispatch went to the suite leg); "
        f"got stderr={result.stderr!r}"
    )


# ---------------------------------------------------------------
# Self-explaining rejections (work-item li-rgr-docs-wi2): EVERY
# rejection mode MUST emit the FULL 2-step Red-Green-Replay protocol
# alongside its mode-specific hint, so a fresh agent recovers the
# correct authoring sequence without spelunking the source. These
# distinctive protocol-text markers must appear in the stderr JSON of
# every reject branch across BOTH `red_green_replay.py` (the
# commit-range reject) and `_red_green_replay_modes.py` (Red-leg /
# Green-leg / suite-green-leg rejects).
# ---------------------------------------------------------------
_PROTOCOL_MARKERS: tuple[str, ...] = (
    "Red-Green-Replay protocol",
    "stage the test file ALONE",
    "Green amend",
    "byte-identical",
)


def _assert_protocol_in_stderr(*, stderr: str, mode: str) -> None:
    """Assert every protocol marker is present in a reject branch's stderr."""
    for marker in _PROTOCOL_MARKERS:
        assert marker in stderr, (
            f"reject mode {mode!r} must emit the full Red-Green-Replay "
            f"protocol; missing marker {marker!r} in stderr={stderr!r}"
        )


def test_suite_red_reject_prints_full_protocol(*, tmp_path: Path) -> None:
    """`red-green-replay-suite-red` reject emits the full protocol."""
    subprocess.run(["git", "init", "-q"], cwd=str(tmp_path), check=True, env=_scrubbed_env())
    (tmp_path / "livespec").mkdir()
    (tmp_path / "livespec" / "foo.py").write_text("VALUE: int = 1\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_broken.py").write_text(
        "def test_broken() -> None:\n    assert False, 'suite fails'\n",
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "add", "livespec/foo.py"],
        cwd=str(tmp_path),
        check=True,
        env=_scrubbed_env(),
    )
    msg_path = tmp_path / "COMMIT_EDITMSG"
    msg_path.write_text("chore: cleanup that breaks the suite\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(_RED_GREEN_REPLAY), str(msg_path)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
        env=_scrubbed_env(),
    )

    assert result.returncode != 0
    assert "suite-red" in result.stderr
    _assert_protocol_in_stderr(stderr=result.stderr, mode="suite-red")


def test_multi_test_file_reject_prints_full_protocol(*, tmp_path: Path) -> None:
    """`red-green-replay-multi-test-file` reject emits the full protocol."""
    subprocess.run(["git", "init", "-q"], cwd=str(tmp_path), check=True, env=_scrubbed_env())
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text(
        "def test_a() -> None:\n    assert True\n", encoding="utf-8"
    )
    (tmp_path / "tests" / "test_b.py").write_text(
        "def test_b() -> None:\n    assert True\n", encoding="utf-8"
    )
    subprocess.run(
        ["git", "add", "tests/test_a.py", "tests/test_b.py"],
        cwd=str(tmp_path),
        check=True,
        env=_scrubbed_env(),
    )
    msg_path = tmp_path / "COMMIT_EDITMSG"
    msg_path.write_text("feat: add new feature\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(_RED_GREEN_REPLAY), str(msg_path)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
        env=_scrubbed_env(),
    )

    assert result.returncode != 0
    assert "multi-test-file" in result.stderr
    _assert_protocol_in_stderr(stderr=result.stderr, mode="multi-test-file")


def test_test_passed_at_red_reject_prints_full_protocol(*, tmp_path: Path) -> None:
    """`red-green-replay-test-passed-at-red` reject emits the full protocol."""
    subprocess.run(["git", "init", "-q"], cwd=str(tmp_path), check=True, env=_scrubbed_env())
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_passing.py").write_text(
        "def test_passing() -> None:\n    assert True\n", encoding="utf-8"
    )
    subprocess.run(
        ["git", "add", "tests/test_passing.py"],
        cwd=str(tmp_path),
        check=True,
        env=_scrubbed_env(),
    )
    msg_path = tmp_path / "COMMIT_EDITMSG"
    msg_path.write_text("feat: add new feature\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(_RED_GREEN_REPLAY), str(msg_path)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
        env=_scrubbed_env(),
    )

    assert result.returncode != 0
    assert "test-passed-at-red" in result.stderr
    _assert_protocol_in_stderr(stderr=result.stderr, mode="test-passed-at-red")


def _author_green_fixture(*, tmp_path: Path, test_bytes: bytes, recorded_checksum: str) -> Path:
    """Init a tmp repo with a Red commit carrying `recorded_checksum`, stage impl.

    Returns the COMMIT_EDITMSG path ready for the Green-amend hook
    invocation. Used by the two Green-mode reject protocol tests.
    """
    subprocess.run(["git", "init", "-q"], cwd=str(tmp_path), check=True, env=_scrubbed_env())
    subprocess.run(
        ["git", "config", "user.email", "test@test.test"],
        cwd=str(tmp_path),
        check=True,
        env=_scrubbed_env(),
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=str(tmp_path),
        check=True,
        env=_scrubbed_env(),
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_x.py").write_bytes(test_bytes)
    subprocess.run(
        ["git", "add", "tests/test_x.py"],
        cwd=str(tmp_path),
        check=True,
        env=_scrubbed_env(),
    )
    red_commit_msg = (
        "feat: red commit\n"
        "\n"
        "TDD-Red-Test: tests/test_x.py\n"
        "TDD-Red-Failure-Reason: stub\n"
        f"TDD-Red-Test-File-Checksum: {recorded_checksum}\n"
        "TDD-Red-Output-Checksum: sha256:abc\n"
        "TDD-Red-Captured-At: 2026-05-02T05:00:00Z\n"
    )
    subprocess.run(
        ["git", "commit", "-m", red_commit_msg],
        cwd=str(tmp_path),
        check=True,
        env=_scrubbed_env(),
    )
    (tmp_path / "livespec").mkdir()
    (tmp_path / "livespec" / "foo.py").write_text("VALUE: int = 1\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "livespec/foo.py"],
        cwd=str(tmp_path),
        check=True,
        env=_scrubbed_env(),
    )
    msg_path = tmp_path / "COMMIT_EDITMSG"
    msg_path.write_text("feat: green impl\n", encoding="utf-8")
    return msg_path


def test_checksum_mismatch_reject_prints_full_protocol(*, tmp_path: Path) -> None:
    """`red-green-replay-checksum-mismatch` reject emits the full protocol."""
    test_bytes = b"def test_x() -> None:\n    assert True\n"
    # Recorded checksum deliberately does NOT match the working-tree test.
    msg_path = _author_green_fixture(
        tmp_path=tmp_path,
        test_bytes=test_bytes,
        recorded_checksum="sha256:" + "0" * 64,
    )

    result = subprocess.run(
        [sys.executable, str(_RED_GREEN_REPLAY), str(msg_path)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
        env=_scrubbed_env(),
    )

    assert result.returncode != 0
    assert "checksum-mismatch" in result.stderr
    _assert_protocol_in_stderr(stderr=result.stderr, mode="checksum-mismatch")


def test_test_still_failing_reject_prints_full_protocol(*, tmp_path: Path) -> None:
    """`red-green-replay-test-still-failing` reject emits the full protocol."""
    test_bytes = b"def test_x() -> None:\n    assert False, 'still-failing'\n"
    real_checksum = f"sha256:{hashlib.sha256(test_bytes).hexdigest()}"
    msg_path = _author_green_fixture(
        tmp_path=tmp_path,
        test_bytes=test_bytes,
        recorded_checksum=real_checksum,
    )

    result = subprocess.run(
        [sys.executable, str(_RED_GREEN_REPLAY), str(msg_path)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
        env=_scrubbed_env(),
    )

    assert result.returncode != 0
    assert "test-still-failing" in result.stderr
    _assert_protocol_in_stderr(stderr=result.stderr, mode="test-still-failing")


def test_chore_green_amend_after_red_takes_green_leg(*, tmp_path: Path) -> None:
    """A non-feat:/fix: subject amending onto Red trailers takes the Green leg.

    Branch 4 of the decision tree is prefix-agnostic: ANY prefix may
    complete a Red->Green pair (a behavior-changing chore authors
    Red then amends Green exactly like a feature). The recorded test
    re-runs green and the `TDD-Green-*` trailers land.
    """
    test_bytes = b"def test_x() -> None:\n    assert True\n"
    real_checksum = f"sha256:{hashlib.sha256(test_bytes).hexdigest()}"
    msg_path = _author_green_fixture(
        tmp_path=tmp_path,
        test_bytes=test_bytes,
        recorded_checksum=real_checksum,
    )
    msg_path.write_text("chore: green impl for a chore-authored red\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(_RED_GREEN_REPLAY), str(msg_path)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
        env=_scrubbed_env(),
    )

    assert result.returncode == 0, (
        f"chore: amending impl onto Red trailers must take the Green leg; "
        f"got returncode={result.returncode} stderr={result.stderr!r}"
    )
    final_msg = msg_path.read_text(encoding="utf-8")
    assert "TDD-Green-Verified-At:" in final_msg, (
        f"the Green leg must record TDD-Green-* trailers regardless of prefix; "
        f"got final_msg={final_msg!r}"
    )


# ---------------------------------------------------------------------------
# Commit-range validation (work-item livespec-dev-tooling-eld + the
# 2026-06-11 green-verified correction): with NO msg-path argv (the
# canonical-aggregate / `just check` / pre-push / CI invocation), the hook
# validates EVERY non-merge commit in `origin/master..HEAD` — any commit
# touching product impl `.py` must carry EITHER the TDD-Red-*/TDD-Green-*
# pair shape OR the TDD-Suite-Green-* shape, REGARDLESS of subject prefix.
# This supersedes the old HEAD-only `_validate_head`, which waved exempt
# prefixes through with no content inspection (the multi-commit + chore:
# holes). An explicit msg path still behaves as the commit-msg hook.
# ---------------------------------------------------------------------------


def _range_git(*, tmp_path: Path, args: list[str]) -> None:
    """Run one git command inside the tmp_path fixture repo."""
    subprocess.run(
        ["git", *args],
        cwd=str(tmp_path),
        check=True,
        capture_output=True,
        text=True,
        env=_scrubbed_env(),
    )


def _init_range_repo(*, tmp_path: Path) -> None:
    """Init a tmp repo with one base commit and `origin/master` pinned to it.

    The `origin/master` remote-tracking ref is created via
    `git update-ref` (no actual remote needed): the range check
    only requires the ref to RESOLVE so `origin/master..HEAD`
    enumerates the branch's own commits.
    """
    _range_git(tmp_path=tmp_path, args=["init", "-q"])
    _range_git(tmp_path=tmp_path, args=["config", "user.email", "test@example.com"])
    _range_git(tmp_path=tmp_path, args=["config", "user.name", "Test"])
    _range_git(tmp_path=tmp_path, args=["config", "commit.gpgsign", "false"])
    (tmp_path / "base.txt").write_text("base\n", encoding="utf-8")
    _range_git(tmp_path=tmp_path, args=["add", "-A"])
    _range_git(tmp_path=tmp_path, args=["commit", "-qm", "chore: base"])
    _range_git(tmp_path=tmp_path, args=["update-ref", "refs/remotes/origin/master", "HEAD"])


def _commit_all(*, tmp_path: Path, message: str) -> None:
    """Stage everything and commit with `message` in the fixture repo."""
    _range_git(tmp_path=tmp_path, args=["add", "-A"])
    _range_git(tmp_path=tmp_path, args=["commit", "-qm", message])


def _run_no_arg(*, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_RED_GREEN_REPLAY)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
        env=_scrubbed_env(),
    )


def test_no_arg_unresolvable_base_rejects_with_actionable_fetch_hint(*, tmp_path: Path) -> None:
    """No argv + `origin/master` unresolvable → exit non-zero with a fetch hint.

    A shallow / single-ref CI checkout (actions/checkout default
    fetch-depth: 1 on a non-master ref) cannot enumerate the range;
    the check MUST fail ACTIONABLY (naming origin/master and the
    fetch remedy), never silently pass.
    """
    _range_git(tmp_path=tmp_path, args=["init", "-q"])
    _range_git(tmp_path=tmp_path, args=["config", "user.email", "test@example.com"])
    _range_git(tmp_path=tmp_path, args=["config", "user.name", "Test"])
    _range_git(tmp_path=tmp_path, args=["config", "commit.gpgsign", "false"])
    (tmp_path / "base.txt").write_text("base\n", encoding="utf-8")
    _commit_all(tmp_path=tmp_path, message="chore: base")

    result = _run_no_arg(tmp_path=tmp_path)

    assert result.returncode != 0, (
        f"unresolvable origin/master must fail actionably, not pass silently; "
        f"got returncode={result.returncode} stderr={result.stderr!r}"
    )
    assert (
        "origin/master" in result.stderr
    ), f"rejection should name the unresolvable base ref; stderr={result.stderr!r}"
    assert "fetch" in result.stderr.lower(), (
        f"rejection should hint at the fetch remedy (e.g. fetch-depth: 0); "
        f"stderr={result.stderr!r}"
    )


def test_no_arg_empty_range_exits_zero(*, tmp_path: Path) -> None:
    """No argv + HEAD == origin/master (empty range) → exit 0.

    On master itself (or any branch with no commits past the base)
    `origin/master..HEAD` is empty and the check trivially passes.
    """
    _init_range_repo(tmp_path=tmp_path)
    result = _run_no_arg(tmp_path=tmp_path)
    assert result.returncode == 0, (
        f"empty origin/master..HEAD range should exit 0; "
        f"got returncode={result.returncode} stderr={result.stderr!r}"
    )


def test_no_arg_range_chore_commit_touching_product_py_rejects(*, tmp_path: Path) -> None:
    """No argv + a `chore:` range commit touching product impl `.py` with NO trailers → reject.

    The trailer-shape requirement is content-based: the prefix does
    not matter (this closes the old `_validate_head` exempt-prefix
    wave-through). The rejection MUST name the
    `range-missing-trailers` check_id, name BOTH acceptable shapes
    (the Red+Green pair AND the suite-green shape), prescribe the
    rewrite + force-push remedy (scoped to unmerged feature branches
    — the 'never force-push' rule covers shared/protected refs), and
    emit the full protocol so the author can redo the change
    correctly.
    """
    _init_range_repo(tmp_path=tmp_path)
    (tmp_path / "livespec").mkdir()
    (tmp_path / "livespec" / "foo.py").write_text("VALUE: int = 1\n", encoding="utf-8")
    _commit_all(tmp_path=tmp_path, message="chore: sneak in product code")

    result = _run_no_arg(tmp_path=tmp_path)

    assert result.returncode != 0, (
        f"range commit touching product .py without trailers must reject; "
        f"got returncode={result.returncode} stderr={result.stderr!r}"
    )
    assert (
        "range-missing-trailers" in result.stderr
    ), f"expected 'range-missing-trailers' check_id in stderr; stderr={result.stderr!r}"
    assert "force-push" in result.stderr, (
        f"rejection should prescribe the rewrite + force-push remedy; " f"stderr={result.stderr!r}"
    )
    assert "TDD-Suite-Green" in result.stderr, (
        f"rejection should name the suite-green shape as an acceptable alternative; "
        f"stderr={result.stderr!r}"
    )
    _assert_protocol_in_stderr(stderr=result.stderr, mode="range-missing-trailers")


def test_no_arg_range_commit_with_suite_green_shape_exits_zero(*, tmp_path: Path) -> None:
    """No argv + a range commit touching product `.py` with the suite-green shape → exit 0.

    The green-verified leg's `TDD-Suite-Green-*` trailer shape is a
    first-class alternative to the Red+Green pair: a
    behavior-preserving product commit verified by a full green
    suite passes the range check.
    """
    _init_range_repo(tmp_path=tmp_path)
    (tmp_path / "livespec").mkdir()
    (tmp_path / "livespec" / "foo.py").write_text("VALUE: int = 1\n", encoding="utf-8")
    message = (
        "chore: behavior-preserving cleanup\n"
        "\n"
        "TDD-Suite-Green-Scope: full-suite\n"
        "TDD-Suite-Green-Output-Checksum: sha256:deadbeef\n"
        "TDD-Suite-Green-Captured-At: 2026-06-11T00:00:00Z\n"
    )
    _commit_all(tmp_path=tmp_path, message=message)

    result = _run_no_arg(tmp_path=tmp_path)

    assert result.returncode == 0, (
        f"suite-green-shaped product commit in range should exit 0; "
        f"got returncode={result.returncode} stderr={result.stderr!r}"
    )


def test_no_arg_range_commit_with_full_trailer_shape_exits_zero(*, tmp_path: Path) -> None:
    """No argv + a range commit touching product `.py` WITH both trailer sets → exit 0."""
    _init_range_repo(tmp_path=tmp_path)
    (tmp_path / "livespec").mkdir()
    (tmp_path / "livespec" / "foo.py").write_text("VALUE: int = 1\n", encoding="utf-8")
    message = (
        "feat: add a feature\n"
        "\n"
        "TDD-Red-Test-File-Checksum: sha256:deadbeef\n"
        "TDD-Green-Verified-At: 2026-06-02T00:00:00Z\n"
    )
    _commit_all(tmp_path=tmp_path, message=message)

    result = _run_no_arg(tmp_path=tmp_path)

    assert result.returncode == 0, (
        f"properly-trailered product commit in range should exit 0; "
        f"got returncode={result.returncode} stderr={result.stderr!r}"
    )


def test_no_arg_range_commit_touching_only_non_product_paths_exits_zero(
    *,
    tmp_path: Path,
) -> None:
    """No argv + range commits touching only non-product paths → exit 0 (any prefix)."""
    _init_range_repo(tmp_path=tmp_path)
    (tmp_path / "notes.md").write_text("notes\n", encoding="utf-8")
    _commit_all(tmp_path=tmp_path, message="fabro(run-7f3k): worker-node (ok)")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_thing.py").write_text(
        "def test_thing() -> None:\n    assert True\n",
        encoding="utf-8",
    )
    _commit_all(tmp_path=tmp_path, message="chore: add a test fixture")

    result = _run_no_arg(tmp_path=tmp_path)

    assert result.returncode == 0, (
        f"range commits without product impl .py should exit 0 regardless of prefix; "
        f"got returncode={result.returncode} stderr={result.stderr!r}"
    )
