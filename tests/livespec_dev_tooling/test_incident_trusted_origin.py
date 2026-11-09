"""Trusted normal origins are named before any inherited incident flag is parsed."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest

from livespec_dev_tooling import incident_trusted_origin
from livespec_dev_tooling.incident_execution import (
    EXPEDITED_INCIDENT_RESPONSE,
    EXPEDITED_INCIDENT_RESPONSE_REVERT,
    Invocation,
)

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-wtsntu
_MASTER = {"GITHUB_ACTIONS": "true", "GITHUB_EVENT_NAME": "push"}
_FLAGS = {EXPEDITED_INCIDENT_RESPONSE: "maybe", EXPEDITED_INCIDENT_RESPONSE_REVERT: "2"}


@pytest.fixture(autouse=True)
def _trusted_origin_is_never_the_hosts_own() -> None:
    """Override the suite-wide neutralizer: this file drives the real probe."""


def _repo(*, root: Path, marker: str | None) -> Path:
    _ = subprocess.run(["git", "init", "-q", str(root)], check=True)
    if marker is not None:
        _ = subprocess.run(
            ["git", "config", "livespec.sandboxExempt", marker], cwd=root, check=True
        )
    return root


def test_a_master_push_job_is_a_trusted_normal_origin_even_with_malformed_flags(
    *, tmp_path: Path
) -> None:
    named = incident_trusted_origin.trusted_invocation(environ=_MASTER | _FLAGS, repo=tmp_path)
    assert named == Invocation.NORMAL_MASTER


@pytest.mark.parametrize(
    "environ",
    [
        {"GITHUB_ACTIONS": "true", "GITHUB_EVENT_NAME": "pull_request"},
        {"GITHUB_EVENT_NAME": "push"},
        {"GITHUB_ACTIONS": "false", "GITHUB_EVENT_NAME": "push"},
        {},
    ],
)
def test_other_ci_events_and_bare_hosts_are_not_trusted_origins(
    *, tmp_path: Path, environ: dict[str, str]
) -> None:
    named = incident_trusted_origin.trusted_invocation(
        environ=environ | {EXPEDITED_INCIDENT_RESPONSE: "1"}, repo=_repo(root=tmp_path, marker=None)
    )
    assert named == Invocation.ORDINARY


def test_a_factory_sandbox_is_a_trusted_follow_up_origin_even_with_malformed_flags(
    *, tmp_path: Path
) -> None:
    repo = _repo(root=tmp_path, marker="true")
    named = incident_trusted_origin.trusted_invocation(environ=_FLAGS, repo=repo)
    assert named == Invocation.NORMAL_FACTORY_FOLLOW_UP


def test_master_push_takes_precedence_over_a_factory_marker(*, tmp_path: Path) -> None:
    repo = _repo(root=tmp_path, marker="true")
    named = incident_trusted_origin.trusted_invocation(
        environ=_MASTER | {EXPEDITED_INCIDENT_RESPONSE: "1"}, repo=repo
    )
    assert named == Invocation.NORMAL_MASTER


@pytest.mark.parametrize("marker", [None, "false", "yes", ""])
def test_only_the_declared_true_marker_identifies_a_factory_sandbox(
    *, tmp_path: Path, marker: str | None
) -> None:
    repo = _repo(root=tmp_path, marker=marker)
    assert incident_trusted_origin.factory_sandbox(repo=repo) is False


def test_a_marker_in_a_non_repository_or_without_git_is_not_a_factory_sandbox(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    facts = [incident_trusted_origin.factory_sandbox(repo=tmp_path) is False]
    repo = _repo(root=tmp_path / "repo", marker="true")
    monkeypatch.setenv("PATH", str(tmp_path / "no-git"))
    facts.append(incident_trusted_origin.factory_sandbox(repo=repo) is False)
    assert all(facts), facts


def test_the_declared_marker_is_read_only_when_an_incident_flag_is_present(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    probe = Mock(return_value=True)
    monkeypatch.setattr(incident_trusted_origin, "factory_sandbox", probe)
    named = incident_trusted_origin.trusted_invocation(environ={}, repo=tmp_path)
    assert (named, probe.call_count) == (Invocation.ORDINARY, 0)
