"""_justfile_bash_recipes — policy-neutral justfile Bash recipe evidence."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from typing import Literal

__all__: list[str] = [
    "JustfileBashClassification",
    "RecipeEvidence",
    "RecipeShape",
    "ShellRecipe",
    "classify_justfile_bash_recipes",
]

RecipeShape = Literal["direct", "multiline", "shebang"]
EvidenceKind = Literal["command", "comment", "shebang", "shell_option"]

_HEADER = re.compile(r"^([A-Za-z0-9_-]+)(?:\s+[^:=][^:]*)?:.*$")
_INTERPOLATION = re.compile(r"\{\{[^{}\n]+\}\}")
_SHELL_OPTION = re.compile(r"^(?:set|shopt)\s+")
_NEUTRAL = "__JUST_INTERPOLATION__"


@dataclass(frozen=True, kw_only=True)
class RecipeEvidence:
    """One classified source line inside a justfile recipe body."""

    kind: EvidenceKind
    text: str
    line: int
    column: int


@dataclass(frozen=True, kw_only=True)
class ShellRecipe:
    """A justfile recipe extracted as Bash evidence, without policy judgement."""

    name: str
    shape: RecipeShape
    header_line: int
    body_start_line: int
    body_end_line: int
    documentation: tuple[str, ...]
    evidence: tuple[RecipeEvidence, ...]
    commands: tuple[str, ...]
    neutralized_body: str
    bash_parseable: bool
    malformed_reason: str | None

    @property
    def has_explanatory_comment(self) -> bool:
        return bool(self.documentation)


@dataclass(frozen=True, kw_only=True)
class JustfileBashClassification:
    """All recipe evidence plus extraction-level validity."""

    recipes: tuple[ShellRecipe, ...]
    extraction_errors: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return not self.extraction_errors and all(recipe.bash_parseable for recipe in self.recipes)


@dataclass(frozen=True, kw_only=True)
class _BodyLine:
    text: str
    line: int
    column: int


@dataclass(frozen=True, kw_only=True)
class _RecipeBlock:
    name: str
    header_line: int
    documentation: tuple[str, ...]
    body: tuple[_BodyLine, ...]


def classify_justfile_bash_recipes(*, justfile_text: str) -> JustfileBashClassification:
    """Extract justfile recipes and classify Bash evidence without enforcing a convention."""
    blocks, errors = _extract_recipe_blocks(justfile_text=justfile_text)
    recipes = tuple(_classify_recipe(block=block) for block in blocks)
    return JustfileBashClassification(recipes=recipes, extraction_errors=tuple(errors))


def _extract_recipe_blocks(*, justfile_text: str) -> tuple[list[_RecipeBlock], list[str]]:
    lines = justfile_text.splitlines()
    blocks: list[_RecipeBlock] = []
    errors: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        header = _match_header(line=line)
        if header is None:
            index += 1
            continue
        block, next_index, block_errors = _collect_block(lines=lines, start=index, name=header)
        blocks.append(block)
        errors.extend(block_errors)
        index = next_index
    return blocks, errors


def _match_header(*, line: str) -> str | None:
    stripped = line.strip()
    if (
        not stripped
        or stripped.startswith("#")
        or line.startswith((" ", "\t"))
        or ":=" in line
        or ":" not in line
    ):
        return None
    match = _HEADER.match(line)
    return match.group(1) if match is not None else None


def _collect_block(
    *, lines: list[str], start: int, name: str
) -> tuple[_RecipeBlock, int, list[str]]:
    body: list[_BodyLine] = []
    errors: list[str] = []
    index = start + 1
    indent: int | None = None
    while index < len(lines):
        raw = lines[index]
        if _match_header(line=raw) is not None:
            break
        if not raw.strip():
            body.append(_BodyLine(text="", line=index + 1, column=1))
            index += 1
            continue
        line_indent = len(raw) - len(raw.lstrip(" \t"))
        if line_indent == 0:
            break
        if indent is None:
            indent = line_indent
        if line_indent < indent:
            errors.append(f"line {index + 1}: indented command is not attached to a recipe")
            index += 1
            continue
        body.append(_BodyLine(text=raw[indent:], line=index + 1, column=indent + 1))
        index += 1
    return (
        _RecipeBlock(
            name=name,
            header_line=start + 1,
            documentation=_documentation_before(lines=lines, header_index=start),
            body=tuple(body),
        ),
        index,
        errors,
    )


def _documentation_before(*, lines: list[str], header_index: int) -> tuple[str, ...]:
    docs: list[str] = []
    index = header_index - 1
    while index >= 0 and lines[index].strip().startswith("#"):
        docs.append(lines[index].strip()[1:].strip())
        index -= 1
    docs.reverse()
    return tuple(docs)


def _classify_recipe(*, block: _RecipeBlock) -> ShellRecipe:
    relevant = tuple(line for line in block.body if line.text.strip())
    body_text = "\n".join(line.text for line in relevant)
    neutralized = _neutralize_interpolation(text=body_text)
    parseable, reason = _bash_parse_result(script=neutralized)
    evidence = tuple(_evidence_for(line=line) for line in relevant)
    commands = tuple(item.text for item in evidence if item.kind == "command")
    return ShellRecipe(
        name=block.name,
        shape=_shape_for(evidence=evidence),
        header_line=block.header_line,
        body_start_line=relevant[0].line if relevant else block.header_line,
        body_end_line=relevant[-1].line if relevant else block.header_line,
        documentation=block.documentation,
        evidence=evidence,
        commands=commands,
        neutralized_body=neutralized,
        bash_parseable=parseable,
        malformed_reason=reason,
    )


def _evidence_for(*, line: _BodyLine) -> RecipeEvidence:
    stripped = line.text.strip()
    kind: EvidenceKind = "command"
    if _SHELL_OPTION.match(stripped) is not None:
        kind = "shell_option"
    if stripped.startswith("#"):
        kind = "shebang" if stripped.startswith("#!") else "comment"
    return RecipeEvidence(kind=kind, text=stripped, line=line.line, column=line.column)


def _shape_for(*, evidence: tuple[RecipeEvidence, ...]) -> RecipeShape:
    if evidence and evidence[0].kind == "shebang":
        return "shebang"
    commands = tuple(item for item in evidence if item.kind == "command")
    return "direct" if len(commands) <= 1 else "multiline"


def _neutralize_interpolation(*, text: str) -> str:
    return _INTERPOLATION.sub(_NEUTRAL, text)


def _bash_parse_result(*, script: str) -> tuple[bool, str | None]:
    completed = subprocess.run(
        ["bash", "-n"],
        input=script,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode == 0:
        return True, None
    reason = completed.stderr.strip() or completed.stdout.strip() or "bash -n failed"
    return False, reason
