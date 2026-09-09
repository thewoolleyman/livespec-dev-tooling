"""shipped_path_release_guard_check — the runnable half of the shipped-path release guard.

Slice B of the R6 guard (work-item `livespec-dev-tooling-l42g`). A sibling in
spirit to `livespec_dev_tooling.checks.commit_pairs_source_and_test`: a
commit-scoped gate that reads the pending commit and the staged diff and exits
non-zero on a violation.

⛔ THIS MODULE DECIDES NOTHING. The rule lives in
`livespec_dev_tooling.shipped_path_release_guard_core.is_violation` and is
delegated to, never restated. That module's docstring assigns this one its whole
scope — RESOLVING the rule's inputs "from a real repository (its release-please
config, its plugin manifests, its staged diff)" — precisely "so that ONE RULE HAS
EXACTLY ONE IMPLEMENTATION". A second copy of the releasing-type grammar or of
the shipped-path prefix match HERE would silently defeat the split that is the
whole point of the two slices. The only thing this file adds to the decision is
the OVERRIDE MECHANISM, which the core's `is_violation` docstring likewise
assigns here: the core takes the override as a bare `bool`, and what an operator
must write to obtain one is policy rather than decision.

TWO MODES, selected by argv, both delegating to the same core call:

- COMMIT-MSG mode (ONE positional argument — the message file git's `commit-msg`
  hook passes as `$1`) judges the PENDING commit against the staged diff. It is
  commit-msg-scoped rather than pre-commit-scoped for a structural reason, not a
  preference: both the commit TYPE and the override marker live in the COMMIT
  MESSAGE, and at pre-commit time no message exists yet.
- RANGE mode (NO argument) judges every non-merge commit in `origin/master..HEAD`,
  each against its OWN message and its OWN changed paths. This is the invocation
  `just check`, pre-push and CI make, and it is the load-bearing branch-level
  gate behind the per-commit hook — which a rebase, a squash or a history rewrite
  can bypass. It mirrors `checks/red_green_replay.py`'s `_validate_range`.

⛔ WHY RANGE MODE REPLACED A `<git-dir>/COMMIT_EDITMSG` FALLBACK on the no-argv
path (work-item `livespec-dev-tooling-sxdz`). The aggregate runs with NO pending
commit: argv is empty AND `git diff --cached` is empty. The old fallback
therefore read the LAST commit's already-judged message against an empty diff,
so as an aggregate member it COULD NOT FAIL — it passed vacuously at best and
reported a verdict on a stale message at worst. An enforcement member that
cannot fail is precisely the defect class this suite exists to remove, so the
no-argv path had to become one that can.

NEITHER PER-REPO INPUT IS A FLEET CONSTANT — not the releasing types and not the
shipped prefixes. Resolving them (and recording WHERE each value was read from,
which travels with the value in `Resolved.source`) now lives in the cohesive
sibling `_shipped_path_release_guard_inputs`, split out when this module crossed
the 250-LLOC ceiling; that module's docstring carries the full rationale,
including why hardcoding either answer is the refuted premise slice A was amended
to escape. This module still LOGS both resolved values with their sources on
every run, so an empty shipped derivation is visible as an answer rather than
passing silently.

This gate is ARMED in livespec-dev-tooling: `lefthook.yml`'s `commit-msg` hook
runs it in commit-msg mode via `just check-shipped-path-release-guard {1}`, and
the `just check` aggregate runs it in range mode. Note that livespec-dev-tooling
carries no `.claude-plugin/` manifest, so its OWN derived shipped set is empty
and the guard is correctly INERT here — it is armed for the consumers whose sets
are not. Operator-facing documentation of the override trailer lives in
livespec-dev-tooling's `docs/shipped-path-release-guard.md`.

EVERY SENTENCE THIS GUARD CAN SAY now lives in the cohesive sibling
`_shipped_path_release_guard_narration`, split out when putting the guard's four
IO seams on the `IOResult` railway (`livespec-dev-tooling-qndn.2`) pushed this
module back over the 250-LLOC ceiling. The override mechanism and the verdict
narration went with it, since they are the vocabulary rather than the control
flow. What remains here is the CLI: the logger, the parser, the two modes, and
the argv split between them.

BOTH RESOLVERS AND BOTH RANGE READERS ARE ON THE RAILWAY, and this module
CONSUMES all four failure tracks rather than unwrapping them. That asymmetry is
the same one range mode already applied to an unresolvable base, for the same
reason: an empty commit list, an empty shipped-prefix set and release-please's
default releasing types all read exactly like a pass, so a read that did not
happen must reach the exit code as a refusal instead of arriving at a verdict
wearing one of them.

Output discipline: `print` (T20) and `sys.stderr.write`
(`check-no-write-direct`) are banned here. Diagnostics flow through structlog
(JSON to stderr); the vendored copy under `livespec_dev_tooling/_vendor` is added
to `sys.path` at module import time.
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
from returns.io import IOFailure  # noqa: E402  — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

from livespec_dev_tooling._shipped_path_release_guard_inputs import (  # noqa: E402
    Resolved,
    resolve_releasing_types,
    resolve_shipped_prefixes,
)
from livespec_dev_tooling._shipped_path_release_guard_narration import (  # noqa: E402
    _OVERRIDE_TRAILER,
    _is_violation_reported,
    _narrate_range_validated,
    _narrate_resolved_inputs,
    _narrate_unreadable_message_file,
    _narrate_unresolvable_range_base,
    _read_input,
    _refuse_unanswered_range,
)
from livespec_dev_tooling._shipped_path_release_guard_range import (  # noqa: E402
    RANGE_BASE,
    commits_in_range,
    range_base_resolvable,
)

__all__: list[str] = []


def _configure_logger() -> structlog.stdlib.BoundLogger:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    return structlog.get_logger("shipped_path_release_guard_check")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="shipped-path-release-guard",
        description=(
            "Refuse a commit that edits SHIPPED bytes under a commit type this "
            "repository cuts no release on, unless the commit message carries a "
            f"`{_OVERRIDE_TRAILER}: <why>` trailer."
        ),
    )
    _ = parser.add_argument(
        "message_file",
        nargs="?",
        default=None,
        help=(
            "Path to the pending commit's message file — what git's `commit-msg` "
            "hook passes as $1. Relative paths resolve against the current "
            "working directory. OMIT IT to validate the commit RANGE "
            f"{RANGE_BASE}..HEAD instead, which is what the `just check` "
            "aggregate, pre-push and CI do."
        ),
    )
    return parser


def _staged_paths(*, repo_root: Path) -> tuple[str, ...]:
    """The paths staged for the pending commit."""
    # S603/S607: argv is a fixed list (literal git binary + literal flags);
    # bare `git` resolves via PATH; no untrusted shell input.
    result = subprocess.run(  # noqa: S603
        ["git", "diff", "--cached", "--name-only"],  # noqa: S607
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=True,
    )
    return tuple(line for line in result.stdout.splitlines() if line.strip())


def _validate_pending_commit(
    *,
    log: structlog.stdlib.BoundLogger,
    repo_root: Path,
    message_file: str,
    releasing: Resolved,
    shipped: Resolved,
) -> int:
    """COMMIT-MSG mode: judge the pending commit against the staged diff."""
    path = repo_root / message_file
    if not path.is_file():
        _narrate_unreadable_message_file(log=log, path=path)
        return 1
    offended = _is_violation_reported(
        log=log,
        message=path.read_text(encoding="utf-8"),
        changed=_staged_paths(repo_root=repo_root),
        releasing=releasing,
        shipped=shipped,
        commit=None,
    )
    return 1 if offended else 0


def _validate_range(
    *,
    log: structlog.stdlib.BoundLogger,
    repo_root: Path,
    releasing: Resolved,
    shipped: Resolved,
) -> int:
    """RANGE mode: judge every non-merge commit in `origin/master..HEAD`.

    An unresolvable base REFUSES rather than passes. That asymmetry is the whole
    point: a shallow clone or a missing fetch yields an empty commit list, which
    is indistinguishable from a clean branch, so treating it as clean would make
    the gate fail OPEN exactly where it is least likely to be noticed.
    """
    probed = range_base_resolvable(repo_root=repo_root)
    if isinstance(probed, IOFailure):
        return _refuse_unanswered_range(log=log, failed=unsafe_perform_io(probed.failure()))
    if not unsafe_perform_io(probed.unwrap()):
        _narrate_unresolvable_range_base(log=log)
        return 1
    enumerated = commits_in_range(repo_root=repo_root)
    if isinstance(enumerated, IOFailure):
        return _refuse_unanswered_range(log=log, failed=unsafe_perform_io(enumerated.failure()))
    commits = unsafe_perform_io(enumerated.unwrap())
    # Materialized rather than short-circuited with `any`: every offending commit
    # must be REPORTED, so an author fixing a branch sees the whole set instead of
    # rediscovering one more on each re-run.
    offenders = [
        commit.sha
        for commit in commits
        if _is_violation_reported(
            log=log,
            message=commit.message,
            changed=commit.changed_paths,
            releasing=releasing,
            shipped=shipped,
            commit=commit.sha,
        )
    ]
    if offenders:
        return 1
    _narrate_range_validated(log=log, commits=len(commits))
    return 0


def main() -> int:
    log = _configure_logger()
    args = _build_parser().parse_args()
    message_file: str | None = args.message_file
    repo_root = Path.cwd()
    # Resolved ONCE, before the mode split, and logged unconditionally: both modes
    # read the same repository, and range mode would otherwise re-resolve the same
    # two answers per commit.
    #
    # ⛔ AND CONSUMED HERE, before either mode runs. An input that did not read
    # cannot be judged against, and it is exactly the case that would otherwise
    # pass: `_read_input` narrates the refusal, and its empty list is the failure
    # track reaching the exit code.
    releasing_read = _read_input(log=log, resolved=resolve_releasing_types(repo_root=repo_root))
    shipped_read = _read_input(log=log, resolved=resolve_shipped_prefixes(repo_root=repo_root))
    if not releasing_read or not shipped_read:
        return 1
    releasing = releasing_read[0]
    shipped = shipped_read[0]
    _narrate_resolved_inputs(log=log, releasing=releasing, shipped=shipped)
    if message_file is None:
        return _validate_range(log=log, repo_root=repo_root, releasing=releasing, shipped=shipped)
    return _validate_pending_commit(
        log=log,
        repo_root=repo_root,
        message_file=message_file,
        releasing=releasing,
        shipped=shipped,
    )


if __name__ == "__main__":
    raise SystemExit(main())
