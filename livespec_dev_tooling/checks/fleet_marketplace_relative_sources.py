"""fleet_marketplace_relative_sources - require relative plugin catalog sources.

Fleet plugin ref pinning depends on marketplace catalog plugin `source` values
being checkout-relative paths such as `./.claude-plugin`. A github-style source
silently ignores the registered marketplace ref and clones the default branch
HEAD instead of the pinned `release` tip, which reintroduces stale plugin code
without an install-time error. This structural check scans every
`marketplace.json` catalog present in the consumer tree and fails loud unless
every plugin entry's `source` is a string beginning with `./`.

The check is deterministic and always invoked through `just check`; repos with
no marketplace catalogs are outside this check's role and pass with an info log.
Diagnostics flow through structlog JSON to stderr.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import cast

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  - vendor-path-aware import after sys.path insert.

__all__: list[str] = []


_CHECK_ID = "fleet_marketplace_relative_sources"
_MARKETPLACE = "marketplace.json"
_SKIP_DIRS = frozenset({".git", ".venv", "__pycache__", "_vendor"})
_FAIL_EXIT = 1


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


def _iter_marketplace_paths(*, root: Path) -> tuple[Path, ...]:
    return tuple(
        path
        for path in sorted(root.rglob(_MARKETPLACE))
        if _SKIP_DIRS.isdisjoint(path.relative_to(root).parts)  # pragma: no branch
    )


def _entry_source(*, entry: object) -> object:
    if not isinstance(entry, dict):  # pragma: no cover - malformed catalog entry
        return None
    return cast("dict[str, object]", entry).get("source")


def _non_relative_sources(*, root: Path, path: Path) -> tuple[tuple[Path, object], ...]:
    catalog_obj: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(catalog_obj, dict):  # pragma: no cover - malformed catalog
        return ((path.relative_to(root), None),)
    catalog = cast("dict[str, object]", catalog_obj)
    plugins_obj = catalog.get("plugins", [])
    if not isinstance(plugins_obj, list):  # pragma: no cover - malformed catalog
        return ((path.relative_to(root), None),)
    plugins = cast("list[object]", plugins_obj)
    return tuple(
        (path.relative_to(root), source)
        for source in (_entry_source(entry=entry) for entry in plugins)
        if not str(source).startswith("./")
    )


def main() -> int:
    log = _configure_logger()
    root = Path.cwd()
    marketplace_paths = _iter_marketplace_paths(root=root)
    if not marketplace_paths:
        log.info(
            "fleet marketplace relative sources: skipped",
            check_id=_CHECK_ID,
            reason="no marketplace.json catalogs found",
        )
        return 0

    offenders = tuple(
        offender
        for path in marketplace_paths
        for offender in _non_relative_sources(root=root, path=path)
    )
    for path, source in offenders:
        log.error(
            "fleet marketplace plugin source must be relative to preserve ref pinning",
            check_id=_CHECK_ID,
            status="fail",
            path=str(path),
            line=0,
            source=source,
            hint=(
                "use a checkout-relative source beginning './'; github-type or other "
                "non-relative sources silently ignore the marketplace ref pin"
            ),
        )
    return _FAIL_EXIT if offenders else 0


if __name__ == "__main__":
    raise SystemExit(main())
