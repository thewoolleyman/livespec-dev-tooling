"""agents_ai_references_resolve — every AGENTS.md `.ai/<topic>.md` reference resolves.

Per `livespec/SPECIFICATION/contracts.md` section "Fleet agent-instruction
core": every `.ai/<topic>.md` path an `AGENTS.md` references MUST
resolve to an existing file, at every directory level that declares
one. This repo-local check enforces that referential integrity over the
working tree — it discovers every `AGENTS.md` (at any directory level),
extracts each concrete `.ai/<topic>.md` reference, and resolves it
relative to that `AGENTS.md`'s own directory. A dangling reference
fails.

A tree whose `AGENTS.md` files reference ZERO `.ai/` paths is reported
as a distinct `vacuous` verdict at WARNING level, carrying the
referenced-path count, rather than as a bare pass (work-item
livespec-dev-tooling-xaxj5w). It still exits 0: a repo may legitimately
carry no `.ai/` tree, so this is not a violation. But the run inspected
nothing, so its exit 0 proves nothing about reference integrity, and the
verdict says so instead of letting silence read as a proof — the state
five of twelve fleet repos were measured in on 2026-08-23, and the one
livespec-driver-pi held from bootstrap until 2026-08-19 with the gate
armed, wired into CI, and structurally incapable of firing. The verdict
is deliberately about the REFERENCE, not the FILE: a repo can ship a
`.ai/` file that no `AGENTS.md` routes to, which leaves this check
inspecting nothing while a presence-shaped rule would call it covered.

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
from typing import NamedTuple

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


class _Scan(NamedTuple):
    """One working-tree scan: how much was inspected, and what dangled.

    `referenced_paths` is the check's own INPUT SIZE — every concrete
    `.ai/<topic>.md` reference found across the non-excluded `AGENTS.md`
    files. At zero, an empty `offenders` list means the scan found
    nothing to inspect rather than that everything resolved, which is
    the distinction the `vacuous` verdict exists to carry.

    A `NamedTuple` rather than a `dataclass` because the check's test
    loads this module by path (`spec_from_file_location`) without
    registering it in `sys.modules`; under CPython 3.10 a dataclass in
    such a module fails at class-creation time, since `_is_type` resolves
    the `from __future__ import annotations` string annotations through
    `sys.modules[cls.__module__]` and finds `None`.
    """

    referenced_paths: int
    offenders: list[tuple[str, int, str, str]]


def _scan_tree(*, cwd: Path) -> _Scan:
    """Inspect every non-excluded `AGENTS.md` under `cwd`.

    Offenders are (agents_md, line, reference, resolved_path), sorted
    deterministically by `AGENTS.md` path then line: discovery walks
    `sorted(rglob(...))` and references within a file are emitted in
    line order, so the explicit final sort only formalizes that.
    """
    referenced_paths = 0
    offenders: list[tuple[str, int, str, str]] = []
    for path in sorted(cwd.rglob(AGENTS_FILENAME)):
        if is_excluded_agents_path(segments=path.relative_to(cwd).parts):
            continue
        text = path.read_text(encoding="utf-8")
        for line, ref in iter_ai_references(text=text):
            referenced_paths += 1
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
    return _Scan(referenced_paths=referenced_paths, offenders=sorted(offenders))


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
    scan = _scan_tree(cwd=cwd)
    if scan.offenders:
        for agents_md, line, reference, resolved_path in scan.offenders:
            log.error(
                "AGENTS.md references a .ai/ file that does not resolve",
                agents_md=agents_md,
                line=line,
                reference=reference,
                resolved_path=resolved_path,
            )
        return 1
    if scan.referenced_paths == 0:
        log.warning(
            "vacuous: no AGENTS.md in this tree references a .ai/ path, so this run "
            "inspected nothing — reference integrity here is UNPROVEN, not proven. "
            "This is not a failure (a repo may legitimately carry no .ai/ tree), but "
            "an exit 0 from this check certifies nothing until AGENTS.md routes to at "
            "least one .ai/ topic",
            verdict="vacuous",
            referenced_paths=scan.referenced_paths,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
