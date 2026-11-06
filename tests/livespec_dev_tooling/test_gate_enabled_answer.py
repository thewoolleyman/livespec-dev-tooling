"""Unit tests for `livespec_dev_tooling._gate_enabled_answer`: the pre-push `enabled` exit code.

Every answer the recipe branches on, from the facts the caller has already read:
a selected push delegates (0); an opted-in host the group repair vouches for
delegates under that group (0); an opted-in non-Linux host that cannot read the
gates kubeconfig is refused naming its missing gates-client enrollment (78); an
opted-in Linux host falls through to the local aggregate and says so (1); and a
repository that has not opted in falls through silently (1).
"""

from __future__ import annotations

import platform
from pathlib import Path

import pytest
import structlog
from structlog.testing import capture_logs

from livespec_dev_tooling import _gate_enabled_answer as answer
from livespec_dev_tooling.gate_credential import GATES_KUBECONFIG_ENV

__all__: list[str] = []

_LOG = structlog.get_logger("test")


def _no_group(*, opted_in: bool) -> None:
    del opted_in


def _the_gates_group(*, opted_in: bool) -> str:
    del opted_in
    return "gates"


@pytest.fixture(autouse=True)
def _an_unreadable_credential(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(GATES_KUBECONFIG_ENV, str(tmp_path / "absent.kubeconfig"))
    monkeypatch.setattr(answer, "group_repair_group", _no_group)


def test_a_selected_push_delegates() -> None:
    assert answer.enabled_answer(selected=True, opted_in=True, log=_LOG) == 0


def test_a_host_the_group_repair_vouches_for_delegates_under_that_group(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(answer, "group_repair_group", _the_gates_group)
    with capture_logs() as logs:
        assert answer.enabled_answer(selected=False, opted_in=True, log=_LOG) == 0
    assert [entry["group"] for entry in logs] == ["gates"]


def test_an_opted_in_non_linux_host_without_the_credential_is_refused(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    with capture_logs() as logs:
        code = answer.enabled_answer(selected=False, opted_in=True, log=_LOG)
    assert code == answer.REFUSED_UNENROLLED_HOST
    [entry] = logs
    assert entry["event"] == answer.UNENROLLED_NON_LINUX_HOST
    assert "gates-client enrollment" in entry["event"]
    assert entry["kubeconfig"] == str(tmp_path / "absent.kubeconfig")


def test_an_opted_in_linux_host_without_the_credential_gates_locally(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    with capture_logs() as logs:
        assert answer.enabled_answer(selected=False, opted_in=True, log=_LOG) == 1
    assert [entry["event"] for entry in logs] == [answer.GATED_LOCALLY]


def test_a_repository_that_has_not_opted_in_falls_through_silently(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    with capture_logs() as logs:
        assert answer.enabled_answer(selected=False, opted_in=False, log=_LOG) == 1
    assert logs == []
