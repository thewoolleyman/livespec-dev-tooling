"""Unit tests for `livespec_dev_tooling/_pre_commit_delegate_evidence.py`."""

from __future__ import annotations

from pathlib import Path

import pytest
from returns.result import Failure

from livespec_dev_tooling import _pre_commit_delegate_evidence as evidence
from livespec_dev_tooling.gate_remote_invocation import GateCommandNotRun

__all__: list[str] = []


def test_an_unreadable_host_never_counts_as_holding_the_judged_tree(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pre-push evidence needs the host to SHOW it still holds the tree, clean."""
    monkeypatch.setattr(
        evidence,
        "default_gate_command_runner",
        lambda **_kwargs: Failure(GateCommandNotRun(argv=("git",), detail="not found")),
    )

    assert evidence.host_holds_tree(repo_root=tmp_path, tree_hash="a" * 40) is False
