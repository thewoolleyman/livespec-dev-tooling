"""Whether this run is a DELEGATED GATE, what it is gating, and what a blind check owes.

R4.S6 (`livespec-dev-tooling-ul61`), plan livespec `k3s-on-gmktec-for-vps-usage`
(epic `livespec-sab5gn`), design in that plan's `research/003` section H, which
prescribes "a check that FAILS, rather than warns, when a target that needs a
credential runs without one inside a gate pod".

THE DEFECT THIS EXISTS TO CLOSE. `check-branch-protection-alignment` and
`check-master-ci-green` shell out to `gh api` and exit 0 with a structured
warning when `gh` carries no usable credential. That is CORRECT on a developer
laptop, where the alternative would be an unrunnable gate for every contributor
without a forge token. It is WRONG in the job that authorises a push: an
unauthenticated gate pod would report the tree green having skipped exactly the
two checks the pushing host runs authenticated. That breaks "move WHERE the gate
runs, not WHAT it runs" while appearing to honour it, and it fails toward a
FALSE GREEN, which is the direction that costs the most.

THE RULING IS NOT NEW HERE. `livespec_dev_tooling/fleet/_credential_preflight.py`
already states it for the fleet-conformance lane: "a check that cannot see must
not report a pass", and escalating a blind row to error is recorded there as a
deliberate anti-vacuous-green ruling. This module carries the same disposition to
the two `gh api` checks, for the one context that needs it.

WHY AN EXPLICIT SIGNAL RATHER THAN DETECTION. The context is declared by whoever
runs the gate, never inferred from the environment. Guessing — "am I in a
container?", "is CI set?", "does this look like Kubernetes?" — is what makes a
rule like this fire where it was not meant to, and a false FAIL on a
contributor's machine would be paid for by every push. A caller that wants the
strict disposition says so.

THE SECOND THING A GATE DECLARES (R4.S7 slice B, `livespec-dev-tooling-rwmo.2`,
same plan, `research/003` sections E and H). A token alone does not let the two
`gh api` checks run: both name their repository from the CLONE, and a gate pod's
clone is fetched from an in-cluster git daemon whose URL is not github.com and
carries no owner segment at all. So a gate declares WHAT IT IS GATING alongside
the fact THAT it is a gate — see `gate_repository` for why that is a declaration
rather than a rewritten `origin`.

SCOPE. This module reads what the RUNNER OF THE GATE declared and nothing else.
It reads no credential, probes no service, contacts no forge, and names no
check. Which targets consult it is each target's own business;
`credential-reading-targets.md` in this directory enumerates the ones that do
and what each degrades to without a credential.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

__all__: list[str] = [
    "GATE_CONTEXT_ENV",
    "GATE_REPOSITORY_ENV",
    "credential_skip_is_failure",
    "gate_repository",
    "in_gate_context",
]

# Set by the gate Job template (`ci-runner/k3s/phase2/gates/gate-job-template.yaml`)
# and by nothing else in this repository. An operator reproducing a gate run by
# hand sets it deliberately, which is the point: the strict disposition is opted
# into, never stumbled into.
GATE_CONTEXT_ENV = "LIVESPEC_GATE_CONTEXT"


def in_gate_context(*, env: Mapping[str, str]) -> bool:
    """True when this run is a delegated gate that authorises a push.

    The environment is INJECTED rather than read from the process, so a test can
    never depend on the host's environment and a caller can never be surprised by
    a variable it did not consider. An empty value reads as unset, matching this
    repository's severity-lever idiom (see `no_todo_registry`).
    """
    return bool(env.get(GATE_CONTEXT_ENV, ""))


# Set beside `GATE_CONTEXT_ENV` by the same gate Job template, and read ONLY
# where that one is set (see `gate_repository`).
GATE_REPOSITORY_ENV = "LIVESPEC_GATE_REPOSITORY"
# `<owner>/<repo>` and nothing else. The value is pasted straight into a
# `gh api repos/...` path, so its shape is checked before use: a bare repository
# name, a clone URL, or a path carrying a third segment are each a form a
# hand-set variable plausibly holds, and each would otherwise become a request
# for something that is not a repository. Both segments use GitHub's own
# vocabulary — alphanumerics with `-`, `_` and `.`.
_OWNER_REPO_PATTERN = re.compile(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$")


def gate_repository(*, env: Mapping[str, str]) -> str | None:
    """The `<owner>/<repo>` this gate is judging, or None when it named none.

    THE PROBLEM. `branch_protection_alignment` and `master_ci_green` both name
    their repository from the clone they are run in — the first parses
    `git remote get-url origin` against a github.com-only pattern, the second
    hands `gh` the `{owner}`/`{repo}` placeholders it expands from that same
    remote. A gate pod's origin is `git://git-gates.gates.svc.cluster.local/
    <repo>.git`, which is neither github.com nor owner-qualified, so with a
    perfectly good token in hand both checks fail to identify what they are
    gating.

    WHY A DECLARATION RATHER THAN A REWRITTEN ORIGIN. `origin` in a gate pod is
    load-bearing for something else: the initContainer fetches the gate ref AND
    its `.base` companion into `refs/remotes/origin/master`, the name eight
    range-judging members of the aggregate resolve. Repointing it at github.com
    would either break that fetch or demand a second remote the github.com-only
    pattern still would not read.

    WHY IT IS INERT OUTSIDE A GATE. Read unconditionally, an environment
    variable naming a repository would let anything in a contributor's shell
    silently point `check-master-ci-green` at a repository they are not on — and
    have it report THAT repository's master as this one's. Honouring it only
    where the gate context is declared keeps the blast radius inside the pod
    that set both, and makes the variable unforgeable as a lever: on any host
    that is not a gate it does nothing at all.

    A value that is not an owner/repo pair reads as ABSENT rather than raising.
    Inside a gate that is a FAILURE at the caller (a check that cannot name its
    repository must not report a pass), which is a better answer than a request
    nobody can read.
    """
    if not in_gate_context(env=env):
        return None
    declared = env.get(GATE_REPOSITORY_ENV, "").strip()
    if _OWNER_REPO_PATTERN.match(declared) is None:
        return None
    return declared


def credential_skip_is_failure(*, env: Mapping[str, str]) -> bool:
    """True when a check that could not read its credential must FAIL rather than skip.

    Named for the DECISION rather than for the context, so a caller reads the
    consequence at the call site instead of re-deriving it. Today the two
    coincide; keeping them separate means a future context that also demands the
    strict disposition does not have to be called a gate.
    """
    return in_gate_context(env=env)
