"""The delegated gate's outcome span, including its fail-soft delivery contract."""

from __future__ import annotations

import importlib.util
import urllib.error

import pytest

pytestmark = pytest.mark.integration


def test_each_gate_outcome_has_one_span_with_the_observable_gate_identity() -> None:
    """A reader can distinguish a red tree from a delegation that decided nothing."""
    module_name = "livespec_dev_tooling.gate_outcome_telemetry"

    assert importlib.util.find_spec(module_name) is not None

    telemetry = importlib.import_module(module_name)
    for verdict, outcome in (
        ("PASSED", "passed"),
        ("FAILED", "failed-tree"),
        ("NO_VERDICT", "no-verdict"),
    ):
        payload = telemetry.build_span_payload(
            outcome=outcome,
            repository="thewoolleyman/widget",
            tree_hash="4b825dc642cb6eb9a060e54bf8d69288fbee4904",
            job_name="gate-widget-7f2qd",
        )
        spans = payload["resourceSpans"][0]["scopeSpans"][0]["spans"]
        attributes = {
            attribute["key"]: next(iter(attribute["value"].values()))
            for attribute in spans[0]["attributes"]
        }

        assert len(spans) == 1, verdict
        assert attributes == {
            "livespec.gate.outcome": outcome,
            "livespec.gate.repository": "thewoolleyman/widget",
            "livespec.gate.tree_hash": "4b825dc642cb6eb9a060e54bf8d69288fbee4904",
            "livespec.gate.job_name": "gate-widget-7f2qd",
        }


def test_a_delegated_gate_verdict_is_unchanged_when_outcome_delivery_fails(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Outcome delivery is a bounded, best-effort observer of an already-decided gate."""
    module_name = "livespec_dev_tooling.gate_outcome_telemetry"

    assert importlib.util.find_spec(module_name) is not None

    telemetry = importlib.import_module(module_name)

    def _unreachable(*args: object, **kwargs: object) -> object:
        _ = (args, kwargs)
        raise urllib.error.URLError("receiver refused connection")

    monkeypatch.setattr(telemetry.urllib.request, "urlopen", _unreachable)

    delivered = telemetry.emit_gate_outcome(
        outcome="passed",
        repository="thewoolleyman/widget",
        tree_hash="4b825dc642cb6eb9a060e54bf8d69288fbee4904",
        job_name="gate-widget-7f2qd",
    )

    assert delivered is False
