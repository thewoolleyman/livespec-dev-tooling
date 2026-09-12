"""Every apply-bearing converge under `ci-runner/k3s/phase2/` is on the boot path.

The k3s datastore is tmpfs (`phase2/datastore-tmpfs/`), so every cluster object
exists only until the next reboot unless `reconstruct/converge-ci-stack.sh`
re-applies it at boot from the tree the `ci_converge_unit` Ansible role copies
onto the host. A converge script that applies manifests but is reached by
neither is a Deployment that works until the first reboot and then vanishes
silently. That is what happened to the ghcr pull-through registry mirror on
2026-09-09: applied by hand at 02:21Z, gone at the 05:08Z reboot, while every
node's `registries.yaml` kept routing ghcr.io at it (livespec-dev-tooling-y1t5).

Two checks, both derived from the tree rather than from a list kept beside it:
every `converge-*.sh` that runs `kubectl apply` must be named by the boot
converge, and the `ci_converge_unit` role must install it onto the host.
Exclusions are explicit and each carries its reason.

RELOCATED (epic livespec-qurhq2, C5b): the installer half of this invariant was
`reconstruct/install-converge-unit.sh --stage-to`. That shell installer was
retired when the `ci_converge_unit` Ansible role replaced it, so the second
check now walks the role's committed file set — the `ci_converge_unit_files`
`src` entries plus the three run-time globs — as the root instead of the
installer's stage mode. The invariant is unchanged; only the layer that
satisfies it moved.

The relocation immediately bit: on 2026-09-12 the role installed a SUBSET of
what the retired installer staged, omitting `gates/converge-gates-mirror.sh` and
`warm-cache/registry-mirror/converge-registry-mirror.sh` (both called by the
boot converge) — which, once the installer was gone, would have lost the gates
mirror and the ghcr pull-through mirror at the next reboot. This check caught it
and the role was completed. That is why the check had to be relocated, not
deleted.
"""

from __future__ import annotations

import re
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PHASE2 = _REPO_ROOT / "ci-runner" / "k3s" / "phase2"
_ARC_DIR = _PHASE2 / "arc"
_KUEUE_DIR = _PHASE2 / "kueue"
_BOOT_CONVERGE = _PHASE2 / "reconstruct" / "converge-ci-stack.sh"
# The role that installs the boot tree (replaced reconstruct/install-converge-unit.sh).
_ROLE_DEFAULTS = _REPO_ROOT / "ansible" / "roles" / "ci_converge_unit" / "defaults" / "main.yml"

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


def _role_installed_sources() -> set[str]:
    """Every phase2-relative source path the `ci_converge_unit` role installs.

    The `ci_converge_unit_files` `src:` entries, plus the three sets the role
    resolves at run time with a fileglob — `arc/values-*.yaml` minus the EXAMPLE
    template, `kueue/core/*.yaml`, `kueue/cluster-queue-*.yaml` — the same globs
    its tasks/main.yml resolves. Expressed as phase2-relative posix paths, the
    form the `src:` entries already use, so an apply-bearing converge's
    phase2-relative path is a direct membership test.
    """
    text = _ROLE_DEFAULTS.read_text(encoding="utf-8")
    sources = set(re.findall(r"^\s*- src:\s*(\S+)\s*$", text, re.MULTILINE))
    for path in sorted(_ARC_DIR.glob("values-*.yaml")):
        if path.name != "values-EXAMPLE-repo.yaml":
            sources.add(path.relative_to(_PHASE2).as_posix())
    for path in sorted(_KUEUE_DIR.glob("core/*.yaml")):
        sources.add(path.relative_to(_PHASE2).as_posix())
    for path in sorted(_KUEUE_DIR.glob("cluster-queue-*.yaml")):
        sources.add(path.relative_to(_PHASE2).as_posix())
    return sources


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


def test_ci_converge_unit_role_installs_every_apply_bearing_converge() -> None:
    installed = _role_installed_sources()
    missing = [
        path.relative_to(_PHASE2).as_posix()
        for path in _candidates()
        if path.relative_to(_PHASE2).as_posix() not in installed
    ]
    assert not missing, (
        "apply-bearing converge script(s) the boot converge calls but the ci_converge_unit "
        "Ansible role does not install onto the host, so after the retired shell installer "
        "is gone the boot converge would fail to find them and whatever they apply would be "
        f"lost at the next reboot: {missing}"
    )


def test_exclusions_are_real_files_with_reasons() -> None:
    names = {path.name for path in _apply_bearing_converges()}
    for name, reason in _NOT_ON_BOOT_PATH.items():
        assert name in names, f"exclusion {name!r} names no apply-bearing converge script"
        assert reason.strip(), f"exclusion {name!r} carries no reason"
