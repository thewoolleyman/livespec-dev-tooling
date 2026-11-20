"""Regression coverage for capacity changes paired with cohort-quota changes."""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from types import ModuleType

import pytest

__all__: list[str] = []

_REPO = Path(__file__).resolve().parents[2]
_PROFILES = _REPO / "ci-runner" / "k3s" / "phase0-bare-metal" / "profiles"
_QUOTA = _REPO / "ci-runner" / "k3s" / "phase2" / "kueue" / "cluster-queue-fabro.yaml"
_POSTURE_TEST = Path(__file__).with_name("test_runner_only_node_posture.py")
_MODULE_NAME = "runner_only_node_posture_under_test"


def _posture_module() -> ModuleType:
    """Load the posture test from its committed path."""
    spec = importlib.util.spec_from_file_location(_MODULE_NAME, _POSTURE_TEST)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("profile_name", [path.name for path in sorted(_PROFILES.glob("*.env"))])
def test_the_posture_check_accepts_each_profile_capacity_with_a_matching_quota(
    *, monkeypatch: pytest.MonkeyPatch, profile_name: str
) -> None:
    """A profile edit and its matching cohort quota edit need no posture-test edit."""
    profile = _PROFILES / profile_name
    original_read_text = Path.read_text
    profile_text = original_read_text(profile, encoding="utf-8")
    match = re.search(r"^ADMISSION_CAPACITY_C=(\d+)$", profile_text, re.MULTILINE)
    assert match is not None, f"{profile} must declare ADMISSION_CAPACITY_C"
    capacity = int(match[1])

    def _read_text(
        path: Path, encoding: str | None = None, errors: str | None = None
    ) -> str:
        text = original_read_text(path, encoding=encoding, errors=errors)
        if path == profile:
            return re.sub(
                r"^ADMISSION_CAPACITY_C=\d+$",
                f"ADMISSION_CAPACITY_C={capacity + 1}",
                text,
                flags=re.MULTILINE,
            )
        if path == _QUOTA:
            return re.sub(
                r"(?m)^(\s+nominalQuota: )1$",
                r"\g<1>2",
                text,
                count=1,
            )
        return text

    monkeypatch.setattr(Path, "read_text", _read_text)
    _posture_module().test_the_rebalance_moves_eight_slots_from_poweredge_to_hp_and_keeps_the_total_at_44()
