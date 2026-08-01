"""The `--owner`-or-origin precondition every fleet CLI opens with.

Extracted when the `IOResult` conversion of `resolve_owner` turned a
three-line precondition into a twelve-line one in FOUR modules at once,
pushing two of them past the 250-LLOC hard ceiling — the same
private-sibling split as `_gh_runner` and `_origin_remote`. The ceiling is
PAID here rather than routed around, and the extraction earns its keep: the
precedence rule and its diagnostic now live in ONE place instead of four
copies that kept agreement by being copied (this repo's own `livespec-i04f`
shape).

⛔ BOTH FUNCTIONS RETURN THE CONTAINER, NOT `str | None`, AND THAT IS NOT A
STYLE CHOICE. The first draft of this module returned `str | None` — "the
owner, or None meaning already-reported" — which re-introduced the exact
sentinel the conversion had just removed, one layer further out, and the
armed offender count caught it: 32 became 35, three of them manufactured BY
this extraction. A helper that collapses a discriminated failure back into a
bare `None` for its caller's convenience is this epic's founding defect
wearing a refactor's clothes. These are TAPS: they emit the diagnostic on the
failure track and hand the value through untouched.

TWO SPELLINGS, ONE RULE. The three structlog lanes want structured fields;
`merged_branch_sweep` writes plain stderr by design. Both render from the
same `OriginRemoteUnresolved` and both fail the run — only the SINK differs,
so the decision is not duplicated even though the emission is.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

from livespec_dev_tooling.fleet._origin_remote import OriginRemoteUnresolved, owner_or_origin

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.io import IOFailure, IOResult  # noqa: E402  — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

if TYPE_CHECKING:
    import structlog

__all__: list[str] = ["reported_owner", "stderr_reported_owner"]


_HINT = "pass --owner or run inside a github.com clone"
_UNRESOLVED = "owner unresolvable: no --owner and the origin remote did not answer"


def reported_owner(
    *, argument: str | None, log: structlog.stdlib.BoundLogger, cwd: Path | None = None
) -> IOResult[str, OriginRemoteUnresolved]:
    """`owner_or_origin`, with the failure track narrated to a structlog lane.

    The diagnostic names WHICH of three causes it hit. The old message asserted
    "origin remote is not github.com" for all of them, so an operator whose
    `git` was simply missing was sent to inspect a remote that was fine.
    """
    resolved = owner_or_origin(argument=argument, cwd=cwd)
    if isinstance(resolved, IOFailure):
        failure = unsafe_perform_io(resolved.failure())
        log.error(_UNRESOLVED, reason=failure.reason, detail=failure.detail, hint=_HINT)
    return resolved


def stderr_reported_owner(
    *, argument: str | None, cwd: Path | None = None
) -> IOResult[str, OriginRemoteUnresolved]:
    """The same tap for a lane that writes plain stderr rather than JSON."""
    resolved = owner_or_origin(argument=argument, cwd=cwd)
    if isinstance(resolved, IOFailure):
        failure = unsafe_perform_io(resolved.failure())
        _ = sys.stderr.write(f"{_UNRESOLVED} [{failure.reason}]: {failure.detail}\n{_HINT}\n")
    return resolved
