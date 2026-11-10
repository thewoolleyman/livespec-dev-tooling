"""actionlint_workflows — refuse a workflow file GitHub cannot parse.

The commit-hook workflow check (one of the workflow checks contracts.md names;
the "Hooks and CI" section of non-functional-requirements.md, "Workflow files
must parse"). False-green measured 2026-11-03 (work-item
livespec-dev-tooling-f3q7r7): a `release-please.yml` whose job-level `if:` was
an unquoted YAML scalar containing `: ` passed the commit gate, the push gate
and PR CI, then GitHub rejected the file at parse and no release could be cut
until a fix landed. Only actionlint reports that shape — as
`could not parse as YAML: mapping values are not allowed in this context
[syntax-check]` — and no gate ran it.

The check feeds each `.github/workflows/*.yml` / `*.yaml` file to actionlint
and refuses on every finding of kind `syntax-check`, the kind actionlint
raises for a file GitHub cannot parse (invalid YAML, an unknown or missing
key). Every other kind (`expression`, `runner-label`, `shellcheck`, ...) is a
lint opinion about a file GitHub still accepts, and is NOT refused here: this
gate is about a file that would make the whole workflow unrunnable. shellcheck
and pyflakes are switched off, so the verdict does not depend on either tool.

The STAGED workflow files are judged, read from the index
(`git show :<path>`) so the verdict speaks for what the commit will carry, not
for the working tree. This is the pre-commit gate.

actionlint is a pinned toolchain binary (`.mise.toml`). When it is absent, or
exits with anything but "no findings" (0) or "findings" (1), the check cannot
have looked at the files, so it refuses with exit 3 and a remedy; it never
passes blind.

CLI:
    python -m livespec_dev_tooling.workflow_checks.actionlint_workflows

    Exits 0 when no judged workflow file is unparseable; exits 4 with one
    structured `error` event per finding naming `path`, `line` and `message`;
    exits 3 when actionlint is unavailable or cannot run.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

__all__: list[str] = []

_CHECK_ID = "actionlint-workflows"
_EXIT_PRECONDITION = 3
_EXIT_FAILED = 4
_PARSE_KIND = "syntax-check"
_WORKFLOW = re.compile(r"^\.github/workflows/[^/]+\.ya?ml$")
_ACTIONLINT_FLAGS = ("-shellcheck=", "-pyflakes=", "-format", "{{json .}}")
_REMEDY = (
    "install the actionlint pinned in this repository's .mise.toml and expose it on PATH, "
    "for example with `mise install actionlint` from the repository root"
)


def _staged_sources(*, cwd: Path) -> list[tuple[str, bytes]]:
    listing = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=AM"],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    names = [name for name in listing.stdout.splitlines() if _WORKFLOW.match(name)]
    return [
        (
            name,
            subprocess.run(
                ["git", "show", f":{name}"], cwd=str(cwd), capture_output=True, check=False
            ).stdout,
        )
        for name in names
    ]


def _configure_logger() -> structlog.stdlib.BoundLogger:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    return structlog.get_logger("actionlint_workflows")


def _findings(*, binary: str, name: str, source: bytes) -> list[dict[str, Any]] | str:
    """Return actionlint's findings for one file, or why it could not be run."""
    completed = subprocess.run(
        [binary, *_ACTIONLINT_FLAGS, "-stdin-filename", name, "-"],
        input=source,
        capture_output=True,
        check=False,
    )
    stdout = completed.stdout.decode("utf-8", errors="replace")
    stderr = completed.stderr.decode("utf-8", errors="replace")
    if completed.returncode not in {0, 1}:
        return stderr or stdout
    try:
        return cast("list[dict[str, Any]]", json.loads(stdout))
    except json.JSONDecodeError:
        return stderr or stdout


def _refusal_summary(*, name: str, finding: dict[str, Any]) -> str:
    return (
        f"workflow GitHub cannot parse: {name}:{finding['line']}: "
        f"{finding['message']} [{_PARSE_KIND}]"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=("Refuse a staged .github/workflows file actionlint reports as unparseable.")
    )
    _ = parser.parse_args()
    log = _configure_logger()
    binary = shutil.which("actionlint")
    if binary is None:
        log.error(
            "actionlint is not on PATH, so no workflow file could be judged",
            check_id=_CHECK_ID,
            remedy=_REMEDY,
        )
        return _EXIT_PRECONDITION
    cwd = Path.cwd()
    sources = _staged_sources(cwd=cwd)
    refused = 0
    for name, source in sources:
        found = _findings(binary=binary, name=name, source=source)
        if isinstance(found, str):
            log.error(
                "actionlint could not judge a workflow file",
                check_id=_CHECK_ID,
                path=name,
                stderr=found,
                remedy=_REMEDY,
            )
            return _EXIT_PRECONDITION
        for finding in found:
            if finding["kind"] != _PARSE_KIND:
                continue
            refused += 1
            log.error(
                _refusal_summary(name=name, finding=finding),
                check_id=_CHECK_ID,
                path=name,
                line=finding["line"],
                column=finding["column"],
                message=finding["message"],
                kind=finding["kind"],
            )
    if refused:
        return _EXIT_FAILED
    log.info("every judged workflow file parses", check_id=_CHECK_ID, checked=len(sources))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
