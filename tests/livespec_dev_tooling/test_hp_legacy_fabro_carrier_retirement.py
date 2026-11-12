"""hp-xubuntu's legacy Fabro carrier leftovers are retired by a committed converge.

bd-ib-iud52v (maintainer deadline 2026-11-14T00:00Z): the legacy Fabro carrier must be
fully retired. A read-only check of hp-xubuntu on 2026-11-12 ~00:05Z found two residues
left by the docker-era factory role, which hp left on 2026-11-02:

1. the docker-store sandbox image warm (livespec-sandbox-image-warm.timer and .service)
   still installed and firing, while the two containerd warms that ci-pool.yml applies
   must stay;
2. tailscaled still serving :32276, :32277 and :32278 with no Fabro server behind them,
   hand-made mappings that the additive tailscale_serve role never turns off.

The fleet host guard refuses removing either by hand, so each is retired here.
"""

from __future__ import annotations

from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ANSIBLE = _REPO_ROOT / "ansible"
_SERVE_ROLE = _ANSIBLE / "roles" / "tailscale_serve"
_SERVE_MAIN = _SERVE_ROLE / "tasks" / "main.yml"
_SERVE_RETIRE = _SERVE_ROLE / "tasks" / "retire.yml"
_SERVE_DEFAULTS = _SERVE_ROLE / "defaults" / "main.yml"
_SERVE_HOST_VARS_DOC = _SERVE_ROLE / "HOST_VARS.md"
_FORMER_PLAY = _ANSIBLE / "former-sandbox-hosts.yml"
_HP = _ANSIBLE / "inventory" / "host_vars" / "hp-xubuntu.yml"
_HP_RETIRED_PORTS = [32276, 32277, 32278]


def _former_play_roles() -> list[dict[str, object]]:
    plays = yaml.safe_load(_FORMER_PLAY.read_text(encoding="utf-8"))
    return [role for play in plays for role in play.get("roles", [])]


def test_a_host_retires_no_serve_port_unless_it_names_one() -> None:
    defaults = yaml.safe_load(_SERVE_DEFAULTS.read_text(encoding="utf-8"))
    assert (
        defaults["tailscale_serve_retired_ports"] == []
    ), "a host that names no retired port must keep every mapping it serves"


def test_the_retire_path_turns_off_only_a_named_port_the_node_serves() -> None:
    tasks = yaml.safe_load(_SERVE_RETIRE.read_text(encoding="utf-8"))
    off_tasks = [
        task
        for task in tasks
        if isinstance(task.get("ansible.builtin.command"), dict)
        and "off" in task["ansible.builtin.command"].get("argv", [])
    ]
    assert len(off_tasks) == 1, "exactly one task turns a serve port off"
    off = off_tasks[0]
    assert off["ansible.builtin.command"]["argv"] == [
        "tailscale",
        "serve",
        "--https={{ item }}",
        "off",
    ], "the off task must name the retired port and nothing else"
    assert (
        off["loop"] == "{{ tailscale_serve_retired_ports }}"
    ), "only the host's declared retired ports are turned off"
    assert (
        "tailscale_serve_retire_status.stdout" in off["when"]
    ), "a port the node no longer serves is left alone, so a re-run changes nothing"


def test_a_port_both_published_and_retired_is_refused_before_any_change() -> None:
    tasks = yaml.safe_load(_SERVE_RETIRE.read_text(encoding="utf-8"))
    first = tasks[0]
    assert (
        "ansible.builtin.assert" in first
    ), "the overlap refusal must run before any read or change"
    that = " ".join(first["ansible.builtin.assert"]["that"])
    assert "tailscale_serve_retired_ports" in that
    assert "tailscale_serve_mappings" in that


def test_the_publish_path_includes_the_retire_path_only_for_a_host_that_names_ports() -> None:
    main = yaml.safe_load(_SERVE_MAIN.read_text(encoding="utf-8"))
    includes = [task for task in main if task.get("ansible.builtin.include_tasks") == "retire.yml"]
    assert len(includes) == 1, "tasks/main.yml must include tasks/retire.yml once"
    assert includes[0]["when"] == "tailscale_serve_retired_ports | length > 0"


def test_hp_names_its_three_legacy_fabro_ports_and_publishes_none() -> None:
    hp = yaml.safe_load(_HP.read_text(encoding="utf-8"))
    assert hp["tailscale_serve_retired_ports"] == _HP_RETIRED_PORTS
    assert "tailscale_serve_mappings" not in hp, "hp runs no Fabro server, so it publishes nothing"


def test_the_former_sandbox_play_converges_hps_serve_ports() -> None:
    names = [role.get("role") for role in _former_play_roles()]
    assert (
        "tailscale_serve" in names
    ), "hp leaves fabro-hosts.yml, so the former-sandbox play owns its serve ports"


def test_the_former_sandbox_play_retires_only_the_docker_store_warm() -> None:
    warms = [role for role in _former_play_roles() if role.get("role") == "sandbox_image_warm"]
    assert len(warms) == 1, "exactly one sandbox_image_warm entry retires the docker warm"
    warm = warms[0]
    assert warm["sandbox_image_warm_store"] == "docker"
    assert warm["sandbox_image_warm_state"] == "absent"
    hp = yaml.safe_load(_HP.read_text(encoding="utf-8"))
    assert "sandbox_image_warm_state" not in hp, (
        "the retirement is a role parameter: a host_vars value would also retire the two"
        " containerd warms that ci-pool.yml applies to hp"
    )


def test_the_role_documents_the_retired_ports_variable() -> None:
    doc = _SERVE_HOST_VARS_DOC.read_text(encoding="utf-8")
    assert "`tailscale_serve_retired_ports`" in doc
