"""subagent_stop_guard — block premature sub-agent turn-ends while a dispatch is in flight.

Per work-item livespec-dev-tooling-7us.2: a one-shot dispatch executor
that backgrounds a long gate command and ends its turn "to wait for
the notification" is TERMINATED at turn-end — nothing re-invokes it,
and its half-finished worktree (unpushed commits, unarmed PR) is
orphaned. This Claude Code `SubagentStop` hook blocks the turn-end
while derived in-flight markers exist in a worktree that sub-agent
created.

Wire-up (consuming repo's committed `.claude/settings.json`): a
`SubagentStop` hook entry whose command is

    mise exec -- uv run --no-sync python -m \
        livespec_dev_tooling.agent_hooks.subagent_stop_guard

Hook protocol: hook-input JSON on stdin (`session_id`,
`transcript_path`, `stop_hook_active`, ...). Exit `0` allows the stop;
exit `2` blocks it and feeds stderr back to the sub-agent so it
finishes the handoff. Every error path returns `0` — fail-open: a
broken hook must never wedge a healthy agent.

Marker derivation (all DERIVED — no sentinel files):

1. Scope: absolute worktree paths mentioned in THIS sub-agent's
   transcript, in either the fleet new-root form
   `**/.worktrees/<repo>/<branch>` (leading-dot `.worktrees`, two
   segments — matched through `<branch>` so the git probes target the
   real worktree dir) or the legacy `**/[.claude/]worktrees/<slug>`
   janitor form (capped at
   `_MAX_WORKTREES`). Agents that never touched a worktree (Explore /
   Plan / conversational turns) yield no candidates and are never
   blocked. The scoping is heuristic — a transcript that merely
   MENTIONS a foreign worktree can pull it into scope — so blocks are
   capped (anti-wedge below) rather than unconditional.
2. Per worktree, first marker wins:
   a. uncommitted tracked changes (`git status --porcelain -uno`);
   b. unpushed commits (`git rev-list --count HEAD --not
      --remotes=origin`);
   c. only when the branch is fully pushed AND carries work ahead of
      `origin/master` (the fleet-wide canonical branch): an open PR
      without auto-merge armed, or no PR at all, via `gh pr view
      --json state,autoMergeRequest` (fail-open on any `gh` failure,
      with a hard subprocess timeout).

Anti-wedge: blocks are capped at `_MAX_BLOCKS_PER_SESSION` per
session id (counter file under `$LIVESPEC_STOP_GUARD_STATE_DIR`,
default the system temp dir); past the cap the guard logs a loud
warning and fails open.

Output discipline: structlog JSON to stderr (the blocking reason the
sub-agent reads IS the structured event); no `print`, no
`sys.stderr.write`. The vendored `structlog` under
`livespec_dev_tooling/_vendor` is added to `sys.path` at module
import time so the hook works via `python -m` and direct script
invocation.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import cast

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

__all__: list[str] = []


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
_CANONICAL_REMOTE_REF = "origin/master"
_MAX_WORKTREES = 8
_MAX_BLOCKS_PER_SESSION = 3
_GH_TIMEOUT_SECONDS = 8
_STATE_DIR_ENV = "LIVESPEC_STOP_GUARD_STATE_DIR"


def _configure_logger() -> structlog.stdlib.BoundLogger:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    return structlog.get_logger("subagent_stop_guard")


def _extract_worktree_paths(*, transcript_text: str) -> list[Path]:
    """Return unique worktree-shaped absolute paths mentioned in the transcript."""
    seen: dict[str, None] = {}
    for match in _WORKTREE_PATH_RE.finditer(transcript_text):
        seen.setdefault(match.group(0), None)
    return [Path(raw) for raw in seen]


def _run_git(*, worktree: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(worktree), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _git_count(*, worktree: Path, args: list[str]) -> int | None:
    """Run a `git rev-list --count`-style probe; None on any failure."""
    result = _run_git(worktree=worktree, args=args)
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    if not value.isdigit():
        return None
    return int(value)


def _has_uncommitted_tracked_changes(*, worktree: Path) -> bool | None:
    result = _run_git(worktree=worktree, args=["status", "--porcelain", "--untracked-files=no"])
    if result.returncode != 0:
        return None
    return bool(result.stdout.strip())


def _unpushed_commit_count(*, worktree: Path) -> int | None:
    return _git_count(
        worktree=worktree,
        args=["rev-list", "--count", "HEAD", "--not", "--remotes=origin"],
    )


def _commits_ahead_of_canonical(*, worktree: Path) -> int | None:
    return _git_count(
        worktree=worktree,
        args=["rev-list", "--count", f"{_CANONICAL_REMOTE_REF}..HEAD"],
    )


def _pr_payload_marker(*, stdout: str) -> str | None:
    """Interpret a `gh pr view --json state,autoMergeRequest` payload."""
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    data = cast("dict[str, object]", payload)
    if data.get("state") != "OPEN":
        return None
    if data.get("autoMergeRequest") is None:
        return "PR is open but auto-merge is NOT armed (gh pr merge --auto --rebase)"
    return None


def _unarmed_pr_marker(*, worktree: Path) -> str | None:
    """Marker text when the worktree's pushed branch lacks an armed PR; None otherwise.

    Fail-open contract: any `gh` failure other than the explicit
    "no pull requests found" answer (missing binary, network error,
    auth failure, timeout, malformed payload) yields None.
    """
    try:
        result = subprocess.run(
            ["gh", "pr", "view", "--json", "state,autoMergeRequest"],
            cwd=str(worktree),
            capture_output=True,
            text=True,
            check=False,
            timeout=_GH_TIMEOUT_SECONDS,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if result.returncode != 0:
        if "no pull requests found" in result.stderr.lower():
            return "branch is pushed but has NO PR (gh pr create, then gh pr merge --auto)"
        return None
    return _pr_payload_marker(stdout=result.stdout)


def _worktree_marker(*, worktree: Path) -> str | None:
    """First in-flight marker for one worktree, or None when handoff-complete."""
    dirty = _has_uncommitted_tracked_changes(worktree=worktree)
    if dirty:
        return f"{worktree}: uncommitted tracked changes"
    unpushed = _unpushed_commit_count(worktree=worktree)
    if unpushed is not None and unpushed > 0:
        return f"{worktree}: {unpushed} unpushed commit(s)"
    ahead = _commits_ahead_of_canonical(worktree=worktree)
    if dirty is None or unpushed is None or ahead is None:
        return None
    if ahead == 0:
        return None
    pr_marker = _unarmed_pr_marker(worktree=worktree)
    if pr_marker is None:
        return None
    return f"{worktree}: {pr_marker}"


def _derive_markers(*, worktrees: list[Path]) -> list[str]:
    markers: list[str] = []
    for worktree in worktrees[:_MAX_WORKTREES]:
        marker = _worktree_marker(worktree=worktree)
        if marker is not None:
            markers.append(marker)
    return markers


def _decide(*, markers: list[str], block_count: int) -> bool:
    """Pure block/allow decision — True blocks the stop.

    Blocks iff at least one in-flight marker exists AND the per-session
    block cap has not been reached (anti-wedge fail-open past the cap).
    """
    if not markers:
        return False
    return block_count < _MAX_BLOCKS_PER_SESSION


def _state_path(*, session_id: str) -> Path:
    state_dir = os.environ.get(_STATE_DIR_ENV) or tempfile.gettempdir()
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", session_id) or "unknown"
    return Path(state_dir) / f"livespec-subagent-stop-guard-{safe}.blocks"


def _read_block_count(*, path: Path) -> int:
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return 0
    if not text.isdigit():
        return 0
    return int(text)


def _record_block(*, path: Path, count: int) -> None:
    with contextlib.suppress(OSError):
        _ = path.write_text(f"{count}\n", encoding="utf-8")


def _load_hook_input(*, raw: str) -> dict[str, object] | None:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    return cast("dict[str, object]", payload)


def _gather_worktrees(*, hook_input: dict[str, object]) -> list[Path]:
    """Worktree paths from this agent's transcript that exist as git worktrees."""
    transcript_raw = hook_input.get("transcript_path")
    if not isinstance(transcript_raw, str) or not transcript_raw:
        return []
    try:
        text = Path(transcript_raw).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    candidates = _extract_worktree_paths(transcript_text=text)
    return [path for path in candidates if (path / ".git").exists()]


