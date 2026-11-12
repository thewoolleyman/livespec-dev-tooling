"""Consumer-tier scenarios for the k3s control-plane telemetry emitter."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]
_EMITTER = _REPO_ROOT / "ci-runner" / "observability" / "ci-k3s-control-plane-telemetry.sh"
_COVERAGE = _REPO_ROOT / "tests" / "heading-coverage.json"


def _executable(*, path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def _emit(*, tmp_path: Path, metrics_text: str) -> dict[str, object]:
    """Run the committed emitter against a fixture scrape and capture its OTLP document."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    readyz = tmp_path / "readyz.txt"
    metrics = tmp_path / "metrics.txt"
    captured = tmp_path / "otlp.json"
    readyz.write_text("[+]etcd ok\\n", encoding="utf-8")
    metrics.write_text(metrics_text, encoding="utf-8")
    _executable(
        path=bin_dir / "kubectl",
        body="""#!/usr/bin/env bash
case "$*" in
  *readyz*) cat "$READYZ_FIXTURE"; exit 0 ;;
  *metrics*) cat "$METRICS_FIXTURE" ;;
esac
""",
    )
    _executable(
        path=bin_dir / "curl",
        body="""#!/usr/bin/env bash
for argument in "$@"; do
  case "$argument" in @*) cp "${argument#@}" "$OTLP_CAPTURE" ;; esac
done
""",
    )
    _executable(
        path=bin_dir / "df",
        body="""#!/usr/bin/env bash
printf 'Used 1B-blocks\\n123 456\\n'
""",
    )
    completed = subprocess.run(
        ["bash", str(_EMITTER)],
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "READYZ_FIXTURE": str(readyz),
            "METRICS_FIXTURE": str(metrics),
            "OTLP_CAPTURE": str(captured),
            "CI_K3S_CONTROL_PLANE_HOST_NAME": "fixture-control-plane",
        },
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(captured.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _metric(*, payload: dict[str, object], name: str) -> dict[str, object]:
    metrics = payload["resourceMetrics"][0]["scopeMetrics"][0]["metrics"]
    return next(metric for metric in metrics if metric["name"] == name)


def _attribute(*, point: dict[str, object], name: str) -> str:
    return next(
        attribute["value"]["stringValue"]
        for attribute in point["attributes"]
        if attribute["key"] == name
    )


def _coverage_test(*, heading: str) -> str:
    entries = json.loads(_COVERAGE.read_text(encoding="utf-8"))
    entry = next(item for item in entries if item["heading"] == heading)
    return entry["test"]


def test_lease_put_latency_is_isolated(tmp_path: Path) -> None:
    """A PUT lease series is retained independently of every other request series."""
    payload = _emit(
        tmp_path=tmp_path,
        metrics_text="\n".join(
            [
                'apiserver_request_duration_seconds_bucket{verb="PUT",resource="leases",scope="namespace",le="0.1"} 2',
                'apiserver_request_duration_seconds_bucket{verb="PUT",resource="leases",scope="namespace",le="+Inf"} 4',
                'apiserver_request_duration_seconds_sum{verb="PUT",resource="leases",scope="namespace"} 0.9',
                'apiserver_request_duration_seconds_count{verb="PUT",resource="leases",scope="namespace"} 4',
                'apiserver_request_duration_seconds_bucket{verb="PUT",resource="leases",scope="cluster",le="0.1"} 3',
                'apiserver_request_duration_seconds_bucket{verb="PUT",resource="leases",scope="cluster",le="+Inf"} 5',
                'apiserver_request_duration_seconds_sum{verb="PUT",resource="leases",scope="cluster"} 1.2',
                'apiserver_request_duration_seconds_count{verb="PUT",resource="leases",scope="cluster"} 5',
                'apiserver_request_duration_seconds_bucket{verb="GET",resource="pods",le="+Inf"} 1',
                'apiserver_request_duration_seconds_sum{verb="GET",resource="pods"} 0.01',
                'apiserver_request_duration_seconds_count{verb="GET",resource="pods"} 1',
                "",
            ]
        ),
    )
    points = _metric(payload=payload, name="apiserver_request_duration_seconds")["histogram"][
        "dataPoints"
    ]
    assert {
        (_attribute(point=point, name="verb"), _attribute(point=point, name="resource"))
        for point in points
    } == {
        ("GET", "pods"),
        ("PUT", "leases"),
    }
    lease_put = next(
        point
        for point in points
        if (_attribute(point=point, name="verb"), _attribute(point=point, name="resource"))
        == ("PUT", "leases")
    )
    assert lease_put["count"] == "9"
    assert lease_put["sum"] == 2.1
    assert {attribute["key"] for attribute in lease_put["attributes"]} == {"verb", "resource"}
    assert (
        _coverage_test(
            heading="## Scenario: a lease PUT's latency is readable apart from every other API-server request"
        )
        == "tests.consumer.test_control_plane_emitter_scenarios.test_lease_put_latency_is_isolated"
    )
