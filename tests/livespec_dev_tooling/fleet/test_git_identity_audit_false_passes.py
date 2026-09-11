"""Regression tests for fleet Git-identity audit false-pass boundaries."""

from __future__ import annotations

import subprocess
from pathlib import Path

from livespec_dev_tooling.fleet._git_identity_audit_model import (
    CANONICAL_EMAIL,
    CANONICAL_NAME,
    HOSTS,
    base_report,
    host_findings,
    host_roots,
    valid_evidence,
)
from livespec_dev_tooling.fleet._git_identity_host_git import ProbeConfig, worktree_record
from livespec_dev_tooling.fleet._git_identity_host_probe import author_values

__all__: list[str] = []


def _host_report(*, host: str) -> dict[str, object]:
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
        "owned_repositories": [],
        "excluded_repositories": [],
        "process_author_environment": {
            "total": 2,
            "audited": 2,
            "unreadable": [],
            "violations": [],
            "blind": 0,
        },
        "tmux_author_environment": {
            "scope": "default-user-socket-supplemental",
            "servers": 0,
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


def _evidence() -> dict[str, object]:
    return {
        "schema_version": 1,
        "run_id": "01M26JJ37CN5KB989WJZG1JGE9",
        "repository": "/data/projects/livespec",
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


def test_host_roots_are_exact_observed_nonvacuous_scope() -> None:
    assert host_roots(host="vps") == (
        "/data/projects",
        "/home/ubuntu/workspace",
        "/home/ubuntu/.worktrees",
    )
    for host in HOSTS:
        if host != "vps":
            assert host_roots(host=host) == ("/home/cwoolley/workspace",)


def test_missing_required_root_fails_host_report() -> None:
    report = _host_report(host="vps")
    report["roots"] = [{"path": "/data/projects", "state": "present"}]

    findings, blind, *_counts = host_findings(host="vps", report=report)

    assert blind > 0
    assert any("root" in finding for finding in findings)


def test_unreadable_process_is_blind_even_when_declared_blind_is_falsified() -> None:
    report = _host_report(host="vps")
    report["process_author_environment"] = {
        "total": 3,
        "audited": 2,
        "unreadable": [999],
        "violations": [],
        "blind": 0,
    }

    findings, blind, *_counts = host_findings(host="vps", report=report)

    assert blind > 0
    assert any("process" in finding and "blind" in finding for finding in findings)


def test_fabro_evidence_requires_full_pinned_image_digests() -> None:
    evidence = _evidence()
    evidence["sandbox_image_digests"] = ["sha256:83e0bec5d3ed33"]

    assert valid_evidence(evidence=evidence) is False


def test_empty_base_report_does_not_claim_unobserved_repo_dispositions(tmp_path: Path) -> None:
    report = base_report(inventory_path=tmp_path / "inventory.yml", findings=[])

    assert "dispositions" not in report
    assert report["forbidden_author_emails"] == ["chad@thewoolleyman.com"]
    assert isinstance(report["generated_at"], str)


class _WorktreeRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def __call__(
        self,
        *,
        args: tuple[str, ...],
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        del cwd, env
        self.calls.append(args)
        if args == ("git", "var", "GIT_AUTHOR_IDENT"):
            stdout = f"{CANONICAL_NAME} <{CANONICAL_EMAIL}> 1789084800 +0200\n"
        elif "extensions.worktreeConfig" in args:
            return subprocess.CompletedProcess(args, 1, "", "")
        else:
            stdout = ""
        return subprocess.CompletedProcess(args, 0, stdout, "")


def test_worktree_effective_author_comes_from_git_var() -> None:
    runner = _WorktreeRunner()
    config = ProbeConfig(
        host="vps",
        user="ubuntu",
        owner="thewoolleyman",
        expected_name=CANONICAL_NAME,
        expected_email=CANONICAL_EMAIL,
        roots=("/data/projects",),
    )

    record, errors = worktree_record(config=config, runner=runner, path=Path("/repo"))

    assert errors == []
    assert record["passed"] is True
    assert ("git", "var", "GIT_AUTHOR_IDENT") in runner.calls


def test_process_parser_never_serializes_unrelated_environment_values() -> None:
    parsed = author_values(
        raw=(
            b"SECRET_TOKEN=do-not-serialize\0"
            b"GIT_AUTHOR_NAME=Chad Woolley\0"
            b"GIT_AUTHOR_EMAIL=thewoolleyman@gmail.com\0"
        )
    )

    assert parsed == {
        "GIT_AUTHOR_NAME": CANONICAL_NAME,
        "GIT_AUTHOR_EMAIL": CANONICAL_EMAIL,
    }
