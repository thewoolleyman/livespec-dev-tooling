"""Red-leg, Green-leg, and suite-green-leg handlers for `red_green_replay`.

Extracted from `red_green_replay.py` at cycle 4c so the parent
file's LLOC stays under the 200-line ceiling enforced by
`check-complexity`; the suite-green handler (the green-verified
leg, user design correction 2026-06-11) lives here for the same
reason. The leading underscore in the filename marks this as a
private sibling module — entry-point check scripts under
`dev-tooling/checks/` have no underscore prefix.
"""

from __future__ import annotations

import datetime
import hashlib
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    import structlog.stdlib

# The vendored `returns` resolves through this module's OWN preamble rather
# than through whichever importer happened to run first — the state the
# module that broke the 2026-07-30 release fan-out was in.
_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))
# Make the script's own directory importable so the sibling `_*` trailer-I/O
# module resolves when this module is loaded standalone (the importlib test
# path) as well as via the parent supervisor's own sys.path insert.
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from _red_green_replay_trailers import (  # noqa: E402  — sibling private import
    _narrate_git_failure,
    current_head_sha,
    head_trailer_value,
    write_trailers,
)
from returns.io import IOFailure  # noqa: E402  — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

# These symbols form this private sibling module's public surface to
# its sole importer, `red_green_replay.py` (the parent supervisor imports
# them after a runtime `sys.path.insert`). Declaring them in `__all__` marks
# them as exported so pyright's standalone analysis does not flag them as
# `reportUnusedFunction` — the import IS the use, just across the
# extraPaths-resolved sibling boundary.
__all__: list[str] = [
    "RED_GREEN_REPLAY_PROTOCOL",
    "_handle_green_mode",
    "_handle_red_mode",
    "_handle_suite_green_mode",
]


# The full 2-step Red-Green-Replay protocol, emitted verbatim by EVERY
# rejection branch (here AND in the parent `red_green_replay.py`) so a
# developer or fresh agent recovers the correct authoring sequence from
# the hook output alone, without spelunking the check source
# (work-item li-rgr-docs-wi2). Each reject's mode-specific `hint` says
# what is locally wrong; this `protocol` field says what the correct
# full sequence is.
RED_GREEN_REPLAY_PROTOCOL: str = (
    "Red-Green-Replay protocol (single-commit TDD ritual). "
    "Step 1 — Red commit: stage the test file ALONE (no impl) and commit. The hook runs pytest "
    "on the staged tree; the new test MUST fail meaningfully (an assertion failure, NOT an "
    "ImportError / collection error). ANY subject prefix may author a Red — fix:/feat: declares "
    "the behavior change, and a behavior-changing chore Reds the same way. The hook records "
    "TDD-Red-* trailers (test path, failure reason, test-file checksum, output checksum, "
    "captured-at). "
    "Step 2 — Green amend: stage the impl and run `git commit --amend`. The hook sees the "
    "TDD-Red-* trailers + staged impl, re-runs the SAME test (now passing), and records "
    "TDD-Green-* trailers. The final SINGLE commit carries both files + both trailer sets. The "
    "test file bytes MUST be byte-identical across the Red->Green pair; to change the test, "
    "author a new Red commit. "
    "Behavior-PRESERVING product changes (no new failing test) instead take the green-verified "
    "leg: the FULL pytest suite must pass against the staged tree, and TDD-Suite-Green-* "
    "trailers are recorded as the evidence shape."
)


