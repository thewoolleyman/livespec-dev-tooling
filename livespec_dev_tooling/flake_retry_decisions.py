"""The static safety decision behind the flake-retry pytest hook.

The pytest hook surface delegates here to decide whether a failing test can be
retried. This module reads a test's import closure without executing it and
fails closed whenever that closure or the complete change set is uncertain.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from livespec_dev_tooling._flake_retry_closure import (
    conftest_chain,
    from_import_sources,
    module_imports,
)
from livespec_dev_tooling._flake_retry_parameters import PYTEST_FIXTURES
from livespec_dev_tooling._flake_retry_places import repository_places, request_span
from livespec_dev_tooling._flake_retry_root_terms import DOUBT, Key, RootTerm
from livespec_dev_tooling._flake_retry_roots import module_root_terms, solve_keys
from livespec_dev_tooling._flake_retry_scopes import index_scopes
from livespec_dev_tooling.flake_retry_paths import path_chains
from livespec_dev_tooling.flake_retry_release import version_only_release_change

__all__: list[str] = [
    "RETRY_ATTEMPTS",
    "RETRY_DELAY_SECONDS",
    "retry_marker_for",
    "retry_withheld_reason_for",
    "session_withheld_reason",
]

RETRY_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 60
_UNSAFE_NAMES = {"pyproject.toml", "uv.lock", "justfile", "conftest.py"}
_PLUGIN_FILE_NAMES = {"flake_retry.py", Path(__file__).name}
_ITSELF = frozenset({""})


@dataclass(frozen=True, kw_only=True)
class _ModuleFacts:
    """What one parsed source module contributes to any closure that reaches it.

    A path expression counts only when its base is repository-rooted
    (livespec-dev-tooling-bob7iv). `literals` holds what counts whatever the
    closure; `dependent` holds each path expression whose base is rooted or
    placed only through a binding the closure solves, with the literals it
    then adds and the names it spells under each place it reaches; a span it
    reaches is named whole, and a span at the root is undeterminable.
    `computed` holds each path expression with no literal segment whose base
    is placed only through such a binding: at the root it is undeterminable,
    and in any other repository directory it names that directory
    (livespec-dev-tooling-4ai5ao).
    """

    imports: frozenset[Path]
    literals: frozenset[str]
    undeterminable_paths: bool
    dependent: tuple[tuple[RootTerm, frozenset[str], frozenset[str]], ...]
    computed: tuple[RootTerm, ...]
    bindings: tuple[tuple[Key, RootTerm], ...]
    defined: frozenset[Key]
    requested: frozenset[Key]


def _module_facts(*, repo_root: Path, path: Path) -> _ModuleFacts | None:
    """Parse one module once and keep its imports and path-bearing literals."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError, UnicodeError):
        return None
    index = index_scopes(tree=tree)
    places = repository_places(source_path=path, repo_root=repo_root, index=index)
    roots = frozenset(key for key, place in places.items() if not place)
    chains = path_chains(tree=tree, repo_root=repo_root, index=index, root_expression_ids=roots)
    bindings, base_terms = module_root_terms(
        index=index,
        module=str(path),
        bases=[chain.base for chain in chains],
        import_sources=from_import_sources(nodes=index.nodes, path=path, repo_root=repo_root),
        places=places,
        request_span=request_span(path=path, repo_root=repo_root),
    )
    operand_ids = {operand_id for chain in chains for operand_id in chain.operand_ids}
    path_component_nodes = {
        id(component)
        for node in index.nodes
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div)
        for component in ast.walk(node)
        if isinstance(component, ast.Constant) and isinstance(component.value, str)
    }
    literals = {
        node.value
        for node in index.nodes
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
        if id(node) not in path_component_nodes
        or (Path(node.value).suffix and id(node) not in operand_ids)
    }
    dependent: list[tuple[RootTerm, frozenset[str], frozenset[str]]] = []
    computed: list[RootTerm] = []
    undeterminable = any(chain.undeterminable for chain in chains)
    for chain, term in zip(chains, base_terms, strict=True):
        literals.update(_under(places=term.places, names=chain.names or _ITSELF))
        literals.update(_under(places=term.spans, names=_ITSELF))
        undeterminable = undeterminable or "" in term.spans
        if not chain.names:
            undeterminable = undeterminable or "" in term.places
            computed.extend([term] if term.through else [])
            continue
        literals.update(chain.names | chain.segments if term.rooted else ())
        dependent.extend(
            [(term, chain.names | chain.segments, chain.names)] if term.through else []
        )
    return _ModuleFacts(
        imports=frozenset(module_imports(repo_root=repo_root, path=path, tree=tree)),
        literals=frozenset(literals),
        undeterminable_paths=undeterminable,
        dependent=tuple(dependent),
        computed=tuple(computed),
        bindings=tuple(pair for pair in bindings if pair[1].rooted or pair[1].through),
        defined=frozenset(key for key, _ in bindings if key[0] in {"fixture", "export"}),
        requested=frozenset(
            key
            for term in (*base_terms, *(term for _, term in bindings))
            for key in term.through
            if key[0] in {"request", "export"}
        ),
    )


