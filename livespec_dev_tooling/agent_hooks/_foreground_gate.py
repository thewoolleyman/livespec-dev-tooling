"""_foreground_gate — decide whether a FOREGROUND git command must be refused.

The ratified `SPECIFICATION/contracts.md` section "Agent-session
gate-command guard" gives the `PreToolUse` guard a second refusal, and it
is the one that actually loses verdicts. A BARE BACKGROUNDED gate was
always the easier case: the tool output is the only record, so the hazard
is visible in the shape of the call. A FOREGROUND `git commit` is not. It
looks like the careful thing to do, and the repository hooks it fires run
the whole gate aggregate — measured at more than 21 minutes in
commit-msg `check-red-green-replay` on the shared VPS on 2026-10-24, past
the harness's 20-minute tool-call ceiling. The harness then moves the
call to the background and can kill it, and a kill leaves no exit code,
no output and no verdict, which is INDISTINGUISHABLE FROM A REFUSAL. So
the command is refused here and replaced by the detached form, where a
run that does not finish reports `DIED_WITHOUT_VERDICT` and can never
read as a pass.

WHY THIS IS A REFUSAL AND NOT A REWRITE. Coordinator
gitops-fleet-capacity-monitoring decided the mechanism on 2026-10-24 and
recorded why each alternative fails. An `updatedInput` rewrite is
invisible to the agent, has to quote arbitrary heredoc commit messages
through `bash -c`, changes the cwd semantics of `just` recipes, and is
still judged in its ORIGINAL form by the sibling guards that run beside
this one. A git hook cannot detach itself, because git waits on the
hook's exit status — the commit would land unjudged. A PATH `git` wrapper
shadows git for every caller, which is the hazard this fleet's `bd`
shadowing rule already forbids. And a timeout only moves the silent kill
earlier.

THE HOOK PROBE ASKS GIT, AND THE TWO NON-ANSWERS ARE NOT THE SAME.
Whether a hook is installed is not a fact about `.git/hooks`: a
repository may relocate its hooks with `core.hooksPath`, and a linked
worktree runs the hooks of its COMMON git directory rather than of its
own. Resolving that by hand would reimplement git's own lookup and get
the relocated case wrong — silently, in the ALLOW direction, which is the
whole failure this guard exists to stop. So the directory is read from
`git rev-parse --git-path hooks`, which honours both. Of the two ways
that can fail to produce an answer, only one is an answer: git ANSWERING
that the target is not a repository it can read means no hook of any kind
would run there, which is the "no installed hook" exemption the section
names. Git failing to be CONSULTED at all establishes nothing, and this
module's docstring is where that distinction is recorded because
`_deny_hint` makes exactly the same cut one layer up — absence rides the
success track, an unreadable path does not.

Cost: one `git rev-parse` per foreground git commit or push, which is the
cheapness this directory's `CLAUDE.md` requires of a blocking hook path
(the consuming repository's hook entry allows 15 seconds). No probe runs
for any other command, because the invocation never reaches it.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from livespec_dev_tooling.agent_hooks._command_shape import invocations  # noqa: E402

__all__: list[str] = [
    "ForegroundRefusal",
    "foreground_refusal",
]

# The gate this module refuses so far, and the git hook whose installation
# makes it one. `pre-push` is git's only push-time hook, so a push that
# would run a gate is exactly a push into a repository carrying it.
_PUSH_GATE = "git push"
_PUSH_HOOKS: tuple[str, ...] = ("pre-push",)


@dataclass(frozen=True, kw_only=True)
class ForegroundRefusal:
    """A foreground git command the guard refuses, and the reading behind it.

    `hooks` carries the hook names actually found installed rather than
    the ones that were looked for, so the refusal the agent reads names
    the gate it would really have fired.
    """

    gate: str
    hooks: tuple[str, ...]
    repository: str


def foreground_refusal(*, command: str, cwd: Path) -> ForegroundRefusal | None:
    """The refusal `command` earns, or None when nothing in it is refusable.

    `None` is an ABSENCE every caller acts on as control flow — there is
    no hook-running git command here — rather than a failure to look for
    one: the probe's own non-answers are resolved below it.
    """
    for invocation in invocations(command=command):
        if invocation.binary != "git" or invocation.subcommand != "push":
            continue
        installed = _installed_hooks(repository=cwd, hooks=_PUSH_HOOKS)
        if installed:
            return ForegroundRefusal(gate=_PUSH_GATE, hooks=installed, repository=str(cwd))
    return None


def _installed_hooks(*, repository: Path, hooks: tuple[str, ...]) -> tuple[str, ...]:
    """Which of `hooks` git would actually RUN in `repository`."""
    directory = _hooks_directory(repository=repository)
    if directory is None:
        return ()
    return tuple(name for name in hooks if _would_run(path=directory / name))


def _hooks_directory(*, repository: Path) -> Path | None:
    """The directory git runs `repository`'s hooks from, or None for no repository.

    Relative to `repository`, because `core.hooksPath` may be declared
    relative and `git rev-parse` echoes it back as declared.
    """
    probed = subprocess.run(
        ["git", "-C", str(repository), "rev-parse", "--git-path", "hooks"],
        capture_output=True,
        text=True,
        check=False,
        stdin=subprocess.DEVNULL,
    )
    if probed.returncode != 0:
        return None
    return repository / probed.stdout.strip()


def _would_run(*, path: Path) -> bool:
    """Whether git would run `path` as a hook.

    Executability is half of the question and routinely the half that
    differs: git skips a hook file whose execute bit is clear, so a
    present-but-not-executable file runs no gate and must not be read as
    one.
    """
    return path.is_file() and os.access(path, os.X_OK)
