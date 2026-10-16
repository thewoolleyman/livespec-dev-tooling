"""The Kubernetes sandbox-driver plugin is DELIVERED to every Fabro-server host.

The plugin (`thewoolleyman/sandbox-driver-kubernetes`) runs beside the Fabro
worker on a sandbox host and creates each sandbox as a pod in the `factory`
namespace, with the credential the `factory_kubeconfig` role delivers. This
file asserts the delivery: the `sandbox_driver_kubernetes` role, the digests
it pins, the configuration it renders, and the play that runs it.

WHY THE ROLE IS READ RATHER THAN APPLIED: applying it needs a sandbox host and
a published release, and would prove it of one host. Reading the committed
play, tasks, defaults and templates asserts it of every host the group holds,
as the sibling `test_factory_kubeconfig_delivery.py` does.

Work-item: `bd-ib-nmuyjc.3` (livespec-orchestrator-beads-fabro plan
`kubernetes-sandbox-backend`).
"""

from __future__ import annotations

import re
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ANSIBLE = _REPO_ROOT / "ansible"
_FABRO_PLAY = _ANSIBLE / "fabro-hosts.yml"
_ROLE = _ANSIBLE / "roles" / "sandbox_driver_kubernetes"
_TASKS = _ROLE / "tasks" / "main.yml"
_DEFAULTS = _ROLE / "defaults" / "main.yml"
_PLUGIN_TEMPLATE = _ROLE / "templates" / "plugin-config.toml.j2"
_CLI_TEMPLATE = _ROLE / "templates" / "cli-config.toml.j2"

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _read(*, path: Path) -> str:
    assert path.is_file(), (
        f"{path.relative_to(_REPO_ROOT)} must exist: a sandbox host without the "
        f"plugin cannot launch a sandbox pod"
    )
    return path.read_text(encoding="utf-8")


def _default(*, name: str) -> str:
    match = re.search(rf"^{name}: (.+)$", _read(path=_DEFAULTS), re.MULTILINE)
    assert match, f"defaults/main.yml must set {name}"
    return match.group(1).strip()


def test_the_play_installs_the_plugin_after_the_factory_credential() -> None:
    play = _read(path=_FABRO_PLAY)
    credential = play.find("- role: factory_kubeconfig")
    plugin = play.find("- role: sandbox_driver_kubernetes")
    assert credential != -1, "fabro-hosts.yml must run factory_kubeconfig"
    assert plugin > credential, (
        "fabro-hosts.yml must run sandbox_driver_kubernetes after factory_kubeconfig, "
        "whose credential the plugin is configured to read"
    )


def test_both_binaries_are_pinned_by_a_committed_digest() -> None:
    for name in ("sandbox_driver_kubernetes_sha256", "sandbox_driver_kubernetes_cli_sha256"):
        assert _SHA256.match(_default(name=name)), (
            f"{name} must be a committed 64-hex SHA-256: a digest fetched beside the "
            f"download proves only that the download is internally consistent"
        )
    tasks = _read(path=_TASKS)
    assert 'checksum: "sha256:{{ item.sha256 }}"' in tasks
    assert "sha256:http" not in tasks, (
        "the role must not take its checksum from a URL: that is a published "
        "checksum file, not a committed digest"
    )


def test_the_cli_profile_pins_the_plugin_digest() -> None:
    profile = _read(path=_CLI_TEMPLATE)
    assert 'sha256 = "{{ sandbox_driver_kubernetes_sha256 }}"' in profile
    assert 'path = "{{ sandbox_driver_kubernetes_bin_dir }}/sandbox-driver-kubernetes"' in profile


def test_the_plugin_reads_the_factory_credential_and_refreshes_it_on_a_rejection() -> None:
    template = _read(path=_PLUGIN_TEMPLATE)
    for key in ("kubeconfig", "namespace", "service_account", "workspace_root", "refresh_command"):
        assert re.search(rf"^{key} = ", template, re.MULTILINE), f"the plugin config must set {key}"
    assert "[[tolerations]]" in template
    assert "[node_selector]" in template
    defaults = _read(path=_DEFAULTS)
    assert "refresh-factory-kubeconfig" in defaults
    assert _default(name="sandbox_driver_kubernetes_namespace") == "factory"
    assert _default(name="sandbox_driver_kubernetes_service_account") == "sandbox-launcher"
    assert _default(name="sandbox_driver_kubernetes_workspace_root") == "/srv/factory-workspaces"


def test_no_machine_is_named() -> None:
    for path in (_TASKS, _DEFAULTS, _PLUGIN_TEMPLATE, _CLI_TEMPLATE):
        text = _read(path=path)
        for host in ("hp-xubuntu", "gmktec-xubuntu", "poweredge-xubuntu", "cwoolley"):
            assert host not in text, f"{path.name} must not name {host}; bind it through host_vars"
