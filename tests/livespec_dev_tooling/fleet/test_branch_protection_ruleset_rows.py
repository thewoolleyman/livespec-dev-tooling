"""The fleet `branch-protection` row and its reconcile read the EFFECTIVE required-check set.

The effective set is classic protection's required checks UNION every active
ruleset's `required_status_checks` rule on the member's default branch, per the
`branch_protection_alignment` check contract in this repository's
SPECIFICATION/contracts.md (v149), whose fleet paragraph binds the assert row and
the reconcile to the same set. These cases drive both through a canned-response
`FleetContext`, so a member holding its all-green gate in a ruleset whose only
bypass is a GitHub App is aligned, and the reconcile never writes into classic
protection a check a ruleset already requires.
"""

from __future__ import annotations

import json
import textwrap

from _gh_railway import lift_gh

from livespec_dev_tooling.fleet._context import (
    FleetContext,
    FleetMember,
    GhResult,
    GhRunner,
    RowFinding,
    RowPass,
    RowSkip,
)
from livespec_dev_tooling.fleet._reconcile import reconcile_branch_protection
from livespec_dev_tooling.fleet._rows_github import assert_branch_protection

__all__: list[str] = []

_MEMBER = FleetMember(repo="widget", repo_class="library")
_PROTECTION = ("api", "repos/acme/widget/branches/master/protection")
_TREE = ("api", "repos/acme/widget/git/trees/master?recursive=1")
_CI = (
    "api",
    "repos/acme/widget/contents/.github/workflows/ci.yml?ref=master",
    "-H",
    "Accept: application/vnd.github.raw",
)
_RULES = (
    "api",
    "--paginate",
    "--slurp",
    "repos/acme/widget/rules/branches/master?per_page=100",
)
_RULESET = ("api", "repos/acme/widget/rulesets/26758787")
_PUT = (
    "api",
    "repos/acme/widget/branches/master/protection",
    "--method",
    "PUT",
    "--input",
    "-",
)
_CI_YML = textwrap.dedent(
    """\
    name: CI
    jobs:
      check:
        strategy:
          matrix:
            target:
              - check-lint
              - check-types
        runs-on: ubuntu-latest
      ci-green:
        name: ci-green
        needs: [check]
        runs-on: ubuntu-latest
    """
)
_APP_ONLY = {"bypass_actors": [{"actor_id": 5656677, "actor_type": "Integration"}]}
_ROLE_TOO = {
    "bypass_actors": [
        {"actor_id": 5656677, "actor_type": "Integration"},
        {"actor_id": 5, "actor_type": "RepositoryRole"},
    ]
}


def _ok(*, payload: object) -> GhResult:
    return GhResult(returncode=0, stdout=json.dumps(payload), stderr="")


def _gate_rule(*, strict: bool = False) -> dict[str, object]:
    return {
        "type": "required_status_checks",
        "ruleset_id": 26758787,
        "parameters": {
            "strict_required_status_checks_policy": strict,
            "required_status_checks": [{"context": "ci-green", "integration_id": 15368}],
        },
    }


def _protection(*, contexts: list[str]) -> dict[str, object]:
    return {
        "enforce_admins": {"enabled": True},
        "required_linear_history": {"enabled": True},
        "required_status_checks": {"strict": False, "contexts": contexts},
    }


def _table(
    *,
    protection: object,
    rules: GhResult | None = None,
    ruleset: GhResult | None = None,
) -> dict[tuple[str, ...], GhResult]:
    """A member whose ci.yml declares the single-gate shape; rulesets as given."""
    return {
        _PROTECTION: _ok(payload=protection),
        _TREE: _ok(payload={"tree": [{"path": ".github/workflows/ci.yml", "mode": "100644"}]}),
        _CI: GhResult(returncode=0, stdout=_CI_YML, stderr=""),
        _RULES: rules if rules is not None else _ok(payload=[[_gate_rule()]]),
        _RULESET: ruleset if ruleset is not None else _ok(payload=_APP_ONLY),
        _PUT: _ok(payload={}),
    }


def _context(
    *, table: dict[tuple[str, ...], GhResult], calls: list[tuple[tuple[str, ...], str | None]]
) -> FleetContext:
    def run(*, args: list[str], stdin: str | None = None) -> GhResult:
        calls.append((tuple(args), stdin))
        return table.get(tuple(args), GhResult(returncode=1, stdout="", stderr="no canned"))

    runner: GhRunner = run
    return FleetContext(owner="acme", run_gh=lift_gh(runner))


