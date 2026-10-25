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

from returns.io import IOFailure, IOResult, IOSuccess  # noqa: E402  — vendor-path-aware import.
from returns.pipeline import is_successful  # noqa: E402  — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

from livespec_dev_tooling.agent_hooks._command_shape import (  # noqa: E402
    Invocation,
    invocations,
)

__all__: list[str] = [
    "ForegroundRefusal",
    "foreground_refusal",
]

# The two git subcommands that run a gate, and the hooks whose
# installation makes each one run it. A commit answers to EITHER of its
# two, which is the section's own wording and not a convenience: this
# fleet's commit-time aggregate is split across them — the staged subset
# in `pre-commit` and the Red-Green-Replay gate in `commit-msg` — so
# reading only one of them would miss the hook the 2026-10-24 incident
# actually hung in.
_GATE_HOOKS: dict[str, tuple[str, ...]] = {
    "commit": ("pre-commit", "commit-msg"),
    "push": ("pre-push",),
}

# Asking git what a subcommand does runs no hook. Matched as whole
# TOKENS, never as substrings: `git commit -m "see --help"` carries
# `--help` inside its message and is an ordinary commit.
_HELP_FLAGS: frozenset[str] = frozenset({"-h", "--help"})

# `git push --delete` / `-d` makes every ref it names a deletion.
_DELETE_FLAGS: frozenset[str] = frozenset({"-d", "--delete"})

# What the probe found, as the refusal reports it. The two are not
# interchangeable: one says a gate WILL run, the other says nobody could
# tell — and the ratified section refuses on both, which is only sound if
# the record says which of them happened.
_FOUND_INSTALLED = "installed"
_NOT_ESTABLISHED = "unestablished"


@dataclass(frozen=True, kw_only=True)
class _HookProbeUnreadable:
    """Git could not be CONSULTED about a repository's hooks.

    Deliberately NOT inhabited by "git answered that there is no
    repository there": that is an ANSWER — no hook of any kind would run —
    and it travels the success track as the empty result every caller
    already reads as "no hook of this kind is installed".
    """

    repository: str
    detail: str


@dataclass(frozen=True, kw_only=True)
class ForegroundRefusal:
    """A foreground git command the guard refuses, and the reading behind it.

    `hooks` carries the hook names actually found installed rather than
    the ones that were looked for, so the refusal the agent reads names
    the gate it would really have fired. It is EMPTY when `finding` is
    `unestablished`: nothing was found installed there, because nothing
    could be read.
    """

    gate: str
    hooks: tuple[str, ...]
    repository: str
    finding: str


def foreground_refusal(*, command: str, cwd: Path) -> ForegroundRefusal | None:
    """The refusal `command` earns, or None when nothing in it is refusable.

    `None` is an ABSENCE every caller acts on as control flow — there is
    no hook-running git command here — rather than a failure to look for
    one: the probe's own non-answers are resolved below it.
    """
    for invocation in invocations(command=command):
        hooks = _GATE_HOOKS.get(invocation.subcommand or "") if invocation.binary == "git" else None
        if hooks is None or _runs_no_gate(invocation=invocation):
            continue
        repository = _target_repository(cwd=cwd, options=invocation.options)
        gate = f"git {invocation.subcommand}"
        probed = _installed_hooks(repository=repository, hooks=hooks)
        if not is_successful(probed):
            # Nothing was established, and the section refuses on that:
            # the guard's only other verdict is the fail-open allow, which
            # would release the command whose verdict is at risk.
            return ForegroundRefusal(
                gate=gate, hooks=(), repository=str(repository), finding=_NOT_ESTABLISHED
            )
        installed = unsafe_perform_io(probed.unwrap())
        if installed:
            return ForegroundRefusal(
                gate=gate,
                hooks=installed,
                repository=str(repository),
                finding=_FOUND_INSTALLED,
            )
    return None


