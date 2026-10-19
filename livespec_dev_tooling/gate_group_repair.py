"""The gates credential's OWNING GROUP, and re-running a gate under it.

`gate_credential` answers whether THIS PROCESS can read the gates kubeconfig,
and that is the right question for the switch: a host holding no credential must
keep gating locally. It is the WRONG question for one host shape, measured on the
VPS 2026-10-18. There `/etc/ci-runner/gates.kubeconfig` is
`0640 root:gates-client` and `/etc/group` lists the login user in
`gates-client`, so the HOST is eligible and the OPERATOR is a member — but a
login session started BEFORE that membership was granted does not carry the
group. The read fails, `gate_remote_delegate enabled` exits non-zero, and the
push runs the full local aggregate (about 17 minutes for
livespec-orchestrator-beads-fabro) behind the ordinary `GATED_LOCALLY` line.
Nothing said the host was eligible and nothing named the remedy. The same push
under `/usr/bin/sg gates-client` delegated and reached a verdict in 95 seconds.

THIS MODULE REPAIRS THAT CASE RATHER THAN ONLY NARRATING IT, and the reason it
may is that re-executing under `/usr/bin/sg <group>` GRANTS NOTHING A FRESH LOGIN
WOULD NOT: the group database already lists the user, and `sg` refuses a
non-member. So the three facts below are read TOGETHER — the credential is
unreadable here, the group database lists this user in the group that owns it,
and this PROCESS's group list does not carry that group — and only that exact
conjunction re-executes. Every other shape is left exactly as it was: an absent
credential stays an ineligible host, a user the group database does not list
stays ineligible (and `sg` would refuse them), and a process that ALREADY
carries the group yet still cannot read the file is not missing a group at all —
the mode denies group read, so a re-execution would change nothing and loop.

THE DECISION IS A PURE FUNCTION OVER A RECORD OF THOSE FACTS, which is not
decoration: the state it exists for cannot be constructed in any suite that runs
as root, because every mode is readable there. Splitting the probes from the
decision is what lets each refusal shape be asserted directly while the probes
stay asserted against a real file.

THE `sg` PATH IS ABSOLUTE, AND THAT IS NOT A STYLE CHOICE. On the VPS a bare
`sg` resolves to `ast-grep`, which would take the gate's argv as a code-search
pattern and answer something. `/usr/bin/sg` is the shadow-utils binary that
changes the group.

RE-EXECUTION HAPPENS AT MOST ONCE, and the sentinel that bounds it carries the
GROUP it attempted rather than a bare flag. The child is a fresh process, so the
environment it was handed is the only thing that can tell it that it IS the
re-executed run; and when the child still cannot read the credential the
diagnostic has to name the group that was tried, which a boolean cannot. A
second re-execution is never attempted: `sg` succeeded and the read still
failed, so the group was not the problem and looping would only hide it.
"""

from __future__ import annotations

import grp
import os
import pwd
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from livespec_dev_tooling.gate_credential import gates_kubeconfig_path, gates_kubeconfig_readable
from livespec_dev_tooling.gate_remote_verdict import GATE_NO_VERDICT

# `structlog` is VENDORED, not installed; a bare import here would resolve only
# when some earlier import in the process happened to run first.
_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import.

__all__: list[str] = [
    "GATES_GROUP_REEXEC_ENV",
    "GATES_GROUP_REMEDY",
    "GATE_GROUP_NO_VERDICT",
    "GATE_MODULE",
    "GATE_RUNS_UNDER_GROUP",
    "SG",
    "GateGroupFacts",
    "gate_group_facts",
    "gates_group_reexec_argv",
    "group_repair_group",
    "group_repair_status",
    "reexecuted_gates_group",
    "repairable_gates_group",
    "repairable_group",
    "run_under_gates_group",
]

# The shadow-utils binary that runs a command under one of the caller's groups,
# by ABSOLUTE path — see the module docstring for the `ast-grep` collision a
# bare `sg` walks into on the host this whole module exists for.
SG = "/usr/bin/sg"

# How the re-executed child learns that it IS the re-executed child, and which
# group was tried. Carried in the environment because a fresh process has no
# other channel back to the run that spawned it.
GATES_GROUP_REEXEC_ENV = "LIVESPEC_GATES_GROUP_REEXEC"

# The module the re-execution runs — this client's own entry point, named rather
# than imported, because importing it here would close a cycle (it imports this
# module to reach the repair).
GATE_MODULE = "livespec_dev_tooling.gate_remote_delegate"

