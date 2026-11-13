"""Static repository-path literals collected from test path expressions."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from livespec_dev_tooling._flake_retry_places import repository_root_expressions
from livespec_dev_tooling._flake_retry_scopes import ScopeIndex, index_scopes
from livespec_dev_tooling.flake_retry_divisions import division_operands

__all__: list[str] = ["PathChain", "path_chains", "path_literals"]


@dataclass(frozen=True, kw_only=True)
class PathChain:
    """One path expression: its named paths, its literal segments and its base operand."""

    names: frozenset[str]
    segments: frozenset[str]
    undeterminable: bool
    base: ast.expr
    operand_ids: frozenset[int]


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
