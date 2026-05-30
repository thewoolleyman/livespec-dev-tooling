"""vendor_manifest — `.vendor.jsonc` placeholder + shim discipline.

Per `python-skill-script-style-requirements.md` §"Canonical
target list" (the `check-vendor-manifest` row), `.vendor.jsonc`
is validated against the placeholder-and-shim invariants:

- Every entry has a non-empty `upstream_url`.
- Every entry has a non-empty `upstream_ref`.
- Every entry has a parseable-ISO `vendored_at`.
- The `shim: true` flag is required on the canonical hand-
  authored shim entry (`jsoncomment` per v026 D1) and absent
  on every other entry.

The check parses `.vendor.jsonc` via the vendored `jsonc`
shim under `livespec/parse/jsonc.py` (re-exposed at the
parse layer; the check imports that pure helper rather than
re-implementing JSONC stripping). If the manifest file is
absent, the check exits 0 — vendoring may not have run yet.

Output discipline: per spec, `print` (T20) and
`sys.stderr.write` (`check-no-write-direct`) are banned in
dev-tooling/**. Diagnostics flow through structlog (JSON to
stderr); the vendored copy under `.claude-plugin/scripts/
_vendor/structlog` is added to `sys.path` at module import time.
"""

from __future__ import annotations

import datetime as _dt
import sys
from pathlib import Path
from typing import Any, TypedDict, cast

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import jsoncomment  # noqa: E402  — vendor-path-aware import after sys.path insert.
import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

__all__: list[str] = []


_MANIFEST_FILENAME = ".vendor.jsonc"
_CANONICAL_SHIM_NAMES = frozenset({"jsoncomment"})


class _Manifest(TypedDict, total=False):
    """Top-level shape of `.vendor.jsonc`: a `libraries` array of entries.

    `total=False` mirrors the defensive `.get("libraries")` access — the key
    is optional, so the typed boundary matches runtime semantics exactly (no
    behavior change vs. the prior untyped parse). `libraries` is typed as a
    list of `object` (not `dict[str, Any]`) so the per-entry
    `isinstance(entry, dict)` check in `main` stays a load-bearing runtime
    guard against a malformed manifest rather than a statically-redundant one.
    """

    libraries: list[object]


def _is_iso_parseable(*, value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        _ = _dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _validate_entry(*, entry: dict[str, Any]) -> list[str]:
    name = str(entry.get("name", "<unnamed>"))
    issues: list[str] = []
    upstream_url = entry.get("upstream_url")
    if not isinstance(upstream_url, str) or not upstream_url:
        issues.append(f"{name}: empty or missing `upstream_url`")
    upstream_ref = entry.get("upstream_ref")
    if not isinstance(upstream_ref, str) or not upstream_ref:
        issues.append(f"{name}: empty or missing `upstream_ref`")
    if not _is_iso_parseable(value=entry.get("vendored_at")):
        issues.append(f"{name}: malformed or missing `vendored_at`")
    shim_flag = entry.get("shim")
    is_canonical_shim = name in _CANONICAL_SHIM_NAMES
    if is_canonical_shim and shim_flag is not True:
        issues.append(f"{name}: canonical shim must declare `shim: true`")
    if not is_canonical_shim and shim_flag is not None:
        issues.append(f"{name}: non-shim entry must omit `shim` flag")
    return issues


def main() -> int:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    log = structlog.get_logger("vendor_manifest")
    cwd = Path.cwd()
    manifest_path = cwd / _MANIFEST_FILENAME
    if not manifest_path.is_file():
        return 0
    text = manifest_path.read_text(encoding="utf-8")
    parsed = jsoncomment.loads(text)
    # The `cast` is the single typed parse boundary: `jsoncomment.loads`
    # yields `Any`, the `isinstance` guard narrows to `dict`, and the cast
    # asserts the validated shape so `.get("libraries")` is typed. The
    # `libraries` value is typed as a list of `object` so the per-entry
    # `isinstance(entry, dict)` shape check stays a load-bearing runtime
    # guard against a malformed manifest; the inner cast then types each
    # kept entry for `_validate_entry`.
    manifest = cast("_Manifest", parsed) if isinstance(parsed, dict) else None
    libraries = manifest.get("libraries") if manifest is not None else None
    if not isinstance(libraries, list):
        log.error("`.vendor.jsonc` missing top-level `libraries` array")
        return 1
    issues: list[str] = []
    for entry in libraries:
        if not isinstance(entry, dict):
            issues.append(f"non-dict library entry: {entry!r}")
            continue
        issues.extend(_validate_entry(entry=cast("dict[str, Any]", entry)))
    if issues:
        for issue in issues:
            log.error(".vendor.jsonc validation failure", issue=issue)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
