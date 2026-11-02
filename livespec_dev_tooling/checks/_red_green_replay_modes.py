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

from _red_green_replay_protocol import (  # noqa: E402  — sibling private import
    RED_GREEN_REPLAY_PROTOCOL,
)
from _red_green_replay_suite import _handle_suite_green_mode  # noqa: E402  — sibling private import
from _red_green_replay_trailers import (  # noqa: E402  — sibling private import
    _narrate_git_failure,
    current_head_sha,
    head_trailer_value,
    write_trailers,
)
from returns.io import IOFailure  # noqa: E402  — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

from livespec_dev_tooling.commit_replay_delegate import run_replay  # noqa: E402

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
    "_refuse_half_pair",
]


class _ReplayTestRun:
    """One replay result, retaining remote provenance only for a real verdict."""

    def __init__(
        self,
        *,
        returncode: int,
        output: str,
        output_checksum: str,
        trailers: tuple[tuple[str, str], ...],
    ) -> None:
        self.returncode = returncode
        self.output = output
        self.output_checksum = output_checksum
        self.trailers = trailers


def _run_replay_test(
    *, log: structlog.stdlib.BoundLogger, pytest_argv: list[str], trailer_prefix: str
) -> _ReplayTestRun:
    """Use the gate Job's verdict, or run locally when it did not produce one."""
    verdict = run_replay(repo_root=Path.cwd(), pytest_argv=pytest_argv)
    if (
        not verdict.local
        and verdict.exit_status is not None
        and verdict.job_name is not None
        and verdict.tree_hash is not None
        and verdict.output_checksum is not None
    ):
        log.info(
            "commit-time replay gated by a gate Job",
            check_id="red-green-replay-delegated",
            job_name=verdict.job_name,
            tree_hash=verdict.tree_hash,
        )
        return _ReplayTestRun(
            returncode=verdict.exit_status,
            output=verdict.reason,
            output_checksum=verdict.output_checksum,
            trailers=(
                (f"TDD-{trailer_prefix}-Gate-Job", verdict.job_name),
                (f"TDD-{trailer_prefix}-Staged-Tree", verdict.tree_hash),
            ),
        )
    log.info(
        "commit-time replay gated locally",
        check_id="red-green-replay-gated-locally",
        reason=verdict.reason,
    )
    local = subprocess.run(pytest_argv, capture_output=True, text=True, check=False)
    output = local.stdout + local.stderr
    return _ReplayTestRun(
        returncode=local.returncode,
        output=output,
        output_checksum=f"sha256:{hashlib.sha256(output.encode('utf-8')).hexdigest()}",
        trailers=(),
    )


def _refuse_half_pair(*, log: structlog.stdlib.BoundLogger, dropped: tuple[str, ...]) -> int:
    """Refuse a Green amend whose message no longer carries HEAD's Red block."""
    log.error(
        "green-amend-dropped-red-trailers: the amended message no longer carries "
        "the TDD-Red-* trailers HEAD carries, so admitting it would certify a "
        "HALF-PAIR — Green evidence for a Red the commit no longer records",
        check_id="red-green-replay-green-amend-dropped-red-trailers",
        dropped_trailers=list(dropped),
        hint=(
            "`git commit --amend -m` and `git commit --amend -F` REPLACE the "
            "entire commit message. `git commit --amend --no-edit` is the safe "
            "spelling: it passes the existing message through, Red trailer "
            "block included. To reword, start from `git log -1 --format=%B` so "
            "the block is carried into the new body verbatim — the hook cannot "
            "re-derive it, because the Red pytest run that produced it is gone."
        ),
        protocol=RED_GREEN_REPLAY_PROTOCOL,
    )
    return 1


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
    replay = _run_replay_test(
        log=log,
        pytest_argv=[sys.executable, "-m", "pytest", str(test_file_path), "--tb=no", "-q"],
        trailer_prefix="Red",
    )
    if replay.returncode == 0:
        log.error(
            "test-passed-at-red-moment: not a valid Red moment",
            check_id="red-green-replay-test-passed-at-red",
            tests_paths=tests_paths,
            test_file_checksum=test_file_checksum,
            pytest_returncode=replay.returncode,
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
        pytest_returncode=replay.returncode,
    )
    captured_at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    failure_reason = " ".join(replay.output.split())[:200]
    write_trailers(
        msg_path=msg_path,
        trailers=(
            ("TDD-Red-Test", tests_paths[0]),
            ("TDD-Red-Failure-Reason", failure_reason),
            ("TDD-Red-Test-File-Checksum", test_file_checksum),
            ("TDD-Red-Output-Checksum", replay.output_checksum),
            ("TDD-Red-Captured-At", captured_at),
            *replay.trailers,
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
    replay = _run_replay_test(
        log=log,
        pytest_argv=[sys.executable, "-m", "pytest", str(green_test_path), "--tb=no", "-q"],
        trailer_prefix="Green",
    )
    if replay.returncode != 0:
        log.error(
            "test-still-failing-at-green: not a valid Green moment",
            check_id="red-green-replay-test-still-failing",
            pytest_returncode=replay.returncode,
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
            *replay.trailers,
            *((("TDD-Green-Output-Checksum", replay.output_checksum),) if replay.trailers else ()),
        ),
    )
    return 0
