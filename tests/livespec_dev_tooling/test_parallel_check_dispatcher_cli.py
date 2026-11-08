"""Tests for the dispatcher's command-line surface."""

from __future__ import annotations

import sys

import pytest

from livespec_dev_tooling.parallel_check_dispatcher_cli import parse_args

__all__: list[str] = []


def test_parse_args_reads_workers_skip_and_targets(*, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        sys, "argv", ["dispatcher", "--workers", "3", "--skip", "a b", "--", "x", "y"]
    )
    args = parse_args()
    assert args.workers == 3
    assert args.skip == "a b"
    assert args.targets == ["x", "y"]


def test_parse_args_defaults_workers_to_none_so_the_cpu_derivation_applies(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "argv", ["dispatcher"])
    args = parse_args()
    assert args.workers is None
    assert args.skip == ""
    assert args.targets == []
