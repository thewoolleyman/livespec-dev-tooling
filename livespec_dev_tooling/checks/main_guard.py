"""main_guard — bans `if __name__ == "__main__":` inside plugin-packaging trees.

Per `python-skill-script-style-requirements.md` section "Canonical
target list" (the `check-main-guard` row), no `.py` file under
a `.claude-plugin/scripts/` plugin-packaging tree may contain an
`if __name__ == "__main__":` guard at any nesting level. A
plugin's runnable entry points live in `bin/*.py` (the shebang
wrappers the installer flattens `.claude-plugin/scripts/`
around); a `__main__` guard inside a plugin tree indicates a
wrapper-style file in the wrong place.

The ban is ROLE-SCOPED to that convention: the check inspects
only files under `.claude-plugin/scripts/` (any package name).
First-party modules OUTSIDE that tree — a `python -m`-invoked
package such as `livespec_dev_tooling/**`, a library package, a
harness hook — legitimately carry `__main__` guards and are not
subject to the ban. Within scope, files under the legacy
`.claude-plugin/scripts/livespec/` tree emit a structlog ERROR
(exit 1); files under any other plugin tree emit a Phase-0 WARN
(`newly_covered`, exit 0) per the delta-WARN model. It parses
each file via `ast` and inspects every `If` node whose test
unparses to the canonical `__name__ == "__main__"` string
(either operand order). With no legacy violations, exits 0.

Output discipline: per spec, `print` (T20) and
`sys.stderr.write` (`check-no-write-direct`) are banned in
dev-tooling/**. Diagnostics flow through structlog (JSON to
stderr); the vendored copy under `.claude-plugin/scripts/
_vendor/structlog` is added to `sys.path` at module import time.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

from livespec_dev_tooling.config import (  # noqa: E402
    is_under_any_tree,
    load_config,
    resolve_check_universe,
)

__all__: list[str] = []


_PLUGIN_SCRIPTS_TREE = Path(".claude-plugin") / "scripts"
_MAIN_GUARD_TEXTS = frozenset(
    {
        "__name__ == '__main__'",
        '__name__ == "__main__"',
        "'__main__' == __name__",
        '"__main__" == __name__',
    }
)


def _find_main_guard_lines(*, source: str) -> list[int]:
    tree = ast.parse(source)
    return [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.If) and ast.unparse(node.test) in _MAIN_GUARD_TEXTS
    ]


def main() -> int:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    log = structlog.get_logger("main_guard")
    root, universe = resolve_check_universe()
    config = load_config(repo_root=root)
    legacy_offenders: list[tuple[Path, int]] = []
    newly_covered_offenders: list[tuple[Path, int]] = []
    for rel in universe:
        if not is_under_any_tree(rel=rel, trees=(_PLUGIN_SCRIPTS_TREE,)):
            # main_guard is ROLE-SCOPED to the plugin-packaging convention:
            # the `__main__` ban applies only under `.claude-plugin/scripts/`
            # (the installer-flattened surface where `bin/*.py` wrappers are the
            # entry convention). First-party modules outside that tree — a
            # `python -m`-invoked package, a library, a hook — legitimately
            # carry `__main__` guards and are not subject to the ban.
            continue
        source = (root / rel).read_text(encoding="utf-8")
        for lineno in _find_main_guard_lines(source=source):
            if is_under_any_tree(rel=rel, trees=config.source_trees):
                legacy_offenders.append((rel, lineno))
            else:
                newly_covered_offenders.append((rel, lineno))
    for path, lineno in newly_covered_offenders:
        log.warning(
            "`__main__` guard banned in first-party modules — newly git-derived coverage; "
            "Phase-0 WARN (hard-fails once this repo is flipped to the hard gate in Phase 2)",
            file=str(path),
            line=lineno,
            phase="0-warn",
            newly_covered=True,
        )
    for path, lineno in legacy_offenders:
        log.error(
            "`__main__` guard banned in livespec/**",
            file=str(path),
            line=lineno,
        )
    if legacy_offenders:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
