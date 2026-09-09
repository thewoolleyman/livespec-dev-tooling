"""wrapper_shape — `bin/*.py` 5-statement shebang-wrapper shape (except the non-wrapper files).

Per `python-skill-script-style-requirements.md` section "Canonical
target list" (the `check-wrapper-shape` row), every
`.claude-plugin/scripts/bin/*.py` file that is not one of the
consumer's NON-WRAPPER files MUST conform to the 5-statement
shebang-wrapper shape (the shebang is a comment, not a Python
statement, and is not part of the AST body):

    #!/usr/bin/env python3
    \"\"\"Shebang wrapper for <name>. ...\"\"\"

    from _bootstrap import bootstrap

    bootstrap()

    from <fleet-member-package>.<...> import main

    raise SystemExit(main())

The main-import module's top-level package is the OWNING
plugin's distribution package: `livespec` for livespec-core, or
`livespec_<suffix>` for an impl-plugin (e.g.
`livespec_orchestrator_git_jsonl`, `livespec_orchestrator_beads_fabro`). The shared
check runs across every livespec fleet repo via the pin-and-bump
cross-repo mechanism, so it accepts any fleet-member top-level
package, not just the core `livespec.` prefix.

The AST module body has exactly 5 top-level statements (the
docstring counts as an `Expr(Constant(str))`):

1. `Expr(Constant(str))` -- the module docstring.
2. `ImportFrom(module="_bootstrap", names=["bootstrap"])`.
3. `Expr(Call(Name("bootstrap")))` -- the bootstrap call.
4. `ImportFrom(module="livespec(_<suffix>)?.<...>", names=["main"])`.
5. `Raise(exc=Call(Name("SystemExit"), args=[Call(Name("main"))]))`.

Any deviation (extra statements, missing pieces, wrong
order, wrong identifiers) surfaces as a violation. The
shebang line is a comment and isn't part of the AST body.

The NON-WRAPPER set is consumer-declared. `_bootstrap.py` is the
baseline — statement 2 above imports it, so it can never be held
to the shape — and a consumer whose pre-import machinery outgrows
that one module adds the further filenames through the
`bin_non_wrapper_files` key of its `[tool.livespec_dev_tooling]`
block. The declared names are UNIONED with the baseline, never
substituted for it (`config.load_config`), and the exemption is
NAME-scoped to DIRECT CHILDREN of the bin root: a declared name
nested in a subdirectory is not exempted by the bare name match.
Before that key existed the single allowed filename was hardcoded
in this shared, git-pinned package, so a repo needing a second
pre-import module had to wait on a dev-tooling release and a pin
bump — the rigidity that pushed livespec core's currency package
out of `bin/` entirely (epic livespec-c1k9).

Output discipline: per spec, `print` (T20) and
`sys.stderr.write` (`check-no-write-direct`) are banned in
dev-tooling/**. Diagnostics flow through structlog (JSON to
stderr); the vendored copy under `.claude-plugin/scripts/
_vendor/structlog` is added to `sys.path` at module import time.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.
from returns.pipeline import is_successful  # noqa: E402  — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

from livespec_dev_tooling.checks._config_load import load_config_or_report  # noqa: E402
from livespec_dev_tooling.config import (  # noqa: E402
    BIN_WRAPPER_TREE,
    is_bin_wrapper,
)

__all__: list[str] = []

# Per python-skill-script-style-requirements.md:
# the canonical shebang wrapper has exactly five top-level
# statements (docstring → bootstrap import → bootstrap() call →
# main import → SystemExit(main())). This constant names the
# load-bearing count.
_CANONICAL_WRAPPER_STMT_COUNT: int = 5

_CHECK_ID = "wrapper_shape"

# The main-import statement of a canonical wrapper imports `main`
# from the OWNING plugin's package. For livespec-core that package
# is `livespec`; for each impl-plugin it is the plugin's own
# distribution package (`livespec_orchestrator_git_jsonl`, `livespec_orchestrator_beads_fabro`,
# etc.). The shared check runs across every livespec fleet repo via
# the pin-and-bump cross-repo mechanism, so it must accept any
# fleet-member top-level package, not just the core `livespec.`
# prefix. The fleet rule: the top-level package is either the bare
# `livespec` package or a `livespec_<suffix>` package (an underscore
# separator). A lookalike like `livespecfoo.` (no separator) is NOT
# a fleet member and an unrelated module like `os.` is rejected.
_FLEET_MAIN_IMPORT_RE = re.compile(r"^livespec(_[a-z0-9_]+)?\.")


def _is_docstring(*, stmt: ast.stmt) -> bool:
    return (
        isinstance(stmt, ast.Expr)
        and isinstance(stmt.value, ast.Constant)
        and isinstance(stmt.value.value, str)
    )


def _is_bootstrap_import(*, stmt: ast.stmt) -> bool:
    return (
        isinstance(stmt, ast.ImportFrom)
        and stmt.module == "_bootstrap"
        and len(stmt.names) == 1
        and stmt.names[0].name == "bootstrap"
    )


def _is_bootstrap_call(*, stmt: ast.stmt) -> bool:
    if not isinstance(stmt, ast.Expr):
        return False
    call = stmt.value
    return (
        isinstance(call, ast.Call)
        and isinstance(call.func, ast.Name)
        and call.func.id == "bootstrap"
    )


def _is_livespec_main_import(*, stmt: ast.stmt) -> bool:
    return (
        isinstance(stmt, ast.ImportFrom)
        and stmt.module is not None
        and _FLEET_MAIN_IMPORT_RE.match(stmt.module) is not None
        and len(stmt.names) == 1
        and stmt.names[0].name == "main"
    )


def _is_raise_systemexit_main(*, stmt: ast.stmt) -> bool:
    if not (isinstance(stmt, ast.Raise) and isinstance(stmt.exc, ast.Call)):
        return False
    outer = stmt.exc
    return (
        isinstance(outer.func, ast.Name)
        and outer.func.id == "SystemExit"
        and len(outer.args) == 1
        and isinstance(outer.args[0], ast.Call)
        and isinstance(outer.args[0].func, ast.Name)
        and outer.args[0].func.id == "main"
    )


def _is_compliant_wrapper(*, source: str) -> bool:
    tree = ast.parse(source)
    body = tree.body
    if len(body) != _CANONICAL_WRAPPER_STMT_COUNT:
        return False
    return (
        _is_docstring(stmt=body[0])
        and _is_bootstrap_import(stmt=body[1])
        and _is_bootstrap_call(stmt=body[2])
        and _is_livespec_main_import(stmt=body[3])
        and _is_raise_systemexit_main(stmt=body[4])
    )


def main() -> int:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    log = structlog.get_logger("wrapper_shape")
    cwd = Path.cwd()
    loaded = load_config_or_report(repo_root=cwd, log=log, check_id=_CHECK_ID)
    if not is_successful(loaded):
        return 1
    config = unsafe_perform_io(loaded.unwrap())
    bin_root = cwd / BIN_WRAPPER_TREE
    offenders: list[Path] = []
    if bin_root.is_dir():
        for py_file in sorted(bin_root.glob("*.py")):
            rel = py_file.relative_to(cwd)
            # `is_bin_wrapper` is the single wrapper-identity source of
            # truth (shared with `all_declared`): it filters out the
            # consumer's declared non-wrapper files — `_bootstrap.py` by
            # default — so this check governs exactly the wrapper set.
            if not is_bin_wrapper(rel=rel, config=config):
                continue
            source = py_file.read_text(encoding="utf-8")
            if not _is_compliant_wrapper(source=source):
                offenders.append(rel)
    if offenders:
        for path in offenders:
            log.error(
                "bin/*.py wrapper shape deviates from canonical 5-statement form",
                file=str(path),
            )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
