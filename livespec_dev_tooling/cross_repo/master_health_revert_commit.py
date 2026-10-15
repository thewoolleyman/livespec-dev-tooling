"""Build the revert COMMIT the master-health reconciler's revert step requests.

Per `SPECIFICATION/contracts.md` section "Cross-repo coordination automation
surface", the design in this repository's
`plan/red-master-self-healing/research/001-charter-red-master-self-healing.md`
(epic `livespec-dev-tooling-zcp5vb`), and the negative verification recorded in
`docs/master-health-reconciler.md` section "The negative verification: a
web-flow revert here is UNSIGNED" (work-item `livespec-dev-tooling-7n2itg`).

THE RECONCILER DESCRIBES THE REVERT COMMIT; THE FORGE ONLY COMMITS IT. The
charter expected the revert to be a web-flow revert through the GraphQL
`revertPullRequest` mutation, "so it carries the signing the server-side-revert
exemption recognises". Measured 2026-10-14, it does not: every revert commit
GitHub minted for orchestrator PR #2918 reports `verification.verified: false`
with reason `unsigned`, as do 60 of 60 surveyed `master` commits across two
fleet repositories. The exemption in `docs/server-side-revert-exemption.md`
requires BOTH a signature verifying against the pinned web-flow trust root AND
byte-identity with the reverted commit's parent, and it FAILS CLOSED — so an
unsigned revert of a culprit that touched product impl `.py` is convicted by
`check-red-green-replay`'s commit-range gate, and revert-by-default heals
nothing for the commonest regression there is.

NEITHER HALF OF THE EXEMPTION MOVES. What moves is the only thing in that
pipeline that was ever ours: the reconciler stops asking the forge to AUTHOR
its revert and asks the forge to COMMIT a revert the reconciler itself
described, through `createCommitOnBranch` authenticated with the fleet GitHub
App installation token (`SPECIFICATION/contracts.md` section "GitHub App auth
model"). Whether the forge signs an App-authored commit is a LIVE MEASUREMENT
no sandbox can make — it needs a fleet repository and the App's private key —
and if it comes back unsigned the finding belongs on the plan epic rather than
in a weakened exemption.

THE REQUEST IS DATA, NOT A CALL. This package is network-I/O-free (see this
package's `__init__`), so the mutation is BUILT here and POSTED by the reusable
workflow, exactly as the decision table is computed here and acted on there.
That is also what keeps every claim about the revert replay-testable: the
request a given recorded forge state produces is a value a test can compare,
where a call would only be a thing that happened.

WHY THE CALLER PASSES THE CULPRIT'S DIFF RATHER THAN THE STEP. WHICH commit is
the culprit is `master_health_reconcile`'s answer; WHAT that commit changed is a
further forge read worth making only once the step says to open a revert. The
shape is therefore two-phase on purpose — decide, gather, build — and this
module takes the gathered half.

⚠️ WHAT RESTORING THE PARENT'S BYTES DOES NOT PROMISE. The request restores the
bytes the culprit's parent held, at the paths the culprit changed, and nothing
narrows that by what landed afterwards: if a LATER commit on the branch touched
one of those paths, the revert overwrites it too. That is the same state a
`git revert` would stop on as a conflict, and it is deliberately NOT resolved
here — a hand-resolved conflict is new code the exemption's byte-identity half
would (correctly) refuse, so inventing one would trade a visible clobber for an
invisible conviction. Whether to refuse such an episode outright and raise a
needs-attention item instead is a decision for the fix-forward child, which is
where "the revert may not be safe" already lives.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass

__all__: list[str] = [
    "FORGE_COMMIT_MUTATION",
    "REVERT_COMMIT_CREDENTIAL",
    "CulpritPath",
    "FileAddition",
    "RevertCommitRequest",
    "revert_commit_request",
]

# The forge operation that COMMITS a tree the caller describes. It is the whole
# substitution this module exists for, so it is named once, here, and the
# sibling test asserts that no `master_health_*` module declares any other.
FORGE_COMMIT_MUTATION = "createCommitOnBranch"

# The ONE credential the revert commit may be built with, carried as DATA for
# the same reason `ReconcileStep.auto_merge_held` is: a transport reading the
# request cannot authenticate by omission. `GITHUB_TOKEN` is the omission that
# matters — a commit it authors triggers no downstream CI (GitHub's
# workflow-recursion ceiling), so the revert's own CI would never speak and the
# release step would wait forever on a verdict nothing was going to produce.
REVERT_COMMIT_CREDENTIAL = "github-app-installation-token"

# The revert branch is derived from the CULPRIT rather than from the run, so a
# duplicate reconcile run computes the same name and finds the branch already
# there. Same idempotence argument as the rest of the reconciler: the forge
# state, not a lock or a cursor, is what stops a second revert.
_REVERT_BRANCH_PREFIX = "master-health/revert-"
_SHORT_SHA_CHARS = 12


@dataclass(frozen=True, kw_only=True)
class CulpritPath:
    """One path the culprit merge changed, with the bytes its PARENT held there.

    `parent_contents` is `None` exactly when the parent held nothing at this
    path — the culprit CREATED it. That distinction is the whole reason this is
    a record rather than a plain mapping: the correct revert of a created path
    is a DELETION, and an empty addition would leave behind a module no commit
    ever earned evidence for while also differing from the parent at that path,
    which loses the exemption's byte-identity half.

    Bytes, not text, because the restoration is byte-for-byte: a path the
    culprit changed may hold anything a repository can hold, and decoding it to
    pass it through `str` would corrupt exactly the contents nobody reviews.
    """

    path: str
    parent_contents: bytes | None


@dataclass(frozen=True, kw_only=True)
class FileAddition:
    """One `fileChanges.additions` entry: a path, and its contents base64-encoded.

    The encoding happens here rather than at the transport because it is part of
    the mutation's own input shape, and because a request that is already
    exactly what gets posted is a request a replay test can compare.
    """

    path: str
    contents: str


@dataclass(frozen=True, kw_only=True)
class RevertCommitRequest:
    """One `createCommitOnBranch` mutation, as the data a transport posts.

    `expected_head_oid` is the oid the mutation is told to expect at `branch`,
    which is what makes the post safe to retry: a branch that moved under the
    request fails the mutation rather than committing against a tree the
    reconciler never read.

    `headline` and `body` are separate because the mutation's `message` input
    is. The body carries the `This reverts commit <sha>.` line on its OWN line,
    which is not decoration: it is the lookup the server-side-revert exemption
    reads to decide which ancestor the restored bytes are compared against.

    `additions` and `deletions` are the mutation's `fileChanges`, and they are
    DISJOINT by construction below — a path is restored or removed, never both.
    """

    mutation: str
    credential: str
    branch: str
    expected_head_oid: str
    headline: str
    body: str
    additions: tuple[FileAddition, ...]
    deletions: tuple[str, ...]


def _encoded(*, contents: bytes) -> str:
    """`contents` as the base64 the mutation's `additions` entries carry."""
    return base64.b64encode(contents).decode("ascii")


