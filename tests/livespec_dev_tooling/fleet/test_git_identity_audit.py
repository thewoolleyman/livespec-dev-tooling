"""Hermetic coverage for the operator-invoked fleet Git identity auditor."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from livespec_dev_tooling.fleet._git_identity_audit_model import host_findings, host_roots
from livespec_dev_tooling.fleet._git_identity_audit_report import (
    observed_dispositions,
    valid_evidence,
)
from livespec_dev_tooling.fleet._git_identity_host_probe import author_values
from livespec_dev_tooling.fleet.git_identity_audit import (
    CANONICAL_EMAIL,
    CANONICAL_NAME,
    CommandResult,
    run_audit,
)

__all__: list[str] = []

_HOSTS = ("gmktec-xubuntu", "hp-xubuntu", "poweredge-xubuntu", "vps")
_INVENTORY = """\
all:
  children:
    legacy:
      children:
        dev_hosts:
          hosts:
            vps:
              ansible_connection: local
        ci_pool:
          hosts:
            poweredge-xubuntu:
              ansible_user: cwoolley
            gmktec-xubuntu:
              ansible_user: cwoolley
        sandbox_hosts:
          hosts:
            hp-xubuntu:
              ansible_user: cwoolley
"""


class ScriptedRunner:
    def __init__(self, *, reports: dict[str, dict[str, object]], author: str) -> None:
        self.reports = reports
        self.author = author
        self.calls: list[tuple[tuple[str, ...], bool]] = []

    def __call__(self, *, args: tuple[str, ...], stdin: str | None = None) -> CommandResult:
        self.calls.append((args, stdin is not None))
        if args[0] == "git":
            return CommandResult(returncode=0, stdout=self.author, stderr="")
        host = next(name for name in _HOSTS if any(name in argument for argument in args))
        return CommandResult(
            returncode=0,
            stdout=json.dumps(self.reports[host]),
            stderr="",
        )


def _host_report(host: str) -> dict[str, object]:
    repository_name = "poweredge-xubuntu-info" if host == "poweredge-xubuntu" else "livespec"
    repo = {
        "repo": repository_name,
        "common_dir": f"/srv/{host}/{repository_name}/.git",
        "origin": f"git@github.com:thewoolleyman/{repository_name}.git",
        "worktrees": [
            {
                "path": f"/srv/{host}/livespec",
                "effective_name": CANONICAL_NAME,
                "effective_email": CANONICAL_EMAIL,
                "local_names": [],
                "local_emails": [],
                "worktree_names": [],
                "worktree_emails": [],
                "passed": True,
            }
        ],
    }
    return {
        "schema_version": 1,
        "host": host,
        "global_config": {
            "name": CANONICAL_NAME,
            "email": CANONICAL_EMAIL,
            "use_config_only": True,
            "passed": True,
        },
        "roots": [{"path": path, "state": "present"} for path in host_roots(host=host)],
        "owned_repositories": [repo],
        "excluded_repositories": (
            [
                {
                    "path": "/home/cwoolley/workspace/homelab",
                    "origin": "git@github.com:mi-homelab/homelab.git",
                }
            ]
            if host == "poweredge-xubuntu"
            else []
        ),
        "process_author_environment": {
            "total": 2,
            "audited": 2,
            "unreadable": [],
            "violations": [],
            "blind": 0,
        },
        "tmux_author_environment": {
            "scope": "default-user-socket-supplemental",
            "servers": 1,
            "violations": [],
            "blind": 0,
        },
        "commit_canaries": {
            "positive": {
                "passed": True,
                "author_name": CANONICAL_NAME,
                "author_email": CANONICAL_EMAIL,
            },
            "missing_identity": {"passed": True},
            "invalid_identity": {"passed": True},
        },
        "failures": [],
        "blind": [],
    }


def _evidence(root: Path) -> dict[str, object]:
    return {
        "schema_version": 1,
        "run_id": "01M26JJ37CN5KB989WJZG1JGE9",
        "repository": str(root),
        "commit": "2570277508eddf5997bdd133e84c3ec60c24db29",
        "orchestrator_version": "0.148.2",
        "sandbox_image_version": "1.85.3",
        "sandbox_image_digests": [
            "sha256:83e0bec519eb412d82a1136627193564e356bfa8091f2b9171597141c9d3ed33",
            "sha256:9331287cce9edfb82e143e87072e12774ef7c5f635a6d7d0aa6dd4b8732c7a7c",
        ],
        "negative_ci_run_id": "34518565990",
        "missing_identity_rejected": True,
        "canonical_identity_accepted": True,
    }


def _invoke(
    *, tmp_path: Path, reports: dict[str, dict[str, object]], evidence: object | None = None
) -> tuple[int, dict[str, object], ScriptedRunner]:
    inventory = tmp_path / "legacy.yml"
    inventory.write_text(_INVENTORY, encoding="utf-8")
    evidence_path = tmp_path / "fabro.json"
    evidence_path.write_text(json.dumps(_evidence(tmp_path) if evidence is None else evidence))
    output = tmp_path / "tmp" / "git-identity-audit.json"
    runner = ScriptedRunner(
        reports=reports,
        author=f"{CANONICAL_NAME}\x00{CANONICAL_EMAIL}\n",
    )
    exit_code = run_audit(
        inventory_path=inventory,
        evidence_path=evidence_path,
        output_path=output,
        runner=runner,
        allowed_output_root=tmp_path / "tmp",
    )
    return exit_code, json.loads(output.read_text(encoding="utf-8")), runner


def test_complete_scope_emits_deterministic_schema_versioned_pass(tmp_path: Path) -> None:
    reports = {host: _host_report(host) for host in _HOSTS}

    exit_code, report, runner = _invoke(tmp_path=tmp_path, reports=reports)

    assert exit_code == 0
    assert report["schema_version"] == 1
    assert report["overall"] == "pass"
    assert report["scope"] == {
        "history_scanned": False,
        "hosts": list(_HOSTS),
        "inventory": str(tmp_path / "legacy.yml"),
        "owned_github_origin": "thewoolleyman",
    }
    assert report["summary"] == {
        "blind": 0,
        "failures": 0,
        "hosts": 4,
        "owned_repositories": 4,
        "owned_worktrees": 4,
        "processes_audited": 8,
    }
    assert report["dispositions"]["poweredge-xubuntu-info"] == "owned; audited"
    assert report["dispositions"]["mi-homelab/homelab"] == (
        "not owned by thewoolleyman; excluded and unmodified"
    )
    assert report["fabro_evidence"]["verified_author"] == {
        "email": CANONICAL_EMAIL,
        "name": CANONICAL_NAME,
    }
    assert all(stdin for _args, stdin in runner.calls if _args[0] != "git")
    assert not any("log" in args or "rev-list" in args for args, _stdin in runner.calls)


@pytest.mark.parametrize(
    ("mutate", "expected_fragment"),
    [
        (
            lambda report: report["global_config"].update(
                {"email": "chad@thewoolleyman.com", "passed": False}
            ),
            "global_config",
        ),
        (
            lambda report: report["owned_repositories"][0]["worktrees"][0].update(
                {"effective_email": "wrong@example.com", "passed": False}
            ),
            "worktree",
        ),
        (
            lambda report: report["process_author_environment"].update({"blind": 1}),
            "blind",
        ),
        (
            lambda report: report["process_author_environment"]["violations"].append(
                {"pid": 7, "variable": "GIT_AUTHOR_EMAIL"}
            ),
            "process",
        ),
        (
            lambda report: report["commit_canaries"]["missing_identity"].update({"passed": False}),
            "canary",
        ),
    ],
)
def test_any_failure_or_blind_makes_overall_fail(
    tmp_path: Path, mutate: object, expected_fragment: str
) -> None:
    reports = {host: _host_report(host) for host in _HOSTS}
    mutate(reports["vps"])  # type: ignore[operator]

    exit_code, report, _runner = _invoke(tmp_path=tmp_path, reports=reports)

    assert exit_code == 1
    assert report["overall"] == "fail"
    assert expected_fragment in json.dumps(report["findings"]).lower()


def test_wrong_or_vacuous_inventory_fails_before_any_host_probe(tmp_path: Path) -> None:
    reports = {host: _host_report(host) for host in _HOSTS}
    inventory = tmp_path / "legacy.yml"
    inventory.write_text(_INVENTORY.replace("hp-xubuntu:", "surprise-host:"), encoding="utf-8")
    evidence_path = tmp_path / "fabro.json"
    evidence_path.write_text(json.dumps(_evidence(tmp_path)), encoding="utf-8")
    output = tmp_path / "tmp" / "report.json"
    runner = ScriptedRunner(reports=reports, author=f"{CANONICAL_NAME}\x00{CANONICAL_EMAIL}\n")

    exit_code = run_audit(
        inventory_path=inventory,
        evidence_path=evidence_path,
        output_path=output,
        runner=runner,
        allowed_output_root=tmp_path / "tmp",
    )

    report = json.loads(output.read_text(encoding="utf-8"))
    assert exit_code == 1
    assert report["overall"] == "fail"
    assert "inventory" in json.dumps(report["findings"]).lower()
    assert runner.calls == []


def test_missing_or_unverifiable_fabro_evidence_fails_closed(tmp_path: Path) -> None:
    reports = {host: _host_report(host) for host in _HOSTS}
    evidence = _evidence(tmp_path)
    del evidence["negative_ci_run_id"]

    exit_code, report, runner = _invoke(
        tmp_path=tmp_path,
        reports=reports,
        evidence=evidence,
    )

    assert exit_code == 1
    assert report["overall"] == "fail"
    assert "fabro" in json.dumps(report["findings"]).lower()
    assert not any(args[0] == "git" for args, _stdin in runner.calls)


def test_fabro_commit_must_resolve_to_canonical_author(tmp_path: Path) -> None:
    reports = {host: _host_report(host) for host in _HOSTS}
    inventory = tmp_path / "legacy.yml"
    inventory.write_text(_INVENTORY, encoding="utf-8")
    evidence_path = tmp_path / "fabro.json"
    evidence_path.write_text(json.dumps(_evidence(tmp_path)), encoding="utf-8")
    output = tmp_path / "tmp" / "report.json"
    runner = ScriptedRunner(reports=reports, author="Chad Woolley\x00wrong@example.com\n")

    exit_code = run_audit(
        inventory_path=inventory,
        evidence_path=evidence_path,
        output_path=output,
        runner=runner,
        allowed_output_root=tmp_path / "tmp",
    )

    report = json.loads(output.read_text(encoding="utf-8"))
    assert exit_code == 1
    assert "Fabro commit author" in json.dumps(report["findings"])


def test_output_is_refused_outside_caller_tmp_root(tmp_path: Path) -> None:
    reports = {host: _host_report(host) for host in _HOSTS}
    inventory = tmp_path / "legacy.yml"
    inventory.write_text(_INVENTORY, encoding="utf-8")
    evidence_path = tmp_path / "fabro.json"
    evidence_path.write_text(json.dumps(_evidence(tmp_path)), encoding="utf-8")
    runner = ScriptedRunner(reports=reports, author=f"{CANONICAL_NAME}\x00{CANONICAL_EMAIL}\n")

    exit_code = run_audit(
        inventory_path=inventory,
        evidence_path=evidence_path,
        output_path=tmp_path / "outside.json",
        runner=runner,
        allowed_output_root=tmp_path / "tmp",
    )

    assert exit_code == 2
    assert not (tmp_path / "outside.json").exists()
    assert runner.calls == []


def test_just_recipe_is_operator_only_and_not_in_aggregate() -> None:
    root = Path(__file__).resolve().parents[3]
    justfile = (root / "justfile").read_text(encoding="utf-8")
    inventory = (root / "check-targets.txt").read_text(encoding="utf-8")
    ci = (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "git-identity-audit" in justfile
    assert "git-identity-audit" not in inventory
    assert "git-identity-audit" not in ci


def test_process_parser_includes_namespaced_author_selectors() -> None:
    assert author_values(
        raw=(
            b"LIVESPEC_GIT_AUTHOR_NAME=Chad Woolley\0"
            b"LIVESPEC_GIT_AUTHOR_EMAIL=chad@thewoolleyman.com\0"
        )
    ) == {
        "LIVESPEC_GIT_AUTHOR_NAME": CANONICAL_NAME,
        "LIVESPEC_GIT_AUTHOR_EMAIL": "chad@thewoolleyman.com",
    }


@pytest.mark.parametrize(
    "evidence",
    [
        None,
        {"schema_version": 2},
        {"schema_version": 1, "sandbox_image_digests": "not-a-list"},
        {"schema_version": 1, "sandbox_image_digests": [7]},
    ],
)
def test_fabro_evidence_rejects_malformed_envelopes(evidence: object) -> None:
    assert valid_evidence(evidence=evidence) is False  # type: ignore[arg-type]


def test_unobserved_dispositions_are_failures_not_claims() -> None:
    findings: list[str] = []
    dispositions = observed_dispositions(
        host_reports=[
            {"owned_repositories": "malformed", "excluded_repositories": [{"origin": None}]},
            {"owned_repositories": [{}], "excluded_repositories": "malformed"},
        ],
        findings=findings,
    )

    assert len(findings) == 2
    assert all("not observed" in value for value in dispositions.values())


def test_malformed_root_and_tmux_scope_are_blind() -> None:
    report = _host_report("vps")
    report["roots"] = [{"path": 7, "state": "present"}]
    report["tmux_author_environment"] = {
        "scope": "all-tmux-servers",
        "servers": 0,
        "violations": [],
        "blind": 0,
    }

    findings, blind, *_counts = host_findings(host="vps", report=report)

    assert blind == 2
    assert any("root" in finding for finding in findings)
    assert any("tmux" in finding for finding in findings)
