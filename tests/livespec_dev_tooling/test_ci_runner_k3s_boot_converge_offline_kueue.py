"""The Kueue core overlay the boot converge applies needs no internet to render.

The k3s datastore is tmpfs, so `reconstruct/converge-ci-stack.sh` re-creates
Kueue from scratch on every boot of `poweredge-xubuntu` — the fleet's single k3s
server. Step 4 does that with ONE `kubectl apply --server-side -k` of the
`kueue/core/` overlay, and that overlay used to name the upstream release
manifest by its github.com download URL. A kustomize render therefore reached
out to the internet at the earliest, least-attended moment in the host's life,
and the whole fleet's CI capacity rode on that fetch answering.

It did not, once. Measured 2026-10-12: the 11:58Z unattended reboot's converge
failed at step 4 in 35 s because GitHub's edge answered HTTP 504 for the
release-download path from this host (ten of ten tries against one edge address,
while another edge and an unrelated VPS got the normal 302). Kustomize reported
it as the misleading `URL is a git repository`. The cluster came up with no
Kueue, no ARC and no scale sets, and the unit is `Type=oneshot` — so the fleet
had no CI until an operator re-ran the converge by hand.

The fix holds the artifact on the host instead: the version-pinned upstream
manifest is vendored beside the overlay (the same shape as
`container-hook/bundle/<version>/`, which vendors its upstream asset for the
same boot-durability reason), and the overlay names that local file. The
`ci_converge_unit` role's `kueue/core/*.yaml` glob already installs everything
in that directory, so the manifest travels to the host with no role edit.

These tests assert the three properties that keep it that way: the overlay
resolves only LOCAL paths, those paths exist, the vendored manifest IS the
pinned release (by its own image tag and by its recorded digest), and converge
step 4 still asserts version agreement against the overlay — the drift guard
the URL form used to provide, re-expressed over the local filename so a
`KUEUE_VERSION` bump cannot land without the manifest beside it.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PHASE2 = _REPO_ROOT / "ci-runner" / "k3s" / "phase2"
_KUEUE_CORE = _PHASE2 / "kueue" / "core"
_KUSTOMIZATION = _KUEUE_CORE / "kustomization.yaml"
_BOOT_CONVERGE = _PHASE2 / "reconstruct" / "converge-ci-stack.sh"

# The pinned Kueue release, co-maintained with `KUEUE_VERSION` in the boot
# converge — which the last test below asserts agrees with this.
_PINNED_KUEUE_VERSION = "v0.19.1"
_UPSTREAM_MANIFEST = f"upstream-manifests-{_PINNED_KUEUE_VERSION}.yaml"
# The one image the upstream release manifest carries, tagged with the release.
# Its presence is what makes "this file IS v0.19.1" an assertion about CONTENT
# rather than about a filename anyone could rename.
_PINNED_MANAGER_IMAGE = f"registry.k8s.io/kueue/kueue:{_PINNED_KUEUE_VERSION}"


def _resource_entries() -> tuple[str, ...]:
    """The `resources:` list entries of the Kueue core kustomization.

    Hand-parsed rather than loaded with a YAML library: this repository has no
    YAML runtime dependency, and the shape in question is a flat block sequence
    under one top-level key.

    It walks the WHOLE file and leaves the sequence by clearing its flag rather
    than `break`ing out of the loop. That is not a style preference: the
    per-file coverage gate reads test modules too, so a `break` this
    kustomization ALWAYS takes would leave the loop's normal-completion arm
    unexercised — an arm of the parser that nothing verifies.
    """
    entries: list[str] = []
    in_resources = False
    for line in _KUSTOMIZATION.read_text(encoding="utf-8").splitlines():
        if line.startswith("resources:"):
            in_resources = True
            continue
        if not in_resources:
            continue
        match = re.match(r"^\s+-\s+(\S+)\s*$", line)
        if match is None:
            in_resources = False
            continue
        entries.append(match.group(1))
    assert entries, f"{_KUSTOMIZATION} declares no `resources:` entries"
    return tuple(entries)


def test_kueue_core_overlay_resources_are_all_local_paths() -> None:
    remote = [entry for entry in _resource_entries() if "://" in entry]
    assert not remote, (
        "the Kueue core overlay the boot converge applies names remote "
        "resource(s), so rendering it at boot needs the internet and a "
        "transient upstream outage leaves the fleet with no Kueue, no ARC and "
        f"no CI until an operator re-runs the converge by hand: {remote}"
    )


def test_kueue_core_overlay_resource_files_sit_beside_it() -> None:
    missing = [entry for entry in _resource_entries() if not (_KUEUE_CORE / entry).is_file()]
    assert not missing, (
        "the Kueue core overlay names resource path(s) that do not exist beside "
        "it, so the boot converge's kustomize render fails closed at step 4: "
        f"{missing}"
    )


def test_vendored_upstream_manifest_is_the_pinned_kueue_release() -> None:
    assert _UPSTREAM_MANIFEST in _resource_entries(), (
        f"the Kueue core overlay does not name {_UPSTREAM_MANIFEST}, so whatever "
        "it renders is not the pinned upstream release"
    )
    manifest = _KUEUE_CORE / _UPSTREAM_MANIFEST
    assert manifest.is_file(), f"the pinned upstream Kueue manifest is absent: {manifest}"
    assert _PINNED_MANAGER_IMAGE in manifest.read_text(encoding="utf-8"), (
        f"{manifest} does not carry {_PINNED_MANAGER_IMAGE}, so the vendored "
        f"manifest is not the {_PINNED_KUEUE_VERSION} release it is named for"
    )


def test_vendored_upstream_manifest_matches_its_recorded_digest() -> None:
    manifest = _KUEUE_CORE / _UPSTREAM_MANIFEST
    digest_file = _KUEUE_CORE / f"{_UPSTREAM_MANIFEST}.sha256"
    assert manifest.is_file(), f"the pinned upstream Kueue manifest is absent: {manifest}"
    assert digest_file.is_file(), (
        f"{digest_file} is absent, so nothing records the provenance of the "
        "vendored upstream manifest and a local edit to it would be invisible"
    )
    recorded = digest_file.read_text(encoding="utf-8").split()[0]
    actual = hashlib.sha256(manifest.read_bytes()).hexdigest()
    assert actual == recorded, (
        f"{manifest} does not match the digest recorded in {digest_file.name} "
        f"({actual} != {recorded}): the vendored upstream release asset has "
        "been edited locally, which makes the pin a fiction"
    )


def test_boot_converge_step_four_still_asserts_overlay_version_agreement() -> None:
    converge = _BOOT_CONVERGE.read_text(encoding="utf-8")
    pinned = re.search(r'^KUEUE_VERSION="([^"]+)"', converge, re.MULTILINE)
    assert pinned is not None, f"{_BOOT_CONVERGE} declares no KUEUE_VERSION"
    assert pinned.group(1) == _PINNED_KUEUE_VERSION, (
        f"the boot converge pins Kueue {pinned.group(1)} while the overlay "
        f"carries {_PINNED_KUEUE_VERSION}; bump them together"
    )
    assert "upstream-manifests-${KUEUE_VERSION}.yaml" in converge, (
        "boot converge step 4 no longer asserts that the Kueue core overlay "
        "pins the same release as KUEUE_VERSION, so the two can drift apart "
        "silently — the drift guard the release URL used to carry must be "
        "re-expressed over the vendored manifest's name"
    )
