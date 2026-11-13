"""Static repository-path literals collected from test path expressions."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from functools import partial
from pathlib import Path, PurePosixPath

from livespec_dev_tooling._flake_retry_scopes import (
    Scope,
    ScopeIndex,
    binding_scope,
    index_scopes,
    is_root_name,
)
from livespec_dev_tooling.flake_retry_divisions import division_operands

__all__: list[str] = ["PathChain", "path_chains", "path_literals", "repository_root_expressions"]


@dataclass(frozen=True, kw_only=True)
class PathChain:
    """One path expression: its named paths, its literal segments and its base operand."""

    names: frozenset[str]
    segments: frozenset[str]
    undeterminable: bool
    base: ast.expr
    operand_ids: frozenset[int]


def _path_from_file_expression(
    *,
    expression: ast.expr,
    scope: Scope,
    index: ScopeIndex,
    source_path: Path,
    repo_root: Path,
) -> Path | None:
    """Resolve the limited ``Path(__file__)`` forms that can bind the repository root."""
    again = partial(
        _path_from_file_expression,
        scope=scope,
        index=index,
        source_path=source_path,
        repo_root=repo_root,
    )
    if isinstance(expression, ast.Name):
        return repo_root if is_root_name(name=expression.id, scope=scope, index=index) else None
    if (
        isinstance(expression, ast.Call)
        and isinstance(expression.func, ast.Name)
        and expression.func.id == "Path"
        and len(expression.args) == 1
        and isinstance(expression.args[0], ast.Name)
        and expression.args[0].id == "__file__"
    ):
        return source_path
    if (
        isinstance(expression, ast.Call)
        and isinstance(expression.func, ast.Attribute)
        and expression.func.attr == "resolve"
    ):
        base = again(expression=expression.func.value)
        return None if base is None else base.resolve()
    if isinstance(expression, ast.Attribute) and expression.attr == "parent":
        base = again(expression=expression.value)
        return None if base is None else base.parent
    if (
        isinstance(expression, ast.Subscript)
        and isinstance(expression.value, ast.Attribute)
        and expression.value.attr == "parents"
        and isinstance(expression.slice, ast.Constant)
        and isinstance(expression.slice.value, int)
        and not isinstance(expression.slice.value, bool)
    ):
        base = again(expression=expression.value.value)
        position = expression.slice.value
        if base is not None and 0 <= position < len(base.parents):
            return base.parents[position]
    return None


def _repository_root_context(
    *, source_path: Path | None, repo_root: Path | None, index: ScopeIndex
) -> frozenset[int] | None:
    """Find expressions statically bound to this module's repository root.

    Returns None when the module's location is unknown, so no expression can be
    shown to be anything other than a repository path.
    """
    if source_path is None or repo_root is None:
        return None
    return repository_root_expressions(source_path=source_path, repo_root=repo_root, index=index)


def repository_root_expressions(
    *, source_path: Path, repo_root: Path, index: ScopeIndex
) -> frozenset[int]:
    """The ids of every expression of one module that resolves to the repository root."""
    resolved_root = repo_root.resolve()
    changed = True
    while changed:
        changed = False
        for targets, value, scope in index.assignments:
            resolved = _path_from_file_expression(
                expression=value,
                scope=scope,
                index=index,
                source_path=source_path,
                repo_root=resolved_root,
            )
            if resolved != resolved_root:
                continue
            for target in targets:
                if not isinstance(target, ast.Name):
                    continue
                target_scope = binding_scope(name=target.id, scope=scope, index=index)
                target_scope.bound.add(target.id)
                if target.id not in target_scope.roots:
                    target_scope.roots.add(target.id)
                    changed = True
    return frozenset(
        id(expression)
        for expression in index.nodes
        if isinstance(expression, ast.expr)
        and _path_from_file_expression(
            expression=expression,
            scope=index.scope_of[id(expression)],
            index=index,
            source_path=source_path,
            repo_root=resolved_root,
        )
        == resolved_root
    )


def _path_names(
    *,
    operands: tuple[ast.expr, ...],
    repo_root: Path | None,
    repository_root_expression_ids: frozenset[int] | None,
) -> tuple[set[str], bool]:
    """Name the paths one division chain spells, and whether a segment is unknowable.

    A chain with no string literal names nothing; it is undeterminable only when
    its base is the repository root, because a computed segment under the root
    names a repository path no literal of the closure spells
    (livespec-dev-tooling-4ai5ao).
    """
    has_literal = any(
        isinstance(operand, ast.Constant) and isinstance(operand.value, str) and operand.value
        for operand in operands
    )
    if not has_literal:
        rooted_base = (
            repository_root_expression_ids is not None
            and id(operands[0]) in repository_root_expression_ids
        )
        return set(), rooted_base
    segments: list[str] = []
    undeterminable = False
    dynamic_segments_are_undeterminable = (
        repository_root_expression_ids is None
        or (
            isinstance(operands[0], ast.Constant)
            and bool(operands[0].value)
            and isinstance(operands[0].value, str)
        )
        or (id(operands[0]) in repository_root_expression_ids)
    )
    for position, operand in enumerate(operands):
        if isinstance(operand, ast.Constant) and isinstance(operand.value, str) and operand.value:
            segments.append(operand.value)
        elif position > 0 and dynamic_segments_are_undeterminable:
            undeterminable = True
    paths = {named_path := "/".join(segments)}
    if repo_root is not None and (repo_root / named_path).is_dir():
        return paths, undeterminable
    if "/" in named_path:
        paths.add(named_path.rsplit("/", maxsplit=1)[0])
    final = operands[-1]
    if (
        isinstance(final, ast.Constant)
        and isinstance(final.value, str)
        and not PurePosixPath(final.value).suffix
    ):
        paths.add(final.value)
    return paths, undeterminable


def path_chains(
    *,
    tree: ast.AST,
    repo_root: Path | None = None,
    source_path: Path | None = None,
    index: ScopeIndex | None = None,
    root_expression_ids: frozenset[int] | None = None,
) -> tuple[PathChain, ...]:
    """Every outermost path expression with what it names and whether it is undeterminable.

    `root_expression_ids`, when given, are the module's repository-root
    expressions already found; otherwise they are found from `source_path`.
    """
    scope_index = index_scopes(tree=tree) if index is None else index
    if root_expression_ids is None:
        root_expression_ids = _repository_root_context(
            source_path=source_path, repo_root=repo_root, index=scope_index
        )
    nested_divisions = {
        id(child)
        for node in scope_index.nodes
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div)
        for child in (node.left, node.right)
        if isinstance(child, ast.BinOp) and isinstance(child.op, ast.Div)
    }
    chains: list[PathChain] = []
    for node in scope_index.nodes:
        if (
            not isinstance(node, ast.BinOp)
            or not isinstance(node.op, ast.Div)
            or id(node) in nested_divisions
        ):
            continue
        operands = division_operands(expression=node)
        names, undeterminable = _path_names(
            operands=operands,
            repo_root=repo_root,
            repository_root_expression_ids=root_expression_ids,
        )
        segments = {
            operand.value
            for operand in operands
            if isinstance(operand, ast.Constant)
            and isinstance(operand.value, str)
            and PurePosixPath(operand.value).suffix
        }
        chains.append(
            PathChain(
                names=frozenset(names),
                segments=frozenset(segments),
                undeterminable=undeterminable,
                base=operands[0],
                operand_ids=frozenset(id(operand) for operand in operands),
            )
        )
    return tuple(chains)


def path_literals(
    *,
    tree: ast.AST,
    repo_root: Path | None = None,
    source_path: Path | None = None,
) -> tuple[set[str], bool]:
    """Return named literal paths and whether a path segment cannot be resolved."""
    chains = path_chains(tree=tree, repo_root=repo_root, source_path=source_path)
    return (
        {name for chain in chains for name in chain.names},
        any(chain.undeterminable for chain in chains),
    )
