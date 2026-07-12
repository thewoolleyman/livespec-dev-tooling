"""_subagent_stop_guard_transcript — parse worktree paths out of a sub-agent transcript.

Extracted from `subagent_stop_guard.py` so the parent hook module
stays under the file-LLOC ceiling (fleet-check-coverage). This
sibling carries ONLY the transcript-scanning surface: the
worktree-path regex plus the `git worktree add -b <path>` command
parser that derives the absolute worktree paths THIS sub-agent
created. It performs no git probes, no I/O beyond string parsing,
and imports nothing from its parent — `subagent_stop_guard.py`
imports `extract_created_worktree_paths` (its sole public entry) via
the normal package path.

The leading underscore in the filename marks this as a private
helper module; its behavior is exercised through the public hook and
its own mirror-paired test.
"""

from __future__ import annotations

import json
import re
import shlex
from pathlib import Path
from typing import cast

__all__: list[str] = ["extract_created_worktree_paths"]


_WORKTREE_SEGMENT = r"[A-Za-z0-9][A-Za-z0-9._-]*"
_WORKTREE_PATH_RE = re.compile(
    r"/[^\s\"'\\]*?/(?:"
    # Fleet new root: ~/.worktrees/<repo>/<branch> — leading-dot
    # `.worktrees` with TWO segments; capture through <branch> so the
    # downstream `git -C <match>` probes hit the real worktree dir.
    rf"\.worktrees/{_WORKTREE_SEGMENT}/{_WORKTREE_SEGMENT}"
    r"|"
    # Legacy janitor / .claude forms: [.claude/]worktrees/<slug>.
    rf"(?:\.claude/)?worktrees/{_WORKTREE_SEGMENT}"
    r")"
)
_COMPACT_BRANCH_OPTION_PREFIX_LENGTH = 2


def _extract_worktree_paths(*, transcript_text: str) -> list[Path]:
    """Return unique worktree-shaped absolute paths mentioned in the transcript."""
    seen: dict[str, None] = {}
    for match in _WORKTREE_PATH_RE.finditer(transcript_text):
        seen.setdefault(match.group(0), None)
    return [Path(raw) for raw in seen]


def extract_created_worktree_paths(*, transcript_text: str) -> list[Path]:
    """Return unique worktree paths created by `git worktree add -b` commands."""
    seen: dict[str, None] = {}
    for line in transcript_text.splitlines():
        for segment in _transcript_line_segments(line=line):
            for path in _created_worktree_targets_from_segment(segment=segment):
                seen.setdefault(str(path), None)
    return [Path(raw) for raw in seen]


def _transcript_line_segments(*, line: str) -> list[str]:
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        return [line]
    segments = _json_string_values(value=payload)
    if not segments:
        return [line]
    return segments


def _json_string_values(*, value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        strings: list[str] = []
        data = cast("dict[object, object]", value)
        for item in data.values():
            strings.extend(_json_string_values(value=item))
        return strings
    if isinstance(value, list):
        strings = []
        data = cast("list[object]", value)
        for item in data:
            strings.extend(_json_string_values(value=item))
        return strings
    return []


def _created_worktree_targets_from_segment(*, segment: str) -> list[Path]:
    try:
        tokens = shlex.split(segment)
    except ValueError:
        return []
    targets: list[Path] = []
    for index, word in enumerate(tokens):
        if word != "git":
            continue
        target = _created_worktree_target_from_git_args(args=tokens[index + 1 :])
        if target is not None:
            targets.append(target)
    return targets


def _created_worktree_target_from_git_args(*, args: list[str]) -> Path | None:
    for index in range(len(args) - 1):
        if args[index] == "worktree" and args[index + 1] == "add":
            return _worktree_add_target(args=args[index + 2 :])
    return None


def _worktree_add_target(*, args: list[str]) -> Path | None:
    positional: list[str] = []
    saw_branch = False
    index = 0
    while index < len(args):
        word = args[index]
        if word == "--":
            positional.extend(args[index + 1 :])
            break
        if word in {"-b", "-B"}:
            saw_branch = True
            index += 2
            continue
        if word.startswith(("-b", "-B")) and len(word) > _COMPACT_BRANCH_OPTION_PREFIX_LENGTH:
            saw_branch = True
            index += 1
            continue
        if word == "--reason":
            index += 2
            continue
        if word.startswith("-"):
            index += 1
            continue
        positional.append(word.rstrip(";,"))
        index += 1
    if not saw_branch or not positional:
        return None
    target = positional[0]
    if _extract_worktree_paths(transcript_text=target) != [Path(target)]:
        return None
    return Path(target)
