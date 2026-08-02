"""agents_ai_references_resolve — every AGENTS.md `.ai/<topic>.md` reference resolves.

Per `livespec/SPECIFICATION/contracts.md` section "Fleet agent-instruction
core": every `.ai/<topic>.md` path an `AGENTS.md` references MUST
resolve to an existing file, at every directory level that declares
one. This repo-local check enforces that referential integrity over the
working tree — it discovers every `AGENTS.md` (at any directory level),
extracts each concrete `.ai/<topic>.md` reference, and resolves it
relative to that `AGENTS.md`'s own directory. A repo whose `AGENTS.md`
references zero `.ai/` files passes; a dangling reference fails.

Unlike `claude_md_coverage`, this check is repo-wide and
config-independent: `AGENTS.md` may live at any directory level per the
contract, so there is no layout-dependent scope to read from
`load_config`. Vendored, generated, and archival trees (`_vendor`,
`__pycache__`, `archive`, …) are excluded via the shared
`is_excluded_agents_path` predicate.

Output discipline: per spec, `print` (T20) and `sys.stderr.write`
(`check-no-write-direct`) are banned in dev-tooling/**. Diagnostics flow
through structlog (JSON to stderr); the vendored copy under
`livespec_dev_tooling/_vendor/structlog` is added to `sys.path` at module
import time.
"""

from __future__ import annotations

import sys
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

from livespec_dev_tooling.checks._ai_references import (  # noqa: E402
    AGENTS_FILENAME,
    is_excluded_agents_path,
    iter_ai_references,
)

__all__: list[str] = []


def _collect_offenders(*, cwd: Path) -> list[tuple[str, int, str, str]]:
    """Every dangling reference as (agents_md, line, reference, resolved_path).

    Sorted deterministically by `AGENTS.md` path then line: discovery
    walks `sorted(rglob(...))` and references within a file are emitted
    in line order, so the explicit final sort only formalizes that.
    """
    offenders: list[tuple[str, int, str, str]] = []
    for path in sorted(cwd.rglob(AGENTS_FILENAME)):
        if is_excluded_agents_path(segments=path.relative_to(cwd).parts):
            continue
        text = path.read_text(encoding="utf-8")
        for line, ref in iter_ai_references(text=text):
            target = path.parent / ref
            if not target.is_file():
                offenders.append(
                    (
                        str(path.relative_to(cwd)),
                        line,
                        ref,
                        str(target.relative_to(cwd)),
                    )
                )
    return sorted(offenders)


def main() -> int:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    log = structlog.get_logger("agents_ai_references_resolve")
    cwd = Path.cwd()
    offenders = _collect_offenders(cwd=cwd)
    if offenders:
        for agents_md, line, reference, resolved_path in offenders:
            log.error(
                "AGENTS.md references a .ai/ file that does not resolve",
                agents_md=agents_md,
                line=line,
                reference=reference,
                resolved_path=resolved_path,
            )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
