"""canonical_checks — single source of truth for the canonical check-slug set.

Enumerates which `livespec_dev_tooling.checks.<slug>` modules are
universally wired across the livespec fleet. Discovery is dynamic
(filesystem walk via `pkgutil.iter_modules` over the
`livespec_dev_tooling.checks` package directory) so adding a new
`checks/<name>.py` file automatically extends the canonical set on
next invocation — no second-source-of-truth hardcoded list to drift.

Consumers (downstream in epic li-univck):

- `aggregate_completeness` (Phase 1.3, li-aggchk) — set-membership
  plus ordering comparison against consumer justfiles.
- `livespec/templates/impl-plugin/justfile.jinja` (Phase 2.2,
  li-jnjtpl) — stamping the aggregate at copier-copy time.
- doctor's cross-repo invariant (Phase 2.3, li-dctxr) — fleet-wide
  drift detection.

Exclusions (filtered out before slug-mapping):

- Modules whose name starts with `_` (helper convention; the existing
  `_red_green_replay_modes` helper follows this).
- `__init__.py` (package marker, not a check).

Slug mapping: snake_case module name → kebab-case slug with
`check-` prefix. Examples:

- `keyword_only_args` → `check-keyword-only-args`
- `primary_checkout_commit_refuse_hook_installed`
  → `check-primary-checkout-commit-refuse-hook-installed`

Public API:

- `canonical_check_slugs() -> tuple[str, ...]` — returns the
  alphabetically-sorted slug tuple computed over the live
  `livespec_dev_tooling.checks` package directory.
- `python -m livespec_dev_tooling.canonical_checks --json` — thin-
  transport surface emitting `{"slugs": [...]}` on stdout, exit 0.

Output discipline: this module emits JSON to stdout (thin transport
contract) when invoked via `--json`. No structlog wiring needed
because no diagnostic surface exists — successful discovery is the
only path.
"""

from __future__ import annotations

import argparse
import json
import pkgutil
import sys
from pathlib import Path

__all__: list[str] = [
    "canonical_check_slugs",
    "main",
]


_CHECKS_PACKAGE_DIR = Path(__file__).resolve().parent / "checks"
_SLUG_PREFIX = "check-"


def _discover_slugs(*, package_path: Path) -> tuple[str, ...]:
    """Discover canonical check slugs from a checks-package directory.

    Walks `package_path` via `pkgutil.iter_modules`, filters out
    underscore-prefixed module names (helpers) and the implicit
    `__init__` entry, then maps each remaining `snake_case` module
    name to its `check-kebab-case` slug. Returns the result as an
    alphabetically-sorted tuple.

    The argument is the package's directory `Path`, not the
    importable name, so tests can point the discovery at a
    synthetic fixture tree without monkeypatching the live
    `livespec_dev_tooling.checks` package.
    """
    discovered: list[str] = []
    for module_info in pkgutil.iter_modules([str(package_path)]):
        name = module_info.name
        if name.startswith("_"):
            continue
        slug = _SLUG_PREFIX + name.replace("_", "-")
        discovered.append(slug)
    return tuple(sorted(discovered))


def canonical_check_slugs() -> tuple[str, ...]:
    """Return the alphabetically-sorted tuple of canonical check slugs.

    Computed over the live `livespec_dev_tooling.checks` package
    directory at every invocation. Adding a new `checks/<name>.py`
    file automatically extends the returned tuple on the next call;
    no second source of truth.
    """
    return _discover_slugs(package_path=_CHECKS_PACKAGE_DIR)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="canonical-checks",
        description=(
            "Emit the canonical-check slug set as JSON on stdout. "
            "Thin-transport surface consumed by aggregate-completeness, "
            "the impl-plugin justfile.jinja template, and doctor's "
            "cross-repo invariant (epic li-univck Phases 1.3 / 2.2 / 2.3)."
        ),
    )
    _ = parser.add_argument(
        "--json",
        action="store_true",
        help=(
            'Emit `{"slugs": [...]}` to stdout. Required flag; '
            "reserved for a future plain-text mode if a consumer "
            "needs one. Today JSON is the only supported output."
        ),
    )
    return parser


def main() -> int:
    parser = _build_parser()
    # Parse args for argparse-driven `--help` handling and to reserve
    # the `--json` flag namespace; the parsed value is not consulted
    # because JSON is currently the only supported emission mode.
    _ = parser.parse_args()
    slugs = canonical_check_slugs()
    payload = {"slugs": list(slugs)}
    _ = sys.stdout.write(json.dumps(payload) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
