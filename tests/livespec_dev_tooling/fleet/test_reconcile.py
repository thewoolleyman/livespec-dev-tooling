"""Tests for `livespec_dev_tooling/fleet/_reconcile.py`.

Reconcile operations run against a canned-response, call-recording
`FleetContext`. Secret-value hygiene is asserted directly: values
reach the runner only as stdin, and never appear in outcome text.
"""

from __future__ import annotations

import base64
import json
from typing import TYPE_CHECKING

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
from livespec_dev_tooling.fleet._reconcile import (
    _rewrap_pem,
    reconcile_branch_protection,
    reconcile_delete_branch_on_merge,
    reconcile_merge_settings,
    reconcile_secret_names,
    reconcile_topic,
)
from livespec_dev_tooling.fleet._reconcile_shims import (
    SHIM_BRANCH,
    reconcile_shim_workflows,
    shim_content,
)
from livespec_dev_tooling.fleet._rows_files import (
    BUMP_PIN_WORKFLOW,
    CI_WORKFLOW,
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
    "repos/acme/widget/contents/.github/workflows/ci.yml?ref=master",
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
# main-default-repo argv shapes (livespec-dev-tooling-17o): when the canned
# table answers the `repos/acme/widget` lookup with `default_branch: main`,
# `FleetContext.canonical_ref` resolves `main` and every reconcile read AND
# write must target it — never a hardcoded `master`.
_REPO_GET: tuple[str, ...] = ("api", "repos/acme/widget")
_CI_ARGS_MAIN: tuple[str, ...] = (
    "api",
    "repos/acme/widget/contents/.github/workflows/ci.yml?ref=main",
    "-H",
    "Accept: application/vnd.github.raw",
)
_PROTECTION_PUT_MAIN: tuple[str, ...] = (
    "api",
    "repos/acme/widget/branches/main/protection",
    "--method",
    "PUT",
    "--input",
    "-",
)
_TREE_ARGS_MAIN: tuple[str, ...] = ("api", "repos/acme/widget/git/trees/main?recursive=1")
_MAIN_REF: tuple[str, ...] = ("api", "repos/acme/widget/git/ref/heads/main")

_CI_YML = "jobs:\n  check:\n    strategy:\n      matrix:\n        target:\n          - check-lint\n"
# The member tree carrying ci.yml. Required now that the row separates a
# ci.yml that is ABSENT from one this run failed to READ: without it the
# reconcile skips instead of deriving the matrix.
_CI_TREE = GhResult(
    returncode=0,
    stdout=json.dumps({"tree": [{"path": CI_WORKFLOW, "mode": "100644"}], "truncated": False}),
    stderr="",
)


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
    return FleetContext(owner="acme", run_gh=lift_gh(runner))


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


def test_rewrap_pem_normalizes_collapsed_single_line_key() -> None:
    # The 1Password Environment stores GITHUB_PRIVATE_KEY as a collapsed
    # single-line PEM (interior newlines stripped). Piped verbatim to
    # `gh secret set`, that value fails `create-github-app-token` decode
    # (OpenSSL `DECODER routines::unsupported`). `_rewrap_pem` must
    # normalize it to canonical 64-column multi-line PEM, be idempotent on
    # an already-wrapped key, and pass a non-PEM value (APP_ID) through.
    canonical = (
        "-----BEGIN RSA PRIVATE KEY-----\n"
        + "A" * 64
        + "\n"
        + "B" * 64
        + "\n"
        + "CCCC\n"
        + "-----END RSA PRIVATE KEY-----\n"
    )
    collapsed = (
        "-----BEGIN RSA PRIVATE KEY-----"
        + "A" * 64
        + "B" * 64
        + "CCCC"
        + "-----END RSA PRIVATE KEY-----"
    )
    rewrapped = _rewrap_pem(value=collapsed)
    # (a) collapsed single-line key becomes canonical multi-line form.
    assert rewrapped == canonical
    lines = rewrapped.splitlines()
    assert len(lines) > 3
    assert lines[0] == "-----BEGIN RSA PRIVATE KEY-----"
    assert lines[-1] == "-----END RSA PRIVATE KEY-----"
    assert all(len(line) <= 64 for line in lines[1:-1])
    # (b) an already-wrapped PEM re-wraps to itself (idempotent).
    assert _rewrap_pem(value=canonical) == canonical
    # (c) a non-PEM value (e.g. APP_ID) passes through unchanged.
    assert _rewrap_pem(value="1234567") == "1234567"


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
        _TREE_ARGS: _CI_TREE,
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
    """WITHOUT A MATRIX, which the old empty table did not actually arrange.

    An empty canned table made every read fail, so this asserted the
    finding for a ci.yml that was never READ — the fused case. The row now
    separates them, and the fixture has to say which one it means: a
    readable ci.yml that declares no matrix targets.
    """
    table = {
        _TREE_ARGS: _CI_TREE,
        _CI_ARGS: GhResult(returncode=0, stdout="name: CI\n", stderr=""),
    }

    outcome = reconcile_branch_protection(ctx=make_context(table=table, calls=[]), member=_MEMBER)

    assert isinstance(outcome, RowFinding)
    assert "manually" in outcome.message
    assert "declares no matrix targets" in outcome.message


def test_reconcile_protection_failed_put_is_finding() -> None:
    table = {_TREE_ARGS: _CI_TREE, _CI_ARGS: GhResult(returncode=0, stdout=_CI_YML, stderr="")}
    outcome = reconcile_branch_protection(ctx=make_context(table=table, calls=[]), member=_MEMBER)
    assert isinstance(outcome, RowFinding)


def test_reconcile_protection_puts_to_resolved_default_branch() -> None:
    """On a main-default member the protection PUT targets `branches/main`.

    livespec-dev-tooling-17o: the WRITE path must route through the same
    memoized `FleetContext.canonical_ref` resolver as the reads (7vj).
    A hardcoded `master` PUT against a main-default repo configures
    protection for a branch that does not exist, leaving the operator
    believing the repo is protected while the real default branch is
    wide open.
    """
    calls: list[tuple[tuple[str, ...], str | None]] = []
    table = {
        _REPO_GET: ok(payload={"default_branch": "main"}),
        _TREE_ARGS_MAIN: _CI_TREE,
        _CI_ARGS_MAIN: GhResult(returncode=0, stdout=_CI_YML, stderr=""),
        _PROTECTION_PUT_MAIN: ok(payload={}),
    }
    outcome = reconcile_branch_protection(
        ctx=make_context(table=table, calls=calls), member=_MEMBER
    )
    assert isinstance(outcome, RowPass)
    assert any(args == _PROTECTION_PUT_MAIN for args, _stdin in calls)
    assert all("branches/master" not in " ".join(args) for args, _stdin in calls)


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


def test_reconcile_delete_branch_on_merge_patches_repo_setting() -> None:
    calls: list[tuple[tuple[str, ...], str | None]] = []
    table = {_REPO_PATCH: ok(payload={})}
    outcome = reconcile_delete_branch_on_merge(
        ctx=make_context(table=table, calls=calls), member=_MEMBER
    )
    assert isinstance(outcome, RowPass)
    assert "delete_branch_on_merge" in outcome.note
    body = next(stdin for args, stdin in calls if args == _REPO_PATCH)
    assert body is not None
    assert json.loads(body) == {"delete_branch_on_merge": True}


def test_reconcile_delete_branch_on_merge_permission_failure_is_actionable() -> None:
    table = {
        _REPO_PATCH: GhResult(
            returncode=1,
            stdout='{"message":"Resource not accessible by integration"}',
            stderr="",
        )
    }
    outcome = reconcile_delete_branch_on_merge(
        ctx=make_context(table=table, calls=[]), member=_MEMBER
    )
    assert isinstance(outcome, RowFinding)
    assert "Administration" in outcome.message
    assert "gh api repos/acme/widget --method PATCH" in outcome.message
    assert "delete_branch_on_merge" in outcome.message


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
    """The only calls are the one-time default-branch lookup and the tree read."""
    calls: list[tuple[tuple[str, ...], str | None]] = []
    table = {
        _TREE_ARGS: _tree(
            paths=[BUMP_PIN_WORKFLOW, PIN_FRESHNESS_WORKFLOW, RELEASE_DISPATCH_WORKFLOW]
        )
    }
    outcome = reconcile_shim_workflows(ctx=make_context(table=table, calls=calls), member=_MEMBER)
    assert isinstance(outcome, RowPass)
    assert "all shim workflows present" in outcome.note
    assert len(calls) == 2


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


def test_reconcile_shims_pr_bases_on_resolved_default_branch() -> None:
    """On a main-default member the shim PR bases on `main` via `main`'s sha.

    livespec-dev-tooling-17o: with `base` hardcoded to `master`, PR
    creation against a main-default repo fails outright and shim
    provisioning can never complete; the branch-point sha lookup one
    step earlier fails the same way. Both must resolve through
    `FleetContext.canonical_ref`.
    """
    calls: list[tuple[tuple[str, ...], str | None]] = []
    table = {
        _REPO_GET: ok(payload={"default_branch": "main"}),
        _TREE_ARGS_MAIN: _tree(paths=[BUMP_PIN_WORKFLOW]),
        _BRANCH_PROBE: GhResult(returncode=1, stdout="", stderr="Not Found"),
        _MAIN_REF: ok(payload={"object": {"sha": "abc123"}}),
        _REFS_POST: ok(payload={}),
        _put_args(path=PIN_FRESHNESS_WORKFLOW): ok(payload={}),
        _put_args(path=RELEASE_DISPATCH_WORKFLOW): ok(payload={}),
        _PULLS_POST: ok(payload={"number": 7}),
    }
    outcome = reconcile_shim_workflows(ctx=make_context(table=table, calls=calls), member=_MEMBER)
    assert isinstance(outcome, RowPass)
    assert any(args == _MAIN_REF for args, _stdin in calls)
    assert all("git/ref/heads/master" not in " ".join(args) for args, _stdin in calls)
    pr_body = next(stdin for args, stdin in calls if args == _PULLS_POST)
    assert pr_body is not None
    assert json.loads(pr_body)["base"] == "main"
