"""staged_precheck — refuse a commit's staged lint and type errors in seconds.

The commit-hook workflow check (one of the workflow checks contracts.md
names) that heads a consumer's `check-pre-commit` (work-item
livespec-dev-tooling-nil6v7; the "Hooks and CI" section of
non-functional-requirements.md). The full pre-commit aggregate can take
more than ten minutes to reach a refusal its own lint and type members could
have given in seconds: factory run 01M5QNH88NHN68ST28Y80CZJ48 waited 711 s
for a refusal on three pyright errors in one staged module, then gave up on
a fixable failure. This module runs the
cheapest refusals FIRST, against the staged Python files only.

- ruff lints every staged `.py` file, with `--force-exclude` so the
  repository's own ruff excludes still apply to explicitly named paths.
- pyright type-checks the staged files the repository's pyright
  configuration covers. pyright IGNORES its configured `include`/`exclude`
  for paths named on its command line, so the scope is computed here from
  `[tool.pyright]` in `pyproject.toml` (or `pyrightconfig.json`): a staged
  test outside `include`, or a vendored file under an `exclude`, is never
  judged by a rule set the full aggregate does not apply to it.

The tools write their own output straight to the inherited stdout; both name
each finding's `file:line` and rule. The pre-check refuses nothing the aggregate's lint and
type members would not refuse: it moves those refusals earlier. A commit
that passes proceeds to the full aggregate, which runs exactly as before.

The tools run as `sys.executable -m ruff` / `-m pyright`, from the venv this
module was launched in (`uv run python -m ...`), so no `uv run` re-resolves
an environment inside the hook.

CLI:
    python -m livespec_dev_tooling.workflow_checks.staged_precheck

    Exits 0 when no Python file is staged or every staged file passes;
    exits 4 (check failed) after the tools print their findings, with a
    structured `staged-precheck-refused` finding on stderr.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

# stdlib `tomllib` lands in 3.11; the repo floor is 3.10, so fall back to the
# vendored `tomli` exactly as `config.py` does.
if sys.version_info >= (3, 11):  # pragma: no cover — 3.11 path unused on the 3.10 floor.
    import tomllib as _toml
else:
    import tomli as _toml

__all__: list[str] = ["typecheck_scope"]


def typecheck_scope(*, staged: list[str], include: list[str], exclude: list[str]) -> list[str]:
    """Return the staged paths the type checker's include/exclude covers, in order."""
    return [
        path
        for path in staged
        if _included(path=path, include=include)
        and not any(_excluded(path=path, pattern=pattern) for pattern in exclude)
    ]


def _included(*, path: str, include: list[str]) -> bool:
    for entry in include:
        root = entry.strip("/")
        if root in {"", "."} or path == root or path.startswith(root + "/"):
            return True
    return False


def _excluded(*, path: str, pattern: str) -> bool:
    # `**/x/**` must also match `x/...` at the top level, which fnmatch's
    # `*` (matching `/` too) only does once the leading `**/` is dropped.
    return fnmatch.fnmatch(path, pattern) or (
        pattern.startswith("**/") and fnmatch.fnmatch(path, pattern[3:])
    )


def _pyright_scope(*, root: Path) -> tuple[list[str], list[str]]:
    """Return pyright's (include, exclude), defaulting include to the whole tree."""
    config_json = root / "pyrightconfig.json"
    if config_json.is_file():
        table = cast("dict[str, Any]", json.loads(config_json.read_text(encoding="utf-8")))
    else:
        pyproject = root / "pyproject.toml"
        data: dict[str, Any] = (
            _toml.loads(pyproject.read_text(encoding="utf-8")) if pyproject.is_file() else {}
        )
        table = cast("dict[str, Any]", data.get("tool", {}).get("pyright", {}))
    include = [str(entry) for entry in cast("list[Any]", table.get("include", ["."]))]
    exclude = [str(entry) for entry in cast("list[Any]", table.get("exclude", []))]
    return include, exclude


def _staged_python(*, cwd: Path) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=AM"],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    return [line for line in result.stdout.splitlines() if line.endswith(".py")]


def _run_tool(*, cwd: Path, argv: list[str]) -> int:
    """Run one tool from this venv on the inherited stdout; return its exit code."""
    return subprocess.run(
        [sys.executable, "-m", *argv],
        cwd=str(cwd),
        check=False,
    ).returncode


def _configure_logger() -> structlog.stdlib.BoundLogger:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    return structlog.get_logger("staged_precheck")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Lint the staged Python files and type-check those pyright covers, "
            "refusing in seconds before the pre-commit aggregate starts."
        )
    )
    _ = parser.parse_args()
    log = _configure_logger()
    cwd = Path.cwd()
    staged = _staged_python(cwd=cwd)
    if not staged:
        return 0
    lint_rc = _run_tool(
        cwd=cwd,
        argv=["ruff", "check", "--force-exclude", "--output-format=concise", *staged],
    )
    include, exclude = _pyright_scope(root=cwd)
    typed = typecheck_scope(staged=staged, include=include, exclude=exclude)
    type_rc = _run_tool(cwd=cwd, argv=["pyright", *typed]) if typed else 0
    if lint_rc != 0 or type_rc != 0:
        log.error(
            "staged-file pre-check refused the commit; fix the findings above",
            check_id="staged-precheck-refused",
            staged_count=len(staged),
            typed_count=len(typed),
            lint_exit=lint_rc,
            type_exit=type_rc,
        )
        return 4
    log.info("staged-file pre-check passed", staged_count=len(staged), typed_count=len(typed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
