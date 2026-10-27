"""The factory sandbox images are pre-pulled into k3s's containerd on factory nodes.

Ledger item `bd-ib-kogktm` (tenant `livespec-orchestrator-beads-fabro`). The
scheduler's image locality pinned every factory pod to the one node holding the
current sandbox tag, so the role pulls the declared images into the other factory
nodes' k3s containerd.

Three claims, each asserted against the committed files: the image list is the
provider catalogue's own `process_spec.image` set and spells no image itself, so
a pin bump cannot desync them; the role is wired into `ci-pool.yml` under the
FACTORY_NODE gate; and the tasks use k3s's containerd (`k3s crictl` on the k3s
socket), never Docker.
"""

from __future__ import annotations

import re
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ROLE = _REPO_ROOT / "ansible" / "roles" / "factory_sandbox_image_prepull"
_PLAY = _REPO_ROOT / "ansible" / "ci-pool.yml"
_HOST_VARS = _REPO_ROOT / "ansible" / "inventory" / "host_vars"

_IMAGE = re.compile(r"^\s+image:\s*(?P<ref>ghcr\.io/\S+)\s*$", re.MULTILINE)
_PROCESS_SPEC_IMAGE = re.compile(r"^\s+process_spec:\n\s+image:\s*(?P<ref>\S+)\s*$", re.MULTILINE)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _provider_images() -> set[str]:
    """Every `process_spec.image` under a host_vars `sandbox_providers:` block."""
    found: set[str] = set()
    for host_vars in sorted(_HOST_VARS.glob("*.yml")):
        text = _read(host_vars)
        if "sandbox_providers:" in text:
            found.update(m.group("ref") for m in _PROCESS_SPEC_IMAGE.finditer(text))
    return found


def test_the_provider_catalogue_declares_images_for_the_role_to_derive() -> None:
    """The positive control: the extraction below can hit, so a zero is a finding."""
    images = _provider_images()
    assert images, "no sandbox_providers process_spec.image found in any host_vars"
    assert all("livespec-fabro-sandbox:" in ref for ref in images)


def test_the_image_list_is_derived_from_the_provider_catalogue_and_spells_no_image() -> None:
    """The list reads exactly the path the providers declare, and holds no literal ref."""
    defaults = _read(_ROLE / "defaults" / "main.yml")
    for token in (
        "groups['sandbox_hosts']",
        "'fabro_server_instances'",
        "attribute='sandbox_providers'",
        "attribute='value.process_spec.image'",
    ):
        assert token in defaults, f"the derivation must read {token}"
    assert not re.search(
        r"^\s*-?\s*ghcr\.io/", defaults, re.MULTILINE
    ), "defaults must not spell an image; the provider catalogue is the one source"
    assert not _IMAGE.search(defaults)
    assert not _IMAGE.search(_read(_ROLE / "tasks" / "main.yml"))


def test_every_pre_pulled_image_is_a_provider_image_and_the_tasks_loop_the_derived_list() -> None:
    """The tasks consume the derived list for both probe and pull, never another."""
    tasks = _read(_ROLE / "tasks" / "main.yml")
    assert tasks.count('loop: "{{ factory_sandbox_image_prepull_refs }}"') == 1
    assert "factory_sandbox_image_prepull_probe.results" in tasks
    assert "when: item.rc != 0" in tasks


def test_the_role_is_wired_into_the_ci_pool_play_under_the_factory_node_gate() -> None:
    """Reached by the play that addresses k3s nodes, gated on FACTORY_NODE only."""
    play = _read(_PLAY)
    entry = re.search(
        r"^    - role: factory_sandbox_image_prepull\n(?P<body>(?:      .*\n)+)",
        play,
        re.MULTILINE,
    )
    assert entry is not None, "ci-pool.yml must include the factory_sandbox_image_prepull role"
    assert "when: ci_pool_factory_node == 'true'" in entry.group("body")
    assert "tags: [factory_sandbox_image_prepull]" in entry.group("body")
    assert "hosts: ci_pool" in play


def test_the_tasks_use_k3s_containerd_and_never_docker() -> None:
    """kubelet reads k3s's containerd; a Docker pull would warm a store no pod reads."""
    defaults = _read(_ROLE / "defaults" / "main.yml")
    tasks = _read(_ROLE / "tasks" / "main.yml")
    assert "/usr/local/bin/k3s" in defaults
    assert "unix:///run/k3s/containerd/containerd.sock" in defaults
    assert tasks.count("      - crictl\n") == 3
    assert "inspecti" in tasks
    assert "      - pull\n" in tasks
    for text in (defaults, tasks):
        assert not re.search(r"\bdocker\s+(pull|image|inspect)\b", text)
        assert "docker.sock" not in text


def test_the_role_documents_its_source_of_truth_choice() -> None:
    """HOST_VARS.md justifies the single-source wiring, as the task requires."""
    doc = _read(_ROLE / "HOST_VARS.md")
    assert "bd-ib-kogktm" in doc
    assert "single source of truth" in doc
    assert "check-ansible-hostname-free" in doc
