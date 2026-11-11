"""Reject test loops whose body coverage depends on ``os.environ``."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.
from returns.pipeline import is_successful  # noqa: E402  — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

from livespec_dev_tooling.checks._config_load import load_config_or_report  # noqa: E402
from livespec_dev_tooling.config import iter_py_files  # noqa: E402

__all__: list[str] = []

CHECK_PURITY = "tree-pure"
_EXIT_VIOLATIONS = 4
_REWRITE = "replace the loop with a single-expression rewrite"


_SCOPE_NODES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def _nodes_in_scope(*, node: ast.AST) -> list[ast.AST]:
    """Return descendants belonging to this scope but not a nested scope."""
    nodes: list[ast.AST] = []
    for child in ast.iter_child_nodes(node):
        if isinstance(child, _SCOPE_NODES):
            continue
        nodes.append(child)
        nodes.extend(_nodes_in_scope(node=child))
    return nodes


def _nested_scopes(*, node: ast.AST) -> list[ast.AST]:
    """Return every function or class scope nested directly in ``node``'s scope."""
    scopes: list[ast.AST] = []
    for child in ast.iter_child_nodes(node):
        if isinstance(child, _SCOPE_NODES):
            scopes.append(child)
        else:
            scopes.extend(_nested_scopes(node=child))
    return scopes


def _imported_names(*, nodes: list[ast.AST]) -> tuple[set[str], set[str]]:
    """Return local names that refer to the ``os`` module or ``os.environ``."""
    os_names: set[str] = set()
    environ_names: set[str] = set()
    for node in nodes:
        if isinstance(node, ast.Import):
            os_names.update(
                alias.asname or alias.name.split(".", maxsplit=1)[0]
                for alias in node.names
                if alias.name == "os" or alias.name.startswith("os.")
            )
        if isinstance(node, ast.ImportFrom) and node.module == "os":
            environ_names.update(
                alias.asname or alias.name for alias in node.names if alias.name == "environ"
            )
    return os_names, environ_names


def _is_environment_value(*, node: ast.AST, os_names: set[str], environ_names: set[str]) -> bool:
    """Whether a value is the environment itself or an allowed copied spelling."""
    if isinstance(node, ast.Name):
        return node.id in environ_names
    if isinstance(node, ast.Attribute):
        return (
            node.attr == "environ"
            and isinstance(node.value, ast.Name)
            and node.value.id in os_names
        )
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        return node.func.attr == "copy" and _is_environment_value(
            node=node.func.value,
            os_names=os_names,
            environ_names=environ_names,
        )
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "dict"
        and len(node.args) == 1
        and _is_environment_value(node=node.args[0], os_names=os_names, environ_names=environ_names)
    )


def _assignment_names(*, node: ast.AST) -> set[str]:
    """Return simple names assigned by one environment-derived assignment."""
    targets: list[ast.expr] = []
    if isinstance(node, ast.Assign):
        targets = node.targets
    if isinstance(node, ast.AnnAssign):
        targets = [node.target]
    return {target.id for target in targets if isinstance(target, ast.Name)}


def _bound_environment_names(
    *, nodes: list[ast.AST], os_names: set[str], environ_names: set[str]
) -> set[str]:
    """Resolve simple environment aliases declared in this one lexical scope."""
    aliases = set(environ_names)
    while True:
        additions: set[str] = set()
        for node in nodes:
            if not isinstance(node, ast.Assign | ast.AnnAssign) or node.value is None:
                continue
            if _is_environment_value(
                node=node.value,
                os_names=os_names,
                environ_names=aliases,
            ):
                additions.update(_assignment_names(node=node))
        if additions.issubset(aliases):
            return aliases
        aliases.update(additions)


def _reads_environment(*, node: ast.AST, os_names: set[str], environ_names: set[str]) -> bool:
    """Whether an iterable expression contains an ambient-environment read."""
    return any(
        _is_environment_value(node=child, os_names=os_names, environ_names=environ_names)
        for child in ast.walk(node)
    )


def _scope_offenders(*, node: ast.AST, os_names: set[str], environ_names: set[str]) -> list[int]:
    """Find loop statements using environment reads in this scope and descendants."""
    nodes = _nodes_in_scope(node=node)
    imported_os, imported_environ = _imported_names(nodes=nodes)
    local_os_names = os_names | imported_os
    local_environ_names = _bound_environment_names(
        nodes=nodes,
        os_names=local_os_names,
        environ_names=environ_names | imported_environ,
    )
    offenders = [
        loop.lineno
        for loop in nodes
        if isinstance(loop, ast.For | ast.AsyncFor)
        and _reads_environment(
            node=loop.iter,
            os_names=local_os_names,
            environ_names=local_environ_names,
        )
    ]
    return offenders + [
        line
        for scope in _nested_scopes(node=node)
        for line in _scope_offenders(
            node=scope,
            os_names=local_os_names,
            environ_names=environ_names | imported_environ,
        )
    ]


def _find_offenders(*, source: str) -> list[int]:
    """Return the lines of ``for`` statements that read the ambient environment."""
    return _scope_offenders(node=ast.parse(source), os_names=set(), environ_names=set())


def _configure_logger() -> structlog.stdlib.BoundLogger:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    return structlog.get_logger("no_ambient_environment_loops")


def main() -> int:
    """Report every test loop that reads the ambient environment."""
    log = _configure_logger()
    root = Path.cwd()
    loaded = load_config_or_report(
        repo_root=root,
        log=log,
        check_id="no_ambient_environment_loops",
    )
    if not is_successful(loaded):
        return 1
    config = unsafe_perform_io(loaded.unwrap())
    tests_root = root / config.tests_tree_prefix
    findings = [
        (path.relative_to(root), lineno)
        for path in iter_py_files(root=tests_root)
        for lineno in _find_offenders(source=path.read_text(encoding="utf-8"))
    ]
    for path, lineno in findings:
        log.error(
            "ambient environment loop makes test coverage host-dependent",
            file=str(path),
            line=lineno,
            rewrite=_REWRITE,
        )
    return _EXIT_VIOLATIONS if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
