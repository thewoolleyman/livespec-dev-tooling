"""pretooluse_background_guard — deny `run_in_background` for gate commands.

Per work-item livespec-dev-tooling-7us.2: the premature-turn-end
failure starts when an executor backgrounds a long gate command
(`just check`, the Red-Green-Replay commit hook, `git push`, the PR
handoff) because it exceeds the default foreground Bash timeout, then
ends its turn to "wait for the notification" — fatal in a one-shot
sub-agent. A BARE backgrounded gate leaves the tool output as the only
record of the verdict, so nothing survives the turn. This Claude Code
`PreToolUse` hook (matcher `Bash`) denies any Bash call that combines
`run_in_background` with a gate command.

Exception — the sanctioned detached runner. The original rationale
also claimed that "with the committed `BASH_DEFAULT_TIMEOUT_MS`
raised, gates always fit FOREGROUND". That premise was measured
false: the commit aggregate runs 593s and 1043s unloaded and exceeds
`BASH_MAX_TIMEOUT_MS=1200000` under sustained fleet load, at which
point the harness kills the tool call and NO verdict is produced at
all. `scripts/gate-run.sh` (and the `just gate-start|gate-wait|
gate-status|gate-list` recipes that delegate to it) exists for exactly
that case: it runs the gate in its own detached session and records a
durable verdict on disk, so the record does NOT live in the tool
output and its waiter is safe to background. Commands dispatched
through it are therefore allowed. The allowance is anchored at the
START of the command, so merely NAMING the runner cannot launder a
bare backgrounded gate. See `.ai/gate-runtime-vs-harness-patience.md`.

VENUE-AWARE PRESCRIPTION (livespec-dev-tooling-h7qp). The deny used to
prescribe `just gate-start` / `gate-wait` and cite that `.ai/` doc
UNCONDITIONALLY, and both are absent in most venues where this hook
fires. The recipes ship in the worktree pack's `worktree.just`, which a
consumer root justfile pulls in via an OPTIONAL `import?` — the
optional form silently no-ops while the gitignored-and-installed pack
is absent, and a fresh `git worktree add` does not materialize it (the
authoring repo included). The `.ai/` doc is checkout-local to this
repo. So the deny left an agent with the direct path denied, the
prescribed path absent, the rationale unreadable, and the foreground
fallback explicitly foreclosed — which invites engineering AROUND the
guard, the worst available exit. The hint is therefore composed
against the venue: the runner is prescribed directly only where the
recipes actually resolve, otherwise the one-line install command that
makes them resolve is named FIRST, and the doc is cited only where it
exists. Detection is pure filesystem reads (no subprocess), keeping
the blocking path cheap per this directory's hook discipline.

SELF-INSTALL WAS CONSIDERED AND DECLINED, per the item's pinned
fix-order ruling, which prefers "the deny path detects recipe absence
and EITHER materializes the pack OR names that exact step as the
remedy". Naming it is the arm taken: a `PreToolUse` guard runs on a
DENY path under a cheapness obligation, and having it mutate the
repository it is judging would make a read-only veto into a writer —
a surprising mutation from a hook the agent did not ask to run, and
an unbounded install on a path required to stay sub-second. The
remedy is one line the agent runs deliberately, in the venue, where
its output is visible.

Wire-up (consuming repo's committed `.claude/settings.json`): a
`PreToolUse` hook entry with matcher `Bash` whose command is

    mise exec -- uv run --no-sync python -m \
        livespec_dev_tooling.agent_hooks.pretooluse_background_guard

Hook protocol: hook-input JSON on stdin (`tool_name`, `tool_input`
with the Bash `command` + `run_in_background` fields). Exit `2` denies
the tool call and feeds stderr back to the agent; exit `0` allows it.
Every error path returns `0` (fail-open).

Scoping limitation (documented per the work-item): Claude Code
settings-level hooks carry no agent identity in the hook input, so
per-agent (executor-only) scoping is NOT expressible — this deny
applies session-wide, main session included. That is acceptable
because the deny fires only on the conjunction (`run_in_background`
AND a gate command); legitimate main-session background usage of
non-gate commands is untouched, and a BARE backgrounded gate has no
legitimate use in any session — the one legitimate background form,
the detached runner's waiter, is allowed explicitly above.

Output discipline: structlog JSON to stderr (the deny reason the
agent reads IS the structured event); no `print`, no
`sys.stderr.write`. The vendored `structlog` under
`livespec_dev_tooling/_vendor` is added to `sys.path` at module
import time.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import cast

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

__all__: list[str] = []


# Gate-command shapes. Each pattern tolerates wrapper prefixes
# (`mise exec -- git commit`, `git -C <path> push`) by allowing
# non-separator filler between the binary and the subcommand; the
# filler class excludes shell separators so `git log && just build`
# does not bridge into a false match across commands.
_GATE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("just check", re.compile(r"\bjust\b[^\n;|&]*\bcheck")),
    ("git commit", re.compile(r"\bgit\b[^\n;|&]*\bcommit\b")),
    ("git push", re.compile(r"\bgit\b[^\n;|&]*\bpush\b")),
    ("gh pr", re.compile(r"\bgh\s+pr\b")),
)

# The sanctioned detached-gate runner. Anchored at the START of the
# command (tolerating a `mise exec --` wrapper and any path prefix) so
# the command must BE a runner invocation rather than merely mention
# one: `git commit -m 'add scripts/gate-run.sh'` stays denied.
_SANCTIONED_RUNNER: re.Pattern[str] = re.compile(
    r"^\s*(?:mise\s+exec\s+--\s+)?(?:\S*/)?"
    r"(?:gate-run\.sh|just\s+gate-(?:start|wait|status|list))\b"
)


# Venue probe constants. The gate recipes resolve only when the pack's
# `worktree.just` fragment is installed AND imported by the root justfile
# AND the `gate-run.sh` body its stanzas invoke is installed beside it —
# any one of the three missing makes `just gate-start` unresolvable.
_PACK_DIR_NAME = "dev-tooling"
_PACK_FRAGMENT_NAME = "worktree.just"
_PACK_RUNNER_NAME = "gate-run.sh"
_JUSTFILE_NAMES: tuple[str, ...] = ("justfile", "Justfile", ".justfile")
_PRESCRIBED_RECIPES: tuple[str, ...] = ("gate-start", "gate-wait")

# The rationale doc is checkout-local to livespec-dev-tooling, so it is
# cited only when it is actually readable from the venue.
_RATIONALE_DOC = ".ai/gate-runtime-vs-harness-patience.md"

# The one-line repair, spelled as the MODULE invocation rather than as
# `just install-worktree-pack`: the module is guaranteed importable
# wherever this hook runs (the hook itself is a `python -m` entry of the
# same package), whereas the convenience recipe is per-repo.
_INSTALL_COMMAND = "mise exec -- uv run python -m livespec_dev_tooling.install_worktree_pack"

_HINT_PREAMBLE = (
    "Gate commands (just check*, git commit, git push, gh pr ...) must not be "
    "backgrounded BARE: the tool output is then the only record of the verdict, "
    "so a killed task or a turn-end leaves nothing behind. Do NOT answer this by "
    "re-issuing it foreground and waiting — the commit aggregate exceeds "
    "BASH_MAX_TIMEOUT_MS under load, and that kill produces NO verdict at all. "
)

_DISPATCH_CLAUSE = (
    "run_id=$(mise exec -- just gate-start -- <your gate command>) then background "
    '`mise exec -- just gate-wait "$run_id"`. '
)

_RUNNER_PRESENT_CLAUSE = (
    "Dispatch through the sanctioned detached runner instead, which IS allowed here: "
    f"{_DISPATCH_CLAUSE}"
)

# The install command is named BEFORE the recipes it materializes: naming
# an unresolvable recipe first is the defect this clause exists to fix.
_RUNNER_ABSENT_CLAUSE = (
    "The sanctioned detached runner is NOT installed in this working tree, so its gate "
    "recipes do not resolve here yet: the runner ships in the worktree-discipline pack, "
    "which is gitignored-and-installed, and a fresh `git worktree add` does not "
    f"materialize it. Install the pack HERE first, with exactly: {_INSTALL_COMMAND} — "
    f"then dispatch through the runner, which IS allowed here: {_DISPATCH_CLAUSE}"
)

_HINT_TAIL = (
    "The gate then runs in its own session that outlives the tool call, killing the "
    "waiter loses nothing, and the verdict is one of PASSED / FAILED / RUNNING / "
    "DIED_WITHOUT_VERDICT — so a gate that did not finish can never read as a pass. "
    "The wrapper does not exempt the wrapped command from the OTHER guards: a CI wait "
    "must still be a single loop-free call, e.g. `mise exec -- just gate-start -- gh "
    "run watch <run-id> --exit-status --interval 30` rather than an `until`/`sleep` "
    "loop over uncached `gh pr checks`, which the rate-limit guard denies wrapped or not."
)


def _read_text(*, path: Path) -> str:
    """Read `path` as text, degrading an unreadable path to an empty body.

    A venue probe must never raise: the caller's only alternative is the
    module's fail-open boundary, which would ALLOW the bare backgrounded
    gate this hook exists to deny. An unreadable justfile or fragment
    means "cannot establish that the recipes resolve", which is exactly
    what an empty body yields downstream.
    """
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _repo_root(*, start: Path) -> Path | None:
    """Return the nearest ancestor of `start` holding a `.git` entry.

    `.git` is a DIRECTORY in a primary checkout and a FILE in a linked
    worktree — the venue this item is about — so the probe is `exists()`
    rather than `is_dir()`.
    """
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def _imports_pack_fragment(*, root: Path) -> bool:
    """True when the root justfile imports the pack's `worktree.just`."""
    target = f"{_PACK_DIR_NAME}/{_PACK_FRAGMENT_NAME}"
    for name in _JUSTFILE_NAMES:
        body = _read_text(path=root / name)
        for line in body.splitlines():
            if line.lstrip().startswith("import") and target in line:
                return True
    return False


