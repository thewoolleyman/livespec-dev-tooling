"""_shipped_path_release_guard_narration — every sentence this guard can say, in one place.

Private sibling of `shipped_path_release_guard_check`, extracted when putting the
guard's four IO seams on the `IOResult` railway (`livespec-dev-tooling-qndn.2`,
epic `8o8e`) pushed the parent back over its 250-LLOC hard ceiling. It follows
the precedent `checks/_primary_checkout_narration` set for the identical event,
and it is the third split of this guard after `_shipped_path_release_guard_inputs`
(the per-repo inputs) and `_shipped_path_release_guard_range` (the git range).

⛔ THIS MODULE STILL DECIDES NOTHING — the parent's rule is unchanged and so is
its reason. The verdict is `shipped_path_release_guard_core.is_violation`'s
alone, delegated to from `_is_violation_reported` below and never restated. What
lives here is the guard's whole VOCABULARY: the override mechanism (which is
policy, not decision), the remedy each refusal routes to, and every structlog
line the two modes emit. Keeping the sentences together is the point — with the
inputs, the range and the modes all feeding it, the parent was no longer the one
place a reader could find them.

THE REFUSALS DIVIDE IN TWO, and the division is load-bearing rather than
cosmetic. `_is_violation_reported` and `_narrate_unresolvable_range_base` are
statements about the REPOSITORY: the guard looked, and this is what it found.
`_read_input` and `_refuse_unanswered_range` are statements about this RUN — a
read that did not happen — and they exist because every natural empty answer this
guard has (release-please's defaults, a repository shipping no plugin bytes, an
empty commit list) reads exactly like a PASS. Folding an unmade read onto one of
them would hand the operator a grammatical, specific, actionable verdict about a
repository nothing managed to look at.

Names stay `_`-prefixed and are re-exported through `__all__`: they were private
in the parent, and making them public to satisfy the extraction would enrol
unconverted functions in the railway universe as brand-new offenders — the split
reporting work it did not do.

Output discipline, inherited from the parent: `print` (T20) and
`sys.stderr.write` (`check-no-write-direct`) are banned here. Diagnostics flow
through structlog (JSON to stderr); the vendored copy under
`livespec_dev_tooling/_vendor` is added to `sys.path` at module import time.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.
from returns.io import IOFailure, IOResult  # noqa: E402  — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

from livespec_dev_tooling._shipped_path_release_guard_inputs import (  # noqa: E402
    InputUnreadable,
    Resolved,
)
from livespec_dev_tooling._shipped_path_release_guard_range import (  # noqa: E402
    RANGE_BASE,
    RangeCommandFailed,
)
from livespec_dev_tooling.shipped_path_release_guard_core import (  # noqa: E402
    is_violation,
    touches_shipped_path,
)

__all__: list[str] = [
    "_CHECK_ID",
    "_OVERRIDE_TRAILER",
    "_is_violation_reported",
    "_narrate_range_validated",
    "_narrate_resolved_inputs",
    "_narrate_unreadable_message_file",
    "_narrate_unresolvable_range_base",
    "_read_input",
    "_refuse_unanswered_range",
]


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


def _read_input(
    *, log: structlog.stdlib.BoundLogger, resolved: IOResult[Resolved, InputUnreadable]
) -> list[Resolved]:
    """One per-repo input as a 0-or-1 list, NARRATING an unread one before it empties.

    An EMPTY list IS the failure track, which is why this returns a list rather
    than an `Optional`: a sentinel standing in for an unmade read is precisely
    what the conversion removed, and re-introducing one here would move it rather
    than remove it. Both resolvers have a near-empty ANSWER — release-please's
    defaults, and "ships no plugin bytes" — so an input that never read must not
    arrive at a verdict wearing one of them.
    """
    if not isinstance(resolved, IOFailure):
        return [unsafe_perform_io(resolved.unwrap())]
    unreadable = unsafe_perform_io(resolved.failure())
    log.error(
        "a per-repo input this guard judges AGAINST could not be read, so nothing can be "
        "judged and this gate MUST NOT silently pass; both of its natural empty answers "
        "(release-please's defaults, and a repository shipping no plugin bytes) read "
        "exactly like a clean result",
        check_id=_CHECK_ID,
        failure_mode="input_unreadable",
        input_source=unreadable.source,
        detail=unreadable.detail,
        status="fail",
    )
    return []


def _refuse_unanswered_range(
    *, log: structlog.stdlib.BoundLogger, failed: RangeCommandFailed
) -> int:
    """Refuse a range a git command left UNKNOWN — never the same answer as clean.

    The sibling of `_narrate_unresolvable_range_base`, refused for the same
    reason with a different remedy: THAT one has a base git answered about, so
    "fetch the base ref" is actionable advice; this one has a git that did not
    answer at all, for which the same advice would be noise, so the operator is
    handed the exact invocation instead.
    """
    log.error(
        "a git command the commit-range enumeration depends on did not answer, so the "
        "range is UNKNOWN rather than clean and this gate MUST NOT silently pass; a "
        "range that was never enumerated reads exactly like a branch with no violations",
        check_id=_CHECK_ID,
        failure_mode="range_command_failed",
        argv=failed.argv,
        detail=failed.detail,
        status="fail",
    )
    return 1


def _narrate_unresolvable_range_base(*, log: structlog.stdlib.BoundLogger) -> None:
    """The base ref does not resolve — an UNDECIDABLE range, refused rather than passed."""
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


def _narrate_unreadable_message_file(*, log: structlog.stdlib.BoundLogger, path: Path) -> None:
    """COMMIT-MSG mode was handed no readable message, so it can read neither input."""
    log.error(
        "the pending commit message file is not readable, so neither the commit type "
        "nor an override trailer can be read; pass the message file as the one "
        "positional argument (git's commit-msg hook supplies it as $1)",
        check_id=_CHECK_ID,
        failure_mode="message_file_unreadable",
        message_file=str(path),
        status="fail",
    )


def _narrate_resolved_inputs(
    *, log: structlog.stdlib.BoundLogger, releasing: Resolved, shipped: Resolved
) -> None:
    """Both per-repo inputs, with their sources, on EVERY run.

    Emitted even on the clean path because an EMPTY shipped derivation is an
    answer that must be visible — that is what distinguishes "armed here and
    correctly inert" from "never ran".
    """
    log.info(
        "shipped-path release guard resolved this repository's inputs",
        check_id=_CHECK_ID,
        releasing_types=sorted(releasing.values),
        releasing_types_source=releasing.source,
        shipped_prefixes=sorted(shipped.values),
        shipped_prefixes_source=shipped.source,
    )


def _narrate_range_validated(*, log: structlog.stdlib.BoundLogger, commits: int) -> None:
    """The range was ENUMERATED and every commit in it was judged clean."""
    log.info(
        "shipped-path release guard validated the commit range",
        check_id=_CHECK_ID,
        mode="range",
        range_base=RANGE_BASE,
        commits_validated=commits,
        status="pass",
    )
