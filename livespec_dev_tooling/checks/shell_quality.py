"""shell_quality — canonical shell-quality policy gate."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402

from livespec_dev_tooling.shellcheck import (  # noqa: E402
    ShellFinding,
    run_shellcheck,
)

__all__: list[str] = []

_CHECK_ID = "shell-quality"
_JUST_ENV = "LIVESPEC_SHELL_QUALITY_CHECK_JUSTFILE"
_EXIT_VIOLATIONS = 1
_SET_WORD_COUNT = 2


@dataclass(frozen=True, kw_only=True)
class _Finding:
    reason: str
    path: Path
    line: int
    recipe: str | None = None
    code: str | None = None
    severity: str | None = None


def _configure_logger() -> structlog.stdlib.BoundLogger:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    return structlog.get_logger("shell_quality")


def _has_errexit(*, line: str) -> bool:
    words = line.split()
    return len(words) >= _SET_WORD_COUNT and words[0] == "set" and "e" in words[1].removeprefix("-")


def _shellcheck_findings(*, repo_root: Path) -> list[_Finding]:
    result = run_shellcheck(repo_root=repo_root).unwrap()
    findings: list[_Finding] = []
    for item in result:
        findings.extend(_finding_for_shellcheck_severity(item=item))
    return findings


def _finding_for_shellcheck_severity(*, item: ShellFinding) -> list[_Finding]:
    finding = _from_shellcheck(item=item)
    findings_by_severity = {
        "error": [finding],
        "warning": [finding],
        "info": [],
        "style": [],
    }
    return findings_by_severity[item.severity]


def _from_shellcheck(*, item: ShellFinding) -> _Finding:
    return _Finding(
        reason="shellcheck-finding",
        path=item.path,
        line=1,
        code=item.code,
        severity=item.severity,
    )


def _flatten_body_line(*, parts: object) -> tuple[str, bool]:
    fragments = cast(list[object], parts)
    text = ""
    interpolated = False
    for part in fragments:
        if isinstance(part, str):
            text += part
        else:
            interpolated = True
            text += "__JUST_INTERPOLATION__"
    return text.strip(), interpolated


def _just_json(*, repo_root: Path) -> Mapping[str, object] | None:
    if not (repo_root / "justfile").is_file():
        return None
    just_binary = cast(str, shutil.which("just"))
    completed = subprocess.run(
        [just_binary, "--dump", "--dump-format", "json"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    return cast(Mapping[str, object], json.loads(completed.stdout))


def _recipe_findings(*, repo_root: Path) -> list[_Finding]:
    payload = _just_json(repo_root=repo_root)
    if payload is None:
        return []
    recipes = cast(Mapping[str, Mapping[str, object]], payload["recipes"])
    findings: list[_Finding] = []
    for recipe in recipes.values():
        findings.extend(_findings_for_recipe(recipe=recipe))
    return findings


def _findings_for_recipe(*, recipe: Mapping[str, object]) -> list[_Finding]:
    name = cast(str, recipe["name"])
    body = cast(list[object], recipe["body"])
    lines = [_flatten_body_line(parts=line) for line in body]
    interpolated = any(flag for _, flag in lines)
    commands = [line for line, _ in lines if line and not line.startswith("#")]
    findings: list[_Finding] = []
    if interpolated:
        findings.append(
            _Finding(reason="just-interpolation", path=Path("justfile"), line=1, recipe=name)
        )
    if (
        cast(bool, recipe["shebang"])
        and commands[0].startswith("set ")
        and not _has_errexit(line=commands[0])
    ):
        findings.append(
            _Finding(
                reason="missing-errexit-rationale",
                path=Path("justfile"),
                line=1,
                recipe=name,
            )
        )
    if len(commands) > 1:
        findings.append(
            _Finding(reason="embedded-shell-program", path=Path("justfile"), line=1, recipe=name)
        )
    return findings


def _emit_findings(*, log: structlog.stdlib.BoundLogger, findings: Sequence[_Finding]) -> None:
    for finding in findings:
        log.error(
            "shell-quality policy violation",
            check_id=_CHECK_ID,
            reason=finding.reason,
            path=str(finding.path),
            line=finding.line,
            recipe=finding.recipe,
            code=finding.code,
            severity=finding.severity,
        )


def main() -> int:
    log = _configure_logger()
    repo_root = Path.cwd()
    findings = _shellcheck_findings(repo_root=repo_root)
    recipe_finders = cast(
        Mapping[bool, list[_Finding]],
        {
            False: [],
            True: _recipe_findings(repo_root=repo_root),
        },
    )
    findings.extend(recipe_finders[bool(os.environ.get(_JUST_ENV))])
    exit_codes = {
        False: lambda: 0,
        True: lambda: _EXIT_VIOLATIONS,
    }
    _emit_findings(log=log, findings=findings)
    return exit_codes[bool(findings)]()


if __name__ == "__main__":
    raise SystemExit(main())
