"""shell_quality — canonical shell-quality policy gate."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict, cast

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402
from returns.pipeline import is_successful  # noqa: E402

from livespec_dev_tooling.shellcheck import (  # noqa: E402
    ShellCheckUnavailable,
    ShellFinding,
    run_shellcheck,
)

__all__: list[str] = []

_CHECK_ID = "shell-quality"
_EXIT_VIOLATIONS = 1
_SET_WORD_COUNT = 2
_INTERPOLATION_SENTINEL = "__JUST_INTERPOLATION__"


class _JustSettings(TypedDict, total=False):
    positional_arguments: bool


class _JustRecipe(TypedDict, total=False):
    attributes: list[str]
    body: list[list[object]]
    doc: str | None
    name: str
    parameters: list[object]
    shebang: bool


class _JustDump(TypedDict, total=False):
    recipes: dict[str, _JustRecipe]
    settings: _JustSettings


@dataclass(frozen=True, kw_only=True)
class _Finding:
    reason: str
    path: Path
    line: int
    recipe: str | None = None
    binary_name: str | None = None
    required_version: str | None = None
    remedy: str | None = None
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
    run_result = run_shellcheck(repo_root=repo_root)
    if not is_successful(run_result):
        failure = run_result.failure()
        if isinstance(failure, ShellCheckUnavailable):
            return [_finding_for_shellcheck_unavailable(repo_root=repo_root, failure=failure)]
    shell_findings = run_result.unwrap()
    findings: list[_Finding] = []
    for item in shell_findings:
        findings.extend(_finding_for_shellcheck_severity(item=item))
    return findings


def _finding_for_shellcheck_unavailable(
    *, repo_root: Path, failure: ShellCheckUnavailable
) -> _Finding:
    return _Finding(
        reason="shellcheck-unavailable",
        path=repo_root,
        line=1,
        binary_name=failure.binary_name,
        required_version=failure.required_version,
        remedy=failure.remedy,
    )


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
            text += _INTERPOLATION_SENTINEL
    return text.strip(), interpolated


def _just_dump(*, repo_root: Path) -> _JustDump | None:
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
    parsed = json.loads(completed.stdout)
    return cast(_JustDump, parsed if isinstance(parsed, Mapping) else {})


def _recipe_findings(*, repo_root: Path) -> list[_Finding]:
    payload = _just_dump(repo_root=repo_root)
    if payload is None:
        return []
    findings: list[_Finding] = []
    settings = payload.get("settings", {})
    if settings.get("positional_arguments", False):
        findings.append(
            _Finding(reason="global-positional-arguments", path=Path("justfile"), line=1)
        )
    for recipe in payload.get("recipes", {}).values():
        findings.extend(_findings_for_recipe(recipe=recipe))
    return findings


def findings_for_repo(*, repo_root: Path) -> list[_Finding]:
    findings = _shellcheck_findings(repo_root=repo_root)
    findings.extend(_recipe_findings(repo_root=repo_root))
    return findings


def _findings_for_recipe(*, recipe: _JustRecipe) -> list[_Finding]:
    findings: list[_Finding] = []
    name = recipe.get("name", "")
    body = recipe.get("body", [])
    lines = [_flatten_body_line(parts=line) for line in body]
    if any(flag for _, flag in lines):
        findings.append(
            _Finding(
                reason="just-interpolation",
                path=Path("justfile"),
                line=1,
                recipe=name,
            )
        )
    if _missing_per_recipe_positional_arguments(recipe=recipe):
        findings.append(
            _Finding(
                reason="missing-per-recipe-positional-arguments",
                path=Path("justfile"),
                line=1,
                recipe=name,
            )
        )
    if _missing_errexit_rationale(recipe=recipe, lines=lines):
        findings.append(
            _Finding(
                reason="missing-errexit-rationale",
                path=Path("justfile"),
                line=1,
                recipe=name,
            )
        )
    if _nonconforming_recipe(recipe=recipe, lines=lines):
        findings.append(
            _Finding(
                reason="nonconforming-just-recipe",
                path=Path("justfile"),
                line=1,
                recipe=name,
            )
        )
    return findings


def _missing_per_recipe_positional_arguments(*, recipe: _JustRecipe) -> bool:
    return bool(recipe.get("parameters", [])) and "positional-arguments" not in recipe.get(
        "attributes", []
    )


def _missing_errexit_rationale(*, recipe: _JustRecipe, lines: list[tuple[str, bool]]) -> bool:
    commands = [line for line, _ in lines if _executable_line(line=line)]
    set_lines = [line for line in commands if line.startswith("set ")]
    return bool(
        recipe.get("shebang", False)
        and set_lines
        and not _has_errexit(line=set_lines[0])
        and not _mentions_errexit(text=recipe.get("doc") or "")
    )


def _nonconforming_recipe(*, recipe: _JustRecipe, lines: list[tuple[str, bool]]) -> bool:
    if _documented_no_errexit_deviation(recipe=recipe, lines=lines):
        return False
    commands = [line for line, _ in lines if _executable_line(line=line)]
    return (
        bool(recipe.get("shebang", False))
        or len(commands) > 1
        or any(_has_forbidden_shell_syntax(line=line) for line in commands)
    )


def _documented_no_errexit_deviation(*, recipe: _JustRecipe, lines: list[tuple[str, bool]]) -> bool:
    commands = [line for line, _ in lines if _executable_line(line=line)]
    set_lines = [line for line in commands if line.startswith("set ")]
    return bool(
        recipe.get("shebang", False)
        and set_lines
        and not _has_errexit(line=set_lines[0])
        and _mentions_errexit(text=recipe.get("doc") or "")
    )


def _executable_line(*, line: str) -> bool:
    return bool(line) and not line.startswith("#")


def _has_forbidden_shell_syntax(*, line: str) -> bool:
    return any(token in line for token in ("$(", "`", "|", ">", "<", "&&", "||", ";"))


def _mentions_errexit(*, text: str) -> bool:
    normalized = text.lower()
    return "errexit" in normalized or "-e" in normalized


def _emit_findings(*, log: structlog.stdlib.BoundLogger, findings: Sequence[_Finding]) -> None:
    for finding in findings:
        log.error(
            "shell-quality policy violation",
            check_id=_CHECK_ID,
            reason=finding.reason,
            path=str(finding.path),
            line=finding.line,
            recipe=finding.recipe,
            binary_name=finding.binary_name,
            required_version=finding.required_version,
            remedy=finding.remedy,
            code=finding.code,
            severity=finding.severity,
        )


def main() -> int:
    log = _configure_logger()
    repo_root = Path.cwd()
    findings = findings_for_repo(repo_root=repo_root)
    exit_codes = {
        False: lambda: 0,
        True: lambda: _EXIT_VIOLATIONS,
    }
    _emit_findings(log=log, findings=findings)
    return exit_codes[bool(findings)]()


if __name__ == "__main__":
    raise SystemExit(main())
