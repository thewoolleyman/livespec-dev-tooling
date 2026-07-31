"""plugin_structure — the single structural gate for a Driver plugin bundle.

This is the single reconciliation of the two formerly-divergent vendored
copies that lived in the two Driver repos: the CLAUDE packaging profile
(`livespec-driver-claude`) and the CODEX packaging profile
(`livespec-driver-codex`). Both Drivers invoke THIS module (via
`python -m livespec_dev_tooling.driver_checks.plugin_structure`) and have
deleted their own copies; this file is the union, not a merge that weakens
either side — each profile's invariants are preserved VERBATIM and run
mutually-exclusively under a profile auto-detect.

The per-profile invariant sets live in two cohesive helper modules —
`_plugin_structure_claude` (which also owns the byte-identical shared
helpers) and `_plugin_structure_codex` — and are re-imported here so
`plugin_structure.claude_profile_violations` /
`plugin_structure.codex_profile_violations` remain the module's public
surface. This file keeps the profile auto-detect and dispatch.

It lives under `driver_checks/` (NOT `checks/`) deliberately: a
driver-specific gate is not a fleet-universal canonical invariant, so it
must stay out of the `canonical_checks` set that `check-aggregate-
completeness` forces onto every consumer (livespec-2exa).

Profile auto-detect (anchored on `--project-root`, default `Path.cwd()`):

- `<root>/.claude-plugin/plugin.json` present → the CLAUDE profile.
- else `<root>/.agents/plugins/marketplace.json` present → the CODEX
  profile.
- else → SKIP (exit 0). The self-skip branch is load-bearing: it keeps
  the check a clean no-op on any non-Driver tree (e.g. livespec-core or
  the orchestrator plugins, which carry no Driver manifest).

Exit 0 when every assertion holds (or the check self-skips); exit 1 with
one structured `log.error` per violation otherwise. Output discipline:
structlog JSON to stderr (no `print`, no `sys.stderr.write`), mirroring
the sibling checks.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.
from returns.io import IOFailure  # noqa: E402  — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

from livespec_dev_tooling.driver_checks._plugin_structure_claude import (  # noqa: E402
    claude_profile_violations,
)
from livespec_dev_tooling.driver_checks._plugin_structure_codex import (  # noqa: E402
    codex_profile_violations,
)

__all__: list[str] = [
    "claude_profile_violations",
    "codex_profile_violations",
]


_CHECK_ID = "plugin_structure"
_FAIL_EXIT = 1
# A THIRD answer for a third condition. The check used to have only
# "violation" or "clean" to report, so a run that could not READ the
# bundle had to pick one of them — and "clean" is the one it would reach
# now that unreadability has left the violation list. A distinct code
# keeps a run that measured NOTHING from being counted as a run that
# measured everything and found nothing.
_UNREADABLE_EXIT = 2

_PROFILE_CLAUDE = "claude"
_PROFILE_CODEX = "codex"


def detect_profile(*, root: Path) -> str | None:
    """Auto-detect the packaging profile from the on-disk manifest topology.

    `.claude-plugin/plugin.json` → claude; else
    `.agents/plugins/marketplace.json` → codex; else None (self-skip).
    """
    if (root / ".claude-plugin" / "plugin.json").is_file():
        return _PROFILE_CLAUDE
    if (root / ".agents" / "plugins" / "marketplace.json").is_file():
        return _PROFILE_CODEX
    return None


def _configure_logger() -> structlog.stdlib.BoundLogger:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    return structlog.get_logger(_CHECK_ID)


def run_check(*, root: Path, log: structlog.stdlib.BoundLogger) -> int:
    """Detect the profile, run its invariants, emit violations; return exit code.

    Returns 0 on a clean pass or a self-skip (no plugin manifest);
    `_FAIL_EXIT` when the detected profile reports one or more violations;
    `_UNREADABLE_EXIT` when a file the profile had to inspect could not be
    READ, which is not a statement about the bundle and must not be
    reported as one.
    """
    profile = detect_profile(root=root)
    if profile is None:
        log.info(
            "plugin-structure: skipped (no plugin manifest)",
            check_id=_CHECK_ID,
            root=str(root),
        )
        return 0
    outcome = (
        claude_profile_violations(root=root)
        if profile == _PROFILE_CLAUDE
        else codex_profile_violations(root=root)
    )
    if isinstance(outcome, IOFailure):
        unreadable = unsafe_perform_io(outcome.failure())
        log.error(
            "plugin-structure: bundle could not be read (NOT a violation)",
            check_id=_CHECK_ID,
            profile=profile,
            path=unreadable.path,
            detail=unreadable.detail,
        )
        return _UNREADABLE_EXIT
    violations = unsafe_perform_io(outcome.unwrap())
    for violation in violations:
        log.error(
            "plugin-structure violation",
            check_id=_CHECK_ID,
            profile=profile,
            detail=violation,
        )
    return _FAIL_EXIT if violations else 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="check-plugin-structure",
        description=(
            "Profile-auto-detecting structural gate for a Driver plugin bundle "
            "(claude / codex). Skips when no plugin manifest is present."
        ),
    )
    _ = parser.add_argument(
        "--project-root",
        type=str,
        default=None,
        help=(
            "Repo root to check (defaults to the current working directory). "
            "Reserved for hermetic test fixtures; production callers omit it."
        ),
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    project_root: str | None = args.project_root
    log = _configure_logger()
    root = Path(project_root).resolve() if project_root is not None else Path.cwd()
    return run_check(root=root, log=log)


if __name__ == "__main__":
    raise SystemExit(main())
