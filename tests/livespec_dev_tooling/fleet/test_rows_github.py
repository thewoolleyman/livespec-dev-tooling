"""Tests for `livespec_dev_tooling/fleet/_rows_github.py`.

Every GitHub-side row is exercised across pass / finding / skip via a
canned-response `FleetContext` — including the can't-read paths that
permission-limited tokens hit (secrets, protection, installation).
"""

from __future__ import annotations

import json
import textwrap
from typing import TYPE_CHECKING

from livespec_dev_tooling.fleet import _rows_github
from livespec_dev_tooling.fleet._context import (
    FleetContext,
    FleetMember,
    GhResult,
    GhRunner,
    RowFinding,
    RowPass,
    RowSkip,
)
from livespec_dev_tooling.fleet._rows_github import (
    REQUIRED_MERGE_SETTINGS,
    assert_app_installation,
    assert_branch_protection,
    assert_merge_settings,
    assert_secret_names,
    assert_topic,
    member_matrix_targets,
    parse_ci_matrix,
)

if TYPE_CHECKING:
    import pytest

__all__: list[str] = []


_MEMBER = FleetMember(repo="widget", repo_class="library")
_SECRETS_ARGS: tuple[str, ...] = ("api", "repos/acme/widget/actions/secrets")
_INSTALL_ARGS: tuple[str, ...] = ("api", "installation/repositories?per_page=100")
_PROTECTION_ARGS: tuple[str, ...] = ("api", "repos/acme/widget/branches/master/protection")
_REPO_ARGS: tuple[str, ...] = ("api", "repos/acme/widget")
_TOPICS_ARGS: tuple[str, ...] = ("api", "repos/acme/widget/topics")
_CI_ARGS: tuple[str, ...] = (
    "api",
    "repos/acme/widget/contents/.github/workflows/ci.yml?ref=master",
    "-H",
    "Accept: application/vnd.github.raw",
)

_CI_YML = textwrap.dedent(
    """\
    name: CI
    jobs:
      check:
        strategy:
          matrix:
            os: [ubuntu-latest]
            target:
              # leading comment survives

              - check-lint
              - check-types
            python: ["3.10"]
    """
)

# The SINGLE-GATE ci.yml shape the fleet actually runs: a matrix job whose
# legs report under the templated `${{ matrix.target }}` name, plus a
# TOP-LEVEL `ci-green` aggregate gate job that fans the matrix in through
# `needs:`. Per livespec NFR §"CI as a merge gate (branch protection)" the
# required-check set is exactly that one gate job — which is NOT a matrix
# leg, so a matrix-only view of ci.yml cannot see it.
_CI_YML_SINGLE_GATE = textwrap.dedent(
    """\
    name: CI
    jobs:
      check:
        name: ${{ matrix.target }}
        strategy:
          matrix:
            target:
              - check-lint
              - check-types
      ci-green:
        name: ci-green
        needs: [check]
    """
)


def make_context(*, table: dict[tuple[str, ...], GhResult]) -> FleetContext:
    """A `FleetContext` for owner `acme` over a canned-response runner."""

    def run(*, args: list[str], stdin: str | None = None) -> GhResult:
        del stdin
        return table.get(tuple(args), GhResult(returncode=1, stdout="", stderr="no canned"))

    runner: GhRunner = run
    return FleetContext(owner="acme", run_gh=runner)


def ok(*, payload: object) -> GhResult:
    """A successful API result carrying a JSON payload."""
    return GhResult(returncode=0, stdout=json.dumps(payload), stderr="")


def test_parse_ci_matrix_extracts_targets_and_stops_at_next_key() -> None:
    assert parse_ci_matrix(source=_CI_YML) == {"check-lint", "check-types"}


def test_parse_ci_matrix_ignores_lines_outside_matrix() -> None:
    source = "jobs:\n  - check-zzz\ntarget:\n  - check-yyy\n"
    assert parse_ci_matrix(source=source) == set()


