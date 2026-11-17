"""The ARC runner pods' soft fill order, rendered from runner-node-preference.conf.

`render-arch-overlay.sh` adds one weighted node preference per line of the
declared fill-order file to every scale set's runner pod. These tests assert
the derivation (the rendered preferences are exactly the file's entries) and
the two properties that make it safe: it is only ever a PREFERENCE, never a
requirement beside the architecture rule, and an empty or absent file renders
none. They never pin a committed weight, as the contracts rule on committed
configuration values requires.
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
_COMMITTED = _PHASE2 / "arc" / "runner-node-preference.conf"
_DEFAULTS = Path(__file__).resolve().parents[2] / "ansible/roles/ci_converge_unit/defaults/main.yml"
_ARCH = "release fake-set amd64,arm64 none: a fixture\n"


def _overlay(*, tmp_path: Path, preference: Path | None) -> dict[str, Any]:
    (tmp_path / "arch.conf").write_text(_ARCH, encoding="utf-8")
    env = {"PATH": "/usr/bin:/bin", "WORKLOAD_ARCH_CONF": str(tmp_path / "arch.conf")}
    if preference is not None:
        env["RUNNER_NODE_PREFERENCE_CONF"] = str(preference)
    done = subprocess.run(
        ["/bin/bash", str(_RENDER), "release", "fake-set", str(tmp_path / "out")],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=30,
    )
    assert done.returncode == 0, done.stderr
    rendered: dict[str, Any] = yaml.safe_load((tmp_path / "out").read_text(encoding="utf-8"))
    affinity: dict[str, Any] = rendered["template"]["spec"]["affinity"]["nodeAffinity"]
    return affinity


def _entries(*, path: Path) -> list[tuple[str, int]]:
    rows: list[tuple[str, int]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            fields = line.split()
            rows.append((fields[0], int(fields[1])))
    return rows


def test_the_rendered_preferences_are_exactly_the_declared_entries(tmp_path: Path) -> None:
    affinity = _overlay(tmp_path=tmp_path, preference=_COMMITTED)
    rendered = [
        (
            term["preference"]["matchExpressions"][0]["values"][0],
            term["weight"],
        )
        for term in affinity["preferredDuringSchedulingIgnoredDuringExecution"]
    ]
    assert rendered == _entries(path=_COMMITTED)
    assert rendered, "the committed file declares at least one node"
    assert all(1 <= weight <= 100 for _, weight in rendered)


def test_a_node_is_only_ever_preferred_never_required(tmp_path: Path) -> None:
    affinity = _overlay(tmp_path=tmp_path, preference=_COMMITTED)
    required = affinity["requiredDuringSchedulingIgnoredDuringExecution"]["nodeSelectorTerms"]
    keys = {e["key"] for term in required for e in term["matchExpressions"]}
    assert keys == {"kubernetes.io/arch"}, "a node name must never be a hard requirement"


def test_an_empty_or_absent_file_renders_no_preference(tmp_path: Path) -> None:
    empty = tmp_path / "empty.conf"
    empty.write_text("# only a comment\n\n", encoding="utf-8")
    for source in (empty, tmp_path / "missing.conf"):
        affinity = _overlay(tmp_path=tmp_path, preference=source)
        assert "preferredDuringSchedulingIgnoredDuringExecution" not in affinity
        assert "requiredDuringSchedulingIgnoredDuringExecution" in affinity


def test_the_converge_unit_installs_the_preference_file_beside_the_renderer() -> None:
    defaults = yaml.safe_load(_DEFAULTS.read_text(encoding="utf-8"))
    installed = {
        str(item["dest"])
        for value in defaults.values()
        if isinstance(value, list)
        for item in value
        if isinstance(item, dict) and "dest" in item
    }
    assert "arc/runner-node-preference.conf" in installed
