"""Tests for `master_health_revert_commit` — the commit the revert step requests.

Plan `red-master-self-healing` (epic `livespec-dev-tooling-zcp5vb`), work-item
`livespec-dev-tooling-7n2itg`.

WHY THIS MODULE EXISTS AT ALL is a negative measurement, and nothing asserted
here is legible without it. `docs/master-health-reconciler.md` section "The
negative verification: a web-flow revert here is UNSIGNED" records that every
revert commit GitHub minted for orchestrator PR #2918 reports
`verification.verified: false` with reason `unsigned`, as do 60 of 60 surveyed
`master` commits across two fleet repositories. The exemption in
`docs/server-side-revert-exemption.md` requires BOTH a signature verifying
against the pinned web-flow trust root AND byte-identity with the reverted
commit's parent, and it FAILS CLOSED — so an unsigned revert of a culprit that
touched product impl `.py` is convicted by `check-red-green-replay`'s
commit-range gate, and revert-by-default heals nothing for the commonest
regression there is.

NEITHER HALF OF THE EXEMPTION IS WEAKENED HERE, and that is the whole point of
the approach: the reconciler stops asking the forge to AUTHOR its revert and
asks the forge to COMMIT a revert the reconciler itself described. The gate
leg of that join — the described commit admitted when signed, refused when not
— lives beside the exemption it exercises, in
`tests/livespec_dev_tooling/checks/test_red_green_replay_revert.py`.
"""

from __future__ import annotations

import ast
from pathlib import Path

from livespec_dev_tooling.cross_repo.master_health_revert_commit import (
    FORGE_COMMIT_MUTATION,
    REVERT_COMMIT_CREDENTIAL,
    revert_commit_request,
)

_PACKAGE = Path(__file__).resolve().parents[3] / "livespec_dev_tooling" / "cross_repo"

# The 2026-10-14 incident's culprit — orchestrator PR #2917's rebase-merge —
# spelled as a full object name, because the lookup line the exemption reads out
# of the commit message is matched against 7-to-40 hex characters and a short
# sha would prove the easy half of that.
_CULPRIT_SHA = "35fea321d4e9c7b5a1f08632d9c4ee17ab095d3c"
_SHORT_CULPRIT = "35fea321d4e9"
# The branch head the revert branch is cut from, and what the mutation is told
# to expect there.
_HEAD_OID = "372f5d3dcb1a4e07f9d2b6538ac1e04d7fb9e215"


def _declared_mutations() -> set[str]:
    """Every forge mutation name a `master_health_*` module DECLARES as a constant.

    Walked as SOURCE over a GLOB — the shape `test_master_health_state` already
    uses for the no-LLM closure — so a sibling slice added later inherits this
    assertion without anyone remembering to extend this file.

    Prose may still NAME `revertPullRequest`, the API this step replaces: a
    design record that cannot name what it rejected is not a record. A DECLARED
    mutation constant may not be it.
    """
    declared: set[str] = set()
    for module in sorted(_PACKAGE.glob("master_health_*.py")):
        for node in ast.parse(module.read_text(encoding="utf-8")).body:
            if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Constant):
                continue
            names = [target.id for target in node.targets if isinstance(target, ast.Name)]
            if any(name.endswith("_MUTATION") for name in names):
                declared.add(str(node.value.value))
    return declared


def test_the_revert_step_asks_the_forge_to_commit_a_revert_the_reconciler_described() -> None:
    """The operation and the credential, both carried as DATA the transport posts.

    `createCommitOnBranch` is asserted as a LITERAL rather than against the
    module's own constant: a test comparing the request to the constant that
    produced it would pass for any value, including the revert-PR mutation this
    step exists to stop calling.

    The credential is carried for the same reason `ReconcileStep.auto_merge_held`
    is — so a transport reading the request cannot authenticate by omission.
    `GITHUB_TOKEN` is the specific omission that matters: a commit it authors
    triggers no downstream CI, so the revert's own CI would never speak and the
    release step would wait forever on a verdict nothing was going to produce.

    The `This reverts commit` line is asserted as a WHOLE LINE because that is
    what the exemption's lookup is anchored to; a sha mentioned mid-sentence
    names no ancestor to compare against.
    """
    request = revert_commit_request(
        culprit_sha=_CULPRIT_SHA, target_branch="master", expected_head_oid=_HEAD_OID
    )

    assert request.mutation == "createCommitOnBranch"
    assert request.mutation == FORGE_COMMIT_MUTATION
    assert request.credential == REVERT_COMMIT_CREDENTIAL == "github-app-installation-token"
    assert request.branch == f"master-health/revert-{_SHORT_CULPRIT}"
    assert request.expected_head_oid == _HEAD_OID
    assert f"This reverts commit {_CULPRIT_SHA}." in request.body.splitlines()
    assert _SHORT_CULPRIT in request.headline


def test_the_decision_package_declares_one_forge_mutation_and_it_builds_a_commit() -> None:
    """`createCommitOnBranch` is the ONLY forge mutation this package asks for.

    The closure, not the constant: a later slice that reintroduced
    `revertPullRequest` as a declared mutation fails here rather than at a red
    master nobody can heal, because the commits that API mints are unsigned and
    the exemption fails closed on every one of them.
    """
    assert _declared_mutations() == {"createCommitOnBranch"}