def _under(*, places: Iterable[str], names: Iterable[str]) -> set[str]:
    """Each name spelled under each repository directory a path base is placed in.

    The root adds nothing a bare name does not already spell; `_ITSELF` names
    the directory itself.
    """
    spelled = list(names)
    return {"/".join(filter(None, (place, name))) for place in places if place for name in spelled}


def _unresolved_terms(*, facts: Iterable[_ModuleFacts]) -> list[tuple[Key, RootTerm]]:
    """A doubt for each fixture request and import that no module of the closure resolves.

    A parameter pytest feeds requests a fixture; an import names a module-level
    binding. When no reached module defines it -- a fixture of an unresolvable
    plugin, a name a module builds dynamically -- its value is unknown, so it
    is rooted, never placed.
    """
    collected = list(facts)
    defined = {key for module in collected for key in module.defined}
    return [
        (key, DOUBT)
        for key in {key for module in collected for key in module.requested}
        if (key[0] == "export" and key not in defined)
        or (
            key[0] == "request"
            and key[1] not in PYTEST_FIXTURES
            and ("fixture", key[1]) not in defined
        )
    ]


def _closure(
    *, repo_root: Path, test_path: Path, memo: dict[Path, _ModuleFacts | None] | None = None
) -> tuple[set[Path], set[str], bool] | None:
    """Read imports and string literals without executing the test tree.

    `memo` holds each module's parsed facts for the caller's whole collection
    pass, so a module many tests import is parsed once rather than once per
    collected item (livespec-dev-tooling-pprfq2). A path expression whose base
    is rooted only through a binding, fixture or attribute store counts when
    the closure's bindings, solved together, root it.
    """
    facts_by_path = {} if memo is None else memo
    pending = [test_path, *conftest_chain(repo_root=repo_root, test_path=test_path)]
    reached: dict[Path, _ModuleFacts] = {}
    while pending:
        path = pending.pop()
        if path in reached:
            continue
        if path not in facts_by_path:
            facts_by_path[path] = _module_facts(repo_root=repo_root, path=path)
        facts = facts_by_path[path]
        if facts is None:
            return None
        reached[path] = facts
        pending.extend(facts.imports - reached.keys())
    literals = {literal for facts in reached.values() for literal in facts.literals}
    dependent = [pair for facts in reached.values() for pair in facts.dependent]
    computed = [term for facts in reached.values() for term in facts.computed]
    undeterminable = any(facts.undeterminable_paths for facts in reached.values())
    if (dependent or computed) and not undeterminable:
        bindings = [pair for facts in reached.values() for pair in facts.bindings]
        bindings.extend(_unresolved_terms(facts=reached.values()))
        rooted, placed, spanned = solve_keys(
            terms=bindings,
            rooted_queries=(
                key
                for term in (*computed, *(term for term, _, _ in dependent))
                for key in term.through
            ),
            placed_queries=(
                key
                for term in (*computed, *(term for term, _, _ in dependent))
                for key in term.evidence
            ),
        )
        literals.update(
            name for term, names, _ in dependent if term.through & rooted for name in names
        )
        for term, _, spelled in dependent:
            term_places = {place for key in term.evidence for place in placed.get(key, ())}
            literals.update(_under(places=term_places, names=spelled))
        computed_places = [
            {place for key in term.evidence for place in placed.get(key, ())} for term in computed
        ]
        reached_spans = [
            {span for key in term.through for span in spanned.get(key, ())}
            for term in (*computed, *(term for term, _, _ in dependent))
        ]
        undeterminable = any("" in places for places in (*computed_places, *reached_spans))
        literals.update(
            name
            for places in (*computed_places, *reached_spans)
            for name in _under(places=places, names=_ITSELF)
        )
    return set(reached), literals, undeterminable