def _gate_recipes_resolve(*, root: Path | None) -> bool:
    """True when `just gate-start` / `gate-wait` actually resolve at `root`."""
    if root is None:
        return False
    pack_dir = root / _PACK_DIR_NAME
    fragment = _read_text(path=pack_dir / _PACK_FRAGMENT_NAME)
    declared = all(
        re.search(rf"(?m)^{re.escape(name)}\b", fragment) is not None
        for name in _PRESCRIBED_RECIPES
    )
    runner_installed = (pack_dir / _PACK_RUNNER_NAME).is_file()
    return declared and runner_installed and _imports_pack_fragment(root=root)


def _hint(*, cwd: Path) -> str:
    """Compose the deny hint against the venue the hook is firing in.

    Every command the hint names resolves in `cwd`, and every path it
    cites exists there — the minimum bar the guard's own prescription
    has to clear before it can demand the agent follow it.
    """
    root = _repo_root(start=cwd)
    prescription = (
        _RUNNER_PRESENT_CLAUSE if _gate_recipes_resolve(root=root) else _RUNNER_ABSENT_CLAUSE
    )
    doc_readable = root is not None and (root / _RATIONALE_DOC).is_file()
    citation = f" See {_RATIONALE_DOC}." if doc_readable else ""
    return f"{_HINT_PREAMBLE}{prescription}{_HINT_TAIL}{citation}"


