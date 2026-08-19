"""_self_hosted_uv_lane_parse — pure workflow-YAML parsers for self_hosted_uv_lane.

Private sibling of `self_hosted_uv_lane.py`, following the same pure/IO split as
`_self_hosted_routing_parse` / `self_hosted_routing`: the parsers here are PURE
(no IO, no logging) and the parent owns every diagnostic and reads the files.

Like that sibling, every parse runs over a COMMENT-STRIPPED view of the
workflow (the parent reuses `_self_hosted_routing_parse.strip_yaml_comments`).
That is load-bearing here for a specific, measured reason rather than as
inherited habit: `livespec-orchestrator-beads-fabro` is hosted-only BY DESIGN
and carries a header COMMENT block explaining why it does not route
self-hosted -- a block that NAMES `vars.CI_RUNNER_LABELS` and even quotes the
self-hosted `runs-on` form it is refusing to use. A raw substring precondition
therefore flags the one repo the precondition exists to exempt, demanding the
uv variables in a workflow whose own header says not to add them.

The central parse is `variable_fallback_literal`, which answers "what does
`vars.<NAME>` fall back to in this expression?". It exists because the shipped
`_self_hosted_routing_parse.repo_variable_fallback` CANNOT answer that question
for the shapes this check reads. That function deliberately returns the LAST
`||` alternative, which is correct for a `runs-on` expression carrying one
operator but wrong for the lane-selection `env` expressions, which carry two:

    runs-on   ${{ fromJSON(vars.CI_RUNNER_LABELS || '["ubuntu-latest"]') }}
    env       ${{ contains(vars.CI_RUNNER_LABELS || '["ubuntu-latest"]', 'ubuntu') && '50' || '4' }}

On the `env` form the last alternative is `4` -- the self-hosted uv VALUE, not
the routing fallback. A lockstep comparison built on it would compare
`["ubuntu-latest"]` against `4`, mismatch on every correctly-configured repo,
and fail the entire fleet. So this module anchors on the variable REFERENCE and
reads the one quoted literal immediately following that specific `||`, which
resolves both shapes to the same `["ubuntu-latest"]`.

A real YAML parser is deliberately not used, for the reasons the sibling parse
module records: this package vendors no YAML library, and the established
convention in this domain is line-oriented parsing over a comment-stripped view.
"""

from __future__ import annotations

import re

__all__: list[str] = [
    "env_assignments",
    "references_variable",
    "uses_uv",
    "variable_fallback_literal",
]

_VARS_PREFIX = "vars."
_OR_OPERATOR = "||"
_QUOTE_CHARS = "\"'"
# A quoted literal needs at least an opening and a closing quote.
_MIN_QUOTED_LENGTH = 2

# Markers proving a workflow actually invokes uv. Deliberately INDEPENDENT of
# the two variables this check governs: gating the precondition on `UV_*` names
# would make deleting those variables also delete the precondition, so the
# check would pass on exactly the regression it exists to catch. `uv sync` is
# present in every routed fleet workflow today; the other two are included so a
# workflow that only runs or only installs uv is still covered.
_UV_MARKERS = ("uv sync", "uv run", "astral-sh/setup-uv")

# Top-level `env:` only at column 0, optionally quoted, with no inline value —
# a job-level or step-level `env:` is indented and must not be read as the
# workflow-wide block this check governs.
_TOP_ENV_LINE = re.compile(r"^(?P<q>[\"']?)env(?P=q):\s*$")
_ENV_ENTRY_LINE = re.compile(r"^(?P<indent>[ \t]+)(?P<key>[A-Za-z_][\w-]*)\s*:(?P<value>.*)$")


def references_variable(*, value: str, variable: str) -> bool:
    """Return whether `value` references the repo variable `variable`."""
    return f"{_VARS_PREFIX}{variable}" in value


def uses_uv(*, stripped: str) -> bool:
    """Return whether this comment-stripped workflow invokes uv at all."""
    return any(marker in stripped for marker in _UV_MARKERS)


def _leading_quoted_literal(*, text: str) -> str:
    """Return the de-quoted literal `text` opens with, or `""` when it has none.

    Returns `""` for every unresolvable shape -- text not opening with a quote,
    and an opening quote with no matching close -- so the caller distinguishes
    "no fallback offered" (`None` from `variable_fallback_literal`) from
    "a fallback was offered and could not be read" (`""`) without this helper
    needing a second sentinel.
    """
    if len(text) < _MIN_QUOTED_LENGTH or text[0] not in _QUOTE_CHARS:
        return ""
    quote = text[0]
    closing = text.find(quote, 1)
    if closing == -1:
        return ""
    return text[1:closing]


def variable_fallback_literal(*, value: str, variable: str) -> str | None:
    """Return the literal `vars.<variable>` falls back to in `value`.

    THREE outcomes, and every input reaches one of them -- this function is
    TOTAL over `str` and raises for no input, matching the discipline its
    sibling `repo_variable_fallback` adopted after an earlier regex-and-cast
    implementation crashed on an unquoted fallback (a check failing open by
    dying):

    * `None` -- `value` does not reference the variable at all, or references
      it with no `||` fallback. There is no lockstep claim to make.
    * `""` -- a `||` fallback was offered and no quoted literal follows it.
      Reported rather than passed silently.
    * a non-empty string -- the de-quoted fallback literal.

    The FIRST reference to the variable is the anchor, and the operator must
    follow it immediately. That is what makes the result the ROUTING fallback
    in both the `runs-on` and lane-selection `env` shapes, rather than the last
    `||` alternative -- which on the `env` shape is the uv value, not a routing
    literal at all.
    """
    reference = f"{_VARS_PREFIX}{variable}"
    if reference not in value:
        return None
    _, _, remainder = value.partition(reference)
    remainder = remainder.lstrip()
    if not remainder.startswith(_OR_OPERATOR):
        return None
    return _leading_quoted_literal(text=remainder[len(_OR_OPERATOR) :].lstrip())


def env_assignments(*, stripped: str) -> dict[str, str]:
    """Return the top-level `env:` block of a comment-stripped workflow.

    Maps each variable name to its raw value string. Entries are read at the
    FIRST child indent under `env:`; a dedent to column 0 ends the block, so a
    later top-level key cannot leak in. Returns an empty mapping when the
    workflow declares no top-level `env:`.
    """
    lines = stripped.splitlines()
    for idx, line in enumerate(lines):
        if _TOP_ENV_LINE.match(line) is None:
            continue
        return _env_entries(lines=lines, start=idx + 1)
    return {}


def _env_entries(*, lines: list[str], start: int) -> dict[str, str]:
    """Collect `key: value` entries at the first child indent after `start`."""
    child_indent: int | None = None
    entries: dict[str, str] = {}
    for line in lines[start:]:
        if not line.strip():
            continue
        if not line.startswith((" ", "\t")):
            break
        match = _ENV_ENTRY_LINE.match(line)
        if match is None:
            continue
        indent = len(match.group("indent"))
        if child_indent is None:
            child_indent = indent
        if indent == child_indent:
            entries[match.group("key")] = match.group("value").strip()
    return entries
