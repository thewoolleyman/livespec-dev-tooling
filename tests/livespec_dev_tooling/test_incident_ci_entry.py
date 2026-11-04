"""Normal master precedence is resolved before incident payloads or authority reads."""

from __future__ import annotations

from livespec_dev_tooling import incident_ci_entry
from livespec_dev_tooling.incident_ci_policy import CiEvent, CiTarget

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-egy3ri


def test_normal_master_scrubs_flags_before_any_incident_payload_or_reader(tmp_path):
    entry = incident_ci_entry.CiEntry(
        repo=tmp_path, targets=(CiTarget(name="check-lint", classification="fast"),)
    )
    event = CiEvent(kind="push", repository="owner/repo", base_sha="a" * 40, head_sha="b" * 40)
    plan = entry.plan(
        event=event,
        payload="not-json",
        environ={
            "EXPEDITED_INCIDENT_RESPONSE": "malformed",
            "EXPEDITED_INCIDENT_RESPONSE_REVERT": "malformed",
            "LIVESPEC_INCIDENT_CONTEXT": "malformed",
        },
    )
    assert plan is not None
    assert plan.mode == "normal"
    assert plan.selected == entry.targets
    assert dict(plan.environment) == {}
