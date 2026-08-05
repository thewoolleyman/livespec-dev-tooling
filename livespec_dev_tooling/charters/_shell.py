"""Shared shell/prose parsing helpers for charter detectors."""

from __future__ import annotations

import re
from contextlib import suppress

FENCE = re.compile(r"^[ \t]*(`{3,}|~{3,})[^\n]*\n(.*?)^[ \t]*\1[ \t]*$", re.MULTILINE | re.DOTALL)
BUSY_FLAG = re.compile(r"\b(?:is_)?(?:busy|working)\b\s*=", re.IGNORECASE)
GREP_CALL = re.compile(r"\bgrep\b((?:[ \t]+-{1,2}[A-Za-z][A-Za-z-]*)*)[ \t]+('[^']*'|\"[^\"]*\")")
TAIL_HEAD = re.compile(r"\b(tail|head)\b[ \t]+-(?:n[ \t]*)?(\d+)")
POSIX_CLASS = re.compile(r"\[:(alpha|digit|alnum|space|blank|upper|lower|punct|xdigit):\]")
BRE_ESCAPED_OP = re.compile(r"\\([|+?(){}])")
BRE_BARE_OP = re.compile(r"(?<!\\)([|+?(){}])")
POSIX_EXPANSION: dict[str, str] = {
    "alpha": "a-zA-Z",
    "digit": "0-9",
    "alnum": "a-zA-Z0-9",
    "space": r" \t\n\r\f\v",
    "blank": r" \t",
    "upper": "A-Z",
    "lower": "a-z",
    "punct": r"!-/:-@\[-`{-~",
    "xdigit": "0-9A-Fa-f",
}

__all__: list[str] = [
    "code_blocks",
    "compiled_pattern",
    "decides_busy",
    "is_comment",
    "logical_lines",
    "pipeline_segments",
    "posix_to_python",
    "segment_effect",
    "strip_trailing_comment",
]


def code_blocks(*, text: str) -> list[str]:
    """Every fenced block body, in document order. Prose is discarded."""
    return [match.group(2) for match in FENCE.finditer(text)]


def is_comment(*, line: str) -> bool:
    return line.lstrip().startswith("#")


def strip_trailing_comment(*, line: str) -> str:
    """Drop a trailing `# ...` comment, respecting quotes."""
    quote = ""
    for index, char in enumerate(line):
        if quote:
            if char == quote:
                quote = ""
        elif char in "'\"":
            quote = char
        elif char == "#" and (index == 0 or line[index - 1].isspace()):
            return line[:index]
    return line


def logical_lines(*, block: str) -> list[str]:
    """Physical lines joined across trailing backslash continuations."""
    joined: list[str] = []
    pending = ""
    for line in block.splitlines():
        stripped = line.rstrip()
        if stripped.endswith("\\"):
            pending += stripped[:-1] + " "
            continue
        joined.append(pending + stripped)
        pending = ""
    if pending:
        joined.append(pending)
    return joined


def pipeline_segments(*, line: str) -> list[str]:
    """Split a logical line on shell pipes, ignoring pipes inside quotes."""
    segments: list[str] = []
    current = ""
    quote: str | None = None
    index = 0
    while index < len(line):
        char = line[index]
        if quote is not None:
            current += char
            if char == quote:
                quote = None
        elif char in "'\"":
            quote = char
            current += char
        elif char == "|":
            segments.append(current)
            current = ""
            if line[index + 1 : index + 2] == "|":
                index += 1
        else:
            current += char
        index += 1
    segments.append(current)
    return segments


def posix_to_python(*, pattern: str, extended: bool) -> str:
    """Translate a POSIX grep pattern into Python regex source."""
    translated = POSIX_CLASS.sub(lambda m: POSIX_EXPANSION[m.group(1)], pattern)
    if extended:
        return translated
    translated = BRE_BARE_OP.sub(r"\\\1", translated)
    return BRE_ESCAPED_OP.sub(r"\1", translated)


def compiled_pattern(*, flags: str, quoted: str) -> re.Pattern[str] | None:
    """The Python equivalent of one grep pattern, or None if it cannot be read."""
    body = quoted[1:-1]
    fixed = "F" in flags or "--fixed-strings" in flags
    extended = "E" in flags or "--extended-regexp" in flags
    source = re.escape(body) if fixed else posix_to_python(pattern=body, extended=extended)
    compiled: re.Pattern[str] | None = None
    with suppress(re.error):
        compiled = re.compile(source)
    return compiled


def segment_effect(*, segment: str, lines: list[str]) -> tuple[list[str], re.Pattern[str] | None]:
    """Apply one pipeline stage to the working line set."""
    narrowed = lines
    for verb, count in TAIL_HEAD.findall(segment):
        n = int(count)
        narrowed = narrowed[-n:] if verb == "tail" else narrowed[:n]
    for flags, quoted in GREP_CALL.findall(segment):
        compiled = compiled_pattern(flags=flags, quoted=quoted)
        if compiled is None:
            continue
        if "v" in flags.replace("--", "") or "--invert-match" in flags:
            narrowed = [line for line in narrowed if not compiled.search(line)]
            continue
        return narrowed, compiled
    return narrowed, None


def decides_busy(*, lines: list[str], index: int) -> bool:
    """Whether the grep on `lines[index]` is what sets the busy verdict."""
    line = lines[index]
    if BUSY_FLAG.search(line) is not None:
        return True
    opens_block = line.lstrip().startswith(("if ", "while ")) or line.rstrip().endswith(
        ("then", "do")
    )
    return opens_block and any(BUSY_FLAG.search(nxt) for nxt in lines[index + 1 : index + 3])
