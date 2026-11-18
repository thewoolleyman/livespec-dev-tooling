"""Runner placement after a homelab worker leaves the CI class.

The architecture overlay is applied to every ARC scale set by the CI-stack
converge.  This integration test renders it from a synthetic per-class
architecture declaration, rather than naming a committed scale set or host,
then evaluates the rendered hard placement requirements against worker labels.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

__all__: list[str] = []

pytestmark = pytest.mark.integration

_PHASE2 = Path(__file__).resolve().parents[2] / "ci-runner" / "k3s" / "phase2"
_RENDER = _PHASE2 / "arc" / "render-arch-overlay.sh"
_WORKER_CLASS = "homelab-worker.livespec.dev/class"
_CI_ENROLLMENT = "k3s-role"


def _render(*, tmp_path: Path) -> dict[str, Any]:
    declaration = tmp_path / "workload-arch.conf"
    declaration.write_text("release synthetic-ci amd64,arm64 none: fixture\\n", encoding="utf-8")
    result = subprocess.run(
        ["/bin/bash", str(_RENDER), "release", "synthetic-ci", str(tmp_path / "overlay.yaml")],
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "WORKLOAD_ARCH_CONF": str(declaration)},
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    rendered: dict[str, Any] = yaml.safe_load((tmp_path / "overlay.yaml").read_text("utf-8"))
    return rendered["template"]["spec"]


def _selects(*, template: dict[str, Any], labels: dict[str, str]) -> bool:
    if any(labels.get(key) != value for key, value in template.get("nodeSelector", {}).items()):
        return False
    terms = template["affinity"]["nodeAffinity"]["requiredDuringSchedulingIgnoredDuringExecution"][
        "nodeSelectorTerms"
    ]
    for term in terms:
        if all(
            expression["operator"] == "In" and labels.get(expression["key"]) in expression["values"]
            for expression in term["matchExpressions"]
        ):
            return True
    return False


def test_an_unenrolled_homelab_worker_is_excluded_but_an_enrolled_one_is_selected(
    tmp_path: Path,
) -> None:
    template = _render(tmp_path=tmp_path)
    unenrolled_worker = {_WORKER_CLASS: "worker", "kubernetes.io/arch": "arm64"}
    enrolled_worker = {**unenrolled_worker, _CI_ENROLLMENT: "arc-runner-host"}

    assert not _selects(template=template, labels=unenrolled_worker)
    assert _selects(template=template, labels=enrolled_worker)
