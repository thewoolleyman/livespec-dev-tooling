"""_ai_references — pure `.ai/<topic>.md` reference + path-exclusion helpers.

Shared by BOTH the repo-local `agents_ai_references_resolve` check (a
working-tree scan) and the central `assert_agent_ai_references_resolve`
fleet obligation row (a master-tree scan), so the concrete-reference
grammar and the excluded-directory set have ONE definition. This module
is PURE — no IO, no structlog: callers own all filesystem access and
diagnostic output.

The concrete-reference regex deliberately distinguishes a REAL
`.ai/<topic>.md` reference from the documentation placeholder
`` `.ai/<topic>.md` ``: the character class excludes `<` and `>`, so the
angle-bracket placeholder is not matched, while a backtick-wrapped
concrete path like `` `.ai/agent-disciplines.md` `` is. The negative
lookbehind rejects a `.ai` that is the tail of a larger token (e.g.
`foo.ai/x.md`).

Per `livespec/SPECIFICATION/contracts.md` §"Fleet agent-instruction
core": every `.ai/<topic>.md` path an `AGENTS.md` references MUST
resolve to an existing file, at every directory level that declares one.
"""

from __future__ import annotations

import re

__all__: list[str] = [
    "AGENTS_FILENAME",
    "is_excluded_agents_path",
    "iter_ai_references",
]


AGENTS_FILENAME = "AGENTS.md"

# A CONCRETE `.ai/<topic>.md` reference. The negative lookbehind
# `(?<![\w-])` rejects a `.ai` that is the tail of a larger token (so
# `foo.ai/x.md` is not treated as a reference). The character class
# excludes `<` and `>`, so the documentation placeholder `.ai/<topic>.md`
# is NOT matched as a concrete reference — only a real path such as
# `.ai/agent-disciplines.md` is.
_AI_REFERENCE = re.compile(r"(?<![\w-])\.ai/[A-Za-z0-9._/-]+\.md")

# Directory segments whose presence anywhere in an `AGENTS.md` path
# excludes that file from the resolvability scan: vendored, generated,
# or archival trees are not part of the live agent-instruction surface.
_EXCLUDED_SEGMENTS = frozenset(
    {"archive", "_vendor", "__pycache__", "node_modules", ".venv", ".git"}
)


def iter_ai_references(*, text: str) -> list[tuple[int, str]]:
    """Every concrete `.ai/<topic>.md` reference in `text`, as (line, ref).

    Lines are 1-indexed; each tuple's second element is the matched
    reference string exactly as it appears (e.g. `.ai/agent-disciplines.md`).
    """
    references: list[tuple[int, str]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        for match in _AI_REFERENCE.finditer(line):
            references.append((line_number, match.group(0)))
    return references


def is_excluded_agents_path(*, segments: tuple[str, ...]) -> bool:
    """True iff any path segment is an excluded (vendored/generated/archival) dir."""
    return any(segment in _EXCLUDED_SEGMENTS for segment in segments)