def _assert(**table: object) -> tuple[object, list[tuple[tuple[str, ...], str | None]]]:
    calls: list[tuple[tuple[str, ...], str | None]] = []
    ctx = _context(table=_table(**table), calls=calls)  # type: ignore[arg-type]
    return assert_branch_protection(ctx=ctx, member=_MEMBER), calls


def test_a_gate_held_by_an_app_only_ruleset_with_no_classic_check_is_aligned() -> None:
    outcome, calls = _assert(protection=_protection(contexts=[]))
    assert outcome == RowPass()
    assert any(args == _RULES for args, _ in calls)
    assert any(args == _RULESET for args, _ in calls)


def test_an_absent_classic_status_check_object_is_empty_when_a_ruleset_holds_the_gate() -> None:
    protection = _protection(contexts=[])
    del protection["required_status_checks"]
    outcome, _ = _assert(protection=protection)
    assert outcome == RowPass()


def test_no_ruleset_and_no_classic_check_is_still_an_empty_required_set() -> None:
    outcome, _ = _assert(protection=_protection(contexts=[]), rules=_ok(payload=[[]]))
    assert isinstance(outcome, RowFinding)
    assert "required-check set is empty" in outcome.message


def test_a_non_app_bypass_on_the_contributing_ruleset_is_a_finding() -> None:
    outcome, _ = _assert(protection=_protection(contexts=[]), ruleset=_ok(payload=_ROLE_TOO))
    assert isinstance(outcome, RowFinding)
    assert "ruleset 26758787" in outcome.message
    assert "non-App" in outcome.message


def test_a_strict_contributing_ruleset_is_a_finding() -> None:
    outcome, _ = _assert(
        protection=_protection(contexts=[]), rules=_ok(payload=[[_gate_rule(strict=True)]])
    )
    assert isinstance(outcome, RowFinding)
    assert "ruleset 26758787" in outcome.message
    assert "strict" in outcome.message


def test_unreadable_ruleset_rules_skip_rather_than_pass() -> None:
    unreadable = GhResult(returncode=1, stdout="", stderr="HTTP 404")
    for table in (
        {"rules": unreadable},
        {"rules": GhResult(returncode=0, stdout="not json", stderr="")},
        {"rules": _ok(payload={"not": "pages"})},
        {"ruleset": unreadable},
        {"ruleset": GhResult(returncode=0, stdout="not json", stderr="")},
        {"ruleset": _ok(payload={"name": "no bypass list"})},
    ):
        outcome, _ = _assert(protection=_protection(contexts=[]), **table)
        assert isinstance(outcome, RowSkip), table
        assert "ruleset" in outcome.reason


def test_the_reconcile_writes_no_classic_check_when_a_ruleset_holds_the_gate() -> None:
    calls: list[tuple[tuple[str, ...], str | None]] = []
    ctx = _context(table=_table(protection=_protection(contexts=[])), calls=calls)
    outcome = reconcile_branch_protection(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowPass)
    body = json.loads(next(stdin for args, stdin in calls if args == _PUT) or "{}")
    assert body["required_status_checks"] == {"strict": False, "contexts": []}
    assert body["enforce_admins"] is True
    assert body["required_linear_history"] is True


def test_the_reconcile_keeps_the_matrix_when_no_ruleset_holds_a_check() -> None:
    calls: list[tuple[tuple[str, ...], str | None]] = []
    table = _table(protection=_protection(contexts=[]), rules=_ok(payload=[[]]))
    outcome = reconcile_branch_protection(ctx=_context(table=table, calls=calls), member=_MEMBER)
    assert isinstance(outcome, RowPass)
    body = json.loads(next(stdin for args, stdin in calls if args == _PUT) or "{}")
    assert body["required_status_checks"]["contexts"] == ["check-lint", "check-types"]


def test_the_reconcile_does_not_write_blind_when_rulesets_are_unreadable() -> None:
    calls: list[tuple[tuple[str, ...], str | None]] = []
    table = _table(
        protection=_protection(contexts=[]),
        rules=GhResult(returncode=1, stdout="", stderr="HTTP 404"),
    )
    outcome = reconcile_branch_protection(ctx=_context(table=table, calls=calls), member=_MEMBER)
    assert isinstance(outcome, RowSkip)
    assert all(args != _PUT for args, _ in calls)
