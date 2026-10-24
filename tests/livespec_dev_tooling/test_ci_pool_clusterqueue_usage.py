"""Hermetic proof for ClusterQueue flavor usage in the pool emitter."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[2]
_EMITTER = _REPO_ROOT / "ci-runner" / "observability" / "ci-pool-attributed-gauges.sh"
_FIXTURE = Path(__file__).with_name("fixtures") / "clusterqueues-flavors-usage.json"


def _write_executable(*, path: Path, body: str) -> None:
    """Write one executable test double."""
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def _metrics(*, tmp_path: Path) -> dict[str, dict[str, object]]:
    """Run the pool emitter with a fixture-backed Kubernetes and OTLP boundary."""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    captured = tmp_path / "otlp.json"
    _write_executable(
        path=fake_bin / "kubectl",
        body="""#!/bin/sh
case "$*" in
  *'get clusterqueues'*) cat "$CI_TEST_CLUSTERQUEUES" ;;
  *) exit 0 ;;
esac
""",
    )
    _write_executable(
        path=fake_bin / "curl",
        body="""#!/bin/sh
while [ "$#" -gt 0 ]; do
  if [ "$1" = "-d" ]; then
    printf '%s' "$2" > "$CI_TEST_OTLP_CAPTURE"
    exit 0
  fi
  shift
done
exit 2
""",
    )
    completed = subprocess.run(
        ["bash", str(_EMITTER)],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
        env={
            **os.environ,
            "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
            "CI_POOL_KUBECTL": str(fake_bin / "kubectl"),
            "CI_RUNNER_HEARTBEAT_OTLP": "http://127.0.0.1:4319/v1/metrics",
            "CI_POOL_OTLP_LOGS": "http://127.0.0.1:4319/v1/logs",
            "CI_TEST_CLUSTERQUEUES": str(_FIXTURE),
            "CI_TEST_OTLP_CAPTURE": str(captured),
        },
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(captured.read_text(encoding="utf-8"))
    metrics = payload["resourceMetrics"][0]["scopeMetrics"][0]["metrics"]
    return {metric["name"]: metric for metric in metrics}


def _attributes(*, point: dict[str, object]) -> dict[str, str]:
    """Turn OTLP attributes into a test-friendly mapping."""
    return {
        attribute["key"]: attribute["value"]["stringValue"] for attribute in point["attributes"]
    }


def test_pool_emitter_reports_each_clusterqueue_flavor_usage_and_quota(*, tmp_path: Path) -> None:
    """Usage and nominal quota keep resource and flavor identity from Kueue."""
    metrics = _metrics(tmp_path=tmp_path)
    usage = metrics["livespec.ci_pool.queue_resource_usage"]["gauge"]["dataPoints"]
    quota = metrics["livespec.ci_pool.queue_resource_nominal_quota"]["gauge"]["dataPoints"]
    expected_attributes = {
        "ci.queue": "example-cq",
        "ci.flavor": "default",
        "ci.resource": "ci-runner.io/churn-slot",
    }
    assert any(
        point["asDouble"] == 7 and expected_attributes.items() <= _attributes(point=point).items()
        for point in usage
    )
    assert any(
        point["asDouble"] == 12 and expected_attributes.items() <= _attributes(point=point).items()
        for point in quota
    )


def test_pool_emitter_reports_scientific_notation_clusterqueue_quantities(
    *, tmp_path: Path
) -> None:
    """A valid binary Kubernetes quantity is not lost after normalization."""
    metrics = _metrics(tmp_path=tmp_path)
    expected_attributes = {
        "ci.queue": "example-cq",
        "ci.flavor": "default",
        "ci.resource": "memory",
    }
    for metric_name in (
        "livespec.ci_pool.queue_resource_usage",
        "livespec.ci_pool.queue_resource_nominal_quota",
    ):
        points = metrics[metric_name]["gauge"]["dataPoints"]
        assert any(
            point["asDouble"] == 1125899906842624
            and expected_attributes.items() <= _attributes(point=point).items()
            for point in points
        )


def test_pool_emitter_reports_clusterqueue_read_failure_without_unbound_variable(
    *, tmp_path: Path
) -> None:
    """A failed ClusterQueue listing records the omission rather than crashing."""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_executable(
        path=fake_bin / "kubectl",
        body="""#!/bin/sh
case "$*" in
  *'get clusterqueues'*) echo 'clusterqueues unavailable' >&2; exit 1 ;;
  *) exit 0 ;;
esac
""",
    )
    _write_executable(
        path=fake_bin / "curl",
        body="""#!/bin/sh
exit 0
""",
    )

    completed = subprocess.run(
        ["bash", str(_EMITTER)],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
        env={
            **os.environ,
            "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
            "CI_POOL_KUBECTL": str(fake_bin / "kubectl"),
            "CI_RUNNER_HEARTBEAT_OTLP": "http://127.0.0.1:4319/v1/metrics",
            "CI_POOL_OTLP_LOGS": "http://127.0.0.1:4319/v1/logs",
        },
    )

    assert completed.returncode == 1, completed.stderr
    assert "could not read ClusterQueues (clusterqueues unavailable)" in completed.stderr
    assert "unbound variable" not in completed.stderr