def _runs_no_gate(*, invocation: Invocation) -> bool:
    """Whether this invocation names a gate subcommand and still fires no hook.

    Graded BEFORE the hook probe, which keeps the probe off a path that
    could not have been refused anyway — the cheapness this directory's
    hook discipline asks for, got by not asking the question.

    `--dry-run` is deliberately absent. The proposal that became the
    ratified section listed it; the ratification review removed it,
    because git runs `pre-push` on a dry run, so a dry run pays the full
    gate runtime and loses its verdict exactly as a real push does.
    """
    if _HELP_FLAGS & set(invocation.options + invocation.args):
        return True
    return invocation.subcommand == "push" and _deletes_only(args=invocation.args)


def _deletes_only(*, args: tuple[str, ...]) -> bool:
    """Whether every refspec this push carries deletes a remote branch.

    A deletion-only push publishes no tree, so there is nothing for a
    gate to judge — the same reading this repository's own pre-push gate
    takes of one. ONLY, though: a push carrying one ordinary refspec
    beside a deletion does publish a tree, and must still be refused.

    The first operand is the remote; a refspec with an empty source
    (`:refs/heads/x`) is git's other spelling of a deletion.
    """
    if _DELETE_FLAGS & set(args):
        return True
    operands = [word for word in args if not word.startswith("-")]
    return len(operands) > 1 and all(word.startswith(":") for word in operands[1:])


def _target_repository(*, cwd: Path, options: tuple[str, ...]) -> Path:
    """The repository a git invocation targets: its `-C`, else the session's cwd.

    Read from the GLOBAL option region alone, which is what makes the
    collision with `git commit -C <commit>` (`--reuse-message`)
    unrepresentable here rather than merely unlikely. Repeated `-C`s
    compose, each relative to the last, exactly as git resolves them; an
    absolute one replaces what came before, which `Path.__truediv__`
    already does.
    """
    target = cwd
    pending = False
    for word in options:
        if pending:
            target, pending = target / word, False
        elif word == "-C":
            pending = True
    return target


def _installed_hooks(
    *, repository: Path, hooks: tuple[str, ...]
) -> IOResult[tuple[str, ...], _HookProbeUnreadable]:
    """Which of `hooks` git would RUN in `repository`, or no answer at all.

    An EMPTY tuple on the SUCCESS track is the answer "none of them":
    git read the repository, or answered that there is none to read, and
    no hook of this kind is installed either way. The failure track is
    the one state that is not an answer.
    """
    directory = _hooks_directory(repository=repository)
    if not is_successful(directory):
        return IOFailure(unsafe_perform_io(directory.failure()))
    named = unsafe_perform_io(directory.unwrap())
    if named is None:
        return IOSuccess(())
    return IOSuccess(tuple(name for name in hooks if _would_run(path=named / name)))


def _hooks_directory(*, repository: Path) -> IOResult[Path | None, _HookProbeUnreadable]:
    """The directory git runs `repository`'s hooks from, on the railway.

    `None` on the success track is git ANSWERING that `repository` is not
    a repository it can read — a missing directory, or one holding no
    `.git`. No hook runs there, so it is the "no installed hook"
    exemption rather than a failure to look.

    The failure track is git failing to be CONSULTED: not on `PATH`, or a
    spawn the kernel refused. Nothing is established then, and the caller
    must not read that as absence — which is what the raised `OSError`
    used to buy, by escaping to the hook's fail-open ALLOW.

    The path is resolved relative to `repository`, because `core.hooksPath`
    may be declared relative and `git rev-parse` echoes it back as declared.
    """
    try:
        probed = subprocess.run(
            ["git", "-C", str(repository), "rev-parse", "--git-path", "hooks"],
            capture_output=True,
            text=True,
            check=False,
            stdin=subprocess.DEVNULL,
        )
    except OSError as exc:
        return IOFailure(
            _HookProbeUnreadable(repository=str(repository), detail=type(exc).__name__)
        )
    if probed.returncode != 0:
        return IOSuccess(None)
    return IOSuccess(repository / probed.stdout.strip())


def _would_run(*, path: Path) -> bool:
    """Whether git would run `path` as a hook.

    Executability is half of the question and routinely the half that
    differs: git skips a hook file whose execute bit is clear, so a
    present-but-not-executable file runs no gate and must not be read as
    one.
    """
    return path.is_file() and os.access(path, os.X_OK)
