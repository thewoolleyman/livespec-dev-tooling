"""A gate lost with its worker retries instead of publishing a failed verdict."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.integration

_TEMPLATE = (
    Path(__file__).resolve().parents[2]
    / "ci-runner"
    / "k3s"
    / "phase2"
    / "gates"
    / "gate-job-template.yaml"
)


def test_a_gate_pod_terminated_for_node_disruption_does_not_count_toward_its_backoff_limit() -> (
    None
):
    """Kubernetes retries a gate whose pod was lost with a departed worker."""
    template = _TEMPLATE.read_text(encoding="utf-8")

    assert (
        re.search(
            r"podFailurePolicy:\n"
            r"\s+rules:\n"
            r"\s+- action: Ignore\n"
            r"\s+onPodConditions:\n"
            r"\s+- type: DisruptionTarget\n"
            r"\s+status: \"?True\"?",
            template,
        )
        is not None
    )