def test_member_matrix_targets_reads_ci_yml() -> None:
    ctx = make_context(table={_CI_ARGS: GhResult(returncode=0, stdout=_CI_YML, stderr="")})
    assert member_matrix_targets(ctx=ctx, member=_MEMBER) == {"check-lint", "check-types"}


def test_member_matrix_targets_none_when_unreadable_or_empty() -> None:
    assert member_matrix_targets(ctx=make_context(table={}), member=_MEMBER) is None
    empty_ctx = make_context(
        table={_CI_ARGS: GhResult(returncode=0, stdout="name: CI\n", stderr="")}
    )
    assert member_matrix_targets(ctx=empty_ctx, member=_MEMBER) is None


def test_secret_names_all_present_passes() -> None:
    payload = {"secrets": [{"name": "APP_ID"}, {"name": "APP_PRIVATE_KEY"}, {"name": "OTHER"}]}
    ctx = make_context(table={_SECRETS_ARGS: ok(payload=payload)})
    assert assert_secret_names(ctx=ctx, member=_MEMBER) == RowPass()


def test_secret_names_missing_name_is_finding() -> None:
    payload = {"secrets": [{"name": "APP_ID"}, {"id": 9}, "junk"]}
    ctx = make_context(table={_SECRETS_ARGS: ok(payload=payload)})
    outcome = assert_secret_names(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    assert "APP_PRIVATE_KEY" in outcome.message


def test_secret_names_unreadable_or_shapeless_skips() -> None:
    assert isinstance(assert_secret_names(ctx=make_context(table={}), member=_MEMBER), RowSkip)
    shapeless = make_context(table={_SECRETS_ARGS: ok(payload={"secrets": "nope"})})
    assert isinstance(assert_secret_names(ctx=shapeless, member=_MEMBER), RowSkip)


def test_app_installation_covered_passes() -> None:
    payload = {"repositories": [{"name": "widget"}]}
    ctx = make_context(table={_INSTALL_ARGS: ok(payload=payload)})
    assert assert_app_installation(ctx=ctx, member=_MEMBER) == RowPass()


def test_app_installation_not_covered_is_finding() -> None:
    payload = {"repositories": [{"name": "other"}]}
    ctx = make_context(table={_INSTALL_ARGS: ok(payload=payload)})
    outcome = assert_app_installation(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    assert "App installation" in outcome.message


def test_app_installation_unreadable_skips() -> None:
    outcome = assert_app_installation(ctx=make_context(table={}), member=_MEMBER)
    assert isinstance(outcome, RowSkip)
    assert "installation token" in outcome.reason


def _protection_payload(
    *,
    enforce: bool = True,
    strict: bool = False,
    contexts: list[str] | None = None,
) -> dict[str, object]:
    return {
        "enforce_admins": {"enabled": enforce},
        "required_status_checks": {
            "strict": strict,
            "contexts": contexts if contexts is not None else ["check-lint", "check-types"],
        },
    }


def _protection_ctx(*, payload: object, ci_text: str | None = _CI_YML) -> FleetContext:
    table = {_PROTECTION_ARGS: ok(payload=payload)}
    if ci_text is not None:
        table[_CI_ARGS] = GhResult(returncode=0, stdout=ci_text, stderr="")
    return make_context(table=table)


def test_branch_protection_aligned_passes() -> None:
    ctx = _protection_ctx(payload=_protection_payload())
    assert assert_branch_protection(ctx=ctx, member=_MEMBER) == RowPass()


def test_branch_protection_definitively_absent_is_finding() -> None:
    table = {_PROTECTION_ARGS: GhResult(returncode=1, stdout="", stderr="404 Branch not protected")}
    ctx = make_context(table=table)
    outcome = assert_branch_protection(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    assert "no branch protection" in outcome.message


def test_branch_protection_permission_error_skips() -> None:
    table = {_PROTECTION_ARGS: GhResult(returncode=1, stdout="", stderr="404 Not Found")}
    ctx = make_context(table=table)
    outcome = assert_branch_protection(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowSkip)
    assert "admin scope" in outcome.reason


def test_branch_protection_unparseable_or_shapeless_payload_skips() -> None:
    bad_json = make_context(
        table={_PROTECTION_ARGS: GhResult(returncode=0, stdout="not json", stderr="")}
    )
    assert isinstance(assert_branch_protection(ctx=bad_json, member=_MEMBER), RowSkip)
    not_dict = make_context(table={_PROTECTION_ARGS: ok(payload=[1])})
    assert isinstance(assert_branch_protection(ctx=not_dict, member=_MEMBER), RowSkip)


def test_branch_protection_enforce_admins_disabled_is_finding() -> None:
    ctx = _protection_ctx(payload=_protection_payload(enforce=False))
    outcome = assert_branch_protection(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    assert "enforce_admins" in outcome.message


def test_branch_protection_missing_required_status_checks_is_finding() -> None:
    ctx = _protection_ctx(payload={"enforce_admins": {"enabled": True}})
    outcome = assert_branch_protection(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    assert "required_status_checks is absent" in outcome.message


def test_branch_protection_strict_enabled_is_finding() -> None:
    # Strict (require-branches-up-to-date) MUST be OFF per livespec NFR
    # §"CI as a merge gate (branch protection)"; strict=True is the
    # misalignment the row now flags.
    ctx = _protection_ctx(payload=_protection_payload(strict=True))
    outcome = assert_branch_protection(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    assert "strict" in outcome.message
    assert "OFF" in outcome.message


def test_branch_protection_empty_contexts_is_finding() -> None:
    ctx = _protection_ctx(payload=_protection_payload(contexts=[]))
    outcome = assert_branch_protection(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    assert "empty" in outcome.message


def test_branch_protection_non_string_context_entries_count_as_empty() -> None:
    payload = {
        "enforce_admins": {"enabled": True},
        "required_status_checks": {"strict": False, "contexts": [7]},
    }
    ctx = _protection_ctx(payload=payload)
    outcome = assert_branch_protection(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    assert "empty" in outcome.message


def test_branch_protection_required_check_missing_from_matrix_is_finding() -> None:
    ctx = _protection_ctx(payload=_protection_payload(contexts=["check-lint", "check-gone"]))
    outcome = assert_branch_protection(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    assert "check-gone" in outcome.message


def test_branch_protection_top_level_gate_job_is_not_flagged() -> None:
    """A required TOP-LEVEL `ci-green` gate job is a valid required check.

    livespec NFR §"CI as a merge gate (branch protection)": "A required
    top-level all-green gate job (the `ci-green` single-gate model) is a
    valid required check and is NOT flagged, even though it is not a matrix
    leg, because requiring it gates the whole matrix through its `needs:`."
    Diffing the required contexts against the matrix legs ALONE therefore
    reports a phantom check for the exact configuration the contract
    mandates.
    """
    ctx = _protection_ctx(
        payload=_protection_payload(contexts=["ci-green"]),
        ci_text=_CI_YML_SINGLE_GATE,
    )
    assert assert_branch_protection(ctx=ctx, member=_MEMBER) == RowPass()


def test_branch_protection_phantom_flagged_alongside_recognized_gate_job() -> None:
    """Widening to top-level jobs does not blind the row to a real phantom.

    `check-phantom` matches neither a matrix leg (`check-lint`,
    `check-types`) nor a top-level job id (`check`, `ci-green`) nor a
    literal `name:` (`ci-green`), so it is still reported — while the
    recognized `ci-green` gate job is not.
    """
    ctx = _protection_ctx(
        payload=_protection_payload(contexts=["ci-green", "check-phantom"]),
        ci_text=_CI_YML_SINGLE_GATE,
    )
    outcome = assert_branch_protection(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    assert "check-phantom" in outcome.message
    assert "ci-green" not in outcome.message


def test_branch_protection_alignment_skipped_when_ci_unreadable() -> None:
    ctx = _protection_ctx(payload=_protection_payload(contexts=["check-anything"]), ci_text=None)
    assert assert_branch_protection(ctx=ctx, member=_MEMBER) == RowPass()


def _merge_payload(**overrides: object) -> dict[str, object]:
    """A repo-object payload carrying the rebase-only (green-path) merge settings."""
    payload: dict[str, object] = dict(REQUIRED_MERGE_SETTINGS)
    payload.update(overrides)
    return payload


def test_merge_settings_rebase_only_passes() -> None:
    ctx = make_context(table={_REPO_ARGS: ok(payload=_merge_payload())})
    assert assert_merge_settings(ctx=ctx, member=_MEMBER) == RowPass()


def test_merge_settings_merge_commit_enabled_is_finding() -> None:
    # The freshly-scaffolded-repo default: GitHub leaves allow_merge_commit
    # true, which violates the rebase-only rule (livespec NFR §"Commit and
    # merge discipline").
    ctx = make_context(table={_REPO_ARGS: ok(payload=_merge_payload(allow_merge_commit=True))})
    outcome = assert_merge_settings(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    assert "allow_merge_commit" in outcome.message
    assert "rebase-only" in outcome.message


def test_merge_settings_rebase_disabled_is_finding() -> None:
    ctx = make_context(table={_REPO_ARGS: ok(payload=_merge_payload(allow_rebase_merge=False))})
    outcome = assert_merge_settings(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    assert "allow_rebase_merge" in outcome.message


def test_merge_settings_auto_merge_disabled_is_finding() -> None:
    ctx = make_context(table={_REPO_ARGS: ok(payload=_merge_payload(allow_auto_merge=False))})
    outcome = assert_merge_settings(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    assert "allow_auto_merge" in outcome.message


def test_merge_settings_unreadable_skips() -> None:
    outcome = assert_merge_settings(ctx=make_context(table={}), member=_MEMBER)
    assert isinstance(outcome, RowSkip)
    assert "admin scope" in outcome.reason


def test_delete_branch_on_merge_true_passes(*, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    ctx = make_context(table={_REPO_ARGS: ok(payload={"delete_branch_on_merge": True})})
    assert _rows_github.assert_delete_branch_on_merge(ctx=ctx, member=_MEMBER) == RowPass()


def test_delete_branch_on_merge_false_fails_when_token_present(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GH_TOKEN", "token")
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    ctx = make_context(table={_REPO_ARGS: ok(payload={"delete_branch_on_merge": False})})

    outcome = _rows_github.assert_delete_branch_on_merge(ctx=ctx, member=_MEMBER)

    assert isinstance(outcome, RowFinding)
    assert outcome.severity == "error"
    assert "widget" in outcome.message
    assert "delete_branch_on_merge" in outcome.message


def test_delete_branch_on_merge_false_warns_without_token(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    ctx = make_context(table={_REPO_ARGS: ok(payload={"delete_branch_on_merge": False})})

    outcome = _rows_github.assert_delete_branch_on_merge(ctx=ctx, member=_MEMBER)

    assert isinstance(outcome, RowFinding)
    assert outcome.severity == "warning"
    assert "widget" in outcome.message
    assert "delete_branch_on_merge" in outcome.message


def test_topic_present_passes() -> None:
    ctx = make_context(table={_TOPICS_ARGS: ok(payload={"names": ["livespec-sibling", "x"]})})
    assert assert_topic(ctx=ctx, member=_MEMBER) == RowPass()


def test_topic_missing_is_finding() -> None:
    ctx = make_context(table={_TOPICS_ARGS: ok(payload={"names": ["other"]})})
    outcome = assert_topic(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    assert "livespec-sibling" in outcome.message


def test_topic_unreadable_or_shapeless_skips() -> None:
    assert isinstance(assert_topic(ctx=make_context(table={}), member=_MEMBER), RowSkip)
    shapeless = make_context(table={_TOPICS_ARGS: ok(payload={"names": "nope"})})
    assert isinstance(assert_topic(ctx=shapeless, member=_MEMBER), RowSkip)