def _changed_names(*, paths: set[Path]) -> set[str]:
    """Produce whole literal spellings that can identify changed code or data paths.

    A literal may name the changed file, its filename, or an entire directory
    prefix. Individual directory components are deliberately not candidates:
    a common name such as ``livespec_dev_tooling`` is not a path to every
    directory that happens to contain that segment.
    """
    names: set[str] = set()
    for path in paths:
        names.update((path.as_posix(), path.name))
        names.update(parent.as_posix() for parent in path.parents if parent != Path())
        if path.suffix == ".py":
            names.add(".".join(path.with_suffix("").parts))
    return names


def _unsafe_change_reason(*, repo_root: Path, change_paths: set[Path]) -> str | None:
    """Name an unsafe whole-session change unless it is release metadata only."""
    unsafe = {
        path
        for path in change_paths
        if path.name in _UNSAFE_NAMES or path.name in _PLUGIN_FILE_NAMES
    }
    if not unsafe:
        return None
    release_paths = {Path("pyproject.toml"), Path("uv.lock")}
    if unsafe <= release_paths and version_only_release_change(
        repo_root=repo_root, change_paths=change_paths
    ):
        return None
    if unsafe & release_paths:
        return "a non-version-only pyproject.toml or uv.lock change"
    if any(path.name == "justfile" for path in unsafe):
        return "a justfile change"
    if any(path.name == "conftest.py" for path in unsafe):
        return "a conftest.py change"
    return "a flake-retry plugin change"


def retry_withheld_reason_for(
    *,
    repo_root: Path,
    test_path: Path,
    memo: dict[Path, _ModuleFacts | None],
    change_paths: set[Path] | None = None,
) -> str | None:
    """Name the closure evidence that makes this test itself count as touched."""
    if not test_path.is_relative_to(repo_root):
        return None
    analyzed = _closure(repo_root=repo_root, test_path=test_path, memo=memo)
    if analyzed is None:
        return "an unparseable closure module"
    if analyzed[2]:
        return "an indeterminable path in a closure module"
    if change_paths is None:
        return None
    modules, literals, _ = analyzed
    changed_modules = {path.relative_to(repo_root) for path in modules} & change_paths
    if changed_modules:
        return f"changed closure module {min(changed_modules).as_posix()}"
    named_literals = literals & _changed_names(paths=change_paths)
    return f"closure string literal {min(named_literals)!r}" if named_literals else None


def session_withheld_reason(
    *,
    repo_root: Path,
    test_paths: Iterable[Path],
    change_paths: set[Path],
    memo: dict[Path, _ModuleFacts | None],
) -> str | None:
    """Return the one whole-session reason that must withhold every retry."""
    del test_paths, memo
    unsafe = _unsafe_change_reason(repo_root=repo_root, change_paths=change_paths)
    return unsafe


def retry_marker_for(
    *,
    repo_root: Path,
    test_path: Path,
    change_paths: set[Path],
    memo: dict[Path, _ModuleFacts | None] | None = None,
    retry_attempts: int = RETRY_ATTEMPTS,
    retry_delay_seconds: int = RETRY_DELAY_SECONDS,
) -> dict[str, int] | None:
    """Return a rerun marker only when no changed path touches the closure.

    A test file outside `repo_root` cannot be analysed against the repository's
    change set, so it takes the same conservative path as an unanalysable
    closure: no marker, and it fails at once when it fails.
    """
    if not test_path.is_relative_to(repo_root):
        return None
    if _unsafe_change_reason(repo_root=repo_root, change_paths=change_paths) is not None:
        return None
    analyzed = _closure(repo_root=repo_root, test_path=test_path, memo=memo)
    if analyzed is None:
        return None
    if (
        retry_withheld_reason_for(
            repo_root=repo_root,
            test_path=test_path,
            memo={} if memo is None else memo,
            change_paths=change_paths,
        )
        is not None
    ):
        return None
    return {"reruns": retry_attempts, "reruns_delay": retry_delay_seconds}
