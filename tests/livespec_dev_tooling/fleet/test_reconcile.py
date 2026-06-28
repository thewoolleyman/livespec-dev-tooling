"""Tests for `livespec_dev_tooling/fleet/_reconcile.py`.

Reconcile operations run against a canned-response, call-recording
`FleetContext`. Secret-value hygiene is asserted directly: values
reach the runner only as stdin, and never appear in outcome text.
"""

from __future__ import annotations

import base64
import json
from typing import TYPE_CHECKING

from livespec_dev_tooling.fleet._context import (
    FleetContext,
    FleetMember,
    GhResult,
    GhRunner,
    RowFinding,
    RowPass,
    RowSkip,
)
from livespec_dev_tooling.fleet._reconcile import (
    SHIM_BRANCH,
    reconcile_branch_protection,
    reconcile_merge_settings,
    reconcile_secret_names,
    reconcile_shim_workflows,
    reconcile_topic,
    shim_content,
)
from livespec_dev_tooling.fleet._rows_files import (
    BUMP_PIN_WORKFLOW,
    PIN_FRESHNESS_WORKFLOW,
    RELEASE_DISPATCH_WORKFLOW,
)
from livespec_dev_tooling.fleet._rows_github import REQUIRED_MERGE_SETTINGS
from livespec_dev_tooling.fleet.wire_fleet_member import __doc__ as wire_fleet_member_doc

if TYPE_CHECKING:
    import pytest

__all__: list[str] = []


_MEMBER = FleetMember(repo="widget", repo_class="impl-plugin")
_TREE_ARGS: tuple[str, ...] = ("api", "repos/acme/widget/git/trees/master?recursive=1")
_TOPICS_GET: tuple[str, ...] = ("api", "repos/acme/widget/topics")
_TOPICS_PUT: tuple[str, ...] = (
    "api",
    "repos/acme/widget/topics",
    "--method",
    "PUT",
    "--input",
    "-",
)
_PROTECTION_PUT: tuple[str, ...] = (
    "api",
    "repos/acme/widget/branches/master/protection",
    "--method",
    "PUT",
    "--input",
    "-",
)
_REPO_PATCH: tuple[str, ...] = (
    "api",
    "repos/acme/widget",
    "--method",
    "PATCH",
    "--input",
    "-",
)
_CI_ARGS: tuple[str, ...] = (
    "api",
    "repos/acme/widget/contents/.github/workflows/ci.yml",
    "-H",
    "Accept: application/vnd.github.raw",
)
_MASTER_REF: tuple[str, ...] = ("api", "repos/acme/widget/git/ref/heads/master")
_BRANCH_PROBE: tuple[str, ...] = ("api", f"repos/acme/widget/git/ref/heads/{SHIM_BRANCH}")
_REFS_POST: tuple[str, ...] = (
    "api",
    "repos/acme/widget/git/refs",
    "--method",
    "POST",
    "--input",
    "-",
)
_PULLS_POST: tuple[str, ...] = (
    "api",
    "repos/acme/widget/pulls",
    "--method",
    "POST",
    "--input",
    "-",
)

_CI_YML = "jobs:\n  check:\n    strategy:\n      matrix:\n        target:\n          - check-lint\n"


def _put_args(*, path: str) -> tuple[str, ...]:
    return ("api", f"repos/acme/widget/contents/{path}", "--method", "PUT", "--input", "-")


def make_context(
    *,
    table: dict[tuple[str, ...], GhResult],
    calls: list[tuple[tuple[str, ...], str | None]],
) -> FleetContext:
    """A call-recording `FleetContext` for owner `acme`."""

    def run(*, args: list[str], stdin: str | None = None) -> GhResult:
        key = tuple(args)
        calls.append((key, stdin))
        return table.get(key, GhResult(returncode=1, stdout="", stderr="no canned"))

    runner: GhRunner = run
    return FleetContext(owner="acme", run_gh=runner)


def ok(*, payload: object) -> GhResult:
    """A successful API result carrying a JSON payload."""
    return GhResult(returncode=0, stdout=json.dumps(payload), stderr="")


def test_shim_content_templates_owner_and_repo() -> None:
    body = shim_content(
        path=RELEASE_DISPATCH_WORKFLOW,
        ctx=make_context(table={}, calls=[]),
        member=_MEMBER,
    )
    assert "source_repo: widget" in body
    assert "acme/livespec-dev-tooling" in body
    assert "${{ github.event.release.tag_name }}" in body
    generic = shim_content(
        path=BUMP_PIN_WORKFLOW, ctx=make_context(table={}, calls=[]), member=_MEMBER
    )
    assert "${{ github.event.client_payload.source_repo }}" in generic


