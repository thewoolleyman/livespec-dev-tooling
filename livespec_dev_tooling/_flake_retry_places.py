"""Repository directories that `__file__`-derived expressions resolve to.

SPECIFICATION non-functional-requirements.md "Untouched-test retry": a path
expression whose base is derived from `__file__` is repository-rooted. When the
base resolves to a directory inside the repository, that directory is a path
the closure names (livespec-dev-tooling-4ai5ao). This module resolves each
expression of one module to its repository-relative path, with `""` for the
repository root.
"""

from __future__ import annotations

import ast
from collections.abc import Callable
from functools import partial
from pathlib import Path

from livespec_dev_tooling._flake_retry_scopes import (
    Scope,
    ScopeIndex,
    binding_scope,
    is_root_name,
)

__all__: list[str] = [
    "is_request_path",
    "repository_places",
    "repository_root_expressions",
    "request_span",
]

_SAME_PATH_FUNCTIONS = frozenset({"Path", "PurePath", "PosixPath", "abspath", "realpath", "str"})
_ROOT_ATTRIBUTES = frozenset({"rootpath", "rootdir"})
_TEST_PATH_ATTRIBUTES = frozenset({"path", "fspath"})
_Resolve = Callable[..., Path | None]


def _called_path(*, call: ast.Call, again: _Resolve) -> Path | None:
    """Resolve `.resolve()`, `dirname(...)` and the constructors that keep a path."""
    func = call.func
    callee = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
    argument = call.args[0] if len(call.args) == 1 else None
    if isinstance(func, ast.Attribute) and callee == "resolve":
        base = again(expression=func.value)
        return None if base is None else base.resolve()
    if argument is None or callee not in _SAME_PATH_FUNCTIONS | {"dirname"}:
        return None
    base = again(expression=argument)
    return base.parent if base is not None and callee == "dirname" else base


def is_request_path(*, attribute: ast.Attribute) -> bool:
    """Say whether an attribute is `request.path`, `request.fspath` or `request.node.path`."""
    owner = attribute.value
    requested = getattr(owner, "id", "") == "request" or (
        isinstance(owner, ast.Attribute)
        and owner.attr == "node"
        and getattr(owner.value, "id", "") == "request"
    )
    return requested and attribute.attr in _TEST_PATH_ATTRIBUTES


def _is_test_module(*, path: Path) -> bool:
    """Say whether pytest collects this file as a test module (`test_*.py` or `*_test.py`)."""
    return path.name.startswith("test_") or path.name.endswith("_test.py")


def request_span(*, path: Path, repo_root: Path) -> str | None:
    """Where a request's test path can lie when read in this module.

    None in a test module, where it is that module's own path. In a
    `conftest.py` it is some test under the conftest's own directory, given
    repository-relative; anywhere else it could be any test, so `""`, the root.
    """
    if _is_test_module(path=path):
        return None
    if path.name != "conftest.py":
        return ""
    relative = path.parent.relative_to(repo_root).as_posix()
    return "" if relative == "." else relative


def _attribute_path(
    *, attribute: ast.Attribute, again: _Resolve, source_path: Path, repo_root: Path
) -> Path | None:
    """Resolve `.parent`, a request's test path and the pytest root attributes.

    `request.path`, `request.fspath` and `request.node.path` resolve to the
    module's own path only in a test module; elsewhere they stay unresolved
    here and the closure reads them as a span (see `request_span`).
    `rootpath`, `rootdir` and `invocation_params.dir` are the repository root.
    """
    owner = attribute.value
    if attribute.attr == "parent":
        base = again(expression=owner)
        return None if base is None else base.parent
    if is_request_path(attribute=attribute):
        return source_path if _is_test_module(path=source_path) else None
    rooted = attribute.attr in _ROOT_ATTRIBUTES or (
        attribute.attr == "dir" and getattr(owner, "attr", "") == "invocation_params"
    )
    return repo_root if rooted else None


def _path_from_file_expression(
    *,
    expression: ast.expr,
    scope: Scope,
    index: ScopeIndex,
    source_path: Path,
    repo_root: Path,
) -> Path | None:
    """Resolve the limited `__file__`-derived forms that name a path in the repository."""
    again = partial(
        _path_from_file_expression,
        scope=scope,
        index=index,
        source_path=source_path,
        repo_root=repo_root,
    )
    if isinstance(expression, ast.Name):
        if expression.id == "__file__":
            return source_path
        return repo_root if is_root_name(name=expression.id, scope=scope, index=index) else None
    if isinstance(expression, ast.Call):
        return _called_path(call=expression, again=again)
    if isinstance(expression, ast.Attribute):
        return _attribute_path(
            attribute=expression, again=again, source_path=source_path, repo_root=repo_root
        )
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


def _relative(*, path: Path, roots: tuple[Path, ...]) -> str | None:
    """The repository-relative directory of a path inside the repository; `""` is the root."""
    for root in roots:
        if path.is_relative_to(root):
            relative = path.relative_to(root).as_posix()
            return "" if relative == "." else relative
    return None


def repository_root_expressions(
    *, source_path: Path, repo_root: Path, index: ScopeIndex
) -> frozenset[int]:
    """The ids of every expression of one module that resolves to the repository root."""
    places = repository_places(source_path=source_path, repo_root=repo_root, index=index)
    return frozenset(key for key, place in places.items() if not place)


def repository_places(*, source_path: Path, repo_root: Path, index: ScopeIndex) -> dict[int, str]:
    """Map each expression that resolves inside the repository to its repository-relative path.

    The repository root itself is `""`. Names bound to the root resolve through
    the module's scopes; any other name is left to the closure's bindings.
    """
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
    roots = (resolved_root, repo_root)
    places: dict[int, str] = {}
    for expression in index.nodes:
        resolved = (
            _path_from_file_expression(
                expression=expression,
                scope=index.scope_of[id(expression)],
                index=index,
                source_path=source_path,
                repo_root=resolved_root,
            )
            if isinstance(expression, ast.expr)
            else None
        )
        place = None if resolved is None else _relative(path=resolved, roots=roots)
        places.update({} if place is None else {id(expression): place})
    return places
