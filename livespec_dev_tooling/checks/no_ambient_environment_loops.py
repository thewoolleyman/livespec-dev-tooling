"""no_ambient_environment_loops — fail a test-tree `for` loop over `os.environ`.

Work item livespec-dev-tooling-dpkz32; specified in SPECIFICATION/contracts.md
(the no_ambient_environment_loops check) and
SPECIFICATION/non-functional-requirements.md (environment-independent test
coverage).

A `for` or `async for` statement whose iterable reads `os.environ` runs its
body only when the host process carries a matching variable, so the file's
line coverage depends on the host: the same commit is 100% covered on a
developer host that exports `GIT_*` and short of it in the factory sandbox
that exports none. A single simple statement — an assignment of a
comprehension — has the same coverage everywhere, so every finding names one.

The check walks every `.py` under the consumer's `tests_tree_prefix` and reads
each file's syntax tree. The iterable "reads `os.environ`" when it contains,
anywhere in its expression:

- `os.environ`, or `<alias>.environ` for `import os as <alias>`;
- the name bound by `from os import environ` (or `... as <alias>`);
- a name bound from `os.environ`, `os.environ.copy()` or `dict(os.environ)`
  in the loop's own function scope or at module level. A module-level
  `ENV = os.environ` iterated inside a helper is the ambient pattern this
  check exists to catch; a name bound in a DIFFERENT function's scope is not
  followed (legacy-coordinator-agent ruling, 2026-11-13).

No other indirection is followed. The verdict is a pure function of the
source text: no network, no environment read, and no coverage pragma, marker,
flag, environment variable or severity setting exempts a loop.

Exit codes: `0` — no such loop; `4` — one structured `error` finding per loop
on stderr naming the file, the line and the single-expression rewrite; `1` —
the consumer's `pyproject.toml` could not be parsed (rendered by
`load_config_or_report`).

Output discipline: `print` and `sys.*.write` are banned in this package;
diagnostics flow through the vendored structlog as JSON on stderr.
"""

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

_CHECK_ID = "no_ambient_environment_loops"
_FAIL_EXIT = 4
_SCOPE_NODES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
_PLACEHOLDER = "<expression>"
_MESSAGE = (
    "a loop over os.environ runs its body only on a host carrying a matching "
    "variable, so this file's coverage depends on the host; write it as one "
    "simple statement"
)


def _import_aliases(*, tree: ast.Module) -> tuple[frozenset[str], frozenset[str]]:
    """Return (names bound to the `os` module, names bound to `os.environ`)."""
    os_names = {"os"}
    environ_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            os_names |= {alias.asname or alias.name for alias in node.names if alias.name == "os"}
        elif isinstance(node, ast.ImportFrom) and node.module == "os":
            environ_names |= {
                alias.asname or alias.name for alias in node.names if alias.name == "environ"
            }
    return frozenset(os_names), frozenset(environ_names)


def _is_environ(*, node: ast.AST, os_names: frozenset[str], environ_names: frozenset[str]) -> bool:
    """True iff `node` itself is `os.environ` (through any import alias)."""
    if isinstance(node, ast.Name):
        return node.id in environ_names
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "environ"
        and isinstance(node.value, ast.Name)
        and node.value.id in os_names
    )


def _is_environ_source(
    *, value: ast.expr, os_names: frozenset[str], environ_names: frozenset[str]
) -> bool:
    """True iff `value` is `os.environ`, `os.environ.copy()` or `dict(os.environ)`."""
    if _is_environ(node=value, os_names=os_names, environ_names=environ_names):
        return True
    if not isinstance(value, ast.Call) or value.keywords:
        return False
    func = value.func
    if isinstance(func, ast.Attribute) and func.attr == "copy" and not value.args:
        inner = func.value
    elif isinstance(func, ast.Name) and func.id == "dict" and len(value.args) == 1:
        inner = value.args[0]
    else:
        return False
    return _is_environ(node=inner, os_names=os_names, environ_names=environ_names)


def _scope_members(*, scope: ast.AST) -> list[ast.AST]:
    """Every node belonging to `scope` itself, not to a nested function scope."""
    members: list[ast.AST] = []
    pending = list(ast.iter_child_nodes(scope))
    while pending:
        node = pending.pop()
        members.append(node)
        if not isinstance(node, _SCOPE_NODES):
            pending.extend(ast.iter_child_nodes(node))
    return members


def _bound_names(
    *, members: list[ast.AST], os_names: frozenset[str], environ_names: frozenset[str]
) -> frozenset[str]:
    """Names this scope binds from an `os.environ` source."""
    bound: set[str] = set()
    for node in members:
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        else:
            continue
        if _is_environ_source(value=value, os_names=os_names, environ_names=environ_names):
            bound |= {target.id for target in targets if isinstance(target, ast.Name)}
    return frozenset(bound)


def _reads_environ(
    *, iterable: ast.expr, os_names: frozenset[str], environ_names: frozenset[str]
) -> bool:
    return any(
        _is_environ(node=node, os_names=os_names, environ_names=environ_names)
        for node in ast.walk(iterable)
    )


def _rewrite(*, loop: ast.For | ast.AsyncFor) -> str:
    """The single-expression rewrite of `loop`, as one assignment of a comprehension."""
    body = loop.body
    element = (
        ast.unparse(body[0].value)
        if len(body) == 1 and isinstance(body[0], ast.Expr)
        else _PLACEHOLDER
    )
    keyword = "async for" if isinstance(loop, ast.AsyncFor) else "for"
    return f"_ = [{element} {keyword} {ast.unparse(loop.target)} in {ast.unparse(loop.iter)}]"


def _ambient_loops(*, source: str) -> list[tuple[int, str]]:
    """Return (line, rewrite) for every loop in `source` whose iterable reads os.environ."""
    tree = ast.parse(source)
    os_names, environ_names = _import_aliases(tree=tree)
    scopes = [tree, *(node for node in ast.walk(tree) if isinstance(node, _SCOPE_NODES))]
    module_names = environ_names | _bound_names(
        members=_scope_members(scope=tree), os_names=os_names, environ_names=environ_names
    )
    found: list[tuple[int, str]] = []
    for scope in scopes:
        members = _scope_members(scope=scope)
        names = module_names | _bound_names(
            members=members, os_names=os_names, environ_names=environ_names
        )
        found.extend(
            (node.lineno, _rewrite(loop=node))
            for node in members
            if isinstance(node, ast.For | ast.AsyncFor)
            and _reads_environ(iterable=node.iter, os_names=os_names, environ_names=names)
        )
    return sorted(found)


def main() -> int:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    log = structlog.get_logger(_CHECK_ID)
    cwd = Path.cwd()
    loaded = load_config_or_report(repo_root=cwd, log=log, check_id=_CHECK_ID)
    if not is_successful(loaded):
        return 1
    config = unsafe_perform_io(loaded.unwrap())
    offenders: list[tuple[str, int, str]] = []
    for py_file in iter_py_files(root=cwd / config.tests_tree_prefix):
        rel_posix = py_file.relative_to(cwd).as_posix()
        source = py_file.read_text(encoding="utf-8")
        offenders.extend(
            (rel_posix, line, rewrite) for line, rewrite in _ambient_loops(source=source)
        )
    for rel_posix, line, rewrite in offenders:
        log.error(
            _MESSAGE,
            check_id=_CHECK_ID,
            status="fail",
            failure_mode="ambient_environment_loop",
            file=rel_posix,
            line=line,
            rewrite=rewrite,
        )
    return _FAIL_EXIT if offenders else 0


if __name__ == "__main__":
    raise SystemExit(main())