def _handle_red_mode(
    *,
    msg_path: Path,
    log: structlog.stdlib.BoundLogger,
    tests_paths: list[str],
) -> int:
    if len(tests_paths) > 1:
        log.error(
            "multi-test-file: Red mode is per-file (one test file per commit)",
            check_id="red-green-replay-multi-test-file",
            tests_paths=tests_paths,
            hint=(
                "The v034 D2 trailer schema's "
                "`TDD-Red-Test-File-Checksum:` is a singular field; "
                "stage exactly one test file per Red commit."
            ),
            protocol=RED_GREEN_REPLAY_PROTOCOL,
        )
        return 1
    test_file_path = Path.cwd() / tests_paths[0]
    test_file_bytes = test_file_path.read_bytes()
    test_file_checksum = f"sha256:{hashlib.sha256(test_file_bytes).hexdigest()}"
    log.info(
        "red-mode-candidate: tests-only staged tree",
        check_id="red-green-replay-red-mode-candidate",
        tests_paths=tests_paths,
        test_file_checksum=test_file_checksum,
    )
    pytest_result = subprocess.run(
        [sys.executable, "-m", "pytest", str(test_file_path), "--tb=no", "-q"],
        capture_output=True,
        text=True,
        check=False,
    )
    if pytest_result.returncode == 0:
        log.error(
            "test-passed-at-red-moment: not a valid Red moment",
            check_id="red-green-replay-test-passed-at-red",
            tests_paths=tests_paths,
            test_file_checksum=test_file_checksum,
            pytest_returncode=pytest_result.returncode,
            hint=(
                "Red mode requires the staged test to fail; "
                "if the test already passes, this is not a Red "
                "moment (the subsequent Green amend has "
                "nothing to verify)."
            ),
            protocol=RED_GREEN_REPLAY_PROTOCOL,
        )
        return 1
    log.info(
        "red-pytest-result: test failed at Red moment as required",
        check_id="red-green-replay-red-pytest-result",
        tests_paths=tests_paths,
        test_file_checksum=test_file_checksum,
        pytest_returncode=pytest_result.returncode,
    )
    pytest_output = pytest_result.stdout + pytest_result.stderr
    output_checksum = f"sha256:{hashlib.sha256(pytest_output.encode('utf-8')).hexdigest()}"
    captured_at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    failure_reason = " ".join(pytest_output.split())[:200]
    write_trailers(
        msg_path=msg_path,
        trailers=(
            ("TDD-Red-Test", tests_paths[0]),
            ("TDD-Red-Failure-Reason", failure_reason),
            ("TDD-Red-Test-File-Checksum", test_file_checksum),
            ("TDD-Red-Output-Checksum", output_checksum),
            ("TDD-Red-Captured-At", captured_at),
        ),
    )
    return 0


def _handle_suite_green_mode(
    *,
    msg_path: Path,
    log: structlog.stdlib.BoundLogger,
    staged_paths: list[str],
) -> int:
    """Green-verify a product/test change that carries no new failing test.

    The green-verified leg (user design correction 2026-06-11): a
    behavior-preserving change — a refactor, a chore touching
    product `.py`, or a passing test-only cleanup — is admitted by
    running the FULL pytest suite against the staged tree. Exit 0
    is the ONLY green outcome (pytest exit 5, zero tests collected,
    proves nothing and rejects). On green, the `TDD-Suite-Green-*`
    trailer shape (scope, output checksum, captured-at — mirroring
    the Red-leg evidence fields) lands in the commit message so the
    commit-range validation recognizes the commit as verified.
    """
    log.info(
        "suite-green-candidate: product/test change without a Red leg; " "running the full suite",
        check_id="red-green-replay-suite-green-candidate",
        staged_paths=staged_paths,
    )
    suite_result = subprocess.run(
        [sys.executable, "-m", "pytest", "--tb=no", "-q"],
        capture_output=True,
        text=True,
        check=False,
    )
    suite_output = suite_result.stdout + suite_result.stderr
    if suite_result.returncode != 0:
        log.error(
            "suite-red: the full pytest suite does not pass against the staged tree",
            check_id="red-green-replay-suite-red",
            pytest_returncode=suite_result.returncode,
            failure_summary=" ".join(suite_output.split())[:400],
            hint=(
                "The green-verified leg requires the FULL suite to pass (exit 0; "
                "an empty suite, pytest exit 5, also rejects): a behavior-"
                "preserving change must keep every existing test green. If this "
                "change is SUPPOSED to alter behavior, author it via the ritual "
                "instead: Red commit (stage the failing test alone), then Green "
                "amend (stage the impl)."
            ),
            protocol=RED_GREEN_REPLAY_PROTOCOL,
        )
        return 1
    output_checksum = f"sha256:{hashlib.sha256(suite_output.encode('utf-8')).hexdigest()}"
    captured_at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    write_trailers(
        msg_path=msg_path,
        trailers=(
            ("TDD-Suite-Green-Scope", "full-suite"),
            ("TDD-Suite-Green-Output-Checksum", output_checksum),
            ("TDD-Suite-Green-Captured-At", captured_at),
        ),
    )
    return 0


