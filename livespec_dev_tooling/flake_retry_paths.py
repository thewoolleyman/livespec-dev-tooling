"""Static repository-path literals collected from test path expressions."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from livespec_dev_tooling._flake_retry_places import repository_root_expressions
from livespec_dev_tooling._flake_retry_scopes import (
    Scope,
    ScopeIndex,
    binding_scope,
    index_scopes,
    owning_scope,
)
from livespec_dev_tooling.flake_retry_divisions import path_operands

__all__: list[str] = ["PathChain", "path_chains", "path_literals"]


@dataclass(frozen=True, kw_only=True)
class PathChain:
    """One path expression: its named paths, its literal segments and its base operand.

    `ascent` counts the `..` components of its literal segments: the upward
    steps the expression takes from its base.
    """

    names: frozenset[str]
    segments: frozenset[str]
    undeterminable: bool
    base: ast.expr
    operand_ids: frozenset[int]
    ascent: int = 0


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
            and not operands[0].value.startswith("/")
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


def _literal_parts(
    *, expression: ast.expr, scope: Scope, index: ScopeIndex, seen: frozenset[int] = frozenset()
) -> tuple[ast.expr, ...] | None:
    """Expand a name only when its binding is a chain of string literals."""
    parts: tuple[ast.expr, ...] | None = None
    if isinstance(expression, ast.Constant) and isinstance(expression.value, str):
        parts = (expression,)
    elif isinstance(expression, ast.BinOp) and isinstance(expression.op, ast.Div):
        left = _literal_parts(expression=expression.left, scope=scope, index=index, seen=seen)
        right = _literal_parts(expression=expression.right, scope=scope, index=index, seen=seen)
        parts = None if left is None or right is None else (*left, *right)
    elif isinstance(expression, ast.Call):
        callee = (
            expression.func.id
            if isinstance(expression.func, ast.Name)
            else getattr(expression.func, "attr", "")
        )
        if callee in {"Path", "PurePath", "PosixPath", "PurePosixPath"}:
            pieces = [
                _literal_parts(expression=argument, scope=scope, index=index, seen=seen)
                for argument in expression.args
            ]
            parts = (
                tuple(item for piece in pieces if piece is not None for item in piece)
                if pieces and all(piece is not None for piece in pieces)
                else None
            )
    elif isinstance(expression, ast.Name) and id(expression) not in seen:
        owner = owning_scope(name=expression.id, scope=scope, index=index)
        values = (
            []
            if owner is None or owner.parent is not None
            else [
                value
                for targets, value, target_scope in index.assignments
                if binding_scope(name=expression.id, scope=target_scope, index=index) is owner
                if any(
                    isinstance(target, ast.Name) and target.id == expression.id
                    for target in targets
                )
            ]
        )
        if owner is not None and len(values) == 1:
            parts = _literal_parts(
                expression=values[0], scope=owner, index=index, seen=seen | {id(expression)}
            )
    return parts


def _expanded_operands(
    *, operands: tuple[ast.expr, ...], index: ScopeIndex
) -> tuple[ast.expr, ...]:
    """Replace literal-only path-name operands without treating them as dynamic."""
    expanded = [operands[0]]
    for operand in operands[1:]:
        scope = index.scope_of[id(operand)]
        expanded.extend(_literal_parts(expression=operand, scope=scope, index=index) or (operand,))
    return tuple(expanded)


def _forced_undeterminable(*, expression: ast.expr, operands: tuple[ast.expr, ...]) -> bool:
    """Identify path forms whose replacement or interpolation cannot be located exactly."""
    indirect_request = (
        any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "getattr"
            and bool(node.args)
            and getattr(node.args[0], "id", "") == "request"
            for node in ast.walk(expression)
        )
        or any(
            isinstance(node, ast.Attribute)
            and node.attr == "path"
            and isinstance(node.value, ast.Attribute)
            and node.value.attr == "parent"
            and isinstance(node.value.value, ast.Attribute)
            and node.value.value.attr == "node"
            and getattr(node.value.value.value, "id", "") == "request"
            for node in ast.walk(expression)
        )
        or any(
            isinstance(node, ast.Attribute)
            and node.attr == "__file__"
            and isinstance(node.value, ast.Attribute)
            and node.value.attr == "module"
            and getattr(node.value.value, "id", "") == "request"
            for node in ast.walk(expression)
        )
    )
    if indirect_request:
        return True
    if not isinstance(expression, ast.Call):
        return False
    callee = (
        expression.func.id
        if isinstance(expression.func, ast.Name)
        else getattr(expression.func, "attr", "")
    )
    if callee == "with_name":
        return False
    if callee == "join":
        return any(not isinstance(operand, ast.Constant) for operand in operands[1:])
    return bool(expression.args and isinstance(expression.args[0], ast.JoinedStr))


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
    nested_paths = {
        id(child)
        for node in scope_index.nodes
        if isinstance(node, ast.expr)
        if path_operands(expression=node) is not None
        for child in ast.iter_child_nodes(node)
        if isinstance(child, ast.expr) and path_operands(expression=child) is not None
    }
    chains: list[PathChain] = []
    for node in scope_index.nodes:
        if not isinstance(node, ast.expr) or id(node) in nested_paths:
            continue
        found_operands = path_operands(expression=node)
        if found_operands is None:
            continue
        operands = _expanded_operands(operands=found_operands, index=scope_index)
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
                undeterminable=undeterminable
                or _forced_undeterminable(expression=node, operands=operands),
                base=operands[0],
                operand_ids=frozenset(id(operand) for operand in operands),
                ascent=sum(
                    str(getattr(operand, "value", "")).split("/").count("..")
                    for operand in operands[1:]
                    if isinstance(operand, ast.Constant)
                ),
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
