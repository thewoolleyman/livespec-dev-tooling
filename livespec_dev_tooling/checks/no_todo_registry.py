"""no_todo_registry — `tests/heading-coverage.json` rejects any `test: "TODO"` entry.

Per `python-skill-script-style-requirements.md` section "Canonical
target list" (the `check-no-todo-registry` row), no entry in
`tests/heading-coverage.json` may have `test: "TODO"`.

The TODO scan ALWAYS runs (no skip carve-out). A self-documenting
severity lever controls only the release-context behavior: when
`LIVESPEC_FAIL_IF_HEADING_COVERAGE_TODOS_EXIST` is set to a
non-empty value (CI sets it to `true` for the release context),
discovered offenders fail the check (exit 1, error-level
diagnostics). When the lever is unset (or empty), the SAME
findings are logged at WARNING level and the check exits 0, so
authoring placeholders surface without blocking per-commit
`just check`. This replaces the prior `LIVESPEC_RELEASE_GATE`
skip carve-out (epic li-cvaudit, cvtodo) — the old carve-out
SILENTLY skipped the scan entirely when the gate was unset.

The check loads the JSON file (strict JSON, not JSONC) and
walks the array. Any entry whose `test` field equals the
literal string `"TODO"` surfaces. If the file is missing or
contains only non-TODO entries, the check exits 0.

Output discipline: per spec, `print` (T20) and
`sys.stderr.write` (`check-no-write-direct`) are banned in
dev-tooling/**. Diagnostics flow through structlog (JSON to
stderr); the vendored copy under `.claude-plugin/scripts/
_vendor/structlog` is added to `sys.path` at module import time.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import cast

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

__all__: list[str] = []


_COVERAGE_PATH = Path("tests") / "heading-coverage.json"
_FAIL_ENV_VAR = "LIVESPEC_FAIL_IF_HEADING_COVERAGE_TODOS_EXIST"


def main() -> int:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    log = structlog.get_logger("no_todo_registry")
    cwd = Path.cwd()
    coverage_path = cwd / _COVERAGE_PATH
    if not coverage_path.is_file():
        return 0
    text = coverage_path.read_text(encoding="utf-8")
    parsed = json.loads(text)
    offenders: list[dict[str, object]] = []
    if isinstance(parsed, list):
        # The `cast` is the single typed parse boundary: `json.loads` yields
        # `Any`, the `isinstance` guard narrows to `list`, and the cast gives
        # the elements a typed `object` shape so the per-element
        # `isinstance(entry, dict)` filter stays a load-bearing runtime guard.
        # The compound condition (single `if`, inline cast evaluated only
        # after the isinstance short-circuit) preserves the original branch
        # shape — no new branch, so coverage stays 100%.
        entries = cast("list[object]", parsed)
        for entry in entries:
            if isinstance(entry, dict) and cast("dict[str, object]", entry).get("test") == "TODO":
                offenders.append(cast("dict[str, object]", entry))
    if offenders:
        fail = bool(os.environ.get(_FAIL_ENV_VAR))
        for entry in offenders:
            emit = log.error if fail else log.warning
            emit(
                'heading-coverage.json entry has `test: "TODO"`',
                heading=entry.get("heading"),
                spec_root=entry.get("spec_root"),
                fail_env_var=_FAIL_ENV_VAR,
                failing=fail,
            )
        return 1 if fail else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
