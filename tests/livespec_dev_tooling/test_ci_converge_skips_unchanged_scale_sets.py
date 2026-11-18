"""The converge upgrades only scale sets whose inputs changed (livespec-dev-tooling-zl6gch).

The decision is taken from an inputs digest stored on the LIVE helm release (its
history description) and read back from the cluster. These tests RUN the real
script in `--scale-sets-only` mode against a stateful stub `helm` standing in for
the cluster: it remembers each release's description between runs.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PHASE2 = _REPO_ROOT / "ci-runner" / "k3s" / "phase2"
_STACK = _PHASE2 / "reconstruct" / "converge-ci-stack.sh"
_FAILING_RELEASE = "livespec-overseer-k3s"

_KUBECTL = r"""#!/usr/bin/env bash
case "$*" in
  "get nodes -l ci-runner.io/always-on=true -o name") echo node/poweredge-xubuntu ;;
esac
exit 0
"""

_HELM = r"""#!/usr/bin/env bash
printf 'helm %s\n' "$*" >> "$STUB_DIR/calls"
verb="$1"
if [ "$verb" = history ]; then
  release="$2"
  [ -n "${HISTORY_FAILS:-}" ] && [ "$release" = "$HISTORY_FAILS" ] && exit 1
  [ -f "$STUB_DIR/live-$release" ] || exit 1
  printf '[{"revision":1,"status":"deployed","description":"%s"}]\n' "$(cat "$STUB_DIR/live-$release")"
  exit 0
fi
release="$3"
args=("$@")
for ((i = 0; i < ${#args[@]}; i++)); do
  if [ "${args[$i]}" = --description ]; then
    printf '%s' "${args[$((i + 1))]}" > "$STUB_DIR/live-$release"
  fi
done
exit 0
"""


def _tree(tmp_path: Path) -> tuple[Path, Path]:
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
    stub = tmp_path / "stub"
    (stub / "bin").mkdir(parents=True)
    for name, body in (("kubectl", _KUBECTL), ("helm", _HELM)):
        path = stub / "bin" / name
        path.write_text(body, encoding="utf-8")
        path.chmod(0o755)
    return tree, stub


def _converge(tree: Path, stub: Path, *, history_fails: str = "") -> list[str]:
    """Run one converge and return the releases it upgraded."""
    calls = stub / "calls"
    calls.unlink(missing_ok=True)
    env = {
        "PATH": f"{stub / 'bin'}:/usr/bin:/bin",
        "STUB_DIR": str(stub),
        "KUBECONFIG": "/nonexistent",
        "CONVERGE_ARTIFACT_DIR": str(tree),
        "HISTORY_FAILS": history_fails,
    }
    done = subprocess.run(
        ["/bin/bash", str(_STACK), "--scale-sets-only"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=120,
    )
    assert done.returncode == 0, done.stdout + done.stderr
    lines = calls.read_text(encoding="utf-8").splitlines() if calls.exists() else []
    return [line.split()[3] for line in lines if line.startswith("helm upgrade --install ")]


def test_an_empty_cluster_installs_every_scale_set(tmp_path: Path) -> None:
    tree, stub = _tree(tmp_path)
    assert len(_converge(tree, stub)) >= 15


def test_a_second_converge_with_no_change_upgrades_nothing(tmp_path: Path) -> None:
    tree, stub = _tree(tmp_path)
    _ = _converge(tree, stub)
    assert _converge(tree, stub) == []


def test_changing_one_scale_sets_values_upgrades_only_that_one(tmp_path: Path) -> None:
    tree, stub = _tree(tmp_path)
    _ = _converge(tree, stub)
    values = tree / "arc" / "values-livespec-overseer.yaml"
    values.write_text(values.read_text(encoding="utf-8") + "\n# changed\n", encoding="utf-8")
    assert _converge(tree, stub) == [_FAILING_RELEASE]


def test_a_failed_digest_read_upgrades_that_release_instead_of_skipping(tmp_path: Path) -> None:
    tree, stub = _tree(tmp_path)
    _ = _converge(tree, stub)
    assert _converge(tree, stub, history_fails=_FAILING_RELEASE) == [_FAILING_RELEASE]
