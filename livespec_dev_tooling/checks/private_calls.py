"""private_calls — no cross-module `_`-prefixed function calls in `livespec/**`.

Per `python-skill-script-style-requirements.md` section "Canonical
target list" (the `check-private-calls` row), no cross-module
calls to `_`-prefixed functions defined elsewhere are
permitted in `livespec/**`. Within a single module, calling
`_helper()` is fine; from another module, calling
`other_module._helper()` is banned.

The check walks the git-derived first-party `.py` universe
(`config.resolve_check_universe`), parses each via `ast`, and
inspects every `Call` whose function is an `Attribute` access.
The check flags violations when:

- The attribute name starts with `_` (and is not a dunder
  `__*__`).
- The receiver is a `Name` that is NOT `self` or `cls`
  (intra-class private access via `self._foo()` is fine).

Cycle 157 implements this minimum-viable structural check.
Subsequent cycles can tighten by verifying the receiver is
an imported module name (vs an arbitrary local variable
holding an instance).

BESIDE-TEST EXEMPTION. This check and ruff's `SLF001`
(`private-member-access`) police the SAME invariant, and they
disagreed about beside-tests: a beside-test calling the private
decision helper it exists to test is exactly what such a test
is FOR. Where a consumer's own
`[tool.ruff.lint.per-file-ignores]` already grants `SLF001` to
a pattern, this check honours that ratification and skips the
matching files (`config.load_slf001_exempt_globs` /
`config.is_slf001_exempt`). The scope is deliberately narrow:
the exemption is keyed to the one ruff rule that polices this
same invariant, so it cannot widen into a general "tests may do
anything" hatch, and the pattern is DERIVED from the consumer's
configuration rather than hardcoded to any one repo's layout.
The production invariant is untouched — a production file that
does not match the consumer's declared pattern still fails.

Phase-0 rollout severity (fleet-check-coverage): the file
universe is the git-derived first-party `.py` set
(`config.iter_first_party_py_files`) rather than a
`config.source_trees` walk. `config.source_trees` is retained
ONLY as a delta-WARN severity classifier: a cross-module
private call in a file UNDER a `source_trees` tree keeps
today's hard gate (an `error`-level diagnostic contributing to
exit 1); the same violation in a file newly pulled into the
git-derived universe emits at WARN (`warning`-level,
`phase="0-warn"`, no exit-1 contribution) until Phase 2 flips
its repo to the hard gate. A genuinely codeless repo (zero
first-party `.py`) passes with an info-level "nothing to
check".

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
    is_slf001_exempt,
    is_under_any_tree,
    load_config,
    load_slf001_exempt_globs,
    resolve_check_universe,
)

__all__: list[str] = []


_INTRA_CLASS_RECEIVERS = frozenset({"self", "cls"})


def _is_dunder(*, name: str) -> bool:
    return name.startswith("__") and name.endswith("__")


def _is_offending_attribute_call(*, call: ast.Call) -> bool:
    func = call.func
    if not isinstance(func, ast.Attribute):
        return False
    if not func.attr.startswith("_") or _is_dunder(name=func.attr):
        return False
    receiver = func.value
    return not (isinstance(receiver, ast.Name) and receiver.id in _INTRA_CLASS_RECEIVERS)


def _find_offenders(*, source: str) -> list[tuple[int, str]]:
    tree = ast.parse(source)
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _is_offending_attribute_call(call=node):
            attr = node.func
            assert isinstance(attr, ast.Attribute)  # noqa: S101 — narrowing for ast.unparse
            out.append((node.lineno, ast.unparse(attr)))
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
    log = structlog.get_logger("private_calls")
    root, universe = resolve_check_universe()
    if not universe:
        log.info("no first-party Python to check")
        return 0
    config = load_config(repo_root=root)
    slf001_exempt = load_slf001_exempt_globs(repo_root=root)
    legacy_offenders: list[tuple[Path, int, str]] = []
    newly_offenders: list[tuple[Path, int, str]] = []
    for rel in universe:
        if is_slf001_exempt(rel=rel, globs=slf001_exempt):
            # The consumer's own ruff config already grants this file `SLF001`,
            # the rule policing this same invariant. Honour that ratification
            # rather than contradicting it with a second verdict on one rule.
            continue
        source = (root / rel).read_text(encoding="utf-8")
        for lineno, attr_path in _find_offenders(source=source):
            record = (rel, lineno, attr_path)
            if is_under_any_tree(rel=rel, trees=config.source_trees):
                legacy_offenders.append(record)
            else:
                newly_offenders.append(record)
    for path, lineno, attr_path in legacy_offenders:
        log.error(
            "cross-module call to `_`-prefixed name is banned",
            file=str(path),
            line=lineno,
            call=attr_path,
        )
    for path, lineno, attr_path in newly_offenders:
        log.warning(
            "cross-module call to `_`-prefixed name is banned — newly "
            "git-derived coverage; Phase-0 WARN (hard-fails once this repo is "
            "flipped to the hard gate in Phase 2)",
            file=str(path),
            line=lineno,
            call=attr_path,
            phase="0-warn",
            newly_covered=True,
        )
    return 1 if legacy_offenders else 0


if __name__ == "__main__":
    raise SystemExit(main())
