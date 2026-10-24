"""Hermetic proof for the host-side k3s control-plane telemetry emitter."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[2]
_EMITTER = _REPO_ROOT / "ci-runner" / "observability" / "ci-k3s-control-plane-gauges.sh"
_FIXTURES = Path(__file__).with_name("fixtures")


def _write_executable(*, path: Path, body: str) -> None:
    """Write one executable test double."""
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def _run_normal_emitter(
    *, tmp_path: Path
) -> tuple[subprocess.CompletedProcess[str], dict[str, object], str]:
    """Run the committed emitter against captured API responses and a stub receiver."""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    captured = tmp_path / "otlp.json"
    kubectl_args = tmp_path / "kubectl.args"
    _write_executable(
        path=fake_bin / "kubectl",
        body="""#!/bin/sh
printf '%s\\n' "$*" > "$CI_TEST_KUBECTL_ARGS"
case "$*" in
  *'/readyz?verbose'*) cat "$CI_TEST_READYZ" ;;
  *'/metrics'*) cat "$CI_TEST_METRICS" ;;
  *) exit 2 ;;
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
    _write_executable(
        path=fake_bin / "df",
        body="""#!/bin/sh
printf '%s\\n' 'Filesystem 1B-blocks Used Available Use% Mounted on'
printf '%s\\n' 'tmpfs 2147483648 1073741824 1073741824 50% /var/lib/rancher/k3s/server/db'
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
            "CI_CONTROL_PLANE_KUBECTL": str(fake_bin / "kubectl"),
            "CI_CONTROL_PLANE_CURL": str(fake_bin / "curl"),
            "CI_CONTROL_PLANE_DF": str(fake_bin / "df"),
            "CI_CONTROL_PLANE_DB_PATH": "/var/lib/rancher/k3s/server/db",
            "CI_CONTROL_PLANE_HOST_NAME": "poweredge-xubuntu",
            "CI_CONTROL_PLANE_NOW_NANO": "1700000000000000000",
            "CI_TEST_KUBECTL_ARGS": str(kubectl_args),
            "CI_TEST_READYZ": str(_FIXTURES / "k3s-control-plane-readyz.txt"),
            "CI_TEST_METRICS": str(_FIXTURES / "k3s-control-plane-metrics.prom"),
            "CI_TEST_OTLP_CAPTURE": str(captured),
        },
    )
    payload = json.loads(captured.read_text(encoding="utf-8")) if captured.is_file() else {}
    return completed, payload, kubectl_args.read_text(encoding="utf-8")


def _metrics(*, payload: dict[str, object]) -> dict[str, dict[str, object]]:
    """Index one OTLP metrics payload by its metric name."""
    resource_metrics = payload["resourceMetrics"]
    scope_metrics = resource_metrics[0]["scopeMetrics"]
    return {metric["name"]: metric for metric in scope_metrics[0]["metrics"]}


def test_control_plane_emitter_reports_readyz_metrics_and_kine_filesystem(
    *, tmp_path: Path
) -> None:
    """One healthy API sample becomes readiness, API metrics, and datastore gauges."""
    assert _EMITTER.is_file(), (
        "ci-runner/observability/ci-k3s-control-plane-gauges.sh must exist: the server "
        "needs one read-only emitter for API readiness, API metrics, and the kine datastore "
        "filesystem rather than a silent gap when the collector excludes tmpfs"
    )
    completed, payload, kubectl_args = _run_normal_emitter(tmp_path=tmp_path)
    assert completed.returncode == 0, completed.stderr
    assert "/etc/otel-collector/kubeconfig" in kubectl_args
    metrics = _metrics(payload=payload)
    assert set(metrics) >= {
        "livespec.k3s.apiserver_readiness",
        "livespec.k3s.apiserver_readyz_latency_seconds",
        "apiserver_storage_size_bytes",
        "etcd_request_duration_seconds",
        "livespec.k3s.kine_datastore_filesystem_used_bytes",
        "livespec.k3s.kine_datastore_filesystem_total_bytes",
    }
    readiness = metrics["livespec.k3s.apiserver_readiness"]["gauge"]["dataPoints"]
    assert {point["asInt"] for point in readiness} == {"1"}
    assert metrics["apiserver_storage_size_bytes"]["gauge"]["dataPoints"][0]["asDouble"] == 2048
    histogram = metrics["etcd_request_duration_seconds"]["histogram"]["dataPoints"][0]
    assert histogram["count"] == "5"
    assert histogram["sum"] == 0.12
    assert (
        metrics["livespec.k3s.kine_datastore_filesystem_used_bytes"]["gauge"]["dataPoints"][0][
            "asInt"
        ]
        == "1073741824"
    )
