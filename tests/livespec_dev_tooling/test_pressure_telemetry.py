"""Pressure-stall telemetry is installed consistently across every execution target."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import jinja2
import yaml

__all__: list[str] = []

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_ANSIBLE = _REPOSITORY_ROOT / "ansible"
_ROLE = _ANSIBLE / "roles" / "pressure_telemetry"
_SCRIPT = _ROLE / "files" / "pressure-telemetry.sh"
_TASKS = _ROLE / "tasks" / "main.yml"
_SERVICE = _ROLE / "templates" / "pressure-telemetry.service.j2"
_TIMER = _ROLE / "templates" / "pressure-telemetry.timer.j2"
_CI_POOL_PLAY = _ANSIBLE / "ci-pool.yml"
_DEV_HOST_PLAY = _ANSIBLE / "dev-host.yml"


def test_pressure_emitter_sends_every_psi_line_directly_from_each_execution_target() -> None:
    """Every host gets all PSI resources, fields, fail-closed reads, and a one-minute timer."""
    assert _SCRIPT.is_file(), "the pressure emitter must be committed with its Ansible role"
    assert _TASKS.is_file(), "the pressure role must converge its script and systemd units"
    assert _SERVICE.is_file(), "the emitter needs the collector-managed ingest-key environment"
    assert _TIMER.is_file(), "the emitter needs a timer no slower than once per minute"

    script = _SCRIPT.read_text(encoding="utf-8")
    for resource in ("cpu", "memory", "io"):
        assert f"/proc/pressure/{resource}" in script
    for line in ("some", "full"):
        assert line in script
    for field in ("avg10", "avg60", "avg300"):
        assert field in script
    assert "host.name" in script
    assert "https://api.honeycomb.io/v1/metrics" in script
    assert "missing pressure file" in script
    assert "return 1" in script

    service = _SERVICE.read_text(encoding="utf-8")
    assert "EnvironmentFile=/etc/otel-collector/.env" in service
    assert "HONEYCOMB_INGEST_KEY_LIVESPEC" in service

    timer = _TIMER.read_text(encoding="utf-8")
    assert "OnUnitActiveSec=60s" in timer
    assert "AccuracySec=1s" in timer

    for play in (_CI_POOL_PLAY, _DEV_HOST_PLAY):
        assert "role: pressure_telemetry" in play.read_text(encoding="utf-8")

    tasks = _TASKS.read_text(encoding="utf-8")
    assert "ansible.builtin.copy:" in tasks
    assert "ansible.builtin.template:" in tasks


def test_pressure_emitter_posts_parseable_otlp_metrics_with_its_host_name(tmp_path: Path) -> None:
    """The direct OTLP payload is valid and carries all PSI gauges for its host."""
    capture = tmp_path / "otlp-payload.json"
    curl = tmp_path / "curl"
    curl.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "while (($#)); do\n"
        '  case "$1" in\n'
        '    -d) printf \'%s\' "$2" > "${PRESSURE_TELEMETRY_CAPTURE:?}"; shift 2 ;;\n'
        "    *) shift ;;\n"
        "  esac\n"
        "done\n",
        encoding="utf-8",
    )
    curl.chmod(0o755)

    completed = subprocess.run(
        ["bash", str(_SCRIPT)],
        capture_output=True,
        check=False,
        env=os.environ
        | {
            "HONEYCOMB_INGEST_KEY_LIVESPEC": "test-ingest-key",
            "PATH": f"{tmp_path}:{os.environ['PATH']}",
            "PRESSURE_TELEMETRY_CAPTURE": str(capture),
        },
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(capture.read_text(encoding="utf-8"))
    resource = payload["resourceMetrics"][0]["resource"]
    attributes = {attribute["key"]: attribute["value"] for attribute in resource["attributes"]}
    expected_host = subprocess.run(
        ["hostname", "-s"], capture_output=True, check=True, text=True
    ).stdout.strip()
    assert attributes["host.name"] == {"stringValue": expected_host}

    metrics = payload["resourceMetrics"][0]["scopeMetrics"][0]["metrics"]
    assert len(metrics) == 18
    assert {metric["name"] for metric in metrics} == {
        f"livespec.host.pressure.{resource}.{line}.{field}"
        for resource in ("cpu", "memory", "io")
        for line in ("some", "full")
        for field in ("avg10", "avg60", "avg300")
    }


_HOST_VARS = _ANSIBLE / "inventory" / "host_vars"
_DEFAULTS = _ROLE / "defaults" / "main.yml"
_CGROUP = "system.slice/k3s.service"


def _render_service(*, host: str) -> str:
    """The emitter's service unit as the role renders it for one inventory host."""
    role_variables = yaml.safe_load(_DEFAULTS.read_text(encoding="utf-8"))
    host_variables = yaml.safe_load((_HOST_VARS / f"{host}.yml").read_text(encoding="utf-8"))
    variables = {
        name: value
        for source in (role_variables, host_variables)
        for name, value in source.items()
        if name.startswith("pressure_telemetry_")
    }
    environment = jinja2.Environment(autoescape=False, undefined=jinja2.StrictUndefined)
    environment.globals["ansible_managed"] = "Ansible managed"
    # Role variables may refer to one another, so resolve them to a fixpoint.
    for _ in range(len(variables)):
        variables = {
            name: environment.from_string(value).render(**variables)
            if isinstance(value, str)
            else value
            for name, value in variables.items()
        }
    return environment.from_string(_SERVICE.read_text(encoding="utf-8")).render(**variables)


