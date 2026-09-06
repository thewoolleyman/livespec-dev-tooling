"""no_raise_outside_io — domain-error raises confined to `io/**` and `errors.py`.

Per `python-skill-script-style-requirements.md` section "Canonical
target list" (the `check-no-raise-outside-io` row), raising a
domain error at runtime is restricted to the consumer's declared
`io_trees` and the `errors.py` sitting beside them. Pure layers
(parse/, validate/, commands/, doctor/, schemas/) return
`Failure(SomeError(...))` on the ROP railway instead. Bug-class
exceptions (TypeError, ValueError, NotImplementedError,
AssertionError, etc.) are permitted anywhere — they propagate to
the supervisor's bug-catcher.

WHICH NAMES COUNT AS DOMAIN ERRORS IS DERIVED FROM THE CONSUMING
REPO. The set used to be livespec-core's four class names
(`LivespecError`, `UsageError`, `PreconditionError`,
`ValidationError`) hardcoded here, which matched ZERO raise sites
anywhere in the fleet — including in core itself, which is fully
ROP and raises none of them. Every consumer got a check that
walked its whole universe and could not report a single offense,
and a vacuous gate is indistinguishable from a passing one, which
is why review rather than CI found it
(`livespec-dev-tooling-6vz`).

Deriving is the move the universe already makes: a set that merely
says "these names" is computed rather than declared, so it cannot
drift as consumers are added and cannot be narrowed into a bypass.
A first-party class is a domain error when it inherits — directly
or transitively — from a builtin exception, from another
first-party domain error, or from a name spelled
`…Error`/`…Exception` (how a consumer subclasses an error class
imported from livespec-core). Builtins are excluded by
construction, since they are not classes the consumer defines,
which is exactly the bug-class carve-out the rule already wanted.

SEVERITY: DETECTION LANDS AT A WARN TIER. Findings are reported at
warning severity and the check exits 0; setting
`LIVESPEC_FAIL_IF_DOMAIN_ERROR_RAISES_EXIST` promotes them to
error severity and exit 1. That is a documented severity lever,
not a skip — nothing is exempted, every finding is reported either
way, and the lever only ever makes the check STRICTER. The tier
exists because arming at fail severity immediately reddens
consumers that have never been checked at all: measured 2026-07-19,
`livespec-orchestrator-beads-fabro` alone carries ~47 raise sites
outside its declared io trees, and nobody has yet adjudicated which
raise shapes ratified v169 sanctions — the `unsafe_perform_io`
command-boundary adapter idiom in particular. Promote to fail once
the fleet is clean. Do NOT answer a finding with a per-repo
exemption, a skip flag, or an allowlist.

The universe is the GIT-DERIVED first-party set
(`resolve_check_universe`) — every tracked first-party `.py`, so a
new module is covered the moment it is tracked. It is deliberately
NOT the declared `source_trees` allowlist: that made
`source_trees = []` mean "scan nothing" while the declaration read
as conformance — a scope dodge that disarmed this check over a
whole package with one empty array. `io_trees` remains DECLARED
because it records an architectural ROLE the git index cannot
supply.

Files under `io_trees`, and the single `errors.py` beside them,
are exempt from RAISING a domain error; with `io_trees` unset
nothing is exempt and every source file is inspected. They are NOT
exempt from DEFINING one — every file in the universe feeds the
derivation, because `errors.py` is precisely where a consumer's
hierarchy is declared and skipping it would derive an empty set.

Output discipline: per spec, `print` (T20) and
`sys.stderr.write` (`check-no-write-direct`) are banned in
dev-tooling/**. Diagnostics flow through structlog (JSON to
stderr); the vendored copy under `.claude-plugin/scripts/
_vendor/structlog` is added to `sys.path` at module import time.
"""

from __future__ import annotations

import ast
import builtins
import os
import sys
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

from livespec_dev_tooling.config import (  # noqa: E402
    Config,
    load_config,
    resolve_check_universe,
)

__all__: list[str] = []


_FAIL_ENV_VAR = "LIVESPEC_FAIL_IF_DOMAIN_ERROR_RAISES_EXIST"
_REASON = "domain-error raise outside `io/`/`errors.py` is banned"

_BUILTIN_EXCEPTION_NAMES = frozenset(
    name
    for name, value in vars(builtins).items()
    if isinstance(value, type) and issubclass(value, BaseException)
)
_ERROR_NAME_SUFFIXES = ("Error", "Exception")


def _head_name(*, expr: ast.expr) -> str:
    """Final dotted component of a raise target or a class base, call arguments dropped.

    `raise errors.SchemaViolationError("x")` and `raise SchemaViolationError("x")`
    name the same class, so both must render to the same key. Matching the whole
    rendering instead would let the qualified spelling — the ordinary shape in a
    module that imports the errors MODULE rather than the class — walk straight
    past the check.
    """
    return ast.unparse(expr).split("(", maxsplit=1)[0].rsplit(".", maxsplit=1)[-1]


