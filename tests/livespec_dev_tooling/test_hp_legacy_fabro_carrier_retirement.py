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

import jinja2
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
    main = yaml.safe_load(_SERVE_MAIN.read_text(encoding="utf-8"))
    first = main[0]
    assert "ansible.builtin.assert" in first, (
        "the overlap refusal must be the role's first task, ahead of the publish path,"
        " so no mapping is published or turned off on a host that names an overlap"
    )
    that = " ".join(first["ansible.builtin.assert"]["that"])
    assert "tailscale_serve_retired_ports" in that
    assert "tailscale_serve_mappings" in that
    retire = yaml.safe_load(_SERVE_RETIRE.read_text(encoding="utf-8"))
    assert not any(
        "ansible.builtin.assert" in task for task in retire
    ), "the refusal lives once, at the top of tasks/main.yml"


def _tailscale_calls(path: Path) -> list[dict[str, object]]:
    tasks = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [
        task
        for task in tasks
        if isinstance(task.get("ansible.builtin.command"), dict)
        and task["ansible.builtin.command"].get("argv", [None])[0] == "tailscale"
    ]


def test_every_tailscale_call_is_bounded() -> None:
    calls = _tailscale_calls(_SERVE_MAIN) + _tailscale_calls(_SERVE_RETIRE)
    assert (
        len(calls) >= 4
    ), "the publish status read, the publish, the retire status read and the off"
    for task in calls:
        assert (
            task.get("timeout") == 30
        ), f"{task.get('name')!r} must carry `timeout: 30`, so a hung tailscaled cannot stall a converge"


def test_the_publish_path_includes_the_retire_path_only_for_a_host_that_names_ports() -> None:
    main = yaml.safe_load(_SERVE_MAIN.read_text(encoding="utf-8"))
    includes = [task for task in main if task.get("ansible.builtin.include_tasks") == "retire.yml"]
    assert len(includes) == 1, "tasks/main.yml must include tasks/retire.yml once"
    assert includes[0]["when"] == "tailscale_serve_retired_ports | length > 0"


def test_hp_retires_only_ports_it_neither_publishes_nor_serves_a_fabro_instance_on() -> None:
    hp = yaml.safe_load(_HP.read_text(encoding="utf-8"))
    retired = hp["tailscale_serve_retired_ports"]
    assert retired, "hp names the legacy Fabro ports it retires"
    assert all(isinstance(port, int) for port in retired), "each retired port is an integer port"
    assert "tailscale_serve_mappings" not in hp, "hp runs no Fabro server, so it publishes nothing"
    instance_ports = {instance["port"] for instance in hp.get("fabro_server_instances", [])}
    assert not instance_ports & set(retired), "a port a live Fabro instance serves is never retired"


_STATUS_SAMPLE = """https://hp-xubuntu.perch-rudd.ts.net:32276 (tailnet only)
|-- / proxy http://127.0.0.1:32276

https://hp-xubuntu.perch-rudd.ts.net:32278 (tailnet only)
|-- / proxy http://127.0.0.1:32278
"""


def test_the_served_port_check_reads_a_captured_status_sample() -> None:
    tasks = yaml.safe_load(_SERVE_RETIRE.read_text(encoding="utf-8"))
    off = next(
        task for task in tasks if "off" in task.get("ansible.builtin.command", {}).get("argv", [])
    )
    condition = jinja2.Environment().compile_expression(off["when"])
    status = {"stdout": _STATUS_SAMPLE}
    assert condition(item=32276, tailscale_serve_retire_status=status) is True
    assert condition(item=32278, tailscale_serve_retire_status=status) is True
    assert (
        condition(item=32277, tailscale_serve_retire_status=status) is False
    ), "a port the status does not list is left alone"
    assert (
        condition(item=3227, tailscale_serve_retire_status=status) is False
    ), "a port that is only a prefix of a served port is not matched"


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
