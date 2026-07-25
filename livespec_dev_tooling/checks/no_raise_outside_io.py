"""no_raise_outside_io — domain-error raises confined to `io/**` and `errors.py`.

Per `python-skill-script-style-requirements.md` §"Canonical
target list" (the `check-no-raise-outside-io` row), raising
of `LivespecError` subclasses (domain errors) at runtime is
restricted to `livespec/io/**` and `livespec/errors.py`.
Pure layers (parse/, validate/, commands/, doctor/, schemas/)
return `Failure(LivespecError(...))` on the ROP railway
instead. Bug-class exceptions (TypeError, ValueError,
NotImplementedError, AssertionError, etc.) are permitted
anywhere — they propagate to the supervisor's bug-catcher.

The known domain-error class names that count as
`LivespecError` subclasses (the closed hierarchy enumerated
by `errors.py`'s `__all__`): `LivespecError`, `UsageError`,
`PreconditionError`, `ValidationError`. Subsequent additions
to the hierarchy widen this set as consumer pressure surfaces
new failure categories.

The check walks every `.py` file under `.claude-plugin/
scripts/livespec/`, parses each via `ast`, and inspects every
`Raise` node whose exception unparses to one of the
domain-error names (or a parameterized call thereof). Files
under `io/` and the single `errors.py` file are exempt; with
`io_trees` unset nothing is exempt and every source file is
inspected.

Output discipline: per spec, `print` (T20) and
`sys.stderr.write` (`check-no-write-direct`) are banned in
dev-tooling/**. Diagnostics flow through structlog (JSON to
stderr); the vendored copy under `.claude-plugin/scripts/
_vendor/structlog` is added to `sys.path` at module import time.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

from livespec_dev_tooling.checks._role_key_gate import source_trees_exit_code  # noqa: E402
from livespec_dev_tooling.config import Config, iter_py_files, load_config  # noqa: E402

__all__: list[str] = []


_DOMAIN_ERROR_NAMES = frozenset(
    {"LivespecError", "UsageError", "PreconditionError", "ValidationError"}
)


def _is_exempt(*, rel_path: Path, config: Config) -> bool:
    # `errors.py` is the canonical domain-error home in livespec-core's
    # layout: the file sitting directly under the (single) io-parent tree.
    for io_tree in config.io_trees:
        if rel_path == io_tree.parent / "errors.py":
            return True
        if io_tree in rel_path.parents:
            return True
    return False


def _find_domain_raises(*, source: str) -> list[tuple[int, str]]:
    tree = ast.parse(source)
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Raise) or node.exc is None:
            continue
        rendered = ast.unparse(node.exc)
        head = rendered.split("(", maxsplit=1)[0]
        if head in _DOMAIN_ERROR_NAMES:
            out.append((node.lineno, head))
    return out


def main() -> int:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    log = structlog.get_logger("no_raise_outside_io")
    cwd = Path.cwd()
    config = load_config(repo_root=cwd)
    gate_exit = source_trees_exit_code(
        config=config, repo_root=cwd, log=log, check_id="no_raise_outside_io"
    )
    if gate_exit is not None:
        return gate_exit
    offenders: list[tuple[Path, int, str]] = []
    inspected = 0
    for tree_rel in config.source_trees:
        for py_file in iter_py_files(root=cwd / tree_rel):
            rel = py_file.relative_to(cwd)
            if _is_exempt(rel_path=rel, config=config):
                continue
            inspected += 1
            source = py_file.read_text(encoding="utf-8")
            for lineno, error_name in _find_domain_raises(source=source):
                offenders.append((rel, lineno, error_name))
    # An inspected count of zero otherwise reads exactly like a clean pass, so
    # it is reported on every run rather than inferred from silence.
    log.info(
        "inspection complete",
        check_id="no_raise_outside_io",
        files_inspected=inspected,
        offenses=len(offenders),
    )
    if offenders:
        for path, lineno, error_name in offenders:
            log.error(
                "domain-error raise outside `io/`/`errors.py` is banned",
                file=str(path),
                line=lineno,
                error=error_name,
            )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
