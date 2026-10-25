"""The k3s control-plane emitter's read-only API and datastore observations."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_EMITTER = _REPO_ROOT / "ci-runner" / "observability" / "ci-k3s-control-plane-telemetry.sh"


def _executable(*, path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def _emit(*, tmp_path: Path, readyz_exit: int = 0) -> dict[str, object]:
    """Run the emitter against captured API responses and return its OTLP payload."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    readyz = tmp_path / "readyz.txt"
    metrics = tmp_path / "metrics.txt"
    captured = tmp_path / "otlp.json"
    readyz.write_text("[+]etcd ok\n[-]etcd-readiness failed: sqlite busy\n", encoding="utf-8")
    metrics.write_text(
        "\n".join(
            [
                'apiserver_storage_size_bytes{storage="kine"} 2048',
                'etcd_request_duration_seconds_bucket{verb="GET",le="0.1"} 2',
                'etcd_request_duration_seconds_bucket{verb="GET",le="+Inf"} 4',
                'etcd_request_duration_seconds_sum{verb="GET"} 0.9',
                'etcd_request_duration_seconds_count{verb="GET"} 4',
                "",
            ]
        ),
        encoding="utf-8",
    )
    _executable(
        path=bin_dir / "kubectl",
        body="""#!/usr/bin/env bash
case "$*" in
  *readyz*) cat "$READYZ_FIXTURE"; exit "$READYZ_EXIT" ;;
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
    environment = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "READYZ_FIXTURE": str(readyz),
        "READYZ_EXIT": str(readyz_exit),
        "METRICS_FIXTURE": str(metrics),
        "OTLP_CAPTURE": str(captured),
        "CI_K3S_CONTROL_PLANE_HOST_NAME": "k3s-server",
    }
    completed = subprocess.run(
        ["bash", str(_EMITTER)],
        capture_output=True,
        check=False,
        env=environment,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(captured.read_text(encoding="utf-8"))


def _metric(payload: dict[str, object], name: str) -> dict[str, object]:
    metrics = payload["resourceMetrics"][0]["scopeMetrics"][0]["metrics"]
    return next(metric for metric in metrics if metric["name"] == name)


def _attribute(point: dict[str, object], name: str) -> str:
    return next(
        attribute["value"]["stringValue"]
        for attribute in point["attributes"]
        if attribute["key"] == name
    )


def test_emitter_reports_api_and_datastore_metrics(tmp_path: Path) -> None:
    """A successful API response preserves its readiness, storage and histogram facts."""
    payload = _emit(tmp_path=tmp_path)
    resource_attributes = payload["resourceMetrics"][0]["resource"]["attributes"]
    assert {one["key"]: one["value"]["stringValue"] for one in resource_attributes}[
        "host.name"
    ] == "k3s-server"
    readiness = _metric(payload, "livespec.ci_k3s.readiness_check")["gauge"]["dataPoints"]
    assert {_attribute(point, "k8s.readiness_check"): point["asInt"] for point in readiness} == {
        "etcd": "1",
        "etcd-readiness": "0",
    }
    assert _metric(payload, "livespec.ci_k3s.readiness_latency_seconds")["gauge"]["dataPoints"]
    assert (
        _metric(payload, "apiserver_storage_size_bytes")["gauge"]["dataPoints"][0]["asDouble"]
        == 2048.0
    )
    histogram = _metric(payload, "etcd_request_duration_seconds")["histogram"]["dataPoints"][0]
    assert histogram["count"] == "4"
    assert histogram["sum"] == 0.9
    assert histogram["bucketCounts"] == ["2", "2"]
    assert histogram["explicitBounds"] == [0.1]
    assert (
        _metric(payload, "livespec.ci_k3s.datastore_used_bytes")["gauge"]["dataPoints"][0]["asInt"]
        == "123"
    )
    assert (
        _metric(payload, "livespec.ci_k3s.datastore_total_bytes")["gauge"]["dataPoints"][0]["asInt"]
        == "456"
    )


def test_emitter_records_an_api_failure_instead_of_silence(tmp_path: Path) -> None:
    """A failed raw readiness request produces a named failed datapoint and latency."""
    payload = _emit(tmp_path=tmp_path, readyz_exit=1)
    readiness = _metric(payload, "livespec.ci_k3s.readiness_check")["gauge"]["dataPoints"]
    assert [
        point
        for point in readiness
        if _attribute(point, "k8s.readiness_check") == "api-server" and point["asInt"] == "0"
    ]
    assert _metric(payload, "livespec.ci_k3s.readiness_latency_seconds")["gauge"]["dataPoints"]
