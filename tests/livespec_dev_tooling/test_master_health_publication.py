"""The ci-green publisher must never paint a failed aggregate green.

The contract deliberately separates ci-green's required status from the
informational master-health check run.  A required-leg or jobs-read failure is
therefore still a defect even when every gating job returned success: publishing
``green`` in that state would make the master-health consumer accept a red
aggregate.
"""

from __future__ import annotations

import importlib.util
import json
from dataclasses import dataclass, field
from typing import Any

_HEAD_SHA = "a" * 40
_RUN_ID = 418


@dataclass
class _Forge:
    """The publisher's check-run write boundary, retained for assertion."""

    check_runs: list[dict[str, Any]] = field(default_factory=list)

    def create_check_run(self, **payload: Any) -> None:
        self.check_runs.append(payload)


def test_red_ci_green_publishes_neutral_defect_master_health() -> None:
    """A failed required-leg read is defect even with wholly green gating jobs."""
    module_name = "livespec_dev_tooling.master_health_publisher"
    spec = importlib.util.find_spec(module_name)
    assert spec is not None, "ci-green needs the master-health publisher"

    from livespec_dev_tooling.master_health_publisher import publish_master_health

    forge = _Forge()
    publish_master_health(
        forge=forge,
        head_sha=_HEAD_SHA,
        run_id=_RUN_ID,
        ci_green_passed=False,
        jobs=[
            {
                "name": "check-python",
                "result": "success",
                "external_only": False,
                "defect_findings": 0,
                "records": [],
            }
        ],
    )

    assert len(forge.check_runs) == 1
    published = forge.check_runs[0]
    assert published["name"] == "master-health"
    assert published["head_sha"] == _HEAD_SHA
    assert published["conclusion"] == "neutral"
    assert published["output"]["title"] == "master-health: defect"
    assert json.loads(published["output"]["summary"])["verdict"] == "defect"