def test_poweredge_renders_the_k3s_cgroup_and_a_host_without_a_list_renders_none() -> None:
    """Only the host that sets `pressure_telemetry_cgroups` is told to read a cgroup."""
    assert "role: pressure_telemetry" in _CI_POOL_PLAY.read_text(encoding="utf-8")
    assert _CGROUP in _render_service(host="poweredge-xubuntu")
    for host in ("gmktec-xubuntu", "hp-xubuntu", "vps"):
        rendered = _render_service(host=host)
        assert "system.slice" not in rendered, host
        assert "k3s" not in rendered, host


_FAKE_CURL = (
    "#!/usr/bin/env bash\n"
    "set -euo pipefail\n"
    "while (($#)); do\n"
    '  case "$1" in\n'
    '    -d) printf \'%s\' "$2" > "${PRESSURE_TELEMETRY_CAPTURE:?}"; shift 2 ;;\n'
    "    *) shift ;;\n"
    "  esac\n"
    "done\n"
)


def _run_emitter(
    *, tmp_path: Path, cgroup_root: Path, cgroups: str
) -> subprocess.CompletedProcess[str]:
    """Run the emitter against a stand-in curl and a fake cgroup tree."""
    curl = tmp_path / "curl"
    curl.write_text(_FAKE_CURL, encoding="utf-8")
    curl.chmod(0o755)
    return subprocess.run(
        ["bash", str(_SCRIPT)],
        capture_output=True,
        check=False,
        env=os.environ
        | {
            "HONEYCOMB_INGEST_KEY_LIVESPEC": "test-ingest-key",
            "PATH": f"{tmp_path}:{os.environ['PATH']}",
            "PRESSURE_TELEMETRY_CAPTURE": str(tmp_path / "otlp-payload.json"),
            "PRESSURE_TELEMETRY_CGROUP_ROOT": str(cgroup_root),
            "PRESSURE_TELEMETRY_CGROUPS": cgroups,
        },
        text=True,
    )


def test_pressure_emitter_sends_a_configured_cgroups_cpu_pressure_with_the_host_datapoints(
    tmp_path: Path,
) -> None:
    """A readable cgroup cpu.pressure rides in the same request, attributed to its path."""
    cgroup_root = tmp_path / "cgroup"
    (cgroup_root / _CGROUP).mkdir(parents=True)
    (cgroup_root / _CGROUP / "cpu.pressure").write_text(
        "some avg10=1.10 avg60=2.20 avg300=3.30 total=123\n"
        "full avg10=0.40 avg60=0.50 avg300=0.60 total=45\n",
        encoding="utf-8",
    )

    completed = _run_emitter(tmp_path=tmp_path, cgroup_root=cgroup_root, cgroups=_CGROUP)

    assert completed.returncode == 0, completed.stderr
    payload = json.loads((tmp_path / "otlp-payload.json").read_text(encoding="utf-8"))
    resource = payload["resourceMetrics"][0]["resource"]
    host_name = next(
        attribute["value"]["stringValue"]
        for attribute in resource["attributes"]
        if attribute["key"] == "host.name"
    )
    expected_host = subprocess.run(
        ["hostname", "-s"], capture_output=True, check=True, text=True
    ).stdout.strip()
    assert host_name == expected_host
    metrics = payload["resourceMetrics"][0]["scopeMetrics"][0]["metrics"]
    assert len(metrics) == 18 + 6
    assert {metric["name"] for metric in metrics if ".host." in metric["name"]} == {
        f"livespec.host.pressure.{resource}.{line}.{field}"
        for resource in ("cpu", "memory", "io")
        for line in ("some", "full")
        for field in ("avg10", "avg60", "avg300")
    }
    cgroup_values: dict[str, float] = {}
    for metric in metrics:
        if not metric["name"].startswith("livespec.cgroup.pressure.cpu."):
            continue
        (datapoint,) = metric["gauge"]["dataPoints"]
        attributes = {item["key"]: item["value"] for item in datapoint["attributes"]}
        assert attributes["cgroup"] == {"stringValue": _CGROUP}
        assert attributes["host.name"] == {"stringValue": expected_host}
        cgroup_values[metric["name"].removeprefix("livespec.cgroup.pressure.cpu.")] = datapoint[
            "asDouble"
        ]
    assert cgroup_values == {
        "some.avg10": 1.10,
        "some.avg60": 2.20,
        "some.avg300": 3.30,
        "full.avg10": 0.40,
        "full.avg60": 0.50,
        "full.avg300": 0.60,
    }


def test_pressure_emitter_with_a_missing_cgroup_file_fails_and_sends_nothing(
    tmp_path: Path,
) -> None:
    """A configured cgroup without cpu.pressure is not turned into zeros or a partial request."""
    cgroup_root = tmp_path / "cgroup"
    (cgroup_root / _CGROUP).mkdir(parents=True)
    missing = cgroup_root / _CGROUP / "cpu.pressure"

    completed = _run_emitter(tmp_path=tmp_path, cgroup_root=cgroup_root, cgroups=_CGROUP)

    assert completed.returncode != 0
    assert str(missing) in completed.stderr
    assert not (tmp_path / "otlp-payload.json").exists()
