"""Outside-in tests for the merge-queue rules of `branch_protection_alignment`.

Per SPECIFICATION/contracts.md, the `branch_protection_alignment` check, an
organization-owned repository named in `QUEUE_REQUIRED_REPOSITORIES` must reach
its default branch only through a rebasing merge queue building at least two
entries, with no bypass but the recovery App; a repository using the guarded
`merge_group` exception of `self_hosted_routing` must hold the strictest fork-PR
approval setting; and on a personal-account repository none of these fire.

`main()` runs in-process. Every forge read goes through `budgeted_gh.gh_read`,
which each reading module binds by name, so the tests replace that binding in
each module with one router answering per API path. The origin and the default
branch are pinned the same way, so no `gh` or `git` subprocess runs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from livespec_dev_tooling.budgeted_gh import GhRead
from livespec_dev_tooling.checks import (
    _branch_protection_api,
    _branch_protection_merge_queue,
    _branch_protection_rulesets,
    branch_protection_alignment,
)

__all__: list[str] = []

_RECOVERY_APP_ID = 123
_RULESET_ID = 7
_CI_YML = (
    "name: CI\n"
    "on:\n"
    "  pull_request:\n"
    "jobs:\n"
    "  check-python:\n"
    "    name: ${{ matrix.target }}\n"
    "    strategy:\n"
    "      matrix:\n"
    "        target:\n"
    "          - check-foo\n"
    "    runs-on: ubuntu-latest\n"
    "  ci-green:\n"
    "    name: ci-green\n"
    "    needs: [check-python]\n"
    "    runs-on: ubuntu-latest\n"
)
_MERGE_GROUP_WORKFLOW = (
    "name: queue\n"
    "on:\n"
    "  merge_group:\n"
    "jobs:\n"
    "  check:\n"
    "    runs-on: [self-hosted, local-ci]\n"
)
_FIVE_RULES = (
    "merge_queue_absent",
    "merge_queue_concurrency_below_floor",
    "merge_queue_method_not_rebase",
    "merge_queue_bypass_path",
    "fork_approval_below_strictest",
)


def _queue_rule(*, build: object = 5, method: object = "REBASE") -> dict[str, object]:
    return {
        "type": "merge_queue",
        "ruleset_id": _RULESET_ID,
        "parameters": {"max_entries_to_build": build, "merge_method": method},
    }


def _recovery_only() -> dict[str, object]:
    return {"bypass_actors": [{"actor_type": "Integration", "actor_id": _RECOVERY_APP_ID}]}


@dataclass(kw_only=True)
class _Forge:
    """The forge state one test answers with, keyed by what the check reads."""

    repo: str = "livespec-dev-tooling"
    owner_type: str | None = "Organization"
    rule_pages: list[object] = field(default_factory=lambda: [[_queue_rule()]])
    rulesets: dict[int, object] = field(default_factory=lambda: {_RULESET_ID: _recovery_only()})
    restrictions: bool = False
    admins_enabled: bool = True
    fork_policy: str | None = "all_external_contributors"
    calls: list[str] = field(default_factory=list)

    def read(self, *, args: list[str], **_: object) -> GhRead:
        path = args[-1]
        self.calls.append(path)
        base = f"repos/test-org/{self.repo}"
        answers: dict[str, object] = {
            f"{base}/branches/master/protection/required_status_checks": {
                "strict": False,
                "contexts": ["ci-green"],
            },
            f"{base}/branches/master/protection/enforce_admins": {"enabled": self.admins_enabled},
            f"{base}/rules/branches/master?per_page=100": self.rule_pages,
            base: {"owner": {"type": self.owner_type}} if self.owner_type else {"name": self.repo},
        }
        answers.update({f"{base}/rulesets/{i}": body for i, body in self.rulesets.items()})
        if self.restrictions:
            answers[f"{base}/branches/master/protection/restrictions"] = {"users": []}
        if self.fork_policy is not None:
            answers[f"{base}/actions/permissions/fork-pr-contributor-approval"] = {
                "approval_policy": self.fork_policy
            }
        if path not in answers:
            return GhRead(returncode=1, stdout='{"message": "Not Found"}', stderr="HTTP 404")
        return GhRead(returncode=0, stdout=json.dumps(answers[path]), stderr="")


def _run(
    *,
    forge: _Forge,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    pyproject: str = f"[tool.livespec_dev_tooling]\nrecovery_bypass_integration_id = {_RECOVERY_APP_ID}\n",
    merge_group_workflow: bool = False,
) -> tuple[int, list[dict[str, object]]]:
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    _ = (workflows / "ci.yml").write_text(_CI_YML, encoding="utf-8")
    if merge_group_workflow:
        _ = (workflows / "queue.yaml").write_text(_MERGE_GROUP_WORKFLOW, encoding="utf-8")
    _ = (tmp_path / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("LIVESPEC_GATE_CONTEXT", raising=False)

    def _which(_name: str) -> str:
        return "/usr/bin/gh"

    def _owner_repo(**_: object) -> str:
        return f"test-org/{forge.repo}"

    monkeypatch.setattr(_branch_protection_api.shutil, "which", _which)
    monkeypatch.setattr(_branch_protection_api, "_resolve_owner_repo", _owner_repo)
    monkeypatch.setattr(_branch_protection_api, "_default_branch_from_git", lambda: "master")
    for module in (
        _branch_protection_api,
        _branch_protection_rulesets,
        _branch_protection_merge_queue,
    ):
        monkeypatch.setattr(module, "gh_read", forge.read)
    rc = branch_protection_alignment.main()
    captured = capsys.readouterr()
    lines = (captured.out + captured.err).splitlines()
    return rc, [json.loads(line) for line in lines if line.startswith("{")]


def _modes(*, findings: list[dict[str, object]]) -> list[object]:
    return [f.get("failure_mode") for f in findings if f.get("level") == "error"]


def test_an_aligned_queue_required_repository_passes(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rc, findings = _run(forge=_Forge(), tmp_path=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert (rc, _modes(findings=findings)) == (0, [])


def test_queue_required_repository_without_a_merge_queue_rule_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """DoD 6 and the v225 scenario: no merge_queue rule -> exit 4, merge_queue_absent."""
    forge = _Forge(rule_pages=[[]], rulesets={})
    rc, findings = _run(forge=forge, tmp_path=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert (rc, _modes(findings=findings)) == (4, ["merge_queue_absent"])


def test_merge_queue_concurrency_below_two_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """DoD 7: build concurrency below 2 -> merge_queue_concurrency_below_floor."""
    forge = _Forge(rule_pages=[[_queue_rule(build=1)]])
    rc, findings = _run(forge=forge, tmp_path=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert (rc, _modes(findings=findings)) == (4, ["merge_queue_concurrency_below_floor"])


def test_merge_queue_not_rebasing_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """DoD 8: merge_method other than REBASE -> merge_queue_method_not_rebase."""
    forge = _Forge(rule_pages=[[_queue_rule(method="SQUASH")]])
    rc, findings = _run(forge=forge, tmp_path=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert (rc, _modes(findings=findings)) == (4, ["merge_queue_method_not_rebase"])


def test_malformed_merge_queue_parameters_fail_both_rules(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rule = {"type": "merge_queue", "ruleset_id": _RULESET_ID, "parameters": "?"}
    forge = _Forge(rule_pages=[["not-a-rule", rule]])
    rc, findings = _run(forge=forge, tmp_path=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert rc == 4
    assert _modes(findings=findings) == [
        "merge_queue_concurrency_below_floor",
        "merge_queue_method_not_rebase",
    ]


@pytest.mark.parametrize(
    "bypass_actors",
    [
        [
            {"actor_type": "Integration", "actor_id": _RECOVERY_APP_ID},
            {"actor_type": "RepositoryRole", "actor_id": 5},
        ],
        [{"actor_type": "Integration", "actor_id": 999}],
        ["not-an-actor"],
        [],
    ],
)
def test_a_bypass_actor_other_than_the_recovery_app_fails(
    *,
    bypass_actors: list[object],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """DoD 9: any ruleset bypass but the one recovery Integration -> merge_queue_bypass_path."""
    forge = _Forge(rulesets={_RULESET_ID: {"bypass_actors": bypass_actors}})
    rc, findings = _run(forge=forge, tmp_path=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert (rc, _modes(findings=findings)) == (4, ["merge_queue_bypass_path"])


def test_an_absent_recovery_bypass_integration_id_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """DoD 9: recovery_bypass_integration_id undeclared -> merge_queue_bypass_path."""
    rc, findings = _run(
        forge=_Forge(),
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        pyproject="[tool.livespec_dev_tooling]\n",
    )
    assert (rc, _modes(findings=findings)) == (4, ["merge_queue_bypass_path"])


def test_a_classic_push_restriction_exception_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    forge = _Forge(restrictions=True)
    rc, findings = _run(forge=forge, tmp_path=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert (rc, _modes(findings=findings)) == (4, ["merge_queue_bypass_path"])


def test_classic_enforce_admins_off_is_a_bypass_path(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    forge = _Forge(admins_enabled=False)
    rc, findings = _run(forge=forge, tmp_path=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert (rc, _modes(findings=findings)) == (
        4,
        ["enforce_admins_disabled", "merge_queue_bypass_path"],
    )


def test_unreadable_ruleset_rules_fail_as_unreadable(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    forge = _Forge(rule_pages=[{"not": "a page"}])
    rc, findings = _run(forge=forge, tmp_path=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert rc == 4
    assert set(_modes(findings=findings)) == {"ruleset_unreadable"}


def test_an_unreadable_active_ruleset_fails_as_unreadable(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    forge = _Forge(rulesets={})
    rc, findings = _run(forge=forge, tmp_path=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert (rc, _modes(findings=findings)) == (4, ["ruleset_unreadable"])


def test_fork_approval_below_strictest_fails_for_a_guarded_merge_group_repository(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """DoD 10: guarded merge_group in use + weaker fork approval -> fork_approval_below_strictest."""
    forge = _Forge(repo="other-repo", fork_policy="first_time_contributors")
    rc, findings = _run(
        forge=forge,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        merge_group_workflow=True,
    )
    assert (rc, _modes(findings=findings)) == (4, ["fork_approval_below_strictest"])


def test_strictest_fork_approval_passes(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    forge = _Forge(repo="other-repo")
    rc, findings = _run(
        forge=forge,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        merge_group_workflow=True,
    )
    assert (rc, _modes(findings=findings)) == (0, [])


def test_an_unreadable_fork_approval_setting_skips_gracefully(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    forge = _Forge(repo="other-repo", fork_policy=None)
    rc, findings = _run(
        forge=forge,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        merge_group_workflow=True,
    )
    assert (rc, _modes(findings=findings)) == (0, [])
    assert any("fork-PR approval" in str(f.get("event")) for f in findings)


def test_none_of_the_five_rules_fire_on_a_personal_account_repository(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """DoD 11: a User-owned repository fires none of the five merge-queue rules."""
    forge = _Forge(
        owner_type="User",
        rule_pages=[[]],
        rulesets={},
        restrictions=True,
        fork_policy="first_time_contributors",
    )
    rc, findings = _run(
        forge=forge,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        pyproject="[tool.livespec_dev_tooling]\n",
        merge_group_workflow=True,
    )
    assert rc == 0
    assert not set(_modes(findings=findings)) & set(_FIVE_RULES)


def test_an_unreadable_owner_type_skips_the_merge_queue_rules(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    forge = _Forge(owner_type=None, rule_pages=[[]], rulesets={})
    rc, findings = _run(forge=forge, tmp_path=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert (rc, _modes(findings=findings)) == (0, [])
    assert any("owner's type" in str(f.get("event")) for f in findings)


def test_a_repository_neither_queue_required_nor_guarded_reads_no_owner(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    forge = _Forge(repo="other-repo", rule_pages=[[]], rulesets={})
    rc, findings = _run(forge=forge, tmp_path=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert (rc, _modes(findings=findings)) == (0, [])
    assert "repos/test-org/other-repo" not in forge.calls


def test_a_malformed_recovery_bypass_integration_id_is_a_config_failure(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rc, _ = _run(
        forge=_Forge(),
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        pyproject='[tool.livespec_dev_tooling]\nrecovery_bypass_integration_id = "x"\n',
    )
    assert rc == 1


def test_queue_required_repositories_is_the_named_constant() -> None:
    assert (
        frozenset({"livespec-dev-tooling", "livespec-orchestrator-beads-fabro"})
        == branch_protection_alignment.QUEUE_REQUIRED_REPOSITORIES
    )
