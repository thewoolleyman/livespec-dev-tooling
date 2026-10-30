"""The recorded-GitHub-state vocabulary the master-health reconciler decides over.

Per `SPECIFICATION/contracts.md` section "Master-health reconciler",
and the design recorded in this repository's
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
    "FIX_CLOSED",
    "FIX_MERGED",
    "FIX_OPEN",
    "RERUN_NOT_ATTEMPTED",
    "RERUN_PASSED",
    "RERUN_STILL_RED",
    "FixCommit",
    "FixForwardClaim",
    "FixPullRequest",
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

# The three states a fix pull request can be recorded in. A fix that is neither
# open nor merged was closed without landing, which can make no further forward
# transition.
FIX_OPEN = "open"
FIX_MERGED = "merged"
FIX_CLOSED = "closed"


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

    `ci_completed_at` is when that CI run concluded, in epoch seconds, and is
    what the hard cap measures how long `master` has been red from. It is
    `None` when the forge did not report it, which makes a claim not hold
    rather than guessing an age.

    `changed_paths` are the paths the commit changed (a rename lists both its
    old and new path). It is recorded for the commits inside a red episode and
    is `None` when the forge did not report it or the list was truncated; the
    revert guard reads that as "cannot show a revert is safe", never as "no
    overlap".
    """

    sha: str
    parent_sha: str
    pull_request: int | None
    ci_workflow: str
    ci_conclusion: str
    failure_signature: str | None
    subject: str
    ci_completed_at: int | None = None
    changed_paths: tuple[str, ...] | None = None


@dataclass(frozen=True, kw_only=True)
class FixForwardClaim:
    """One comment on the revert pull request, carried RAW.

    The comment body is carried unparsed so that WHICH fix it names and whether
    it carries a `Claimed-By:` line are decided in the pure module under test,
    never by the gatherer. `posted_at` is epoch seconds and starts the first
    step's clock.
    """

    author: str
    body: str
    posted_at: int


@dataclass(frozen=True, kw_only=True)
class FixCommit:
    """One commit of a fix pull request, with the CI the forge reported on it.

    `failing_checks` lists one entry per failed check RUN, so a check that failed
    again on a re-run of the same commit appears twice: that repetition is the
    "same check fails repeatedly" evidence. `ci_conclusion` uses the
    `CI_*` vocabulary, and `CI_CANCELLED` and `CI_PENDING` are undecided.
    """

    sha: str
    pushed_at: int
    ci_conclusion: str
    ci_started_at: int | None
    ci_finished_at: int | None
    failing_checks: tuple[str, ...]


@dataclass(frozen=True, kw_only=True)
class FixPullRequest:
    """The recorded state of one fix pull request a claim names.

    `commits` are OLDEST-FIRST. `master_ci_conclusion` and `master_ci_started_at`
    describe the gating CI run on the fix's merge commit and are `None` until
    that run exists. Every timestamp is epoch seconds; the forward-transition
    clock is the newest of them, so a field the gatherer cannot read is `None`
    rather than a guess.
    """

    number: int
    state: str
    opened_at: int
    commits: tuple[FixCommit, ...]
    auto_merge_armed_at: int | None
    merged_at: int | None
    master_ci_conclusion: str | None
    master_ci_started_at: int | None


@dataclass(frozen=True, kw_only=True)
class RevertPullRequest:
    """The revert pull request already in flight for this episode, if any.

    Its presence is what makes a duplicate reconcile run harmless: the step
    table reaches "open a revert" only when this is `None`, so the forge state
    itself — not a lock, a cursor or a dedupe key — is what stops a second
    revert from being opened.

    `auto_merge_armed` records whether the hold has ALREADY been released, which
    is the same idempotence for the release step that this value's existence is
    for the open step. `claims` are the comments posted on this pull request,
    raw, and `culprit_opened_by` is the login that opened the culprit pull
    request: the two facts the claimant set is judged against.
    `fix_pull_requests` carries the recorded state of every pull request a
    `Fix-Forward:` line in those comments names, valid claimant or not.
    """

    number: int
    reverts_pull_request: int
    ci_conclusion: str
    auto_merge_armed: bool
    culprit_opened_by: str | None = None
    claims: tuple[FixForwardClaim, ...] = ()
    fix_pull_requests: tuple[FixPullRequest, ...] = ()


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

    `unrelated_lookback_commits` is how far BELOW the current episode the
    recurring-failure read may look for the same failing check — counted in
    commits, because the decision path holds no clock (see
    `master_health_flake_history` for why the bound is load-bearing).

    The last six fields are the fix-forward half. `maintainer_login` is the
    forge login whose claim is always valid; `hard_cap_minutes` and the four
    `stall_*_minutes` are how long `master` may stay red and how long a claimed
    fix may go without a forward transition in each step. EACH IS `None` WHEN
    MISSING OR MALFORMED AND NONE CARRIES A BUILT-IN DEFAULT, deliberately: the
    fleet default is provisioned into committed configuration, and a number
    baked in here would silently stand in for a missing key and defeat the
    fail-closed clause. A `None` limit makes every claim not hold.
    """

    target_branch: str
    infra_outage_markers: tuple[str, ...]
    gating_workflow: str
    unrelated_lookback_commits: int
    maintainer_login: str | None = None
    hard_cap_minutes: int | None = None
    stall_claim_to_fix_pr_minutes: int | None = None
    stall_ci_in_flight_minutes: int | None = None
    stall_fix_to_merge_minutes: int | None = None
    stall_merged_to_green_minutes: int | None = None


@dataclass(frozen=True, kw_only=True)
class ReconcileState:
    """Everything one reconcile run read from the forge about one branch.

    `head_sha` is supplied rather than derived: the branch head is a fact the
    caller already holds, and deriving it from `commits` by elimination would
    invent an answer for a truncated or disordered window instead of using the
    one the forge gave.

    `open_needs_attention_episodes` carries the episode keys that already have
    an open needs-attention issue, so raising one is open-or-update rather than
    open-again.

    THERE IS NO PRE-COMPUTED "FAILED ELSEWHERE" FIELD, and that is deliberate.
    One used to live here, filled in by the gatherer, and it carried no DISTANCE
    — so the decision could not tell a failure from ten minutes ago from one
    three months old, and the bounded rule the episode calibration asks for was
    not expressible over it. `commits` is the single source for that evidence
    now: a red commit recorded below a green one is a previous episode, which is
    what `master_health_flake_history` reads.

    `observed_at` is NOW, in epoch seconds, supplied by the gatherer so the
    decision path holds no clock of its own; `None` means it was not recorded,
    which makes every fix-forward claim not hold.
    """

    head_sha: str
    commits: tuple[MasterCommit, ...]
    rerun_outcome: str
    revert_pull_request: RevertPullRequest | None
    open_needs_attention_episodes: tuple[str, ...]
    observed_at: int | None = None
