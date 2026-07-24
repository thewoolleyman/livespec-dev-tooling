"""no_inheritance — direct-parent allowlist for `class X(Y):` in `livespec/**`.

Per `python-skill-script-style-requirements.md` §"Canonical
target list" (the `check-no-inheritance` row), `class X(Y):`
inside `.claude-plugin/scripts/livespec/**` is forbidden when
`Y` is not in the closed direct-parent allowlist:
`{Exception, BaseException, LivespecError, Protocol,
NamedTuple, TypedDict, Generic}`. This codifies the
flat-composition direction and the v013 M5 leaf-closed
tightening: `LivespecError` subclasses themselves are NOT
acceptable bases — `class RateLimitError(UsageError):` is
rejected even though `UsageError` is itself a `LivespecError`
subclass. `LivespecError` itself remains an open extension
point. `Generic` is allowlisted because `Generic[...]`
parameterization is structural typing machinery, not
implementation inheritance: the ratified flat-full-ROP railway
(livespec non-functional-requirements v165 §"Shared content
provenance", landed in the Drivers by accepted items 7u7/96q)
requires `Success(Generic[_T])`-shaped containers, and the 3.10
fleet floor rules out the PEP 695 type-parameter syntax that
would remove the base. A SUBSCRIPTED base (`Generic[_T]`,
`Protocol[_T]`) is unwrapped to its value before allowlist
matching; a subscripted DISALLOWED base (`list[int]`) still
fails exactly like its bare form.

The check walks the git-derived first-party `.py` universe
(`config.resolve_check_universe`), parses each via `ast`, and
inspects every `ClassDef` node's `bases` list. Each base is
rendered via `ast.unparse` and the rightmost name (e.g.,
`typing.Protocol` → `Protocol`) is checked against the
allowlist.

Phase-0 rollout severity (fleet-check-coverage): the file
universe is the git-derived first-party `.py` set
(`config.iter_first_party_py_files`) rather than a
`config.source_trees` walk. `config.source_trees` is retained
ONLY as a delta-WARN severity classifier: a base outside the
allowlist in a file UNDER a `source_trees` tree keeps today's
hard gate (an `error`-level diagnostic contributing to exit 1);
the same violation in a file newly pulled into the git-derived
universe emits at WARN (`warning`-level, `phase="0-warn"`, no
exit-1 contribution) until Phase 2 flips its repo to the hard
gate. A genuinely codeless repo (zero first-party `.py`) passes
with an info-level "nothing to check".

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


_ALLOWED_PARENTS = frozenset(
    {
        "Exception",
        "BaseException",
        "LivespecError",
        "Protocol",
        "NamedTuple",
        "TypedDict",
        "Generic",
    }
)


def _base_terminal_name(*, base: ast.expr) -> str:
    # A subscripted base (`Generic[_T]`, `Protocol[_T]`) unwraps to its value
    # first — the whole subscription can never equal an allowlist entry, and
    # parameterization is not what the allowlist discriminates on. Subscripted
    # DISALLOWED bases (`list[int]` -> `list`) still miss the allowlist.
    target = base.value if isinstance(base, ast.Subscript) else base
    rendered = ast.unparse(target)
    return rendered.rsplit(".", maxsplit=1)[-1]


def _find_disallowed_inheritances(*, source: str) -> list[tuple[int, str, str]]:
    tree = ast.parse(source)
    out: list[tuple[int, str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for base in node.bases:
            terminal = _base_terminal_name(base=base)
            if terminal not in _ALLOWED_PARENTS:
                out.append((node.lineno, node.name, ast.unparse(base)))
    return out


def main() -> int:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    log = structlog.get_logger("no_inheritance")
    root, universe = resolve_check_universe()
    if not universe:
        log.info("no first-party Python to check")
        return 0
    config = load_config(repo_root=root)
    legacy_offenders: list[tuple[Path, int, str, str]] = []
    newly_offenders: list[tuple[Path, int, str, str]] = []
    for rel in universe:
        source = (root / rel).read_text(encoding="utf-8")
        for lineno, class_name, base in _find_disallowed_inheritances(source=source):
            record = (rel, lineno, class_name, base)
            if is_under_any_tree(rel=rel, trees=config.source_trees):
                legacy_offenders.append(record)
            else:
                newly_offenders.append(record)
    for path, lineno, class_name, base in legacy_offenders:
        log.error(
            "class base outside direct-parent allowlist",
            file=str(path),
            line=lineno,
            class_name=class_name,
            base=base,
            allowlist=sorted(_ALLOWED_PARENTS),
        )
    for path, lineno, class_name, base in newly_offenders:
        log.warning(
            "class base outside direct-parent allowlist — newly git-derived "
            "coverage; Phase-0 WARN (hard-fails once this repo is flipped to "
            "the hard gate in Phase 2)",
            file=str(path),
            line=lineno,
            class_name=class_name,
            base=base,
            allowlist=sorted(_ALLOWED_PARENTS),
            phase="0-warn",
            newly_covered=True,
        )
    return 1 if legacy_offenders else 0


if __name__ == "__main__":
    raise SystemExit(main())