def _configure_logger() -> structlog.stdlib.BoundLogger:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    return structlog.get_logger("pretooluse_background_guard")


def _matched_gate(*, command: str) -> str | None:
    """Return the gate label the command matches, or None."""
    for label, pattern in _GATE_PATTERNS:
        if pattern.search(command):
            return label
    return None


def _should_deny(*, tool_name: str, tool_input: dict[str, object]) -> str | None:
    """Pure deny decision — the matched gate label, or None to allow.

    Denies iff the call is a Bash tool call, `run_in_background` is
    literally true, the command matches a gate pattern, and it is NOT
    dispatched through the sanctioned detached runner.
    """
    if tool_name != "Bash":
        return None
    if tool_input.get("run_in_background") is not True:
        return None
    command = tool_input.get("command")
    if not isinstance(command, str):
        return None
    if _SANCTIONED_RUNNER.search(command):
        return None
    return _matched_gate(command=command)


def _load_hook_input(*, raw: str) -> dict[str, object] | None:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    return cast("dict[str, object]", payload)


def _guard(*, raw_input: str, log: structlog.stdlib.BoundLogger) -> int:
    hook_input = _load_hook_input(raw=raw_input)
    if hook_input is None:
        log.warning("unparseable hook input; failing open", check_id="pretooluse-background-guard")
        return 0
    tool_name_raw = hook_input.get("tool_name")
    tool_name = tool_name_raw if isinstance(tool_name_raw, str) else ""
    tool_input_raw = hook_input.get("tool_input")
    if not isinstance(tool_input_raw, dict):
        return 0
    tool_input = cast("dict[str, object]", tool_input_raw)
    gate = _should_deny(tool_name=tool_name, tool_input=tool_input)
    if gate is None:
        return 0
    log.error(
        "DENIED: bare-backgrounding a gate command — dispatch it through the detached runner",
        check_id="pretooluse-background-guard-deny",
        gate=gate,
        command=tool_input.get("command"),
        hint=_hint(cwd=Path.cwd()),
    )
    return 2


def main() -> int:
    log = _configure_logger()
    try:
        return _guard(raw_input=sys.stdin.read(), log=log)
    except Exception as exc:  # noqa: BLE001 — sole fail-open hook boundary: silent pass-through, exit 0
        log.warning(
            "pretooluse_background_guard crashed; failing open",
            check_id="pretooluse-background-guard-crash",
            error=repr(exc),
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
