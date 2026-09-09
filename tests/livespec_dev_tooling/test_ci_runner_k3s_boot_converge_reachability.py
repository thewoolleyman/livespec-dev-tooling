"""Every apply-bearing converge under `ci-runner/k3s/phase2/` is on the boot path.

The k3s datastore is tmpfs (`phase2/datastore-tmpfs/`), so every cluster object
exists only until the next reboot unless `reconstruct/converge-ci-stack.sh`
re-applies it at boot from the tree `reconstruct/install-converge-unit.sh`
copies onto the host. A converge script that applies manifests but is reached
by neither is a Deployment that works until the first reboot and then vanishes
silently. That is what happened to the ghcr pull-through registry mirror on
2026-09-09: applied by hand at 02:21Z, gone at the 05:08Z reboot, while every
node's `registries.yaml` kept routing ghcr.io at it (livespec-dev-tooling-y1t5).

Two checks, both derived from the tree rather than from a list kept beside it:
every `converge-*.sh` that runs `kubectl apply` must be named by the boot
converge, and the installer's stage mode must copy it into the boot tree.
Exclusions are explicit and each carries its reason.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PHASE2 = _REPO_ROOT / "ci-runner" / "k3s" / "phase2"
_BOOT_CONVERGE = _PHASE2 / "reconstruct" / "converge-ci-stack.sh"
_INSTALLER = _PHASE2 / "reconstruct" / "install-converge-unit.sh"

# Converge scripts that apply manifests and are deliberately NOT on the boot
# path. Each entry names why; an entry with no reason is the defect this test
# exists to catch, so add one only with the reason beside it.
_NOT_ON_BOOT_PATH: dict[str, str] = {
    # The boot converge itself: it is the root of the reachability walk.
    "converge-ci-stack.sh": "the boot converge is the root, not a step",
}


def _apply_bearing_converges() -> tuple[Path, ...]:
    """Every `converge-*.sh` under phase2 whose body runs `kubectl apply`."""
    found = tuple(
        path
        for path in sorted(_PHASE2.rglob("converge-*.sh"))
        if "kubectl apply" in path.read_text(encoding="utf-8")
    )
    assert found, f"expected at least one apply-bearing converge under {_PHASE2}"
    return found


def _candidates() -> tuple[Path, ...]:
    return tuple(path for path in _apply_bearing_converges() if path.name not in _NOT_ON_BOOT_PATH)


def test_every_apply_bearing_converge_is_named_by_the_boot_converge() -> None:
    boot = _BOOT_CONVERGE.read_text(encoding="utf-8")
    missing = [
        path.relative_to(_PHASE2).as_posix() for path in _candidates() if path.name not in boot
    ]
    assert not missing, (
        "apply-bearing converge script(s) not reached by reconstruct/converge-ci-stack.sh, "
        "so whatever they apply is lost at the next reboot of the tmpfs-datastore host: "
        f"{missing}"
    )


def test_installer_stage_mode_copies_every_apply_bearing_converge(tmp_path: Path) -> None:
    staged = tmp_path / "staged"
    result = subprocess.run(
        ["bash", str(_INSTALLER), "--stage-to", str(staged)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"stage mode failed:\n{result.stdout}\n{result.stderr}"
    staged_names = {path.name for path in staged.rglob("converge-*.sh")}
    missing = [
        path.relative_to(_PHASE2).as_posix()
        for path in _candidates()
        if path.name not in staged_names
    ]
    assert not missing, (
        "apply-bearing converge script(s) the boot converge calls but "
        "reconstruct/install-converge-unit.sh does not copy onto the host, so the boot "
        f"converge would fail to find them: {missing}"
    )


def test_exclusions_are_real_files_with_reasons() -> None:
    names = {path.name for path in _apply_bearing_converges()}
    for name, reason in _NOT_ON_BOOT_PATH.items():
        assert name in names, f"exclusion {name!r} names no apply-bearing converge script"
        assert reason.strip(), f"exclusion {name!r} carries no reason"
