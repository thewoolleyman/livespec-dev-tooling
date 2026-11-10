"""wire-fleet-member does not arm the reconciler ahead of hosted-runner reachability.

Independent review of livespec-dev-tooling#4013, MEDIUM finding 1
(livespec-dev-tooling-ariayn): `reconcile_master_health_shim` installed the
shim into any member, so running wire-fleet-member for livespec-dev-tooling
would arm a reconciler whose every acting pass fails closed, because a
GitHub-hosted runner cannot yet reach the tailnet-only observer. Adoption
first, then arming: a member with an observer gets the shim only once a
reachability proof is recorded in the committed
`master_health_observer.HOSTED_REACHABILITY_PROOFS`.
"""

from __future__ import annotations

import json

from _gh_railway import lift_gh

from livespec_dev_tooling import master_health_observer
from livespec_dev_tooling.fleet._context import FleetContext, FleetMember, GhResult, RowFinding
from livespec_dev_tooling.fleet._reconcile_shims import (
    SHIM_BRANCH,
    reconcile_master_health_shim,
    reconcile_shim_workflows,
)
from livespec_dev_tooling.fleet._reconciler_shim import MASTER_HEALTH_WORKFLOW
from livespec_dev_tooling.fleet._rows_files import (
    BUMP_PIN_WORKFLOW,
    PIN_FRESHNESS_WORKFLOW,
    RELEASE_DISPATCH_WORKFLOW,
)

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-ariayn
_OBSERVED = ("thewoolleyman", "livespec-dev-tooling")
_UNOBSERVED = ("acme", "widget")
_PROOF = "https://github.com/thewoolleyman/livespec-dev-tooling/actions/runs/123456789"
_PIN_AND_BUMP = (BUMP_PIN_WORKFLOW, PIN_FRESHNESS_WORKFLOW, RELEASE_DISPATCH_WORKFLOW)


def _ok(*, payload: object) -> GhResult:
    return GhResult(returncode=0, stdout=json.dumps(payload), stderr="")


def _context(*, owner: str, repo: str, present: tuple[str, ...], calls: list[tuple[str, ...]]):
    base = f"repos/{owner}/{repo}"
    table = {
        ("api", f"{base}/git/trees/master?recursive=1"): _ok(
            payload={"tree": [{"path": p, "mode": "100644"} for p in present], "truncated": False}
        ),
        ("api", f"{base}/git/ref/heads/{SHIM_BRANCH}"): GhResult(
            returncode=1, stdout="", stderr="Not Found"
        ),
        ("api", f"{base}/git/ref/heads/master"): _ok(payload={"object": {"sha": "abc123"}}),
        ("api", f"{base}/git/refs", "--method", "POST", "--input", "-"): _ok(payload={}),
        ("api", f"{base}/pulls", "--method", "POST", "--input", "-"): _ok(payload={"number": 7}),
    }
    for path in (*_PIN_AND_BUMP, MASTER_HEALTH_WORKFLOW):
        table[("api", f"{base}/contents/{path}", "--method", "PUT", "--input", "-")] = _ok(
            payload={}
        )

    def run(*, args: list[str], stdin: str | None = None) -> GhResult:
        _ = stdin
        calls.append(tuple(args))
        return table.get(tuple(args), GhResult(returncode=1, stdout="", stderr="no canned"))

    return FleetContext(owner=owner, run_gh=lift_gh(run)), FleetMember(
        repo=repo, repo_class="impl-plugin"
    )


def _written(*, calls: list[tuple[str, ...]]) -> list[str]:
    """Every path the run PUT into the member, and whether it opened a pull request."""
    return [
        args[1].split("/contents/", 1)[1] if "/contents/" in args[1] else args[1].rsplit("/", 1)[1]
        for args in calls
        if "--method" in args
    ]


def test_an_observed_member_without_a_reachability_proof_is_refused_by_name():
    calls: list[tuple[str, ...]] = []
    ctx, member = _context(
        owner=_OBSERVED[0], repo=_OBSERVED[1], present=_PIN_AND_BUMP, calls=calls
    )

    outcome = reconcile_master_health_shim(ctx=ctx, member=member)

    assert isinstance(outcome, RowFinding)
    assert outcome.message.startswith(
        "livespec-dev-tooling: refusing to install .github/workflows/master-health-reconcile.yml:"
        " the repository has an incident observer"
    )
    assert "HOSTED_REACHABILITY_PROOFS" in outcome.message
    assert _written(calls=calls) == []


def test_a_malformed_proof_is_not_a_proof(monkeypatch):
    monkeypatch.setattr(
        master_health_observer,
        "HOSTED_REACHABILITY_PROOFS",
        {"thewoolleyman/livespec-dev-tooling": "proven, trust me"},
    )
    calls: list[tuple[str, ...]] = []
    ctx, member = _context(
        owner=_OBSERVED[0], repo=_OBSERVED[1], present=_PIN_AND_BUMP, calls=calls
    )

    outcome = reconcile_master_health_shim(ctx=ctx, member=member)

    assert isinstance(outcome, RowFinding)
    assert _written(calls=calls) == []


def test_a_recorded_hosted_run_admits_the_install(monkeypatch):
    monkeypatch.setattr(
        master_health_observer,
        "HOSTED_REACHABILITY_PROOFS",
        {"thewoolleyman/livespec-dev-tooling": _PROOF},
    )
    calls: list[tuple[str, ...]] = []
    ctx, member = _context(
        owner=_OBSERVED[0], repo=_OBSERVED[1], present=_PIN_AND_BUMP, calls=calls
    )

    _ = reconcile_master_health_shim(ctx=ctx, member=member)

    assert _written(calls=calls) == ["refs", MASTER_HEALTH_WORKFLOW, "pulls"]


def test_a_member_with_no_observer_is_installed_as_before():
    calls: list[tuple[str, ...]] = []
    ctx, member = _context(
        owner=_UNOBSERVED[0], repo=_UNOBSERVED[1], present=_PIN_AND_BUMP, calls=calls
    )

    _ = reconcile_master_health_shim(ctx=ctx, member=member)

    assert _written(calls=calls) == ["refs", MASTER_HEALTH_WORKFLOW, "pulls"]


def test_the_shared_shim_install_leaves_out_only_the_unarmed_reconciler():
    """The pin-and-bump rows' install path must not arm the reconciler either."""
    calls: list[tuple[str, ...]] = []
    ctx, member = _context(owner=_OBSERVED[0], repo=_OBSERVED[1], present=(), calls=calls)

    _ = reconcile_shim_workflows(ctx=ctx, member=member)

    assert _written(calls=calls) == ["refs", *_PIN_AND_BUMP, "pulls"]


def test_an_observed_member_missing_only_the_reconciler_gets_no_pull_request():
    calls: list[tuple[str, ...]] = []
    ctx, member = _context(
        owner=_OBSERVED[0], repo=_OBSERVED[1], present=_PIN_AND_BUMP, calls=calls
    )

    outcome = reconcile_shim_workflows(ctx=ctx, member=member)

    assert _written(calls=calls) == []
    assert not isinstance(outcome, RowFinding)
