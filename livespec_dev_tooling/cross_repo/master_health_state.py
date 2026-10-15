"""The recorded-GitHub-state vocabulary the master-health reconciler decides over.

Per `SPECIFICATION/contracts.md` section "Cross-repo coordination automation
surface", and the design recorded in this repository's
`plan/red-master-self-healing/research/001-charter-red-master-self-healing.md`
(child C1, work-item `livespec-dev-tooling-hrpcgl`).

GITHUB IS THE STATE. The reconciler holds no durable state of its own: each run
reads current truth from the forge, decides AT MOST ONE next step, and stops. So
crashes, missed runs and duplicate runs cannot wedge it — there is no checkpoint
to corrupt and no cursor to lose. Everything the decision needs is therefore a
field on a value in THIS module, and nothing the decision needs is read from
disk, a cache or a prior run.

These types are plain frozen dataclasses rather than a parsed forge payload on
purpose: they are the SEAM between the network-touching workflow that gathers
the state and the pure decision that consumes it. The `cross_repo` package is
network-I/O-free (see this package's `__init__`), so the gathering lives in the
reusable workflow and every rule in the sibling modules stays replay-testable
against a recorded state built in-process.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__: list[str] = [
    "CI_CANCELLED",
    "CI_FAILURE",
    "CI_PENDING",
    "CI_SUCCESS",
    "RERUN_NOT_ATTEMPTED",
    "RERUN_PASSED",
    "RERUN_STILL_RED",
    "MasterCommit",
    "ReconcileConfig",
    "ReconcileState",
    "RevertPullRequest",
]

# The four CI conclusions the decision distinguishes. `CI_SUCCESS` is the ONLY
# one that reads as green: `CI_CANCELLED` and `CI_PENDING` are UNDECIDED, not
# green and not red, and conflating either with success is how a reconciler
# reverts a commit whose CI never actually spoke.
CI_SUCCESS = "success"
CI_FAILURE = "failure"
CI_CANCELLED = "cancelled"
CI_PENDING = "pending"

# Whether this episode's failed jobs have been re-run once, and what that said.
# The re-run is the cheap bounded classifier that separates a flake from a
# genuine regression; `RERUN_NOT_ATTEMPTED` is what makes "re-run once" a step
# the reconciler can still take rather than a fact it has to remember.
RERUN_NOT_ATTEMPTED = "not-attempted"
RERUN_PASSED = "passed"
RERUN_STILL_RED = "still-red"


@dataclass(frozen=True, kw_only=True)
class MasterCommit:
    """One commit on the watched branch, with the verdict its own CI reached.

    `parent_sha` is what the culprit rule walks: ancestry is read from this
    field rather than from the position of the commit in a list, so a caller
    that hands over its commits newest-first, oldest-first or unordered gets
    the same answer. `pull_request` is the PR whose merge minted this commit,
    and is `None` for a direct push — a commit the revert step cannot act on,
    because there is no pull request to revert.

    `failure_signature` identifies WHAT failed (a check name, a job name) and is
    `None` exactly when the commit is not red. It is compared across commits to
    recognise a failure that is not attributable to this merge.

    `ci_workflow` names the workflow whose run reached `ci_conclusion`, and it
    is REQUIRED rather than defaulted because a record whose workflow is
    unrecorded would read as the gating one and let a non-gating failure start
    an episode. One commit may therefore carry SEVERAL records, one per
    workflow that ran on it; `master_health_gating` keeps only the gating
    workflow's before any rule indexes the window.

    `subject` is the commit's subject line, carried RAW so the rules that read
    it stay in the decision and under test — see `master_health_commit_shape`.
    It is required for the same reason `ci_workflow` is: a record whose subject
    is unrecorded would read as an ordinary merge, and an ordinary merge is
    exactly what those rules route away from the plain revert.
    """

    sha: str
    parent_sha: str
    pull_request: int | None
    ci_workflow: str
    ci_conclusion: str
    failure_signature: str | None
    subject: str


@dataclass(frozen=True, kw_only=True)
class RevertPullRequest:
    """The revert pull request already in flight for this episode, if any.

    Its presence is what makes a duplicate reconcile run harmless: the step
    table reaches "open a revert" only when this is `None`, so the forge state
    itself — not a lock, a cursor or a dedupe key — is what stops a second
    revert from being opened.

    `auto_merge_armed` records whether the hold has ALREADY been released, which
    is the same idempotence for the release step that this value's existence is
    for the open step. `fix_forward_claim` names the claimed fix-forward (a
    label or comment naming a fix PR) and is `None` when nothing is claimed;
    this module's consumer only distinguishes claimed from unclaimed, because
    judging a claim's PROGRESS is child C2's work, not C1's.
    """

    number: int
    reverts_pull_request: int
    ci_conclusion: str
    auto_merge_armed: bool
    fix_forward_claim: str | None


@dataclass(frozen=True, kw_only=True)
class ReconcileConfig:
    """The committed configuration half of the decision's inputs.

    `target_branch` is a PARAMETER rather than the literal `master` so the
    scheduled end-to-end drill can exercise the whole path against a throwaway
    branch, which is the only way to prove the revert path without reddening a
    real master.

    `infra_outage_markers` are the substrings that identify a failure as an
    infrastructure outage rather than a regression (no runner matching the
    labels, an expired token, a registry that is down). They live in committed
    configuration because the alternative is asking a model to judge the
    failure text, and no LLM may reach this decision path.

    `gating_workflow` names the ONE workflow whose verdict decides whether the
    branch is red: the one whose all-green gate job is the required status
    check branch protection evaluates. It is committed configuration rather
    than a constant because the name is a per-repository fact, and it carries
    no default for the reason `MasterCommit.ci_workflow` carries none.
    """

    target_branch: str
    infra_outage_markers: tuple[str, ...]
    gating_workflow: str


@dataclass(frozen=True, kw_only=True)
class ReconcileState:
    """Everything one reconcile run read from the forge about one branch.

    `head_sha` is supplied rather than derived: the branch head is a fact the
    caller already holds, and deriving it from `commits` by elimination would
    invent an answer for a truncated or disordered window instead of using the
    one the forge gave.

    `open_needs_attention_episodes` carries the episode keys that already have
    an open needs-attention issue, so raising one is open-or-update rather than
    open-again. `unrelated_failure_signatures` carries signatures observed
    OUTSIDE this episode; a failure that also appears there is not attributable
    to this merge, which is one of the three ways a red master is classified as
    something a revert would not fix.
    """

    head_sha: str
    commits: tuple[MasterCommit, ...]
    rerun_outcome: str
    revert_pull_request: RevertPullRequest | None
    open_needs_attention_episodes: tuple[str, ...]
    unrelated_failure_signatures: tuple[str, ...]