def _class_bases(*, source: str) -> list[tuple[str, tuple[str, ...]]]:
    """Every class defined in `source`, paired with the head names of its bases."""
    tree = ast.parse(source)
    return [
        (node.name, tuple(_head_name(expr=base) for base in node.bases))
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
    ]


def _is_error_base(*, base: str, derived: frozenset[str]) -> bool:
    """True when `base` marks its subclass as an error class.

    Three admissible shapes, and the third is what makes this work across repo
    boundaries: a consumer's hierarchy often roots in an error class IMPORTED
    from another repo (livespec-core's `LivespecError`), whose definition is not
    in this universe and so can never appear in `derived`. Naming convention is
    the only signal available there, and it is the same convention the whole
    fleet already follows.
    """
    return (
        base in _BUILTIN_EXCEPTION_NAMES or base in derived or base.endswith(_ERROR_NAME_SUFFIXES)
    )


def _derive_domain_error_names(
    *, class_bases: tuple[tuple[str, tuple[str, ...]], ...]
) -> frozenset[str]:
    """Close over the consumer's own class definitions until the error set stops growing.

    Iterated to a fixpoint rather than resolved in one pass because a hierarchy
    is a CHAIN — `MalformedRecordLineError` → `JsoncParseError` → `Exception` —
    whose links may be defined in any file order, and the order here is `git
    ls-files`', not the author's. A single pass would classify a subclass only
    when its base happened to be seen first.
    """
    derived: frozenset[str] = frozenset()
    while True:
        grown = derived | {
            name
            for name, bases in class_bases
            if any(_is_error_base(base=base, derived=derived) for base in bases)
        }
        if grown == derived:
            return derived
        derived = grown


def _is_exempt(*, rel_path: Path, config: Config) -> bool:
    # `errors.py` is the canonical domain-error home in livespec-core's
    # layout: the file sitting directly under the (single) io-parent tree.
    for io_tree in config.io_trees:
        if rel_path == io_tree.parent / "errors.py":
            return True
        if io_tree in rel_path.parents:
            return True
    return False


def _find_domain_raises(
    *, source: str, domain_error_names: frozenset[str]
) -> list[tuple[int, str]]:
    tree = ast.parse(source)
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Raise) or node.exc is None:
            continue
        head = _head_name(expr=node.exc)
        if head in domain_error_names:
            out.append((node.lineno, head))
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
    log = structlog.get_logger("no_raise_outside_io")
    root, universe = resolve_check_universe()
    # A genuinely codeless repo is a PASS, not a configuration error. It is the
    # one exemption the railway clause grants, and `resolve_check_universe`
    # raises typed git errors rather than returning a spuriously-empty walk, so
    # an empty universe here means exactly what it says.
    if not universe:
        log.info("no first-party Python to check", check_id="no_raise_outside_io")
        return 0
    config = load_config(repo_root=root)
    sources = {rel: (root / rel).read_text(encoding="utf-8") for rel in universe}
    # Derived from the WHOLE universe, exempt files included: `io/` and
    # `errors.py` are exempt from RAISING a domain error, not from DEFINING one.
    # In livespec-core's layout `errors.py` declares the entire hierarchy, so
    # skipping exempt files would derive an empty set and restore the vacuity.
    class_bases = tuple(pair for source in sources.values() for pair in _class_bases(source=source))
    domain_error_names = _derive_domain_error_names(class_bases=class_bases)
    offenders: list[tuple[Path, int, str]] = []
    inspected = 0
    for rel, source in sources.items():
        if _is_exempt(rel_path=rel, config=config):
            continue
        inspected += 1
        for lineno, error_name in _find_domain_raises(
            source=source, domain_error_names=domain_error_names
        ):
            offenders.append((rel, lineno, error_name))
    fail = bool(os.environ.get(_FAIL_ENV_VAR))
    # An inspected count of zero otherwise reads exactly like a clean pass, so
    # it is reported on every run rather than inferred from silence. The derived
    # NAME count is reported for the same reason and is the half that was
    # missing: inspecting every file in the repo against an empty name set is
    # still inspecting nothing, and that was this check's actual state
    # fleet-wide for as long as the set was hardcoded.
    log.info(
        "inspection complete",
        check_id="no_raise_outside_io",
        files_inspected=inspected,
        domain_error_names=len(domain_error_names),
        offenses=len(offenders),
        failing=fail,
    )
    for path, lineno, error_name in offenders:
        finding: dict[str, object] = {
            "file": str(path),
            "line": lineno,
            "error": error_name,
            "failing": fail,
            "fail_env_var": _FAIL_ENV_VAR,
        }
        # Same finding, same wording, two severities — the tier changes what
        # happens to it, never whether it is reported.
        if fail:
            log.error(_REASON, **finding)
        else:
            log.warning(_REASON, **finding)
    return 1 if (fail and offenders) else 0


if __name__ == "__main__":
    raise SystemExit(main())