def test_reconcile_secrets_pushes_values_via_stdin_only(*, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_APP_ID", "12345")
    monkeypatch.setenv("GITHUB_PRIVATE_KEY", "PEMPEM")
    monkeypatch.delenv("APP_ID", raising=False)
    monkeypatch.delenv("APP_PRIVATE_KEY", raising=False)
    calls: list[tuple[tuple[str, ...], str | None]] = []
    table = {
        ("secret", "set", "APP_ID", "--repo", "acme/widget"): ok(payload={}),
        ("secret", "set", "APP_PRIVATE_KEY", "--repo", "acme/widget"): ok(payload={}),
    }
    ctx = make_context(table=table, calls=calls)
    outcome = reconcile_secret_names(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowPass)
    assert [stdin for _args, stdin in calls] == ["12345", "PEMPEM"]
    for args, _stdin in calls:
        assert "12345" not in " ".join(args)
        assert "PEMPEM" not in " ".join(args)
    assert "12345" not in outcome.note
    assert "PEMPEM" not in outcome.note


def test_reconcile_secrets_falls_back_to_destination_env_names(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APP_ID", "12345")
    monkeypatch.setenv("APP_PRIVATE_KEY", "PEMPEM")
    monkeypatch.delenv("GITHUB_APP_ID", raising=False)
    monkeypatch.delenv("GITHUB_PRIVATE_KEY", raising=False)
    calls: list[tuple[tuple[str, ...], str | None]] = []
    table = {
        ("secret", "set", "APP_ID", "--repo", "acme/widget"): ok(payload={}),
        ("secret", "set", "APP_PRIVATE_KEY", "--repo", "acme/widget"): ok(payload={}),
    }
    ctx = make_context(table=table, calls=calls)
    outcome = reconcile_secret_names(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowPass)
    assert [stdin for _args, stdin in calls] == ["12345", "PEMPEM"]
    for args, _stdin in calls:
        assert "12345" not in " ".join(args)
        assert "PEMPEM" not in " ".join(args)
    assert "12345" not in outcome.note
    assert "PEMPEM" not in outcome.note


def test_reconcile_secrets_missing_env_var_is_finding(*, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_APP_ID", raising=False)
    monkeypatch.delenv("GITHUB_PRIVATE_KEY", raising=False)
    monkeypatch.delenv("APP_ID", raising=False)
    monkeypatch.delenv("APP_PRIVATE_KEY", raising=False)
    outcome = reconcile_secret_names(ctx=make_context(table={}, calls=[]), member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    assert "with-livespec-env.sh" in outcome.message


def test_reconcile_secrets_failed_push_is_finding(*, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_APP_ID", raising=False)
    monkeypatch.delenv("GITHUB_PRIVATE_KEY", raising=False)
    monkeypatch.setenv("APP_ID", "12345")
    monkeypatch.setenv("APP_PRIVATE_KEY", "PEMPEM")
    outcome = reconcile_secret_names(ctx=make_context(table={}, calls=[]), member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    assert "gh secret set APP_ID failed" in outcome.message
    assert "12345" not in outcome.message


def test_wire_fleet_member_doc_invocation_preserves_uv_path() -> None:
    assert wire_fleet_member_doc is not None
    assert 'with-livespec-env.sh -- env PATH="$HOME/.local/bin:$PATH" uv run' in (
        wire_fleet_member_doc
    )


def test_reconcile_topic_applies_and_preserves_existing() -> None:
    calls: list[tuple[tuple[str, ...], str | None]] = []
    table = {
        _TOPICS_GET: ok(payload={"names": ["existing", 7]}),
        _TOPICS_PUT: ok(payload={}),
    }
    outcome = reconcile_topic(ctx=make_context(table=table, calls=calls), member=_MEMBER)
    assert isinstance(outcome, RowPass)
    put_bodies = [stdin for args, stdin in calls if args == _TOPICS_PUT]
    assert put_bodies == ['{"names": ["existing", "livespec-sibling"]}']


def test_reconcile_topic_already_present_is_idempotent_pass() -> None:
    calls: list[tuple[tuple[str, ...], str | None]] = []
    table = {_TOPICS_GET: ok(payload={"names": ["livespec-sibling"]})}
    outcome = reconcile_topic(ctx=make_context(table=table, calls=calls), member=_MEMBER)
    assert isinstance(outcome, RowPass)
    assert "already present" in outcome.note
    assert all(args != _TOPICS_PUT for args, _stdin in calls)


def test_reconcile_topic_unreadable_or_shapeless_skips() -> None:
    assert isinstance(
        reconcile_topic(ctx=make_context(table={}, calls=[]), member=_MEMBER), RowSkip
    )
    shapeless = {_TOPICS_GET: ok(payload={"names": "nope"})}
    assert isinstance(
        reconcile_topic(ctx=make_context(table=shapeless, calls=[]), member=_MEMBER), RowSkip
    )


def test_reconcile_topic_failed_put_is_finding() -> None:
    table = {_TOPICS_GET: ok(payload={"names": []})}
    outcome = reconcile_topic(ctx=make_context(table=table, calls=[]), member=_MEMBER)
    assert isinstance(outcome, RowFinding)


def test_reconcile_protection_sets_strict_off_admins_and_matrix() -> None:
    # The reconciler MUST set strict OFF per livespec NFR §"CI as a merge
    # gate (branch protection)": strict (require-branches-up-to-date)
    # injects a merge commit that violates required_linear_history and
    # buries the Red-Green-Replay trailers.
    calls: list[tuple[tuple[str, ...], str | None]] = []
    table = {
        _CI_ARGS: GhResult(returncode=0, stdout=_CI_YML, stderr=""),
        _PROTECTION_PUT: ok(payload={}),
    }
    outcome = reconcile_branch_protection(
        ctx=make_context(table=table, calls=calls), member=_MEMBER
    )
    assert isinstance(outcome, RowPass)
    body = next(stdin for args, stdin in calls if args == _PROTECTION_PUT)
    assert body is not None
    parsed = json.loads(body)
    assert parsed["enforce_admins"] is True
    assert parsed["required_status_checks"] == {"strict": False, "contexts": ["check-lint"]}
    assert parsed["restrictions"] is None


def test_reconcile_protection_without_matrix_is_finding() -> None:
    outcome = reconcile_branch_protection(ctx=make_context(table={}, calls=[]), member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    assert "manually" in outcome.message


def test_reconcile_protection_failed_put_is_finding() -> None:
    table = {_CI_ARGS: GhResult(returncode=0, stdout=_CI_YML, stderr="")}
    outcome = reconcile_branch_protection(ctx=make_context(table=table, calls=[]), member=_MEMBER)
    assert isinstance(outcome, RowFinding)


def test_reconcile_merge_settings_patches_repo_rebase_only() -> None:
    # The reconciler PATCHes the repo object to rebase-only + auto-merge,
    # per livespec NFR §"Commit and merge discipline": a freshly-
    # scaffolded repo defaults to allow_merge_commit=true, so future
    # repos must be flipped rebase-only without a manual gh api call.
    calls: list[tuple[tuple[str, ...], str | None]] = []
    table = {_REPO_PATCH: ok(payload={})}
    outcome = reconcile_merge_settings(ctx=make_context(table=table, calls=calls), member=_MEMBER)
    assert isinstance(outcome, RowPass)
    assert "rebase-only" in outcome.note
    assert "auto-merge" in outcome.note
    body = next(stdin for args, stdin in calls if args == _REPO_PATCH)
    assert body is not None
    parsed = json.loads(body)
    assert parsed == {
        "allow_merge_commit": False,
        "allow_squash_merge": False,
        "allow_rebase_merge": True,
        "allow_auto_merge": True,
    }
    assert parsed == REQUIRED_MERGE_SETTINGS


def test_reconcile_merge_settings_failed_patch_is_finding() -> None:
    outcome = reconcile_merge_settings(ctx=make_context(table={}, calls=[]), member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    assert "merge settings" in outcome.message


def _tree(*, paths: list[str]) -> GhResult:
    entries = [{"path": p, "mode": "100644"} for p in paths]
    return ok(payload={"tree": entries, "truncated": False})


def _shim_happy_table() -> dict[tuple[str, ...], GhResult]:
    return {
        _TREE_ARGS: _tree(paths=[BUMP_PIN_WORKFLOW]),
        _BRANCH_PROBE: GhResult(returncode=1, stdout="", stderr="Not Found"),
        _MASTER_REF: ok(payload={"object": {"sha": "abc123"}}),
        _REFS_POST: ok(payload={}),
        _put_args(path=PIN_FRESHNESS_WORKFLOW): ok(payload={}),
        _put_args(path=RELEASE_DISPATCH_WORKFLOW): ok(payload={}),
        _PULLS_POST: ok(payload={"number": 7}),
    }


def test_reconcile_shims_opens_one_pr_with_rendered_contents() -> None:
    calls: list[tuple[tuple[str, ...], str | None]] = []
    ctx = make_context(table=_shim_happy_table(), calls=calls)
    outcome = reconcile_shim_workflows(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowPass)
    assert PIN_FRESHNESS_WORKFLOW in outcome.note
    put_body = next(
        stdin for args, stdin in calls if args == _put_args(path=RELEASE_DISPATCH_WORKFLOW)
    )
    assert put_body is not None
    decoded = base64.b64decode(json.loads(put_body)["content"]).decode("utf-8")
    assert "source_repo: widget" in decoded
    pr_body = next(stdin for args, stdin in calls if args == _PULLS_POST)
    assert pr_body is not None
    assert json.loads(pr_body)["head"] == SHIM_BRANCH


def test_reconcile_shims_all_present_passes_without_calls_beyond_tree() -> None:
    calls: list[tuple[tuple[str, ...], str | None]] = []
    table = {
        _TREE_ARGS: _tree(
            paths=[BUMP_PIN_WORKFLOW, PIN_FRESHNESS_WORKFLOW, RELEASE_DISPATCH_WORKFLOW]
        )
    }
    outcome = reconcile_shim_workflows(ctx=make_context(table=table, calls=calls), member=_MEMBER)
    assert isinstance(outcome, RowPass)
    assert "all shim workflows present" in outcome.note
    assert len(calls) == 1


def test_reconcile_shims_once_marker_dedupes_within_run() -> None:
    ctx = make_context(table=_shim_happy_table(), calls=[])
    first = reconcile_shim_workflows(ctx=ctx, member=_MEMBER)
    assert isinstance(first, RowPass)
    second = reconcile_shim_workflows(ctx=ctx, member=_MEMBER)
    assert isinstance(second, RowPass)
    assert "already handled" in second.note


def test_reconcile_shims_existing_branch_is_idempotent_pass() -> None:
    table = _shim_happy_table()
    table[_BRANCH_PROBE] = ok(payload={"ref": f"refs/heads/{SHIM_BRANCH}"})
    outcome = reconcile_shim_workflows(ctx=make_context(table=table, calls=[]), member=_MEMBER)
    assert isinstance(outcome, RowPass)
    assert "already exists" in outcome.note


def test_reconcile_shims_unreadable_tree_skips() -> None:
    outcome = reconcile_shim_workflows(ctx=make_context(table={}, calls=[]), member=_MEMBER)
    assert isinstance(outcome, RowSkip)


def test_reconcile_shims_unresolvable_master_sha_is_finding() -> None:
    table = _shim_happy_table()
    table[_MASTER_REF] = ok(payload={"object": {}})
    outcome = reconcile_shim_workflows(ctx=make_context(table=table, calls=[]), member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    assert "master sha" in outcome.message


def test_reconcile_shims_master_ref_shapeless_is_finding() -> None:
    table = _shim_happy_table()
    table[_MASTER_REF] = ok(payload=[1])
    outcome = reconcile_shim_workflows(ctx=make_context(table=table, calls=[]), member=_MEMBER)
    assert isinstance(outcome, RowFinding)


def test_reconcile_shims_failed_branch_creation_is_finding() -> None:
    table = _shim_happy_table()
    del table[_REFS_POST]
    outcome = reconcile_shim_workflows(ctx=make_context(table=table, calls=[]), member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    assert "shim branch" in outcome.message


def test_reconcile_shims_failed_content_put_is_finding() -> None:
    table = _shim_happy_table()
    del table[_put_args(path=PIN_FRESHNESS_WORKFLOW)]
    outcome = reconcile_shim_workflows(ctx=make_context(table=table, calls=[]), member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    assert PIN_FRESHNESS_WORKFLOW in outcome.message


def test_reconcile_shims_failed_pr_creation_is_finding() -> None:
    table = _shim_happy_table()
    del table[_PULLS_POST]
    outcome = reconcile_shim_workflows(ctx=make_context(table=table, calls=[]), member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    assert "shim PR" in outcome.message
