"""An authority call is bounded by a liveness ceiling, never by its normal latency.

livespec-dev-tooling-yaprm4: a 30 s bound refused an expedited commit and push
when a read-local-gates call on a generation-7 chain took 37-39 s on a quiet
dev host (2026-11-08). The bound must only stop a hung call.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from livespec_dev_tooling import incident_hook_process as module

__all__: list[str] = []

_QUERY = {
    "repository": "owner/repo",
    "item": "incident",
    "attempt": "attempt",
    "phase": "repair",
    "operation": "operation",
    "generation": 1,
    "owner": "operator",
}


def _registered(*, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(module, "_governed_root", lambda **_kwargs: tmp_path)
    monkeypatch.setattr(module, "registered_plugin_root", lambda **_kwargs: tmp_path)


def test_an_authority_call_three_times_slower_than_measured_is_not_cut_off(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    bounds: list[float] = []

    def run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        bounds.append(kwargs["timeout"])
        raise subprocess.TimeoutExpired(argv, kwargs["timeout"])

    _registered(monkeypatch=monkeypatch, tmp_path=tmp_path)
    monkeypatch.setattr(module.subprocess, "run", run)
    with pytest.raises(module.HookRefusalError):
        _ = module.invoke_authority(repo=tmp_path, query=_QUERY, action="read-local-gates")
    # 39 s is the slowest call measured; three times that must still complete.
    assert bounds == [module.AUTHORITY_CALL_CEILING_SECONDS]
    assert module.AUTHORITY_CALL_CEILING_SECONDS >= 3 * 39


def test_a_timed_out_authority_call_names_the_action_and_its_elapsed_seconds(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(argv, kwargs["timeout"])

    _registered(monkeypatch=monkeypatch, tmp_path=tmp_path)
    monkeypatch.setattr(module.subprocess, "run", run)
    with pytest.raises(module.HookRefusalError) as refused:
        _ = module.invoke_authority(repo=tmp_path, query=_QUERY, action="record-local-gates")
    message = str(refused.value)
    assert "record-local-gates" in message
    assert f"{module.AUTHORITY_CALL_CEILING_SECONDS} s" in message
