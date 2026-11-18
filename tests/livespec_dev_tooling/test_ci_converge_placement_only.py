"""A placement value file converges alone (livespec-dev-tooling-vksuu2).

`arc/runner-node-preference.conf` and the other files that only feed the scale
sets' pod placement used to reach the cluster only through the whole-stack
converge, which also applies `gates/gates-rbac.yaml`. These tests pin the split:
`converge-ci-stack.sh --scale-sets-only` helm-upgrades the scale sets and applies
nothing else, and the `ci_converge_unit` role's `ci_placement` tag copies only the
placement files and runs only that mode. The script test RUNS the real script
against stub `kubectl` and `helm` binaries, because no cluster exists in the suite.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

__all__: list[str] = []

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PHASE2 = _REPO_ROOT / "ci-runner" / "k3s" / "phase2"
_STACK = _PHASE2 / "reconstruct" / "converge-ci-stack.sh"
_ROLE = _REPO_ROOT / "ansible" / "roles" / "ci_converge_unit"
_PLACEMENT_FILES = {
    "arc/render-arch-overlay.sh",
    "workload-arch.conf",
    "arc/runner-node-preference.conf",
}

_KUBECTL = r"""#!/usr/bin/env bash
printf 'kubectl %s\n' "$*" >> "$STUB_DIR/calls"
case "$*" in
  "get nodes -l ci-runner.io/always-on=true -o name") echo node/poweredge-xubuntu ;;
esac
exit 0
"""

_HELM = r"""#!/usr/bin/env bash
printf 'helm %s\n' "$*" >> "$STUB_DIR/calls"
release="$3"
args=("$@")
for ((i = 0; i < ${#args[@]}; i++)); do
  if [ "${args[$i]}" = -f ]; then
    cat "${args[$((i + 1))]}" >> "$STUB_DIR/values-$release"
  fi
done
exit 0
"""


def _run(
    tmp_path: Path, *, weight_line: str
) -> tuple[subprocess.CompletedProcess[str], list[str], Path]:
    """Run the script in its mode against stubs, in a copy of the installed tree."""
    tree = tmp_path / "tree"
    tree.mkdir()
    for child in _PHASE2.iterdir():
        if child.name == "arc":
            shutil.copytree(child, tree / "arc")
        else:
            (tree / child.name).symlink_to(child)
    (tree / "observability").unlink(missing_ok=True)
    (tree / "observability").symlink_to(_REPO_ROOT / "ci-runner" / "observability")
    charts = tree / "arc" / "charts"
    charts.mkdir()
    (charts / "gha-runner-scale-set-0.14.2.tgz").write_bytes(b"x")
    (tree / "arc" / "runner-node-preference.conf").write_text(weight_line, encoding="utf-8")
    stub = tmp_path / "stub"
    (stub / "bin").mkdir(parents=True)
    for name, body in (("kubectl", _KUBECTL), ("helm", _HELM)):
        path = stub / "bin" / name
        path.write_text(body, encoding="utf-8")
        path.chmod(0o755)
    env = {
        "PATH": f"{stub / 'bin'}:/usr/bin:/bin",
        "STUB_DIR": str(stub),
        "KUBECONFIG": "/nonexistent",
        "CONVERGE_ARTIFACT_DIR": str(tree),
    }
    done = subprocess.run(
        ["/bin/bash", str(_STACK), "--scale-sets-only"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=120,
    )
    calls_file = stub / "calls"
    calls = calls_file.read_text(encoding="utf-8").splitlines() if calls_file.exists() else []
    return done, calls, stub


def test_scale_sets_only_upgrades_every_scale_set_and_applies_nothing(tmp_path: Path) -> None:
    done, calls, _ = _run(tmp_path, weight_line="gamingpc-xubuntu 77 fixture\n")
    assert done.returncode == 0, done.stdout + done.stderr
    upgrades = [c for c in calls if c.startswith("helm upgrade --install ")]
    assert len(upgrades) >= 15, "every scale set is upgraded"
    verbs = ("apply", "create", "delete", "patch", "label")
    mutating = [
        c
        for c in calls
        if c.startswith("kubectl ") and any(f" {verb} " in f"{c} " for verb in verbs)
    ]
    assert not mutating, f"scale-sets-only must apply and create nothing: {mutating}"
    other_helm = [
        c
        for c in calls
        if c.startswith("helm ") and c not in upgrades and not c.startswith("helm history ")
    ]
    assert not other_helm


def test_the_changed_weight_reaches_every_scale_sets_overlay(tmp_path: Path) -> None:
    done, _, stub = _run(tmp_path, weight_line="gamingpc-xubuntu 77 fixture\n")
    assert done.returncode == 0, done.stdout + done.stderr
    rendered = sorted(stub.glob("values-*"))
    assert rendered
    for values in rendered:
        weights = [
            term["weight"]
            for doc in yaml.safe_load_all(values.read_text(encoding="utf-8"))
            if isinstance(doc, dict)
            for term in doc.get("template", {})
            .get("spec", {})
            .get("affinity", {})
            .get("nodeAffinity", {})
            .get("preferredDuringSchedulingIgnoredDuringExecution", [])
        ]
        assert weights == [77], f"{values.name} carries the changed weight: {weights}"


def test_an_unknown_argument_is_refused() -> None:
    done = subprocess.run(
        ["/bin/bash", str(_STACK), "--bogus"],
        capture_output=True,
        text=True,
        env={"PATH": os.environ["PATH"], "KUBECONFIG": "/nonexistent"},
        check=False,
        timeout=60,
    )
    assert done.returncode == 2


def test_the_role_places_exactly_the_placement_files_under_its_own_tag() -> None:
    defaults = yaml.safe_load((_ROLE / "defaults" / "main.yml").read_text(encoding="utf-8"))
    placed = {item["dest"] for item in defaults["ci_converge_unit_placement_files"]}
    assert placed == _PLACEMENT_FILES
    owned = {item["dest"] for item in defaults["ci_converge_unit_files"]}
    assert not placed & owned, "one list, one owner per file"
    tasks = yaml.safe_load((_ROLE / "tasks" / "main.yml").read_text(encoding="utf-8"))
    imported = [t for t in tasks if "ansible.builtin.import_tasks" in t]
    assert [t["tags"] for t in imported] == [["ci_placement"]]
    assert imported[0]["ansible.builtin.import_tasks"] == "placement.yml"
    full = next(t for t in tasks if t.get("name") == "Copy the named members of the installed tree")
    assert (
        "ci_converge_unit_placement_files" in full["loop"]
    ), "the full apply installs the placement files too"


def test_the_placement_tasks_copy_only_placement_files_and_run_only_the_mode() -> None:
    text = (_ROLE / "tasks" / "placement.yml").read_text(encoding="utf-8")
    tasks = yaml.safe_load(text)
    commands = [t for t in tasks if "ansible.builtin.command" in t]
    assert len(commands) == 1
    assert commands[0]["ansible.builtin.command"]["argv"][-1] == "--scale-sets-only"
    assert "gates" not in text
    assert "ci_converge_unit_files" not in text
    copies = [t for t in tasks if "ansible.builtin.copy" in t]
    assert [t["loop"] for t in copies] == ["{{ ci_converge_unit_placement_files }}"]
