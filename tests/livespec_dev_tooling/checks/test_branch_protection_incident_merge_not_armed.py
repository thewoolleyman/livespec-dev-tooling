"""Outside-in tests for the not-yet-armed incident-merge App of `branch_protection_alignment`.

Per SPECIFICATION/contracts.md (v247), a committed `incident_merge_integration_id`
whose `Integration` is not yet on the ruleset is the not-yet-armed state and does
not fail: declaring the key is the adoption and adding the `Integration` to the
ruleset is the arming. An actor that is neither the recovery App nor the declared
incident-merge App still fails `merge_queue_bypass_path`.

The forge double and the in-process runner are the merge-queue tests' own.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.livespec_dev_tooling.checks.test_branch_protection_incident_merge_bypass import (
    _BOTH_KEYS,
    _forge_with,
    _incident_actor,
    _recovery_actor,
)
from tests.livespec_dev_tooling.checks.test_branch_protection_merge_queue import (
    _modes,
    _run,
)

__all__: list[str] = []

_UNDECLARED_ACTOR_ID = 789


def _stranger() -> dict[str, object]:
    return {
        "actor_type": "Integration",
        "actor_id": _UNDECLARED_ACTOR_ID,
        "bypass_mode": "pull_request",
    }


def test_a_declared_incident_merge_app_not_yet_on_the_ruleset_passes(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """v247 scenario: adoption (the key) precedes arming (the ruleset entry)."""
    rc, findings = _run(
        forge=_forge_with(actors=[_recovery_actor()]),
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        pyproject=_BOTH_KEYS,
    )
    assert (rc, _modes(findings=findings)) == (0, [])


@pytest.mark.parametrize(
    "actors",
    [
        [_recovery_actor(), _stranger()],
        [_recovery_actor(), _incident_actor(), _stranger()],
        [_incident_actor()],
        [],
    ],
)
def test_an_actor_that_is_neither_recovery_nor_declared_still_fails(
    *,
    actors: list[object],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The recovery App is required, and no actor beyond the declared two is admitted."""
    rc, findings = _run(
        forge=_forge_with(actors=actors),
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        pyproject=_BOTH_KEYS,
    )
    assert (rc, _modes(findings=findings)) == (4, ["merge_queue_bypass_path"])
