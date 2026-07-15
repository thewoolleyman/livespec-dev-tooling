"""_self_hosted_routing_parse — pure workflow-YAML parsers for self_hosted_routing.

Private sibling of `self_hosted_routing.py` — the same pure/IO plus
LLOC-reduction split as `_ci_matrix_parse` / `ci_matrix_completeness`. The
parsers are PURE (no IO, no logging) so the parent owns every diagnostic and
reads the files itself.

Every parse runs over a COMMENT-STRIPPED view of the workflow text
(`strip_yaml_comments`). YAML `#` comments are removed first (quote-aware) so a
comment that merely NAMES a forbidden trigger — e.g. the self-hosted shadow
lane's `# NEVER pull_request / merge_group / workflow_dispatch` header — is
never mistaken for a real `on:` trigger. That false positive (grepping raw
text) is exactly what the parent security check replaces, so comment stripping
is load-bearing, not cosmetic.

The `on:` trigger set is read STRUCTURALLY from the top-level `on:` key across
its three YAML shapes — scalar (`on: push`), flow list (`on: [push,
pull_request]`), and block mapping (`on:` then indented `push:` / `pull_request:`
keys). `runs_on_values` returns every job's `runs-on:` value as a string
(inline scalar, inline flow list, a `${{ ... }}` expression, or a block list),
which the parent substring-tests for the `local-ci` label.

A real YAML parser is deliberately NOT used: this package ships no YAML library
(only jsoncomment / structlog / tomli are vendored), the project convention
prefers plain-text parsing over adding a YAML dependency, and the sole sibling
in this domain (`_ci_matrix_parse`) already parses workflow YAML with the same
line-oriented regex approach. Parsing over a comment-stripped view keeps the
comment-immunity guarantee a real parser would give for the forbidden-trigger
false positive this check exists to prevent.
"""

from __future__ import annotations

import re

__all__: list[str] = [
    "runs_on_values",
    "strip_yaml_comments",
    "workflow_triggers",
]


# `runs-on:` at any indent; the value is the inline remainder (may be empty for
# a block-list form). `on:` only at column 0 (the top-level trigger key),
# optionally wrapped in matching quotes (`"on":` / `'on':`) and case-insensitive
# — YAML 1.1 reads a bare `on` as the boolean `true`, so authors legitimately
# quote the key, and the guard must read the triggers under it either way. A
# block-mapping trigger key is an indented `name:` line.
_RUNS_ON_LINE = re.compile(r"^(?P<indent>[ \t]*)runs-on:(?P<value>.*)$")
_TOP_ON_LINE = re.compile(r"^(?P<q>[\"']?)on(?P=q):(?P<value>.*)$", re.IGNORECASE)
_BLOCK_KEY_LINE = re.compile(r"^(?P<indent>[ \t]+)(?P<key>[A-Za-z_][\w-]*)\s*:")


def _strip_line_comment(*, line: str) -> str:
    """Truncate a single line at its first YAML `#` comment (quote-aware).

    A `#` opens a comment only when it is OUTSIDE single/double quotes AND is
    either at line start or preceded by whitespace — so `a#b`, and a `#` inside
    a quoted string or a `${{ ... '...' ... }}` expression, are preserved.
    """
    in_single = False
    in_double = False
    for idx, char in enumerate(line):
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif (
            char == "#"
            and not in_single
            and not in_double
            and (idx == 0 or line[idx - 1].isspace())
        ):
            return line[:idx]
    return line


def strip_yaml_comments(*, source: str) -> str:
    """Return `source` with every YAML line comment removed (quote-aware)."""
    return "\n".join(_strip_line_comment(line=line) for line in source.splitlines())


def _line_indent(*, line: str) -> int:
    return len(line) - len(line.lstrip())


def _gather_more_indented(*, lines: list[str], start: int, indent: int) -> list[str]:
    """Return the stripped, non-blank lines after `start` more indented than `indent`.

    Stops at the first non-blank line indented at or below `indent` (the next
    sibling key); blank lines are skipped, not terminal. Captures a block-list
    `runs-on:` value (its `- self-hosted` / `- local-ci` bullets).
    """
    collected: list[str] = []
    for line in lines[start:]:
        if not line.strip():
            continue
        if _line_indent(line=line) <= indent:
            break
        collected.append(line.strip())
    return collected


def runs_on_values(*, stripped: str) -> list[str]:
    """Return every `runs-on:` value in a comment-stripped workflow as a string.

    The value is the inline remainder of the `runs-on:` line joined with any
    more-indented continuation lines (the block-list form). The parent
    substring-tests each returned value for the `local-ci` label, so both
    inline forms (`[self-hosted, local-ci]`, the `${{ fromJSON(...) }}`
    expression) and the block-list form resolve to a single testable string.
    """
    lines = stripped.splitlines()
    values: list[str] = []
    for idx, line in enumerate(lines):
        match = _RUNS_ON_LINE.match(line)
        if match is None:
            continue
        parts = [match.group("value").strip()]
        parts.extend(
            _gather_more_indented(lines=lines, start=idx + 1, indent=_line_indent(line=line))
        )
        values.append(" ".join(part for part in parts if part))
    return values


def _parse_flow_list(*, value: str) -> frozenset[str]:
    """Parse an inline flow list `[a, b, c]` into its de-quoted token set."""
    inner = value.strip()[1:]
    if inner.endswith("]"):
        inner = inner[:-1]
    return frozenset(token.strip().strip("\"'") for token in inner.split(",") if token.strip())


def _parse_block_triggers(*, lines: list[str], start: int) -> frozenset[str]:
    """Collect the top-level trigger keys of a block-form `on:` mapping.

    The trigger keys are the mapping keys at the FIRST child indent under
    `on:`; deeper keys (`branches:`, `types:`) and their bullet values are
    ignored. A dedent to column 0 ends the `on:` block.
    """
    child_indent: int | None = None
    triggers: set[str] = set()
    for line in lines[start:]:
        if not line.strip():
            continue
        if not line.startswith((" ", "\t")):
            break
        match = _BLOCK_KEY_LINE.match(line)
        if match is None:
            continue
        indent = len(match.group("indent"))
        if child_indent is None:
            child_indent = indent
        if indent == child_indent:
            triggers.add(match.group("key"))
    return frozenset(triggers)


def workflow_triggers(*, stripped: str) -> frozenset[str]:
    """Return the top-level `on:` trigger names of a comment-stripped workflow.

    Handles the three YAML shapes of the `on:` value: a flow list (`on: [push,
    pull_request]`), a scalar (`on: push`), and a block mapping (`on:` then
    indented trigger keys). Returns an empty set when no top-level `on:` key is
    present.
    """
    lines = stripped.splitlines()
    for idx, line in enumerate(lines):
        match = _TOP_ON_LINE.match(line)
        if match is None:
            continue
        value = match.group("value").strip()
        if value.startswith("["):
            return _parse_flow_list(value=value)
        if value:
            return frozenset({value})
        return _parse_block_triggers(lines=lines, start=idx + 1)
    return frozenset()
