"""red_leg_scope — compute the Red-commit-gate skip set by staged-path class.

At the Red commit the pre-commit aggregate (`just check`) gates a tree
that stages exactly one test file and no impl. Two classes of leg
cannot tell us anything useful about that tree and so are skipped:

1. The COVERAGE gates (`check-coverage`, `check-per-file-coverage`) —
   already skipped today because coverage is verified at the Green
   amend (work-item livespec-dev-tooling-cvredmd). This module keeps
   that floor byte-for-byte.
2. ORTHOGONAL legs — check legs whose inputs a staged UNIT test cannot
   touch (livespec's `e2e-test-claude-code-mock`, `check-prompts`,
   `check-doctor-static`: gated on `tests/e2e/`, `tests/prompts/`, and
   `SPECIFICATION/` + prose respectively). Per the just-check-
   performance research (archive/research/justcheck-performance/
   baseline-and-research.md §(2), proposed item #4) trimming these at
   Red cuts the livespec Red leg ~89s -> ~40-50s with zero safety loss
   (Green / pre-push / CI run the full aggregate unchanged).

This is CARVE-OUT discipline, not a bypass: the gate stays
always-wired and always-running at Green / pre-push / CI; we only
NARROW which structurally-orthogonal legs run at Red, and only when
the staged path's CLASS proves the leg cannot be affected. A staged
`tests/e2e/` file keeps the e2e leg; a staged `tests/prompts/` file
keeps the prompts leg.

HARD INVARIANT: this module NEVER touches the red_green_replay
commit-msg hook. The staged-test-MUST-fail semantics and the recorded
TDD-Red-* trailer evidence are produced entirely by
`checks/red_green_replay.py` + `checks/_red_green_replay_modes.py`,
left byte-for-byte unmodified by this changeset. Nothing here changes
whether the staged test runs or how its failure is recorded.

FAIL-FAST: an empty target list, an empty staged-path list, or a skip
set that would cover EVERY target raises `ValueError`. An empty Red
selection must surface as a fast, loud error — never an empty pytest
run that silently passes, and never a hang (work-item
livespec-dev-tooling-7us.6 hazard guard).

CLI:
    python -m livespec_dev_tooling.red_leg_scope \
        --targets TARGET ... [--staged PATH ...]

    Computes the skip set from the full target list (--targets) and the
    staged paths (--staged when given, else read from
    `git diff --cached --name-only` in the current worktree), then
    prints it as a single space-separated line on stdout (the
    `just check` Red branch captures it into the `skip=` just-variable).
    Exits 0 on success, 1 on a fail-fast condition (the caller then runs
    the full aggregate, never an empty one).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

__all__: list[str] = []

# The two coverage gates the Red leg has always skipped. Coverage is
# verified at the Green amend, so gating it at Red yields nothing; this
# tuple is the byte-identical floor of every Red-mode skip set.
_COVERAGE_GATES: tuple[str, ...] = ("check-coverage", "check-per-file-coverage")

# Orthogonal legs: target name -> the input-path prefixes a staged file
# would have to fall under to AFFECT that leg. A leg is skippable at Red
# iff it is present in the repo's target list AND no staged path falls
# under any of its input prefixes. These are the livespec legs named in
# work-item 7us.6 / research item #4; dev-tooling itself has none of
# them, so the table is a no-op there beyond the coverage floor (the
# code is consumed cross-repo via the pin-and-bump mechanism). Add a
# row here (with the leg's input tree) to trim a further orthogonal leg
# in any consuming repo.
_ORTHOGONAL_LEGS: dict[str, tuple[str, ...]] = {
    # End-to-end Claude-Code-mock harness: driven by fixtures/scripts
    # under tests/e2e/; a staged unit test elsewhere cannot change its
    # behavior.
    "e2e-test-claude-code-mock": ("tests/e2e/",),
    # Prompt-artifact checks: gated on the prose/prompt trees; a staged
    # unit test elsewhere cannot change a prompt artifact.
    "check-prompts": ("tests/prompts/", "prose/", ".claude-plugin/prose/"),
    # Static doctor checks: gated on the spec tree + doctor prose; a
    # staged unit test elsewhere cannot change the spec.
    "check-doctor-static": ("tests/doctor/", "SPECIFICATION/", "prose/doctor"),
}


def _path_touches_any_prefix(*, staged_paths: list[str], prefixes: tuple[str, ...]) -> bool:
    """Return True iff any staged path falls under one of the input prefixes."""
    return any(path.startswith(prefixes) for path in staged_paths)


def red_mode_skip_targets(*, staged_paths: list[str], available_targets: list[str]) -> list[str]:
    """Return the sorted set of `just check` targets to skip at the Red gate.

    The skip set is the coverage-gate floor plus every orthogonal leg
    whose input tree the staged paths do not touch — intersected with
    the repo's actual target list (no phantom targets). FAIL-FAST: an
    empty target list, an empty staged-path list, or a skip set that
    would cover every target raises ValueError so the caller falls back
    to a full run rather than dispatching an empty / hanging one.
    """
    if not available_targets:
        msg = (
            "red_mode_skip_targets: available_targets is empty; refusing to compute "
            "a skip set against no targets (would yield an empty Red selection)"
        )
        raise ValueError(msg)
    if not staged_paths:
        msg = (
            "red_mode_skip_targets: staged_paths is empty; the Red gate must classify a "
            "staged tree, and an empty staging is malformed for this path"
        )
        raise ValueError(msg)
    target_set = set(available_targets)
    skip: set[str] = {gate for gate in _COVERAGE_GATES if gate in target_set}
    for leg, prefixes in _ORTHOGONAL_LEGS.items():
        if leg in target_set and not _path_touches_any_prefix(
            staged_paths=staged_paths, prefixes=prefixes
        ):
            skip.add(leg)
    if skip >= target_set:
        msg = (
            "red_mode_skip_targets: the computed skip set covers every target — "
            "the Red selection would be empty selection (no leg would run). "
            "Refusing; the caller must run the full aggregate instead."
        )
        raise ValueError(msg)
    return sorted(skip)


def _staged_paths(*, cwd: Path) -> list[str]:
    """Return staged path names via `git diff --cached --name-only`."""
    result = subprocess.run(  # noqa: S603
        ["git", "diff", "--cached", "--name-only"],  # noqa: S607
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    return [line for line in result.stdout.splitlines() if line]


def _configure_logger() -> structlog.stdlib.BoundLogger:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    return structlog.get_logger("red_leg_scope")


def _write(*, text: str) -> None:
    """Write text to stdout and flush; discards the byte-count return value."""
    _ = sys.stdout.write(text)
    _ = sys.stdout.flush()


def main() -> int:
    log = _configure_logger()
    parser = argparse.ArgumentParser(
        description="Compute the Red-commit-gate skip set by staged-path class."
    )
    _ = parser.add_argument(
        "--targets", nargs="*", default=[], help="The repo's full check target list."
    )
    _ = parser.add_argument(
        "--staged",
        nargs="*",
        default=None,
        help="Staged paths to classify; falls back to `git diff --cached` when omitted.",
    )
    parsed = parser.parse_args()
    cwd = Path.cwd()
    staged: list[str] = list(parsed.staged) if parsed.staged is not None else _staged_paths(cwd=cwd)
    targets: list[str] = list(parsed.targets)
    try:
        skip = red_mode_skip_targets(staged_paths=staged, available_targets=targets)
    except ValueError as exc:
        log.exception(
            "red-leg-scope fail-fast; caller must run the full aggregate",
            check_id="red-leg-scope-fail-fast",
            reason=str(exc),
            staged_count=len(staged),
            target_count=len(targets),
        )
        return 1
    log.info(
        "red-leg-scope computed",
        skip=skip,
        staged_count=len(staged),
        target_count=len(targets),
    )
    _write(text=" ".join(skip) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
