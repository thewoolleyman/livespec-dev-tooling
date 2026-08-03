"""shell_quality — canonical shell-quality policy gate."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402

from livespec_dev_tooling.checks._justfile_bash_recipes import (  # noqa: E402
    RecipeEvidence,
    ShellRecipe,
    classify_justfile_bash_recipes,
)
from livespec_dev_tooling.shellcheck import (  # noqa: E402
    ShellFinding,
    run_shellcheck,
)

__all__: list[str] = []

_CHECK_ID = "shell-quality"
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


def _recipe_findings(*, repo_root: Path) -> list[_Finding]:
    justfile = repo_root / "justfile"
    if not justfile.is_file():
        return []
    classification = classify_justfile_bash_recipes(
        justfile_text=justfile.read_text(encoding="utf-8")
    )
    findings: list[_Finding] = []
    for recipe in classification.recipes:
        findings.extend(_findings_for_recipe(recipe=recipe))
    return findings


def _findings_for_recipe(*, recipe: ShellRecipe) -> list[_Finding]:
    findings: list[_Finding] = []
    interpolation_line = _interpolation_line(recipe=recipe)
    if interpolation_line is not None:
        findings.append(
            _Finding(
                reason="just-interpolation",
                path=Path("justfile"),
                line=interpolation_line,
                recipe=recipe.name,
            )
        )
    set_line = _first_set_line(recipe=recipe)
    if set_line is not None and _recipe_needs_errexit_rationale(recipe=recipe, set_line=set_line):
        findings.append(
            _Finding(
                reason="missing-errexit-rationale",
                path=Path("justfile"),
                line=set_line.line,
                recipe=recipe.name,
            )
        )
    return findings


def _interpolation_line(*, recipe: ShellRecipe) -> int | None:
    for item in recipe.evidence:
        if "{{" in item.text or "}}" in item.text:
            return item.line
    return None


def _first_set_line(*, recipe: ShellRecipe) -> RecipeEvidence | None:
    for item in recipe.evidence:
        if item.kind == "shell_option" and item.text.startswith("set "):
            return item
    return None


def _recipe_needs_errexit_rationale(*, recipe: ShellRecipe, set_line: RecipeEvidence) -> bool:
    return (
        recipe.shape == "shebang"
        and not _has_errexit(line=set_line.text)
        and not _has_errexit_rationale(recipe=recipe, set_line=set_line)
    )


def _has_errexit_rationale(*, recipe: ShellRecipe, set_line: RecipeEvidence) -> bool:
    candidates = list(recipe.documentation)
    candidates.extend(
        item.text.removeprefix("#").strip()
        for item in recipe.evidence
        if item.kind == "comment" and item.line < set_line.line
    )
    return any(_mentions_errexit(text=item) for item in candidates)


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
            code=finding.code,
            severity=finding.severity,
        )


def main() -> int:
    log = _configure_logger()
    repo_root = Path.cwd()
    findings = _shellcheck_findings(repo_root=repo_root)
    findings.extend(_recipe_findings(repo_root=repo_root))
    exit_codes = {
        False: lambda: 0,
        True: lambda: _EXIT_VIOLATIONS,
    }
    _emit_findings(log=log, findings=findings)
    return exit_codes[bool(findings)]()


if __name__ == "__main__":
    raise SystemExit(main())
