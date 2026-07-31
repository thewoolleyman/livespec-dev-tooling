"""public_api_result_typed — pure-layer public APIs return Result/IOResult or carry decorator.

Every PUBLIC function returns `Result` or `IOResult` per
annotation OR carries a railway-lifting decorator
(`@impure_safe(...)` lifts to `IOResult`, `@safe(...)` lifts
to `Result`).

WHAT COUNTS AS PUBLIC IS NO LONGER `__all__` MEMBERSHIP.
Ratified livespec v178 (`non-functional-requirements.md`
§"ROP composition") makes a top-level function public only
when it is CONSUMED ACROSS A BOUNDARY, measured FLEET-WIDE.
`checks/_public_api_consumption` computes the forms a
repo-local vantage can see; the consumer DECLARES the rest in
`cross_repo_public_api` (SPECIFICATION v036), because a
repo-local check structurally CANNOT see a sibling's import.
The declaration is TIGHTENING-ONLY — it is UNIONED with the
computed set, so an absent declaration removes nothing — and
a declared entry that no longer resolves to a real top-level
function FAILS the check rather than being carried forward.

COMPLETENESS OF THAT DECLARATION IS NOT VERIFIED HERE, and a
green run does NOT mean it is complete: whether a member's
declared surface omits a name another member consumes is the
central-vantage conformance row's obligation under v178's
split-enforcement clause.

WHICH PUBLIC FUNCTIONS THE RULE REACHES IS SCOPED AGAIN BY
livespec v179, in two members read together here. Member 1 is
COMPUTED every run (`checks/_no_expected_failure_mode`); member 2
is DECLARED per function in `total_absence_returns` and gated by
`checks/_declared_absence_returns` (SPECIFICATION v037). The two
sets are disjoint by construction — clause (e) refuses every
`X | None`, the only shape member 2 admits.

⛔ BOTH DECLARATION KEYS' STALENESS GATES SIT BEHIND THE
`pure_trees` ROLE-ABSENCE GATE, so a repo whose `pure_trees` is
`not_applicable` or `unarmed_until` never reaches them and its
declarations are UNVERIFIED locally until the check is armed
there. That is an artifact of the gate ORDER, not of the
detectors, and it is stated here rather than left to be
discovered.

The scan universe is still `pure_trees`-scoped; the
CONSUMPTION universe is the git-derived first-party set from
`resolve_check_universe()`, because a consumer of a pure-layer
function generally lives outside the pure layer.

For each `.py` in scope, parse via `ast` and inspect each
top-level FunctionDef the criterion calls public. A function
passes if EITHER:

- Its return annotation's terminal name is `Result` or
  `IOResult` (also matching `Result[...]` / `IOResult[...]`
  / `livespec.types.Result` etc.).
- It carries a decorator whose terminal name is `safe` or
  `impure_safe` (call form or bare).

The exemption set is the EXHAUSTIVE four-member set ratified in
livespec v177 (`non-functional-requirements.md` §"ROP
composition"), and all four ARE wired in: `main() -> int` under
`commands_trees` or at `doctor/run_static.py`; `build_parser()
-> ArgumentParser` under `commands_trees`; any function
annotated `None`; and a supervisor entry point in a file
declared in `supervisor_entry_files`. `make_validator`,
`get_logger`, `compile_schema` and `rop_pipeline` are NOT
members — they are cited only to an `archive/brainstorming/`
document this repo treats as reference-only, and appear nowhere
in any `SPECIFICATION/`.

Package-private modules (filename matching `_*.py`) are
skipped, and a `_`-prefixed FUNCTION name is not public
however it is reached — v178 clause 0 (see `_is_public_name`).

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
from typing import TYPE_CHECKING

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

from livespec_dev_tooling.checks._declared_absence_returns import (  # noqa: E402
    declared_absence_names,
    rejected_declarations,
)
from livespec_dev_tooling.checks._no_expected_failure_mode import (  # noqa: E402
    functions_without_expected_failure_mode,
)
from livespec_dev_tooling.checks._public_api_consumption import (  # noqa: E402
    declared_public_names,
    repo_local_public_names,
    stale_declarations,
)
from livespec_dev_tooling.checks._role_key_gate import (  # noqa: E402
    ensure_declared_paths_contain_python,
    role_absence_exit_code,
)
from livespec_dev_tooling.config import (  # noqa: E402
    iter_py_files,
    load_config,
    resolve_check_universe,
    role_trees,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from livespec_dev_tooling.config import Config

__all__: list[str] = []


_RESULT_NAMES = frozenset({"Result", "IOResult"})
# The one non-`commands/` location the spec names for the `main() -> int`
# supervisor exemption.
_DOCTOR_RUN_STATIC = Path("doctor") / "run_static.py"
_RAILWAY_LIFTING_DECORATORS = frozenset({"safe", "impure_safe"})


def _decorator_terminal_name(*, decorator: ast.expr) -> str:
    if isinstance(decorator, ast.Call):
        decorator = decorator.func
    return ast.unparse(decorator).rsplit(".", maxsplit=1)[-1]


def _annotation_head_name(*, annotation: ast.expr) -> str:
    rendered = ast.unparse(annotation)
    head = rendered.split("[", maxsplit=1)[0]
    return head.rsplit(".", maxsplit=1)[-1]


def _railway_aliases(*, tree: ast.Module) -> frozenset[str]:
    """MODULE-LEVEL names assigned a `Result[...]` / `IOResult[...]` type alias.

    A type alias defeats a terminal-name match, and this repo has one:
    `fleet/_snapshot.py` declares `SnapshotResult = IOResult[TreeSnapshot,
    SnapshotUnavailable]` and annotates `memoized_snapshot -> SnapshotResult`,
    so the check convicted a function ALREADY on the railway.

    ⛔ SCOPED TO `tree.body`, NOT `ast.walk`, and that is the bound rather than
    an implementation detail. An assignment inside a function body is a local
    binding that no annotation elsewhere in the file resolves through; reading
    those would let any function exempt itself by naming a local. It also
    resolves only aliases to the RAILWAY — an alias to a plain container stays
    an offender, because the point is to read what the annotation ACTUALLY
    names, not to accept every alias.

    Both `X = Result[...]` and the bare `X = Result` spelling are read, since
    they are the same declaration to a reader and differing on syntax would be
    a rule with two answers.

    ⚠️ A PEP 695 `type X = Result[...]` statement is NOT read, and the omission
    is deliberate rather than an oversight: `ast.TypeAlias` does not exist
    before Python 3.12 and this suite runs on 3.10, so naming it would be an
    `AttributeError` at parse time in every consumer. Add it when the floor
    moves — the fleet-wide floor, not this repo's.
    """
    aliases: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
            value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            targets = [node.target.id]
            value = node.value
        else:
            continue
        if value is not None and _annotation_head_name(annotation=value) in _RESULT_NAMES:
            aliases.update(targets)
    return frozenset(aliases)


def _is_railway_compliant(
    *, func: ast.FunctionDef | ast.AsyncFunctionDef, railway_aliases: frozenset[str] = frozenset()
) -> bool:
    for decorator in func.decorator_list:
        if _decorator_terminal_name(decorator=decorator) in _RAILWAY_LIFTING_DECORATORS:
            return True
    if func.returns is None:
        return False
    head = _annotation_head_name(annotation=func.returns)
    return head in _RESULT_NAMES or head in railway_aliases


def _returns_named(*, func: ast.FunctionDef | ast.AsyncFunctionDef, name: str) -> bool:
    """True iff `func`'s return annotation's terminal name is `name`."""
    if func.returns is None:
        return False
    return _annotation_head_name(annotation=func.returns) == name


def _is_exempt_supervisor(
    *,
    func: ast.FunctionDef | ast.AsyncFunctionDef,
    rel_path: Path,
    commands_trees: tuple[Path, ...],
    supervisor_entry_files: tuple[Path, ...] = (),
) -> bool:
    """True iff the spec exempts `func` from the Result/IOResult return rule.

    Implements `non-functional-requirements.md` verbatim, INCLUDING its
    path scoping — "a supervisor at a deliberate side-effect boundary
    (`main() -> int` in `commands/*.py` and `doctor/run_static.py`, or
    any function returning `None`) ... OR the `build_parser() ->
    ArgumentParser` factory in `commands/**.py`".

    The scoping is load-bearing, not decoration: a flat-layout repo that
    declares no commands tree gets NO `main()` exemption, because the
    spec grants it to a LOCATION, not to a name. Exempting every `main`
    everywhere would be a reading of intent, not the stated rule.

    MEMBER 4, ratified in livespec v177: a supervisor entry point in a file
    the consumer DECLARES in `supervisor_entry_files`. It admits the SAME
    category as the `commands/` members through a per-file declaration rather
    than a directory glob, because a flat-layout consumer cannot satisfy a
    LOCATION scoping at all — its process entry points sit beside its ordinary
    modules. Four other checks (`no_except_outside_io`, `no_write_direct`,
    `supervisor_discipline`, `partition_completeness`) already act on this same
    declaration; this check was the only consumer of the supervisor concept
    that never asked the repo.

    The declaration is STRICTER than the glob it complements: `commands/*.py`
    exempts every present and future file in that directory with nobody
    deciding anything, whereas an undeclared file gets NOTHING here. And it is
    BOUNDED — it exempts the supervisor ENTRY POINTS in a declared file, never
    every function in it.

    Deliberately absent: `make_validator`, `get_logger`, `compile_schema`,
    `rop_pipeline`. This module's docstring cites them to an
    `archive/brainstorming/` document, which the repo's own convention
    makes reference-only; they appear nowhere in `SPECIFICATION/`.
    """
    if _returns_named(func=func, name="None"):
        return True
    under_commands = any(rel_path.is_relative_to(tree) for tree in commands_trees)
    declared_supervisor = rel_path in supervisor_entry_files
    if func.name == "main" and _returns_named(func=func, name="int"):
        return under_commands or declared_supervisor or rel_path == _DOCTOR_RUN_STATIC
    if func.name == "build_parser" and _returns_named(func=func, name="ArgumentParser"):
        return under_commands or declared_supervisor
    return False


def _is_public_name(*, name: str) -> bool:
    """True iff `name` survives v178 CLAUSE 0 — a leading underscore is DECISIVE.

    Clause 0 of the ratified criterion disqualifies a `_`-prefixed name
    outright, regardless of `__all__` membership or of any consumption
    below it. Consumers legitimately list private helpers in `__all__` so
    their tests may import them; `checks/check_mutation.py` is the
    clearest case — its `__all__` holds six `_`-prefixed helpers and does
    not list `main` at all.

    This is the ONE place `__all__` used to decide publicness and no
    longer does. v178 replaced membership with CONSUMED ACROSS A
    BOUNDARY; `_public_api_consumption` computes that, and clause 0
    remains as a disqualifier layered on top of it.
    """
    return not name.startswith("_")


def _find_offenders(
    *,
    source: str,
    rel_path: Path,
    commands_trees: tuple[Path, ...],
    public_names: frozenset[str],
    no_expected_failure_mode: frozenset[str] = frozenset(),
    supervisor_entry_files: tuple[Path, ...] = (),
) -> list[tuple[int, str]]:
    """Offending top-level functions in `source`, given this file's PUBLIC names.

    `public_names` is the v178 answer for THIS file — computed by
    `_public_api_consumption` from the repo's own consumption graph and the
    consumer's `cross_repo_public_api` declaration. It replaces the
    `__all__`-membership proxy, which was false for this repo at scale: 25 of
    31 reported offenders were `__all__` members no boundary ever crossed.

    `no_expected_failure_mode` is the v179 MEMBER 1 answer for this file, from
    `_no_expected_failure_mode`. v178 scoped WHICH functions are public; v179
    scopes which of them the rule reaches at all — a function with no expected
    failure mode has nothing to flow, and a `Result` over it carries an
    uninhabited failure track whose dead unwraps hide the live ones. Read the
    two scopings together: they are the second and third narrowings of "every
    public function" in as many revisions.
    """
    tree = ast.parse(source)
    railway_aliases = _railway_aliases(tree=tree)
    out: list[tuple[int, str]] = []
    for node in tree.body:
        if (
            isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
            and node.name in public_names
            and node.name not in no_expected_failure_mode
            and _is_public_name(name=node.name)
            and not _is_railway_compliant(func=node, railway_aliases=railway_aliases)
            and not _is_exempt_supervisor(
                func=node,
                rel_path=rel_path,
                commands_trees=commands_trees,
                supervisor_entry_files=supervisor_entry_files,
            )
        ):
            out.append((node.lineno, node.name))
    return out


def _scan(
    *,
    cwd: Path,
    pure_trees: tuple[Path, ...],
    config: Config,
    sources: Mapping[Path, str],
) -> list[tuple[Path, int, str]]:
    """Offenders across the scanned trees, given the repo's consumption universe.

    Two universes meet here and they are NOT the same set. The SCANNED universe
    is `pure_trees`; the CONSUMPTION universe is `sources`, the git-derived
    first-party set. A consumer of a pure-layer function generally lives
    outside the pure layer, so deriving consumption from the scanned trees
    alone would miss most of it — and missing consumption is the RELAXING
    direction.
    """
    public = repo_local_public_names(sources=sources) | declared_public_names(
        declared=config.cross_repo_public_api, sources=sources
    )
    # v179 member 1, recomputed here on EVERY run rather than declared. Its
    # universe is the same git-derived set as the consumption graph's, because
    # clause (d)'s fixpoint walks the whole call graph — a callee outside the
    # analysed set is doubt, and doubt disqualifies.
    total = functions_without_expected_failure_mode(sources=sources, io_trees=config.io_trees)
    # v179 MEMBER 2, DECLARED rather than computed, unioned with member 1's computed
    # set. The two are DISJOINT BY CONSTRUCTION — member 1's clause (e) refuses
    # every `X | None`, and that is the only shape bound 1 admits — so the union
    # adds exactly the declared absences, cannot let a declaration mask a member-1
    # result, and cannot let a member-1 result launder an invalid declaration. An
    # entry that FAILS bound 1 or bound 3 contributes nothing here; it fails the
    # check outright in `main()`.
    total |= declared_absence_names(declared=config.total_absence_returns, sources=sources)
    offenders: list[tuple[Path, int, str]] = []
    for tree_rel in pure_trees:
        for py_file in iter_py_files(root=cwd / tree_rel):
            if py_file.name.startswith("_"):
                continue
            rel_path = py_file.relative_to(cwd)
            for lineno, name in _find_offenders(
                source=py_file.read_text(encoding="utf-8"),
                rel_path=rel_path,
                commands_trees=config.commands_trees,
                public_names=frozenset(n for p, n in public if p == rel_path),
                no_expected_failure_mode=frozenset(n for p, n in total if p == rel_path),
                supervisor_entry_files=config.supervisor_entry_files,
            ):
                offenders.append((rel_path, lineno, name))
    return offenders


def main() -> int:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    log = structlog.get_logger("public_api_result_typed")
    cwd = Path.cwd()
    config = load_config(repo_root=cwd)
    gate_exit = role_absence_exit_code(
        config=config,
        role=config.pure_trees,
        key="pure_trees",
        log=log,
        check_id="public_api_result_typed",
    )
    if gate_exit is not None:
        return gate_exit
    pure_trees = role_trees(role=config.pure_trees)
    if not ensure_declared_paths_contain_python(
        repo_root=cwd,
        key="pure_trees",
        paths=pure_trees,
        log=log,
        check_id="public_api_result_typed",
    ):
        return 1
    root, universe = resolve_check_universe()
    sources = {rel: (root / rel).read_text(encoding="utf-8") for rel in universe}
    stale = stale_declarations(declared=config.cross_repo_public_api, sources=sources)
    if stale:
        for entry in stale:
            log.error(
                "declared cross_repo_public_api entry no longer resolves to a public function",
                file=str(entry.file),
                function=entry.function,
                reason=entry.reason,
            )
        return 1
    rejected = rejected_declarations(declared=config.total_absence_returns, sources=sources)
    if rejected:
        for item in rejected:
            log.error(
                "declared total_absence_returns entry is not a legitimate-absence declaration",
                file=str(item.entry.file),
                function=item.entry.function,
                rejection=item.rejection,
                reason=item.entry.reason,
            )
        return 1
    offenders = _scan(cwd=cwd, pure_trees=pure_trees, config=config, sources=sources)
    if offenders:
        for path, lineno, name in offenders:
            log.error(
                "public function not Result-typed and not railway-lifting-decorated",
                file=str(path),
                line=lineno,
                function=name,
            )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
