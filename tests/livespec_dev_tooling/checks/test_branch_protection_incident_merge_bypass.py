"""Outside-in tests for the incident-merge bypass actor of `branch_protection_alignment`.

Per SPECIFICATION/contracts.md (v246), the `branch_protection_alignment` check,
every active default-branch ruleset of a queue-required repository carries as
its bypass actors the recovery `Integration` named by
`recovery_bypass_integration_id` and, when the consumer commits an
`incident_merge_integration_id`, the `Integration` with that id whose
`bypass_mode` is `pull_request`, with no other actor. An incident-merge
`Integration` with any other bypass mode, or an incident-merge id equal to the
recovery id, fails `merge_queue_bypass_path`.

The forge double and the in-process runner are the merge-queue tests' own.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.livespec_dev_tooling.checks.test_branch_protection_merge_queue import (
    _RECOVERY_APP_ID,
    _RULESET_ID,
    _Forge,
    _modes,
    _run,
)

__all__: list[str] = []

_INCIDENT_MERGE_APP_ID = 456
_BOTH_KEYS = (
    "[tool.livespec_dev_tooling]\n"
    f"recovery_bypass_integration_id = {_RECOVERY_APP_ID}\n"
    f"incident_merge_integration_id = {_INCIDENT_MERGE_APP_ID}\n"
)
_SAME_APP_FOR_BOTH = (
    "[tool.livespec_dev_tooling]\n"
    f"recovery_bypass_integration_id = {_RECOVERY_APP_ID}\n"
    f"incident_merge_integration_id = {_RECOVERY_APP_ID}\n"
)
_MALFORMED_INCIDENT_KEY = (
    "[tool.livespec_dev_tooling]\n"
    f"recovery_bypass_integration_id = {_RECOVERY_APP_ID}\n"
    'incident_merge_integration_id = "x"\n'
)


def _recovery_actor() -> dict[str, object]:
    return {"actor_type": "Integration", "actor_id": _RECOVERY_APP_ID, "bypass_mode": "always"}


def _incident_actor(*, mode: str = "pull_request") -> dict[str, object]:
    return {"actor_type": "Integration", "actor_id": _INCIDENT_MERGE_APP_ID, "bypass_mode": mode}


def _forge_with(*, actors: list[object]) -> _Forge:
    return _Forge(rulesets={_RULESET_ID: {"bypass_actors": actors}})


def test_the_recovery_and_a_pull_request_incident_merge_app_pass(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """v246 scenario: both declared Integrations, incident-merge in pull_request mode."""
    forge = _forge_with(actors=[_recovery_actor(), _incident_actor()])
    rc, findings = _run(
        forge=forge, tmp_path=tmp_path, monkeypatch=monkeypatch, capsys=capsys, pyproject=_BOTH_KEYS
    )
    assert (rc, _modes(findings=findings)) == (0, [])


def test_an_incident_merge_app_that_is_the_recovery_app_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """v246 scenario: incident_merge_integration_id == recovery id -> one bypass finding."""
    forge = _forge_with(actors=[_recovery_actor()])
    rc, findings = _run(
        forge=forge,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        pyproject=_SAME_APP_FOR_BOTH,
    )
    assert (rc, _modes(findings=findings)) == (4, ["merge_queue_bypass_path"])


@pytest.mark.parametrize("mode", ["always", "exempt"])
def test_an_incident_merge_app_whose_bypass_mode_is_not_pull_request_fails(
    *,
    mode: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """v246 scenario: the incident-merge Integration must not be able to push directly."""
    forge = _forge_with(actors=[_recovery_actor(), _incident_actor(mode=mode)])
    rc, findings = _run(
        forge=forge, tmp_path=tmp_path, monkeypatch=monkeypatch, capsys=capsys, pyproject=_BOTH_KEYS
    )
    errors = [f for f in findings if f.get("level") == "error"]
    facts = [
        (rc, _modes(findings=findings)) == (4, ["merge_queue_bypass_path"]),
        "pull_request" in str(errors[0].get("event")),
    ]
    assert all(facts)


@pytest.mark.parametrize(
    "actors",
    [
        [_recovery_actor(), _incident_actor(), {"actor_type": "RepositoryRole", "actor_id": 5}],
        [_recovery_actor(), _incident_actor(), _incident_actor()],
        [_incident_actor()],
    ],
)
def test_a_declared_incident_merge_app_admits_no_other_bypass_set(
    *,
    actors: list[object],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Declared, the ruleset carries exactly the two Integrations and no other actor."""
    rc, findings = _run(
        forge=_forge_with(actors=actors),
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        pyproject=_BOTH_KEYS,
    )
    assert (rc, _modes(findings=findings)) == (4, ["merge_queue_bypass_path"])


def test_an_undeclared_incident_merge_app_is_still_another_actor(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Undeclared, only the recovery Integration may bypass: the pre-v246 rule stands."""
    forge = _forge_with(actors=[_recovery_actor(), _incident_actor()])
    rc, findings = _run(forge=forge, tmp_path=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert (rc, _modes(findings=findings)) == (4, ["merge_queue_bypass_path"])


def test_a_recovery_only_ruleset_still_passes_without_the_incident_merge_key(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rc, findings = _run(
        forge=_forge_with(actors=[_recovery_actor()]),
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
    )
    assert (rc, _modes(findings=findings)) == (0, [])


def test_a_malformed_incident_merge_integration_id_is_a_config_failure(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rc, _ = _run(
        forge=_Forge(),
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        pyproject=_MALFORMED_INCIDENT_KEY,
    )
    assert rc == 1
