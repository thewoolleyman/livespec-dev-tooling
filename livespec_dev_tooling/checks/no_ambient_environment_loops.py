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


def _is_os_environ(*, node: ast.AST) -> bool:
    """Whether ``node`` is the direct ``os.environ`` spelling."""
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "environ"
        and isinstance(node.value, ast.Name)
        and node.value.id == "os"
    )


def _find_offenders(*, source: str) -> list[int]:
    """Return the lines of loop forms that read the direct environment spelling."""
    offenders: list[int] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.For | ast.AsyncFor | ast.comprehension):
            continue
        if any(_is_os_environ(node=child) for child in ast.walk(node.iter)):
            line = node.lineno if isinstance(node, ast.For | ast.AsyncFor) else node.iter.lineno
            offenders.append(line)
    return offenders


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
