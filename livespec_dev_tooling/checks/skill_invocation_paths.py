"""skill_invocation_paths — canonical `${CLAUDE_PLUGIN_ROOT}/` form for fenced SKILL.md invocations.

Root cause (li-m4q4h5): Claude Code's plugin installer FLATTENS
`.claude-plugin/scripts/` to `scripts/` and `.claude-plugin/skills/`
to `skills/` in the installed cache. The cache carries NO
`.claude-plugin/` directory and omits `pyproject.toml` / `uv.lock` /
`.python-version`, so `uv run` cannot synthesize a venv there. A
fenced run command that quotes `uv run python3
.claude-plugin/scripts/bin/<name>.py` is therefore broken in the
installed cache on two counts: the literal path does not exist
post-flatten, and `uv run` has no project to resolve.

The canonical invocation form is
`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/bin/<name>.py" "$@"`:
`${CLAUDE_PLUGIN_ROOT}` is the established Claude Code plugin
convention and resolves to the plugin root in BOTH the flattened
cache and `--plugin-dir .` dev mode, with `scripts/` directly beneath
it in both.

How an invocation is IDENTIFIED — the load-bearing semantic:

An "invocation" is a line INSIDE a fenced code block (between ```
fences) that references a `bin/<name>.py` wrapper (regex
`bin/[a-z_]+\\.py`). Inline-prose backtick references OUTSIDE fences
(e.g. a "never call the wrapper directly" counter-example, or
narration that merely mentions `bin/foo.py`) are NOT invocations and
are IGNORED. This fenced-vs-prose distinction is the core of the
check: it scopes the assertion to actual executable command lines and
spares explanatory prose.

For each discovered fenced invocation line the check asserts the
canonical form:

- MUST contain the `${CLAUDE_PLUGIN_ROOT}/` token.
- MUST NOT contain `uv run`.
- MUST NOT contain the literal `.claude-plugin/scripts`.
- The `${CLAUDE_PLUGIN_ROOT}/<relpath>.py` token MUST resolve to a
  real file under `.claude-plugin/<relpath>` in the repo (once
  `${CLAUDE_PLUGIN_ROOT}/` maps to `.claude-plugin/`, the path
  exists).

Any violation logs a structlog ERROR (skill name, file path, line,
reason) and the check returns 1. If no `.claude-plugin/skills/`
directory exists, the check returns 0 — a VACUOUS SKIP (dev-tooling
and the runtime have no plugin skills, so the shared check passes
there). There is deliberately NO "at least one invocation found"
hard assertion, which would break those vacuous-skip repos.

Output discipline: per spec, `print` (T20) and `sys.stderr.write`
(`check-no-write-direct`) are banned in dev-tooling/**. Diagnostics
flow through structlog (JSON to stderr); the vendored copy under
`.claude-plugin/scripts/_vendor/structlog` is added to `sys.path` at
module import time.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

__all__: list[str] = []


_SKILLS_TREE = Path(".claude-plugin") / "skills"
_PLUGIN_ROOT_TREE = Path(".claude-plugin")

_FENCE = "```"
_UV_RUN_TOKEN = "uv run"
_CLAUDE_PLUGIN_SCRIPTS_LITERAL = ".claude-plugin/scripts"

# A wrapper invocation is any in-fence line referencing a
# `bin/<name>.py` wrapper. Matching the `bin/<name>.py` tail keeps the
# check scoped to wrapper invocations (the surface the flatten/uv bug
# affects), ignoring illustrative snippets that merely import package
# modules.
_WRAPPER_INVOCATION_RE = re.compile(r"bin/[a-z_]+\.py\b")
# The required canonical path token form: ${CLAUDE_PLUGIN_ROOT}/<relpath>.py.
# A successful match BOTH proves the token is present AND captures the
# relpath to resolve, so the token-presence and extraction steps are a
# single regex rather than two separate branches.
_PLUGIN_ROOT_PATH_RE = re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}/(\S+?\.py)")


def _fenced_invocation_lines(*, skill_path: Path) -> list[str]:
    """Return the stripped in-fence lines that invoke a `bin/*.py` wrapper.

    Walks the file line by line, toggling `in_fence` whenever a
    stripped line starts with a ``` fence, and gathers every in-fence
    content line. The wrapper-invocation filter is applied afterward
    (the returned comprehension), so a fenced non-wrapper line is
    simply dropped. Prose references OUTSIDE fences are never gathered
    in the first place — they are not executable invocations.
    """
    lines = skill_path.read_text(encoding="utf-8").splitlines()
    in_fence_lines: list[str] = []
    in_fence = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(_FENCE):
            in_fence = not in_fence
            continue
        if in_fence:
            in_fence_lines.append(stripped)
    return [line for line in in_fence_lines if _WRAPPER_INVOCATION_RE.search(line)]


def _violation_reason(*, command: str, plugin_root: Path) -> str | None:
    """Return a violation reason for `command`, or None if it is canonical.

    Applies the canonical-form rules in order: ban `uv run`, ban the
    `.claude-plugin/scripts` literal, require an extractable canonical
    `${CLAUDE_PLUGIN_ROOT}/<relpath>.py` token (the single
    `_PLUGIN_ROOT_PATH_RE` match proves the token is present AND yields
    the relpath), and require that `<relpath>` resolve to a real file
    under `.claude-plugin/`.
    """
    if _UV_RUN_TOKEN in command:
        return "uses `uv run` (the installed cache omits pyproject.toml / uv.lock)"
    if _CLAUDE_PLUGIN_SCRIPTS_LITERAL in command:
        return "hard-codes the `.claude-plugin/scripts/...` literal (flattened in the cache)"
    match = _PLUGIN_ROOT_PATH_RE.search(command)
    if match is None:
        return "missing the canonical `${CLAUDE_PLUGIN_ROOT}/<path>.py` token"
    relative_path = match.group(1)
    resolved = plugin_root / relative_path
    if not resolved.is_file():
        return f"`${{CLAUDE_PLUGIN_ROOT}}/{relative_path}` does not resolve to a real file"
    return None


def main() -> int:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    log = structlog.get_logger("skill_invocation_paths")
    cwd = Path.cwd()
    skills_root = cwd / _SKILLS_TREE
    plugin_root = cwd / _PLUGIN_ROOT_TREE
    if not skills_root.is_dir():
        # Vacuous skip: repos without plugin skills (dev-tooling,
        # runtime) pass — there is nothing to guard.
        return 0
    offenders_found = False
    for skill_path in sorted(skills_root.glob("*/SKILL.md")):
        skill_name = skill_path.parent.name
        rel_path = skill_path.relative_to(cwd)
        for command in _fenced_invocation_lines(skill_path=skill_path):
            reason = _violation_reason(command=command, plugin_root=plugin_root)
            if reason is not None:
                offenders_found = True
                log.error(
                    "SKILL.md wrapper invocation deviates from canonical form",
                    skill=skill_name,
                    file=str(rel_path),
                    line=command,
                    reason=reason,
                )
    if offenders_found:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
