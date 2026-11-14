"""The lifecycle sweep's churn-slot quota gauge sums every flavor of every ClusterQueue.

A ClusterQueue that lists `churn-slot-worker-arm64-flavor` (nominalQuota 0) after
`churn-slot-flavor` carries two churn-slot tokens. The sweep's
`livespec.ci_churn_slot.quota_sum` must add them all; keeping the last token read
every such queue as 0 (livespec-dev-tooling-y5ewfc).
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

__all__: list[str] = []

_SCANNER = (
    Path(__file__).resolve().parents[2]
    / "ci-runner"
    / "k3s"
    / "phase2"
    / "runner-pod-lifecycle"
    / "scan-runner-pod-lifecycle.sh"
)


def test_quota_sum_adds_every_churn_slot_flavor_of_every_queue(tmp_path: Path) -> None:
    """Quotas totalling 31 on the primary flavor and 1 on the arm64 flavor report 32."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    payload = tmp_path / "metrics.json"
    containerd_log = tmp_path / "containerd.log"
    containerd_log.write_text("", encoding="utf-8")
    (bin_dir / "kubectl").write_text(
        "#!/usr/bin/env bash\n"
        'case "$*" in\n'
        "  *clusterqueue*)\n"
        "    printf '%s\\n'"
        " 'primary-cq|ci-runner.io/churn-slot=30 ci-runner.io/churn-slot=0 |1|2'"
        " 'overflow-cq|ci-runner.io/churn-slot=1 ci-runner.io/churn-slot=1 |0|0'"
        " 'phase1-proof-cq|cpu=4 memory=8Gi |0|0'\n"
        "    ;;\n"
        "esac\n"
        "exit 0\n",
        encoding="utf-8",
    )
    (bin_dir / "journalctl").write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    (bin_dir / "curl").write_text(
        '#!/usr/bin/env bash\nwhile [ "$#" -gt 0 ]; do\n  if [ "$1" = "-d" ]; then\n'
        '    printf \'%s\' "$2" > "$OTLP_CAPTURE"\n    exit 0\n  fi\n  shift\ndone\n',
        encoding="utf-8",
    )
    for tool in bin_dir.iterdir():
        tool.chmod(0o755)

    subprocess.run(
        [
            "bash",
            str(_SCANNER),
            "--containerd-log",
            str(containerd_log),
            "--state-file",
            str(tmp_path / "state"),
            "--otlp-endpoint",
            "http://127.0.0.1:1/v1/metrics",
        ],
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "KUBECONFIG": "/etc/rancher/k3s/k3s.yaml",
            "OTLP_CAPTURE": str(payload),
        },
        text=True,
        timeout=120,
    )

    metrics = {
        metric["name"]: metric["gauge"]["dataPoints"]
        for metric in json.loads(payload.read_text(encoding="utf-8"))["resourceMetrics"][0][
            "scopeMetrics"
        ][0]["metrics"]
    }
    assert [point["asInt"] for point in metrics["livespec.ci_churn_slot.quota_sum"]] == ["32"]
