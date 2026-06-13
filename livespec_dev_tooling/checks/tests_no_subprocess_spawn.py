"""tests_no_subprocess_spawn — flag test-spawned Python subprocesses in `tests/`.

Defense-in-depth + perf guard (epic 7us, work-item
livespec-dev-tooling-4i5). Walks every `.py` under the consumer's
`tests/` tree and flags Python subprocess spawns — a
`subprocess.run`/`Popen`/`call`/`check_output`/`check_call` whose argv
list begins with `sys.executable` or a literal `python`/`python3`.

WHY this is forbidden by default:

- CORRECTNESS: a subprocess child run under `pytest --cov` self-
  instruments via the pth-installed `COVERAGE_PROCESS_START` hook and
  writes `.coverage.*` that races concurrent coverage runs under the
  parallel check dispatcher → the flaky "No data to report" failure
  (the 7us.6 bug). An in-process `main()` invocation spawns no
  instrumented child.
- PERF: in-process invocation skips process spawn + venv resolution +
  coverage-subprocess startup — materially faster per test (the
  RGR / `just check` latency epic 7us targets).

The DEFAULT authors are steered to (named in every diagnostic) is the
in-process pattern: `monkeypatch.chdir(tmp_path)` + `capsys` +
`rc = main()`. A check entry point's `main()` reads `Path.cwd()` and
writes structlog JSON to stderr, so a test monkeypatches the cwd to
its fixture root, calls `main()` directly, and asserts on the return
code + captured stderr — no subprocess.

Allowlist: the `subprocess_spawn_allowlist` array under
`[tool.livespec_dev_tooling]` in the consumer's `pyproject.toml` lists
repo-root-relative path prefixes (POSIX separators) that genuinely
need a real subprocess — exercising actual git / commit-refuse-hook /
CLI-binary behavior. An allowlisted test MUST scrub
`COVERAGE_PROCESS_START` (and `COV_CORE_*`) from the child env so the
child does not self-instrument and race. The allowlist is the HONEST
current state, not an endorsement: it shrinks as gratuitous spawns are
converted to in-process `main()` (the deferred 7us conversion
follow-up, tracked separately).

Exit codes:

- `0` — no non-allowlisted spawn found (or no `tests/` tree).
- `1` — one or more non-allowlisted spawns; structured findings on
  stderr, each naming the in-process `main()` alternative.

Output discipline: per spec, `print` (T20) and `sys.stderr.write`
(`check-no-write-direct`) are banned in this package. Diagnostics flow
through structlog (JSON to stderr); the vendored copy under
`livespec_dev_tooling/_vendor/structlog` is added to `sys.path` at
module import time.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

from livespec_dev_tooling.config import (  # noqa: E402
    iter_py_files,
    load_config,
    load_subprocess_spawn_allowlist,
)

__all__: list[str] = []


# The subprocess-spawning call targets we flag: a `subprocess.<fn>(...)`
# or a bare `Popen(...)` / `run(...)` (imported-name) call. The argv
# heuristic below is what actually gates a finding.
_SUBPROCESS_FUNCS = frozenset({"run", "Popen", "call", "check_output", "check_call"})

# A spawn is a *Python* spawn when the first argv element is the running
# interpreter (`sys.executable`) or a literal python binary name.
_PYTHON_BINARY_LITERALS = frozenset({"python", "python3"})

# Named in every diagnostic so authors adopt the default without
# rediscovering it after a flake.
_IN_PROCESS_HINT = (
    "Invoke the CLI entrypoint in-process instead of spawning a child: "
    "`monkeypatch.chdir(tmp_path)` + `capsys`, then `rc = main()` and assert "
    "on rc + the captured stderr. An in-process call spawns no instrumented "
    "child (no COVERAGE_PROCESS_START race) and is materially faster. If the "
    "test genuinely needs a real subprocess (git / commit-refuse-hook / "
    "CLI-binary behavior), add its path prefix to `subprocess_spawn_allowlist` "
    "under [tool.livespec_dev_tooling] in pyproject.toml AND scrub "
    "COVERAGE_PROCESS_START + COV_CORE_* from the child env."
)


def _call_func_name(*, node: ast.Call) -> str | None:
    """Return the called function's terminal name, or None for non-name calls.

    `subprocess.run(...)` → `run`; a bare `run(...)` / `Popen(...)` →
    its name. Anything more exotic (a call on a subscript, etc.) yields
    None and is not treated as a spawn.
    """
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def _argv_first_element(*, node: ast.Call) -> ast.expr | None:
    """Return the first element of the call's argv-list argument, if any.

    The argv is the first positional argument (a list/tuple literal);
    we read element 0 to decide whether the child is a Python process.
    A non-literal first arg (a variable) yields None — see
    `_first_element_is_python`.
    """
    if not node.args:
        return None
    first = node.args[0]
    if isinstance(first, ast.List | ast.Tuple) and first.elts:
        return first.elts[0]
    return None


def _first_element_is_python(*, element: ast.expr) -> bool:
    """True iff the argv's first element is `sys.executable` or a python literal.

    Matches `sys.executable` (attribute access) and the string literals
    `"python"` / `"python3"`. A variable or any other expression is not
    matched — the check is deliberately conservative (it flags the
    egregious, statically-evident pattern, not every conceivable spawn).
    """
    if isinstance(element, ast.Attribute) and element.attr == "executable":
        value = element.value
        if isinstance(value, ast.Name) and value.id == "sys":
            return True
    if isinstance(element, ast.Constant) and isinstance(element.value, str):
        return element.value in _PYTHON_BINARY_LITERALS
    return False


def _find_python_spawns(*, source: str) -> list[int]:
    """Return the line numbers of Python-subprocess spawns in `source`.

    A spawn is a call to one of `_SUBPROCESS_FUNCS` whose first
    positional argument is a list/tuple literal whose element 0 is
    `sys.executable` or a literal `python`/`python3`.
    """
    tree = ast.parse(source)
    lines: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _call_func_name(node=node)
        if name not in _SUBPROCESS_FUNCS:
            continue
        element = _argv_first_element(node=node)
        if element is None:
            continue
        if _first_element_is_python(element=element):
            lines.append(node.lineno)
    return lines


def _is_allowlisted(*, rel_posix: str, allowlist: tuple[str, ...]) -> bool:
    """True iff `rel_posix` starts with any allowlist path prefix."""
    return any(rel_posix.startswith(prefix) for prefix in allowlist)


def main() -> int:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    log = structlog.get_logger("tests_no_subprocess_spawn")
    cwd = Path.cwd()
    config = load_config(repo_root=cwd)
    allowlist = load_subprocess_spawn_allowlist(repo_root=cwd) or ()
    tests_root = cwd / config.tests_tree_prefix
    offenders: list[tuple[str, int]] = []
    for py_file in iter_py_files(root=tests_root):
        rel_posix = py_file.relative_to(cwd).as_posix()
        if _is_allowlisted(rel_posix=rel_posix, allowlist=allowlist):
            continue
        source = py_file.read_text(encoding="utf-8")
        for lineno in _find_python_spawns(source=source):
            offenders.append((rel_posix, lineno))
    if offenders:
        for rel_posix, lineno in offenders:
            log.error(
                "test file spawns a Python subprocess; use the in-process main() pattern",
                check_id="tests_no_subprocess_spawn",
                failure_mode="python_subprocess_spawn",
                file=rel_posix,
                line=lineno,
                hint=_IN_PROCESS_HINT,
                status="fail",
            )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
