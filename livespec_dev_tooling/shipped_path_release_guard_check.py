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

Output discipline: `print` (T20) and `sys.stderr.write`
(`check-no-write-direct`) are banned here. Diagnostics flow through structlog
(JSON to stderr); the vendored copy under `livespec_dev_tooling/_vendor` is added
to `sys.path` at module import time.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

from livespec_dev_tooling._shipped_path_release_guard_inputs import (  # noqa: E402
    Resolved,
    resolve_releasing_types,
    resolve_shipped_prefixes,
)
from livespec_dev_tooling._shipped_path_release_guard_range import (  # noqa: E402
    RANGE_BASE,
    commits_in_range,
    range_base_resolvable,
)
from livespec_dev_tooling.shipped_path_release_guard_core import (  # noqa: E402
    is_violation,
    touches_shipped_path,
)

__all__: list[str] = []


_CHECK_ID = "shipped-path-release-guard"

# The override marker: a commit-message trailer carrying a NON-EMPTY reason. The
# `\S` is load-bearing — a bare `Shipped-Path-Release-Waived:` records nothing,
# and a marker that records nothing is a bypass flag with a longer name. Matched
# per-line anywhere in the message so it survives an amend or a reflowing rebase.
_OVERRIDE_TRAILER = "Shipped-Path-Release-Waived"
_OVERRIDE_LINE = re.compile(rf"^{_OVERRIDE_TRAILER}:[ \t]*\S.*$", re.MULTILINE)

# Hoisted to a module constant rather than assembled at the log site because BOTH
# modes emit it and a remedy that drifted between them would teach two different
# recoveries for one rule. Built by concatenation, not an f-string: ruff's G004
# bans an f-string as a logging message, and the trailer's spelling must come
# from the constant so the remedy can never name a marker the matcher rejects.
_REMEDY = (
    "this commit edits SHIPPED bytes under a commit type this repository cuts no "
    "release on, so the edited bytes would reach ZERO running seats while "
    "`just ensure-plugins` reports 'already current' (it compares pins, not served "
    "bytes). Retype the commit to one of the releasing types below, or — if the edit "
    "genuinely warrants no release — record that decision with a "
    f"`{_OVERRIDE_TRAILER}: <why>` trailer on its own line in the commit message. "
    "The trailer's reason must be non-empty."
)


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


def _split_message(*, message: str) -> tuple[str, str]:
    """Split a raw commit message into `(subject, body)`, dropping git's `#` comments.

    Leading blank lines are skipped so a message file that opens with a comment
    block still yields the real subject. A message with no content at all yields
    two empty strings, which the core reads as an untypeable subject that cuts no
    release — the strictest honest reading.
    """
    lines = [line for line in message.splitlines() if not line.startswith("#")]
    while lines and not lines[0].strip():
        _ = lines.pop(0)
    if not lines:
        return "", ""
    return lines[0].strip(), "\n".join(lines[1:])


def _diagnostic_commit_type(*, subject: str) -> str:
    """Echo the subject's leading `type(scope)!` token FOR THE DIAGNOSTIC ONLY.

    ⛔ NOT a second copy of the rule. This string never reaches a decision: the
    release verdict is `commit_releases`'s alone, computed from the subject
    itself inside the core. This is a plain split on the first colon so the
    refusal can name what the author actually typed, and it deliberately does
    NOT restate the core's Conventional-Commit grammar.
    """
    head, separator, _ = subject.partition(":")
    return head if separator else "<no conventional-commit type>"


def _is_violation_reported(
    *,
    log: structlog.stdlib.BoundLogger,
    message: str,
    changed: tuple[str, ...],
    releasing: Resolved,
    shipped: Resolved,
    commit: str | None,
) -> bool:
    """Judge ONE message-and-paths pair, reporting the refusal, and say whether it offended.

    The single decision site for BOTH modes. Range mode calls it once per commit
    with that commit's sha; commit-msg mode calls it once with `commit=None`,
    because the pending commit has no sha yet.

    ⛔ It delegates, it does not decide — and neither does its caller. A range
    loop is the cheapest place in this codebase to write a second copy of the
    rule (a `startswith` over `changed` would look local and correct), which is
    exactly why the loop calls THIS and this calls the core.
    """
    subject, body = _split_message(message=message)
    if not is_violation(
        subject=subject,
        body=body,
        changed_paths=changed,
        shipped_prefixes=shipped.values,
        releasing_types=releasing.values,
        override=_OVERRIDE_LINE.search(message) is not None,
    ):
        return False
    # Delegated per path rather than re-matched here: the prefix-boundary rule is
    # the core's, and a hand-rolled `startswith` would be the second copy this
    # split exists to prevent.
    offending = [
        p
        for p in changed
        if touches_shipped_path(changed_paths=(p,), shipped_prefixes=shipped.values)
    ]
    log.error(
        _REMEDY,
        check_id=_CHECK_ID,
        failure_mode="shipped_path_edited_without_a_release",
        commit=commit,
        offending_paths=offending,
        commit_type=_diagnostic_commit_type(subject=subject),
        releasing_types=sorted(releasing.values),
        releasing_types_source=releasing.source,
        shipped_prefixes=sorted(shipped.values),
        shipped_prefixes_source=shipped.source,
        override_trailer=f"{_OVERRIDE_TRAILER}: <why this edit warrants no release>",
        documentation="livespec-dev-tooling's docs/shipped-path-release-guard.md",
        status="fail",
    )
    return True


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
        log.error(
            "the pending commit message file is not readable, so neither the commit type "
            "nor an override trailer can be read; pass the message file as the one "
            "positional argument (git's commit-msg hook supplies it as $1)",
            check_id=_CHECK_ID,
            failure_mode="message_file_unreadable",
            message_file=str(path),
            status="fail",
        )
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
    if not range_base_resolvable(repo_root=repo_root):
        log.error(
            "the range base is not resolvable, so the commit range cannot be enumerated "
            "and this gate MUST NOT silently pass; an empty commit list from a shallow "
            "clone reads exactly like a clean branch",
            check_id=_CHECK_ID,
            failure_mode="range_base_unresolvable",
            range_base=RANGE_BASE,
            hint=(
                "Fetch the base ref first (git fetch origin master). In CI, check out "
                "with full history (actions/checkout fetch-depth: 0)."
            ),
            status="fail",
        )
        return 1
    commits = commits_in_range(repo_root=repo_root)
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
    log.info(
        "shipped-path release guard validated the commit range",
        check_id=_CHECK_ID,
        mode="range",
        range_base=RANGE_BASE,
        commits_validated=len(commits),
        status="pass",
    )
    return 0


def main() -> int:
    log = _configure_logger()
    args = _build_parser().parse_args()
    message_file: str | None = args.message_file
    repo_root = Path.cwd()
    # Resolved ONCE, before the mode split, and logged unconditionally: both modes
    # read the same repository, and range mode would otherwise re-resolve the same
    # two answers per commit. The log line is emitted even on the clean path
    # because an EMPTY shipped derivation is an answer that must be visible —
    # that is what distinguishes "armed here and correctly inert" from "never ran".
    releasing = resolve_releasing_types(repo_root=repo_root)
    shipped = resolve_shipped_prefixes(repo_root=repo_root)
    log.info(
        "shipped-path release guard resolved this repository's inputs",
        check_id=_CHECK_ID,
        releasing_types=sorted(releasing.values),
        releasing_types_source=releasing.source,
        shipped_prefixes=sorted(shipped.values),
        shipped_prefixes_source=shipped.source,
    )
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