def _guard(*, raw_input: str, log: structlog.stdlib.BoundLogger) -> int:
    hook_input = _load_hook_input(raw=raw_input)
    if hook_input is None:
        log.warning("unparseable hook input; failing open", check_id="subagent-stop-guard")
        return 0
    worktrees = _gather_worktrees(hook_input=hook_input)
    if not worktrees:
        return 0
    markers = _derive_markers(worktrees=worktrees)
    if not markers:
        return 0
    session_id = str(hook_input.get("session_id") or "unknown")
    state = _state_path(session_id=session_id)
    block_count = _read_block_count(path=state)
    if not _decide(markers=markers, block_count=block_count):
        log.warning(
            "in-flight markers remain but the per-session block cap is reached; failing open",
            check_id="subagent-stop-guard-cap-reached",
            markers=markers,
            block_count=block_count,
        )
        return 0
    _record_block(path=state, count=block_count + 1)
    log.error(
        "BLOCKING turn-end: this dispatch is still in flight — a sub-agent that "
        "ends its turn is terminated and nothing re-invokes it",
        check_id="subagent-stop-guard-block",
        markers=markers,
        block_count=block_count + 1,
        hint=(
            "Finish the handoff FOREGROUND before ending the turn: commit "
            "(mise exec -- git commit ...), push (mise exec -- git push), open the PR "
            "(gh pr create ...), arm auto-merge (gh pr merge --auto --rebase "
            "--delete-branch). Long gate commands fit in the raised foreground Bash "
            "timeout (BASH_DEFAULT_TIMEOUT_MS); NEVER run them with "
            "run_in_background and never end the turn before the PR is armed."
        ),
    )
    return 2


def main() -> int:
    log = _configure_logger()
    try:
        return _guard(raw_input=sys.stdin.read(), log=log)
    except Exception as exc:  # fail-open by contract: never wedge a healthy agent.
        log.warning(
            "subagent_stop_guard crashed; failing open",
            check_id="subagent-stop-guard-crash",
            error=repr(exc),
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
