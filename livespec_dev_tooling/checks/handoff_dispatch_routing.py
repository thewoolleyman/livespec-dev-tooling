"""handoff_dispatch_routing — active plan handoffs must route impl through the factory.

Scans the ACTIVE plan-thread handoffs (`plan/*/handoff.md`, EXCLUDING everything
under `plan/archive/`) and FAILS if any handoff carries the colon-qualified
in-session-implement invocation token `:implement`. That token is the
operation-invocation form — a plugin-namespaced implement command such as
`<plugin>:implement` — NOT the prose words "implement" / "implementation", which
are legitimate and MUST NOT be flagged.

Per-file opt-out: an HTML comment anywhere in the file of the form
`<!-- handoff-lint: allow-in-session-implement — <reason> -->` with a NON-EMPTY
reason suppresses the failure for that file. An empty or missing reason does not.

A repo with no `plan/` directory (or no active handoffs) passes trivially.

Rationale: on 2026-07-15 a session implemented a ready child in-session because
a handoff described the in-session implement operation as "the normal factory
path". The factory route is DISPATCH — the `drive` operation `impl:<id>` / the
Dispatcher drain — and in-session implementation is reserved for
factory-ineligible items, factory outages, or explicit maintainer direction.
The wording fix lands separately; this lint keeps the defect from regenerating,
because handoff authoring is the recurring surface.

Output discipline: per spec, `print` (T20) and `sys.stderr.write`
(`check-no-write-direct`) are banned in dev-tooling/**. Diagnostics flow through
structlog (JSON to stderr); the vendored copy under
`livespec_dev_tooling/_vendor/structlog` is added to `sys.path` at import time.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

__all__: list[str] = []


_PLAN_DIR_NAME = "plan"
_ARCHIVE_DIR_NAME = "archive"
_HANDOFF_GLOB = "*/handoff.md"

# The colon-qualified in-session-implement invocation token. The trailing word
# boundary keeps prose like "implementation" (and a colon-qualified longer word)
# from tripping the lint while still matching every real `<plugin>:implement`
# invocation (followed by a slash, backtick, space, newline, or line end).
_IMPLEMENT_TOKEN_RE = re.compile(r":implement\b")

# Per-file opt-out marker: an HTML comment carrying the marker phrase followed
# by an em-dash separator and a NON-EMPTY reason suppresses the failure for that
# file. A plain hyphen is deliberately NOT accepted as the separator — it is
# ambiguous with the `-->` comment terminator.
_OPT_OUT_RE = re.compile(
    r"<!--\s*handoff-lint:\s*allow-in-session-implement\s*—\s*(?P<reason>.*?)\s*-->",
    re.DOTALL,
)

_REMEDIATION = (
    "the handoff's next action must name the factory dispatch route (the `drive` "
    "operation `impl:<id>` / the Dispatcher drain); in-session implementation is "
    "reserved for factory-ineligible items, factory outages, or explicit "
    "maintainer direction. To suppress intentionally, add "
    "`<!-- handoff-lint: allow-in-session-implement — <reason> -->` with a reason."
)


def _active_handoffs(*, plan_dir: Path) -> list[Path]:
    """Return active `plan/<topic>/handoff.md` paths, excluding `plan/archive/`."""
    return sorted(
        path for path in plan_dir.glob(_HANDOFF_GLOB) if path.parent.name != _ARCHIVE_DIR_NAME
    )


def _has_valid_opt_out(*, text: str) -> bool:
    """Return True iff the file carries an opt-out marker with a non-empty reason."""
    return any(match.group("reason").strip() for match in _OPT_OUT_RE.finditer(text))


def _is_offender(*, text: str) -> bool:
    """Return True iff the handoff carries the token and lacks a valid opt-out."""
    if not _IMPLEMENT_TOKEN_RE.search(text):
        return False
    return not _has_valid_opt_out(text=text)


def main() -> int:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    log = structlog.get_logger("handoff_dispatch_routing")
    cwd = Path.cwd()
    plan_dir = cwd / _PLAN_DIR_NAME
    if not plan_dir.is_dir():
        return 0
    offenders = [
        path
        for path in _active_handoffs(plan_dir=plan_dir)
        if _is_offender(text=path.read_text(encoding="utf-8"))
    ]
    for path in offenders:
        log.error(
            "active plan handoff routes in-session implementation instead of factory dispatch",
            file=str(path.relative_to(cwd)),
            invocation=":implement",
            remediation=_REMEDIATION,
        )
    return 1 if offenders else 0


if __name__ == "__main__":
    raise SystemExit(main())
