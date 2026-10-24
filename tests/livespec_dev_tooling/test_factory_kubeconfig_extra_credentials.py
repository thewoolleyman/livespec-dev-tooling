"""A second factory-namespace credential is delivered, and its consumer names exactly it.

The mi-homelab organisation's Fabro instance runs its Kubernetes sandboxes in its
own namespace, `factory-mi-homelab`, under a launcher that reaches only that
namespace (work-item bd-ib-yetegc; plan kubernetes-sandbox-backend, bd-ib-nmuyjc).
So gmktec consumes TWO factory credentials. The `factory_kubeconfig` role
delivers each entry of `factory_kubeconfig_extra_credentials` the same way it
delivers the fleet's, and the instance's `kubernetes` provider points the plugin
at that entry through its `env` mapping.

A mismatch between the two is silent until it bites: a provider naming a path
the role never installs fails at the first sandbox, and a refresh env-file that
names the fleet's remote path would re-fetch the FLEET credential into homelab's
file on the first 401. These tests read the committed role and host_vars.
"""

from __future__ import annotations

import re
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ROLE = _REPO_ROOT / "ansible" / "roles" / "factory_kubeconfig"
_TASKS = _ROLE / "tasks" / "main.yml"
_EXTRA_TASKS = _ROLE / "tasks" / "extra_credential.yml"
_DEFAULTS = _ROLE / "defaults" / "main.yml"
_GMKTEC = _REPO_ROOT / "ansible" / "inventory" / "host_vars" / "gmktec-xubuntu.yml"
_HOMELAB_KUBECONFIG = "/etc/ci-runner/factory-mi-homelab.kubeconfig"
_HOMELAB_REFRESH_ENV = "/etc/ci-runner/factory-mi-homelab-refresh.env"


def _extra_entry(*, host_vars: str) -> str:
    match = re.search(
        r"^factory_kubeconfig_extra_credentials:\n((?:  .*\n)+)", host_vars, re.MULTILINE
    )
    assert match, "gmktec must declare factory_kubeconfig_extra_credentials"
    return match.group(1)


def _homelab_provider_env(*, host_vars: str) -> str:
    instance = host_vars.split("- unit_name: fabro-server-mi-homelab", 1)[1]
    match = re.search(r"^        env:\n((?:          .*\n)+)", instance, re.MULTILINE)
    assert match, "the mi-homelab instance's kubernetes provider must carry an env mapping"
    return match.group(1)


def test_the_role_delivers_every_extra_credential_like_the_fleet_one() -> None:
    assert "factory_kubeconfig_extra_credentials: []" in _DEFAULTS.read_text(encoding="utf-8"), (
        "the axis must default to empty, so a host running only the fleet instance gets only "
        "the fleet credential"
    )
    tasks = _TASKS.read_text(encoding="utf-8")
    assert "include_tasks: extra_credential.yml" in tasks
    assert 'loop: "{{ factory_kubeconfig_extra_credentials }}"' in tasks
    extra = _EXTRA_TASKS.read_text(encoding="utf-8")
    for fragment in (
        "ansible.builtin.slurp:",
        "'kind: Config' in",
        'group: "{{ factory_kubeconfig_group }}"',
        'mode: "0640"',
        "FACTORY_REMOTE_KUBECONFIG={{ factory_kubeconfig_extra.remote_path }}",
        "no_log: true",
    ):
        assert fragment in extra, (
            f"an extra credential must be fetched, refused if not a kubeconfig, installed 0640 to "
            f"the reader group with its value hidden, and refreshed from its OWN remote path; "
            f"missing {fragment!r}"
        )


def test_the_homelab_provider_names_exactly_the_credential_the_role_installs() -> None:
    host_vars = _GMKTEC.read_text(encoding="utf-8")
    entry = _extra_entry(host_vars=host_vars)
    env = _homelab_provider_env(host_vars=host_vars)
    assert f"dest: {_HOMELAB_KUBECONFIG}" in entry
    assert f"refresh_env: {_HOMELAB_REFRESH_ENV}" in entry
    for line in (
        "SANDBOX_DRIVER_KUBERNETES_NAMESPACE: factory-mi-homelab",
        f"SANDBOX_DRIVER_KUBERNETES_KUBECONFIG: {_HOMELAB_KUBECONFIG}",
        f"FACTORY_KUBECONFIG: {_HOMELAB_KUBECONFIG}",
        f"FACTORY_REFRESH_ENV: {_HOMELAB_REFRESH_ENV}",
    ):
        assert line in env, (
            f"the mi-homelab provider must carry {line!r}: the plugin and its 401 refresh must "
            "reach homelab's own namespace and credential, never the fleet's"
        )
    assert "SANDBOX_DRIVER_KUBERNETES_STATE_DIR:" in env, (
        "the instance shares HOME with the fleet instance, so it needs its own record store or "
        "each lists the other's sandboxes"
    )
