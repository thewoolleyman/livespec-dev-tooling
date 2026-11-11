"""The static safety decision behind the flake-retry pytest hook.

The pytest hook surface delegates here to decide whether a failing test can be
retried. This module reads a test's import closure without executing it and
fails closed whenever that closure or the complete change set is uncertain.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from livespec_dev_tooling._flake_retry_closure import conftest_chain, module_imports
from livespec_dev_tooling.flake_retry_paths import path_literals

__all__: list[str] = [
    "RETRY_ATTEMPTS",
    "RETRY_DELAY_SECONDS",
    "retry_marker_for",
]

RETRY_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 60
_UNSAFE_NAMES = {"pyproject.toml", "uv.lock", "justfile", "conftest.py"}
_PLUGIN_FILE_NAMES = {"flake_retry.py", Path(__file__).name}


@dataclass(frozen=True, kw_only=True)
class _ModuleFacts:
    """What one parsed source module contributes to any closure that reaches it."""

    imports: frozenset[Path]
    literals: frozenset[str]
    undeterminable_paths: bool


def _module_facts(*, repo_root: Path, path: Path) -> _ModuleFacts | None:
    """Parse one module once and keep its imports and path-bearing literals."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError, UnicodeError):
        return None
    path_component_nodes = {
        id(component)
        for node in ast.walk(tree)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div)
        for component in ast.walk(node)
        if isinstance(component, ast.Constant) and isinstance(component.value, str)
    }
    literals = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
        if id(node) not in path_component_nodes or Path(node.value).suffix
    }
    path_names, path_is_undeterminable = path_literals(tree=tree, repo_root=repo_root)
    return _ModuleFacts(
        imports=frozenset(module_imports(repo_root=repo_root, path=path, tree=tree)),
        literals=frozenset(literals | path_names),
        undeterminable_paths=path_is_undeterminable,
    )


def _closure(
    *, repo_root: Path, test_path: Path, memo: dict[Path, _ModuleFacts | None] | None = None
) -> tuple[set[Path], set[str], bool] | None:
    """Read imports and string literals without executing the test tree.

    `memo` holds each module's parsed facts for the caller's whole collection
    pass, so a module many tests import is parsed once rather than once per
    collected item (livespec-dev-tooling-pprfq2).
    """
    facts_by_path = {} if memo is None else memo
    pending = [test_path, *conftest_chain(repo_root=repo_root, test_path=test_path)]
    modules: set[Path] = set()
    literals: set[str] = set()
    undeterminable_paths = False
    while pending:
        path = pending.pop()
        if path in modules:
            continue
        if path not in facts_by_path:
            facts_by_path[path] = _module_facts(repo_root=repo_root, path=path)
        facts = facts_by_path[path]
        if facts is None:
            return None
        modules.add(path)
        literals.update(facts.literals)
        undeterminable_paths = undeterminable_paths or facts.undeterminable_paths
        pending.extend(facts.imports - modules)
    return modules, literals, undeterminable_paths


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


def retry_marker_for(
    *,
    repo_root: Path,
    test_path: Path,
    change_paths: set[Path],
    memo: dict[Path, _ModuleFacts | None] | None = None,
) -> dict[str, int] | None:
    """Return a rerun marker only when no changed path touches the closure.

    A test file outside `repo_root` cannot be analysed against the repository's
    change set, so it takes the same conservative path as an unanalysable
    closure: no marker, and it fails at once when it fails.
    """
    if not test_path.is_relative_to(repo_root):
        return None
    if any(path.name in _UNSAFE_NAMES or path.name in _PLUGIN_FILE_NAMES for path in change_paths):
        return None
    analyzed = _closure(repo_root=repo_root, test_path=test_path, memo=memo)
    if analyzed is None:
        return None
    modules, literals, undeterminable_paths = analyzed
    if undeterminable_paths:
        return None
    relative_modules = {path.relative_to(repo_root) for path in modules}
    if relative_modules & change_paths or literals & _changed_names(paths=change_paths):
        return None
    return {"reruns": RETRY_ATTEMPTS, "reruns_delay": RETRY_DELAY_SECONDS}
