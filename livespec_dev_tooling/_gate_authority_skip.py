"""What a delegated gate Job must be TOLD not to run, and under WHOSE variable name.

The one exception in the "What the delegated gate runs" bullet of this
repository's own `SPECIFICATION/contracts.md`, delegated pre-push gate section,
ratified v082, has two halves. `_gate_host_authority` owns the half that RUNS the
authority-declaring members on the pushing host. This module owns the half that
keeps them OUT of the gate Job, which the scenario about an authority-reading
member of an opted-in push states as its first THEN: "the gate Job MUST NOT run
that member".

THAT HALF REACHED EXACTLY ONE REPOSITORY, AND IT WAS MEASURED TWICE. A gate Job
left an authority member out only through `scripts/just/check.sh` — this
repository's OWN aggregate runner, which no consuming repository carries — so in
every consumer's Job the forge-admin member ran, could not read the admin-scoped
state the pod is designed not to hold, and correctly refused to report a pass it
had not verified. On 2026-10-24 at ~11:00Z gate Job gate-livespec-p87qc refused a
green tree of livespec that way, with HTTP 403 from
`check-branch-protection-alignment`, and livespec withdrew its opt-in; earlier
the same day gate Job gate-livespec-overseer-tpfd2 ran overseer's master green on
every member except that one. Both verdicts were right about the POD and wrong
about the TREE.

THE CLIENT TELLS THE JOB, rather than the Job working it out. The pushing host
already resolves the declaring members for its own half, so resolving them a
second time inside the pod would be a second answer that can disagree with the
first — and a pod that skipped a member the host did not run is an unread
authorization treated as granted, the one outcome the contract forbids outright.

UNDER THE CONSUMER'S OWN VARIABLE, because the fleet does not agree on its name.
livespec's `check` recipe reads its skip list from `SKIP_TARGETS` and
livespec-overseer's reads it from `LIVESPEC_CHECK_SKIP`, so a mechanism naming
either one would be right in one repository and SILENTLY INERT in the other —
and inert means the member runs, fails on the absent credential, and a correct
tree reads as RED. The name is therefore read out of the repository's own recipe,
which is the surface that decides it.

A REPOSITORY WHOSE NAME CANNOT BE ESTABLISHED IS REFUSED, NOT LEFT ALONE, and
the reasoning this replaces is worth keeping because it was plausible and it was
measured wrong. The old argument ran: pass nothing, and such a Job runs exactly
the members it runs today — its authority member executes, cannot read its
authorization, and FAILS — so the unestablished case degrades toward refusing a
correct tree rather than toward passing an unverified one, and is safe to leave
while a repository adopts a skip surface.

BOTH HALVES OF THAT WERE FALSE ON 2026-10-24. The silence is the first half:
three consumers read their skip list from no variable this reader recognises —
livespec-driver-pi's `check` recipe reads none at all, and
livespec-orchestrator-git-jsonl's and livespec-orchestrator-beads-fabro's read
theirs from a `just` surface rather than the environment — so `authority_skip_argv`
returned `[]` for each, no Job printed the `NOT running` line, and nothing on any
surface said a mechanism had been skipped rather than satisfied. The second half
is worse than a red tree: the orchestrator's Job
`gates/gate-livespec-orchestrator-beads-fabro-ssqmj` PASSED, having executed
`check-branch-protection-alignment` in-pod at 18:19:01Z, because that pod's own
forge credential happens to be able to read branch protection. Every accepted
orchestrator delegated verdict since its 2026-10-18 opt-in therefore took the
branch-protection answer from a credential the gate pod holds and not from the
pushing host's — an authorization the host never read, reported as gated, which
is the one outcome the contract's "it never treats an unevaluated authorization
as granted" forbids outright.

SO THE RESOLUTION REFUSES, and the refusal is the mechanism rather than a
diagnostic beside it: a Job that cannot be told to leave the member out is not
submitted at all, which is the only disposition that satisfies "such a member
does not run in the gate Job" for a repository this reader cannot tell. Inventing
a name remains the other unsafe shape: it would export a list nothing reads while
every surface reported a Job that had been told.

A PRIVATE MODULE WITH A PUBLIC SURFACE, per this package's own convention for a
cohesion split (`_gate_remote_assembly.py` and its siblings): the names in
`__all__` are the interface `gate_remote_delegate` composes.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from livespec_dev_tooling.check_authority import repository_authority_members
from livespec_dev_tooling.checks._tool_backed_surfaces import extract_check_recipe_body
from livespec_dev_tooling.gate_remote_invocation import GateStepFailed

# `returns` is VENDORED, not installed; a bare import here would resolve only
# when some earlier import in the process happened to run first.
_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.pipeline import is_successful  # noqa: E402  — vendor-path-aware import.
from returns.result import Failure, Result, Success  # noqa: E402  — same.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — same.

__all__: list[str] = [
    "AUTHORITY_SKIP_ENV_FLAG",
    "AUTHORITY_SKIP_MEMBER_FLAG",
    "authority_skip_argv",
    "check_skip_variable",
]

# The two flags `render-gate-job.sh` accepts, named here because this module is
# the only thing that passes them and a renderer that does not understand one
# refuses the whole render — which `tests/consumer/
# test_delegated_gate_renderer_lockstep.py` is about.
AUTHORITY_SKIP_ENV_FLAG = "--authority-skip-env"
AUTHORITY_SKIP_MEMBER_FLAG = "--authority-skip-member"

_JUSTFILE_NAME = "justfile"

# The step a refusal is reported as. Named for the thing that could not be done
# rather than for the reading that could not be taken, because the assembly
# renders it into one sentence with "did not complete, so no gate was submitted"
# — and the fact an operator needs first is that the member was not kept out.
_AUTHORITY_SKIP_STEP = "keep-authority-members-out-of-gate-job"

# The fleet's own idiom for reading a skip list, in the one shape both consuming
# repositories write it: `read -ra skip_targets <<< "${SKIP_TARGETS:-}"`. Anchored
# to the start of a line so a `#`-comment MENTIONING the variable — and both
# recipes carry such a comment — cannot be read as the read that performs it.
_SKIP_LIST_READ = re.compile(
    r"^[ \t]*read[ \t]+(?:-[A-Za-z]+[ \t]+)*"
    r"(?P<array>[A-Za-z_][A-Za-z0-9_]*)[ \t]*<<<[ \t]*\"?\$\{(?P<variable>[A-Za-z_][A-Za-z0-9_]*)",
    re.MULTILINE,
)

# What the array a skip read fills has to be CALLED for this to be that read.
# The expansion alone is not enough: a recipe legitimately reads other
# environment into other arrays, and a mechanism that exported the member list
# into one of those would both skip nothing and clobber a value the recipe needs.
_SKIP_ARRAY_WORD = "skip"

# What a refused assembly says. The contract requires an authority-declaring
# member not to run in the gate Job, so a Job this client cannot tell is a Job
# it may not submit.
_UNTELLABLE = (
    "this repository's own `check` recipe reads its skip list from no variable this client "
    "recognises, so the gate Job cannot be told to leave out the members that declare they "
    "read an authorization held outside the tree."
)


def check_skip_variable(*, repo_root: Path) -> str | None:
    """The environment variable `repo_root`'s own `check` recipe reads its skip list from.

    `None` means the recipe names none this reader can establish, which is an
    ANSWER rather than a failure: see the module docstring for why the
    unestablished case is left to run the Job it runs today instead of being
    exported somewhere nothing reads.

    Read STATICALLY, out of the committed `justfile`, so resolving it costs one
    file read on the pre-push path and so the answer is a fact about the tree
    under test rather than about whatever the pushing shell happens to hold.

    TWO DIFFERENT NAMES RESOLVE TO NEITHER, which is the one place a first-match
    reader would have been plausible and wrong. A guessed-wrong name fails twice
    in one move and announces neither: the member that must leave the Job is not
    in the list the recipe actually skips on, so it runs and fails on the absent
    credential exactly as before, and whatever the variable that WAS written
    holds is clobbered, so members that should run may not. The same name twice
    is still one answer — both reads fill the same list, so there is nothing to
    be ambiguous about.
    """
    try:
        justfile_text = (repo_root / _JUSTFILE_NAME).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    recipe_body = extract_check_recipe_body(justfile_text=justfile_text)
    if not is_successful(recipe_body):
        return None
    named = {
        matched.group("variable")
        for matched in _SKIP_LIST_READ.finditer(recipe_body.unwrap())
        if _SKIP_ARRAY_WORD in matched.group("array").casefold()
    }
    if len(named) != 1:
        return None
    return named.pop()


def authority_skip_argv(*, repo_root: Path) -> Result[list[str], GateStepFailed]:
    """The renderer flags that keep `repo_root`'s authority members out of its gate Job.

    EMPTY ON THE SUCCESS TRACK when there is nothing to tell a Job — an
    unreadable declaration, or a repository declaring no such member. Both are
    spelled the same way, because the renderer's job is to carry a list rather
    than to grade why there is none, and a malformed declaration is not lost by
    that: `run_host_authority_members` reads the same registry on the pushing
    host and reports it as the member it names failing, which refuses the push
    whatever this Job did.

    ON THE FAILURE TRACK when the repository DOES declare such a member and this
    reader can establish no skip surface to carry it. There is nothing to pass
    and nothing safe to do with a Job that would run it, so the assembly is
    refused and no Job is submitted — see the module docstring for the two
    measured outcomes an un-told Job actually produces, one of which is a
    delegated verdict that read an authorization nobody held.
    """
    resolved = repository_authority_members(repo_root=repo_root)
    if not is_successful(resolved):
        return Success([])
    members = unsafe_perform_io(resolved.unwrap())
    if not members:
        return Success([])
    variable = check_skip_variable(repo_root=repo_root)
    if variable is None:
        return Failure(
            GateStepFailed(step=_AUTHORITY_SKIP_STEP, argv=(), returncode=None, detail=_UNTELLABLE)
        )
    return Success(
        [
            AUTHORITY_SKIP_ENV_FLAG,
            variable,
            *[flag for member in members for flag in (AUTHORITY_SKIP_MEMBER_FLAG, member)],
        ]
    )