def _handle_green_mode(
    *,
    msg_path: Path,
    log: structlog.stdlib.BoundLogger,
    impl_paths: list[str],
) -> int:
    log.info(
        "green-mode-candidate: HEAD~0 carries Red trailers + impl staged",
        check_id="red-green-replay-green-mode-candidate",
        impl_paths=impl_paths,
    )
    # Both reads are on the `IOResult` railway (livespec-dev-tooling-qndn) and
    # a failed one REFUSES the amend. The empty string these used to return on
    # a failed git is what `Path.cwd() / recorded_test` would then resolve to —
    # the repo root — and the checksum comparison below would report a
    # mismatch, blaming the AUTHOR for an environment fault.
    recorded = head_trailer_value(key="TDD-Red-Test")
    if isinstance(recorded, IOFailure):
        return _narrate_git_failure(log=log, failed=unsafe_perform_io(recorded.failure()))
    checksum = head_trailer_value(key="TDD-Red-Test-File-Checksum")
    if isinstance(checksum, IOFailure):
        return _narrate_git_failure(log=log, failed=unsafe_perform_io(checksum.failure()))
    recorded_test = unsafe_perform_io(recorded.unwrap())
    recorded_checksum = unsafe_perform_io(checksum.unwrap())
    green_test_path = Path.cwd() / recorded_test
    green_test_bytes = green_test_path.read_bytes()
    green_test_checksum = f"sha256:{hashlib.sha256(green_test_bytes).hexdigest()}"
    if green_test_checksum != recorded_checksum:
        log.error(
            "test-file-checksum-mismatch: test file changed between Red and Green",
            check_id="red-green-replay-checksum-mismatch",
            recorded=recorded_checksum,
            current=green_test_checksum,
            test_path=recorded_test,
            hint=(
                "The test file referenced by HEAD~0's "
                "TDD-Red-Test must be byte-identical at the "
                "Green amend; if you needed to change the test, "
                "author a new Red commit."
            ),
            protocol=RED_GREEN_REPLAY_PROTOCOL,
        )
        return 1
    green_pytest_result = subprocess.run(
        [sys.executable, "-m", "pytest", str(green_test_path), "--tb=no", "-q"],
        capture_output=True,
        text=True,
        check=False,
    )
    if green_pytest_result.returncode != 0:
        log.error(
            "test-still-failing-at-green: not a valid Green moment",
            check_id="red-green-replay-test-still-failing",
            pytest_returncode=green_pytest_result.returncode,
            test_path=recorded_test,
            hint=(
                "Green mode requires the staged test to pass; "
                "the new impl has not yet made the Red test green."
            ),
            protocol=RED_GREEN_REPLAY_PROTOCOL,
        )
        return 1
    green_verified_at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    # An unread SHA used to be recorded as an empty `TDD-Green-Parent-Reflog`
    # — a failure written into the commit AS EVIDENCE. Refuse instead.
    parent = current_head_sha()
    if isinstance(parent, IOFailure):
        return _narrate_git_failure(log=log, failed=unsafe_perform_io(parent.failure()))
    green_parent_reflog = unsafe_perform_io(parent.unwrap())
    write_trailers(
        msg_path=msg_path,
        trailers=(
            ("TDD-Green-Verified-At", green_verified_at),
            ("TDD-Green-Parent-Reflog", green_parent_reflog),
        ),
    )
    return 0