# What an ELIGIBLE host says when only the pushing PROCESS is missing the group.
# It is the counterpart of `gate_remote_delegate.GATED_LOCALLY` and replaces it
# in exactly this case: that line says the host cannot read the credential,
# which here is true of the process and false of the host, so printing it was
# the defect — it sent the operator looking for a credential that was already
# installed and already theirs.
GATE_RUNS_UNDER_GROUP = (
    "delegated gate is switched on and this host IS eligible, but this process does not "
    "carry the group that owns the gates kubeconfig, so the gate will run under that group"
)

# What an operator has to DO, as opposed to what went wrong. It names a fresh
# login session first because that is the durable fix — the group database
# already lists the user, so the next session carries the group without anyone
# granting anything — and the one-command forms second. `/usr/bin/sg` is spelled
# absolutely here for the same reason it is spelled absolutely in `SG`: on the
# host this exists for, a bare `sg` is `ast-grep`.
GATES_GROUP_REMEDY = (
    "start a fresh login session so the pushing process carries the group; `newgrp "
    "<group>` or `/usr/bin/sg <group> -c <command>` does the same for one shell or "
    "one command"
)

# The refusal, in the one shape a gate is allowed to have when it decided
# nothing. Falling through to the local aggregate here would be the defect this
# module repairs, one layer out: the operator was just told the gate would run
# under a group, so a push that quietly ran something else is exactly the
# outcome that cannot be told apart afterwards.
GATE_GROUP_NO_VERDICT = (
    "delegated gate reached no verdict: this host is eligible, but the gate could not be "
    "run under the group that owns the gates kubeconfig, so this push is refused rather "
    "than falling through to an unannounced local run"
)

# Which of the two ways it failed. Carried as a detail rather than folded into
# the message above because the remedy is the same and the diagnosis is not: one
# is a host missing a program, the other is a group that was not the problem.
_REEXEC_NEVER_STARTED = f"the re-execution never started — {SG} did not run"
_REEXEC_STILL_UNREADABLE = (
    "the re-execution ran and the credential is still unreadable, so the group was not "
    "what was missing"
)

# The name this module's own diagnostics are attributed to, so a reader who
# greps the event back finds the file that emitted it.
_LOGGER = "gate_group_repair"


@dataclass(frozen=True, kw_only=True)
class GateGroupFacts:
    """The three facts a group repair rests on, plus the one it is a repair FOR.

    `user_is_a_member` is read from the GROUP DATABASE and
    `process_carries_it` from this process's own group list, and keeping them
    apart is the whole point: their disagreement IS the defect this module
    repairs, so a record that collapsed them into one "is a member" field could
    not express the state it exists to recognise.
    """

    readable: bool
    owning_group: str | None
    user_is_a_member: bool
    process_carries_it: bool


def _owning_group(*, credential: Path) -> grp.struct_group | None:
    """The group database's entry for the group owning the credential FILE.

    A path that is not a file has no owning group for this purpose, which is the
    same reading `gates_kubeconfig_readable` takes of a directory. Left
    unguarded that is the one shape able to invent a repair out of nothing: a
    directory's group resolves, the pushing user may well be in it, and the read
    fails anyway because a directory is not a kubeconfig.
    """
    if not credential.is_file():
        return None
    try:
        owner = grp.getgrgid(credential.stat().st_gid)
    except (OSError, KeyError):
        return None
    return owner


def _user_is_a_member(*, group: grp.struct_group) -> bool:
    """Whether the GROUP DATABASE lists this user in `group`.

    Never whether the PROCESS carries it — that is the other fact, and the
    difference between the two is the defect. The primary-group case counts too:
    a user whose passwd entry names this group IS a member of it even though
    `gr_mem` does not repeat them there.

    A uid the password database cannot resolve is reported as NOT a member, so
    nothing repairs: `sg` would have no name to accept.
    """
    try:
        user = pwd.getpwuid(os.getuid())
    except KeyError:
        return False
    return user.pw_name in group.gr_mem or user.pw_gid == group.gr_gid


def gate_group_facts() -> GateGroupFacts:
    """Read this host's and this process's facts about the gates credential.

    `os.getgid()` is UNIONED with `os.getgroups()` rather than trusting the
    latter alone, because POSIX permits `getgroups` to omit the caller's own
    group id. Read alone it would report a process as not carrying the group
    that owns a file it created — the repair's own trigger — so the gate would
    re-execute under a group it already holds, and loop.
    """
    credential = gates_kubeconfig_path()
    readable = gates_kubeconfig_readable()
    owner = _owning_group(credential=credential)
    if owner is None:
        return GateGroupFacts(
            readable=readable,
            owning_group=None,
            user_is_a_member=False,
            process_carries_it=False,
        )
    return GateGroupFacts(
        readable=readable,
        owning_group=owner.gr_name,
        user_is_a_member=_user_is_a_member(group=owner),
        process_carries_it=owner.gr_gid in {os.getgid(), *os.getgroups()},
    )


