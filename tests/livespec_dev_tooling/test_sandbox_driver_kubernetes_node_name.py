"""Every gmktec Fabro instance pins the one sandbox-driver-kubernetes binary installed there.

Orchestrator plan `bd-ib-nmuyjc`. Fabro verifies the plugin's sha256 against
the instance's pin at EVERY plugin launch, not only at server start. So a pin
that differs from the binary the role installs fails every run's sandbox
acquire. Measured 2026-11-03 09:01-09:14Z: a v0.7.0 binary under v0.5.0 pins
killed six runs.

This file used to hold a v0.6.0 floor for `K8S_NODE_NAME` (bd-ib-motuct). That
floor was never true on the host: gmktec ran v0.5.0 throughout. A later release
reaches an instance only through the per-instance versioned install path
(`sandbox_driver_kubernetes_versioned_releases`), where each instance's binary
and pin move together at zero runs. Every pin on a versioned path must equal the
digest declared for that release (bd-ib-zl3qcz moved the fleet instance alone to
v0.8.0 this way).
"""

from __future__ import annotations

import re
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULTS = _REPO_ROOT / "ansible" / "roles" / "sandbox_driver_kubernetes" / "defaults" / "main.yml"
_GMKTEC = _REPO_ROOT / "ansible" / "inventory" / "host_vars" / "gmktec-xubuntu.yml"
_PLUGIN_PATH = "/usr/local/bin/sandbox-driver-kubernetes"


def _default(*, name: str) -> str:
    match = re.search(
        rf"^{re.escape(name)}: (\S+)$", _DEFAULTS.read_text(encoding="utf-8"), re.MULTILINE
    )
    assert match, f"{name} must be set in the role defaults"
    return match[1]


# The digest INSTALLED at /usr/local/bin on gmktec (v0.5.0, measured read-only
# 2026-11-02 and again 2026-11-03 after the restore). The plugin is one shared
# binary that every instance verifies at every plugin launch.
_GMKTEC_INSTALLED_DIGEST = "d93437f0bcb495e13a3373a4d2578cc0b2dba2c39c1ad5f3fdcf801ce0788b6e"


def test_every_gmktec_provider_kind_running_the_plugin_carries_the_pinned_digest() -> None:
    digest = _default(name="sandbox_driver_kubernetes_sha256")
    text = _GMKTEC.read_text(encoding="utf-8")
    pinned = re.findall(rf"path: {re.escape(_PLUGIN_PATH)}\n\s+sha256: ([0-9a-f]{{64}})", text)
    assert (
        len(pinned) >= 2
    ), f"expected the gmktec provider kinds that run the plugin, found {pinned!r}"
    assert digest == _GMKTEC_INSTALLED_DIGEST, (
        f"the role installs {digest} but gmktec holds {_GMKTEC_INSTALLED_DIGEST}; replacing the "
        f"shared binary under instances pinned to another digest fails every plugin launch"
    )
    assert set(pinned) == {digest}, (
        f"gmktec provider kinds pin {sorted(set(pinned))} but the role installs {digest}; Fabro "
        f"refuses, at every plugin launch, a plugin whose digest differs from its pin"
    )


_VERSIONED_PIN = re.compile(
    rf"path: ({re.escape(_PLUGIN_PATH)}-(v[0-9.]+))\n\s+sha256: ([0-9a-f]{{64}}|\S+)"
)
_VERSIONED_RELEASE = re.compile(r"- version: (v[0-9.]+)\n\s+sha256: (\S+)")


def _versioned_releases(*, text: str) -> dict[str, str]:
    block = text.split("sandbox_driver_kubernetes_versioned_releases:", 1)
    assert len(block) == 2, "gmktec must declare sandbox_driver_kubernetes_versioned_releases"
    releases = dict(_VERSIONED_RELEASE.findall(block[1].split("\n\n", 1)[0]))
    assert releases, "the versioned release list must name at least one release"
    return releases


def test_every_versioned_plugin_pin_carries_its_declared_release_digest() -> None:
    text = _GMKTEC.read_text(encoding="utf-8")
    releases = _versioned_releases(text=text)
    pins = _VERSIONED_PIN.findall(text)
    assert pins, "expected the fleet instance's provider kinds on a versioned plugin path"
    for path, version, digest in pins:
        assert re.fullmatch(r"[0-9a-f]{64}", digest), f"{path} must pin a 64-hex digest: {digest}"
        assert releases.get(version) == digest, (
            f"{path} is pinned at {digest}, but the role installs "
            f"{releases.get(version, 'no release')} there; change the binary and every pin on it "
            f"together"
        )
    for version, digest in releases.items():
        assert re.fullmatch(r"[0-9a-f]{64}", digest), f"{version} must declare a 64-hex digest"