def revert_commit_request(
    *,
    culprit_sha: str,
    culprit_paths: tuple[CulpritPath, ...],
    target_branch: str,
    expected_head_oid: str,
) -> RevertCommitRequest:
    """The mutation one `STEP_OPEN_REVERT` run asks the forge for.

    The caller is the reusable workflow, which has already read the step out of
    `master_health_reconcile.reconcile_step` — so the culprit is passed in
    rather than re-derived here, and this module stays a builder with one job
    rather than a second copy of the decision table.

    The file changes are ordered BY PATH rather than by however the caller
    enumerated the culprit's diff, so the request is a function of the forge
    state alone: two runs reading the same culprit build the same request, which
    is the property that makes a duplicate reconcile run harmless here as well
    as in the decision table.
    """
    ordered = sorted(culprit_paths, key=lambda changed: changed.path)
    return RevertCommitRequest(
        mutation=FORGE_COMMIT_MUTATION,
        credential=REVERT_COMMIT_CREDENTIAL,
        branch=f"{_REVERT_BRANCH_PREFIX}{culprit_sha[:_SHORT_SHA_CHARS]}",
        expected_head_oid=expected_head_oid,
        additions=tuple(
            FileAddition(path=changed.path, contents=_encoded(contents=changed.parent_contents))
            for changed in ordered
            if changed.parent_contents is not None
        ),
        deletions=tuple(changed.path for changed in ordered if changed.parent_contents is None),
        headline=(
            f"chore(revert): undo {culprit_sha[:_SHORT_SHA_CHARS]} "
            f"to return {target_branch} to green"
        ),
        body=(
            f"This reverts commit {culprit_sha}.\n"
            "\n"
            "Built by the master-health reconciler's revert step, which "
            "describes the\nrevert commit itself rather than asking the forge "
            "to author one.\n"
        ),
    )