def repairable_group(*, facts: GateGroupFacts) -> str | None:
    """Name the group a re-execution would repair the credential read with.

    `None` for every other shape, and the module docstring carries why each one
    is left alone. The conjunction is deliberately narrow: this is the only
    answer that causes a gate to re-execute itself, so a loose reading of it
    would re-run pushes that have nothing to gain from the group.
    """
    if facts.readable or facts.owning_group is None:
        return None
    if not facts.user_is_a_member or facts.process_carries_it:
        return None
    return facts.owning_group


def repairable_gates_group() -> str | None:
    """The repair decision, against the facts this host and process actually answer."""
    return repairable_group(facts=gate_group_facts())


def reexecuted_gates_group() -> str | None:
    """The group a parent run already re-executed under, or `None` on a first run.

    An EMPTY value reads as absent, for the reason `gates_kubeconfig_path` reads
    an empty override as absent: an exported-but-empty variable is how a shell
    says "unset" in practice.
    """
    return os.environ.get(GATES_GROUP_REEXEC_ENV) or None


def gates_group_reexec_argv(*, group: str) -> list[str]:
    """The `/usr/bin/sg` invocation that re-runs THIS gate under `group`.

    `sg` takes its command as ONE shell word, so the re-run is quoted rather
    than passed as an argv list — and quoted through `shlex` rather than by
    hand, because the interpreter's path is the one component this process does
    not choose.
    """
    return [SG, group, "-c", shlex.join([sys.executable, "-m", GATE_MODULE, "run"])]


def run_under_gates_group(*, group: str) -> int | None:
    """Re-run this gate under `group` and answer its exit status.

    `None` means the re-execution NEVER STARTED — `sg` is not installed, or the
    spawn itself failed — and is kept apart from every integer for the reason
    the client's own command seam keeps the two tracks apart: a fabricated exit
    code would make a gate that never ran indistinguishable from one that
    answered. The caller turns a never-started re-execution into a refusal, so
    the distinction has to survive this far.

    The child's streams are NOT captured: its verdict is the one the operator
    has to read, and capturing it is exactly what would swallow it.
    """
    if shutil.which(SG) is None:
        return None
    env = dict(os.environ)
    env[GATES_GROUP_REEXEC_ENV] = group
    try:
        completed = subprocess.run(  # noqa: S603  — argv is a list; no shell is involved.
            gates_group_reexec_argv(group=group),
            env=env,
            check=False,
        )
    except OSError:
        return None
    return completed.returncode


def group_repair_group(*, opted_in: bool) -> str | None:
    """Name the group an opted-in push would re-execute under, or `None`.

    Two gates stand before the host is read at all, and both are about silence.
    A repository that has NOT opted in must not be told anything about this
    host's groups — that is the path the overwhelming majority of pushes take.
    And a run that is ALREADY the re-executed child must never re-execute again,
    for the reason the module docstring records.
    """
    if not opted_in or reexecuted_gates_group() is not None:
        return None
    return repairable_gates_group()


def group_repair_status(*, opted_in: bool) -> int | None:
    """The exit status a group re-execution decided, or `None` to gate RIGHT HERE.

    The two answers are kept apart because they are different events rather
    than different values: an integer means another process already gated this
    tree and its verdict is the push's, while `None` means no re-execution was
    wanted and this process must carry on and gate. Collapsing them — a `0`
    for "nothing to do" — would complete a push on a gate that never ran.

    BOTH FAILURE SHAPES REFUSE, and neither may answer `None`. A re-execution
    that never started and one that ran and still could not read the credential
    leave this process holding no verdict, and `None` here means "gate locally"
    — which is the very fall-through the operator was just told would not
    happen. The child's own check is the first branch: it is the re-executed run
    reading its own result, which is the only place that answer exists.
    """
    log = structlog.get_logger(_LOGGER)
    attempted = reexecuted_gates_group()
    if attempted is not None and not gates_kubeconfig_readable():
        log.error(
            GATE_GROUP_NO_VERDICT,
            state=GATE_NO_VERDICT,
            group=attempted,
            detail=_REEXEC_STILL_UNREADABLE,
            remedy=GATES_GROUP_REMEDY,
        )
        return 1
    group = group_repair_group(opted_in=opted_in)
    if group is None:
        return None
    status = run_under_gates_group(group=group)
    if status is None:
        log.error(
            GATE_GROUP_NO_VERDICT,
            state=GATE_NO_VERDICT,
            group=group,
            detail=_REEXEC_NEVER_STARTED,
            remedy=GATES_GROUP_REMEDY,
        )
        return 1
    return status
