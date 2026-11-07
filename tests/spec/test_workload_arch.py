"""The per-class architecture selection of `SPECIFICATION/non-functional-requirements.md`, "Homelab worker nodes".

These run the real `ci-runner/k3s/phase2/arc/render-arch-overlay.sh` under `/bin/bash` against a
mocked architecture list, so no assertion restates a committed architecture value; the one test
that reads the committed list asserts a value-independent rule (every scale set the CI stack
converge installs is declared there).
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest
import yaml

__all__: list[str] = []

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PHASE2 = _REPO_ROOT / "ci-runner" / "k3s" / "phase2"
_RENDER = _PHASE2 / "arc" / "render-arch-overlay.sh"
_CONVERGE = _PHASE2 / "reconstruct" / "converge-ci-stack.sh"
_CONF = _PHASE2 / "workload-arch.conf"


def _render(*, tmp_path: Path, conf: str, kind: str, name: str) -> subprocess.CompletedProcess[str]:
    (tmp_path / "list.conf").write_text(conf, encoding="utf-8")
    return subprocess.run(
        ["/bin/bash", str(_RENDER), kind, name, str(tmp_path / "out")],
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "WORKLOAD_ARCH_CONF": str(tmp_path / "list.conf")},
        check=False,
        timeout=30,
    )


def _overlay_arches(*, tmp_path: Path) -> list[str]:
    overlay = yaml.safe_load((tmp_path / "out").read_text(encoding="utf-8"))
    affinity = overlay["template"]["spec"]["affinity"]["nodeAffinity"]
    [term] = affinity["requiredDuringSchedulingIgnoredDuringExecution"]["nodeSelectorTerms"]
    [expr] = term["matchExpressions"]
    assert expr["key"] == "kubernetes.io/arch"
    assert expr["operator"] == "In"
    return list(expr["values"])


def test_a_release_gets_a_required_affinity_on_exactly_its_declared_arches(tmp_path: Path) -> None:
    conf = "# mocked\nrelease alpha-k3s amd64 arm64: lacks\nrelease beta-k3s amd64,arm64 none\n"
    assert _render(tmp_path=tmp_path, conf=conf, kind="release", name="alpha-k3s").returncode == 0
    assert _overlay_arches(tmp_path=tmp_path) == ["amd64"]
    assert _render(tmp_path=tmp_path, conf=conf, kind="release", name="beta-k3s").returncode == 0
    assert _overlay_arches(tmp_path=tmp_path) == ["amd64", "arm64"]


def test_an_amd64_only_class_never_admits_an_arm64_node(tmp_path: Path) -> None:
    conf = "release only-amd64-k3s amd64 arm64: no arm64 image\n"
    assert (
        _render(tmp_path=tmp_path, conf=conf, kind="release", name="only-amd64-k3s").returncode == 0
    )
    assert "arm64" not in _overlay_arches(tmp_path=tmp_path)


def test_gate_and_factory_classes_render_their_arches_alone(tmp_path: Path) -> None:
    conf = "gate gate amd64 lacks\nfactory python-agent amd64,arm64 none\n"
    assert _render(tmp_path=tmp_path, conf=conf, kind="gate", name="gate").returncode == 0
    assert (tmp_path / "out").read_text(encoding="utf-8") == "amd64\n"
    assert (
        _render(tmp_path=tmp_path, conf=conf, kind="factory", name="python-agent").returncode == 0
    )
    assert (tmp_path / "out").read_text(encoding="utf-8") == "amd64,arm64\n"


def test_an_undeclared_class_is_refused_rather_than_placed_anywhere(tmp_path: Path) -> None:
    result = _render(
        tmp_path=tmp_path, conf="release alpha-k3s amd64 x\n", kind="release", name="gamma-k3s"
    )
    assert result.returncode != 0
    assert "gamma-k3s" in result.stderr
    assert not (tmp_path / "out").exists()


def test_every_scale_set_the_ci_stack_converge_installs_is_declared() -> None:
    converge = _CONVERGE.read_text(encoding="utf-8")
    block = converge.split("declare -A SCALE_SETS=(", 1)[1].split("\n)", 1)[0]
    releases = set(re.findall(r"\[([a-z0-9-]+)\]=", block))
    declared = {
        line.split()[1]
        for line in _CONF.read_text(encoding="utf-8").splitlines()
        if line.startswith("release ")
    }
    assert releases, "the converge's SCALE_SETS map must name at least one release"
    assert releases <= declared, f"undeclared releases: {sorted(releases - declared)}"


def test_the_converge_passes_each_release_its_arch_overlay() -> None:
    converge = _CONVERGE.read_text(encoding="utf-8")
    assert 'render-arch-overlay.sh" release "$release" "$arch_overlay"' in converge
    assert '-f "$arch_overlay"' in converge
