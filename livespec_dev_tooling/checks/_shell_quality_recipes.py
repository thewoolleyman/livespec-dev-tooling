"""The shell-quality check's justfile-recipe policy half.

Split from `shell_quality` at the seam between its two independent finding
sources: this module reads the `just --dump` JSON and decides which RECIPES
violate policy, while the check module keeps the ShellCheck-derived findings
and the reporting entry point. Neither half knows anything about the other;
both speak the shared `Finding` record from `_shell_quality_finding`.

The policy itself is unchanged by the split — a recipe is reported for just
interpolation, for taking parameters without the per-recipe
`positional-arguments` attribute, for omitting errexit with no documented
rationale, and for being a non-thin recipe (a shebang body, more than one
command, or shell syntax that belongs in a script rather than a recipe).

Those four rules all judge a recipe's SHAPE. The fifth,
`bash-only-syntax-under-default-sh`, is the only one that asks whether the
conforming line can RUN: see `_shell_quality_bashisms` for the lexicon it reads
and for the shipped defect (`livespec-f3tf`) that proved the shape rules alone
let a recipe die silently on every invocation.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import TypedDict, cast

from livespec_dev_tooling.checks._shell_quality_bashisms import (
    bash_only_constructs,
    shell_is_bash_compatible,
)
from livespec_dev_tooling.checks._shell_quality_finding import Finding

__all__: list[str] = [
    "recipe_findings",
]

_SET_WORD_COUNT = 2
_INTERPOLATION_SENTINEL = "__JUST_INTERPOLATION__"
# `set -e` is matched with boundaries so it cannot fire from inside an
# ordinary hyphenated word; a bare "-e" substring previously could.
_ERREXIT_RATIONALE_PATTERN = re.compile(r"errexit|(?<![\w-])set\s+-e(?![\w-])")


class _JustShell(TypedDict, total=False):
    arguments: list[str]
    command: str


class _JustSettings(TypedDict, total=False):
    positional_arguments: bool
    shell: _JustShell | None


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


def _has_errexit(*, line: str) -> bool:
    words = line.split()
    return len(words) >= _SET_WORD_COUNT and words[0] == "set" and "e" in words[1].removeprefix("-")


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


def recipe_findings(*, repo_root: Path) -> list[Finding]:
    payload = _just_dump(repo_root=repo_root)
    if payload is None:
        return []
    findings: list[Finding] = []
    settings = payload.get("settings", {})
    if settings.get("positional_arguments", False):
        findings.append(
            Finding(reason="global-positional-arguments", path=Path("justfile"), line=1)
        )
    default_sh = not _declares_bash_compatible_shell(settings=settings)
    for recipe in payload.get("recipes", {}).values():
        findings.extend(_findings_for_recipe(recipe=recipe, default_sh=default_sh))
    return findings


def _declares_bash_compatible_shell(*, settings: _JustSettings) -> bool:
    """Has this justfile opted OUT of `just`'s default `sh` for every recipe?

    `set shell` is file-scoped, so one declaration exempts the whole resolved
    justfile from the Bash-only lexicon: those bodies are genuinely handed to
    the interpreter named here rather than to dash. `just --dump` reports the
    setting as `null` when it is absent, which is the case that matters — an
    absent declaration is what makes the default `sh` load-bearing.
    """
    shell = settings.get("shell")
    if shell is None:
        return False
    return shell_is_bash_compatible(command=shell.get("command", ""))


def _findings_for_recipe(*, recipe: _JustRecipe, default_sh: bool) -> list[Finding]:
    findings: list[Finding] = []
    name = recipe.get("name", "")
    body = recipe.get("body", [])
    lines = [_flatten_body_line(parts=line) for line in body]
    if any(flag for _, flag in lines):
        findings.append(
            Finding(
                reason="just-interpolation",
                path=Path("justfile"),
                line=1,
                recipe=name,
            )
        )
    if _missing_per_recipe_positional_arguments(recipe=recipe):
        findings.append(
            Finding(
                reason="missing-per-recipe-positional-arguments",
                path=Path("justfile"),
                line=1,
                recipe=name,
            )
        )
    if _missing_errexit_rationale(recipe=recipe, lines=lines):
        findings.append(
            Finding(
                reason="missing-errexit-rationale",
                path=Path("justfile"),
                line=1,
                recipe=name,
            )
        )
    if _nonconforming_recipe(recipe=recipe, lines=lines):
        findings.append(
            Finding(
                reason="nonconforming-just-recipe",
                path=Path("justfile"),
                line=1,
                recipe=name,
            )
        )
    findings.extend(_bash_only_syntax_findings(recipe=recipe, lines=lines, default_sh=default_sh))
    return findings


def _bash_only_syntax_findings(
    *, recipe: _JustRecipe, lines: list[tuple[str, bool]], default_sh: bool
) -> list[Finding]:
    """Report Bash-only syntax in a body `just` will hand to the default `sh`.

    Two exemptions apply BEFORE the lexicon is consulted, and both are about
    which interpreter actually receives the body:

    - `default_sh` is false when the justfile declared a Bash-compatible
      `set shell`, so nothing in the file runs under dash.
    - A shebang recipe names its own interpreter on its first body line, so
      Bash syntax there is legitimate. Reporting it would bury the real signal
      under every deliberately-Bash recipe in the file — the exact failure a
      naive grep over the justfile produces.

    One finding per DISTINCT construct rather than per line: a recipe that
    repeats `${@:2}` on three lines has one defect, and `dict.fromkeys` keeps
    the report in lexicon order instead of set-iteration order.
    """
    if not default_sh or recipe.get("shebang", False):
        return []
    commands = [line for line, _ in lines if _executable_line(line=line)]
    constructs = dict.fromkeys(
        construct for line in commands for construct in bash_only_constructs(line=line)
    )
    return [
        Finding(
            reason="bash-only-syntax-under-default-sh",
            path=Path("justfile"),
            line=1,
            recipe=recipe.get("name", ""),
            construct=construct,
        )
        for construct in constructs
    ]


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
    """Does this doc actually STATE an errexit rationale?

    The exemption a deviating recipe earns here is the only thing standing
    between a deliberate omission and an accidental one, so the test must not
    be satisfiable by prose that never mentions errexit at all. A bare
    ``"-e" in text`` was: it matches the two characters inside any ordinary
    hyphenated word (``byte-for-entry``, ``pre-existing``), which silently
    granted the exemption to recipes carrying no rationale whatsoever.

    Accepted spellings are the literal word ``errexit`` and the flag form
    ``set -e``, the latter matched with boundaries so it cannot fire from the
    middle of a hyphenated word.
    """
    return bool(_ERREXIT_RATIONALE_PATTERN.search(text.lower()))
