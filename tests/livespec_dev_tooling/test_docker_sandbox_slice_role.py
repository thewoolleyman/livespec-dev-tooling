"""The docker_sandbox_slice role's reading of "this host has a container daemon".

A host the docker_engine guard rolled back keeps the Docker packages it
unpacked, `/usr/bin/dockerd` included, with every unit disabled and no daemon
running (gmktec-xubuntu, 2026-10-18). Until that guard commits, the daemon and
its configuration are the guard's: docker_engine writes `cgroup-parent` itself
and refuses a first start unless this slice is loaded. So the binary existing is
not the question; the guard having committed is. A host whose Docker predates
the guard has no state root at all, and there the binary is the whole answer.

These arms read the role's own fact expression and evaluate it against modelled
host states, because Ansible is not importable in this suite (see the justfile).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

__all__: list[str] = []

_ROLE = Path(__file__).resolve().parents[2] / "ansible" / "roles" / "docker_sandbox_slice"
_TASKS = _ROLE / "tasks" / "main.yml"
_DEFAULTS = _ROLE / "defaults" / "main.yml"
_ENGINE_DEFAULTS = (
    Path(__file__).resolve().parents[2]
    / "ansible"
    / "roles"
    / "docker_engine"
    / "defaults"
    / "main.yml"
)

_FACT = "docker_sandbox_slice_daemon_present"


def _tasks() -> list[str]:
    body = _TASKS.read_text(encoding="utf-8")
    return [f"- name: {chunk}" for chunk in body.split("\n- name: ")[1:]]


def _fact_expression() -> str:
    task = next(task for task in _tasks() if f"    {_FACT}:" in task)
    match = re.search(rf"^    {_FACT}: >-\n((?:      .+\n)+)", task + "\n", re.MULTILINE)
    assert match is not None, f"{_FACT} must be a folded expression:\n{task}"
    return " ".join(line.strip() for line in match[1].splitlines())


def _evaluate(*, dockerd: bool, state_root: bool, confirmed: bool) -> bool:
    expression = _fact_expression()
    inner = expression.removeprefix("{{").removesuffix("}}").strip()
    names = {
        "docker_sandbox_slice_dockerd.stat.exists": dockerd,
        "docker_sandbox_slice_guard.results[0].stat.exists": state_root,
        "docker_sandbox_slice_guard.results[1].stat.exists": confirmed,
    }
    python = inner
    for name, value in names.items():
        python = python.replace(name, str(value))
    assert (
        re.fullmatch(r"[\s()A-Za-z]*", python.replace("True", "").replace("False", "")) is not None
    )
    assert set(re.findall(r"[A-Za-z_][A-Za-z_.\[\]0-9]*", python)) <= {
        "True",
        "False",
        "and",
        "or",
        "not",
    }, python
    return bool(eval(python))  # noqa: S307 — a restricted boolean over literals, asserted above


# (dockerd exists, guard state root exists, guard committed) -> daemon present
_CASES = [
    ((False, False, False), False),
    ((True, False, False), True),
    ((True, True, False), False),
    ((True, True, True), True),
    ((False, True, True), False),
]


@pytest.mark.parametrize(("host", "expected"), _CASES)
def test_a_daemon_is_present_only_once_the_guard_has_committed_or_where_there_is_no_guard(
    host: tuple[bool, bool, bool], expected: object
) -> None:
    dockerd, state_root, confirmed = host
    assert _evaluate(dockerd=dockerd, state_root=state_root, confirmed=confirmed) is expected


def test_the_guard_paths_are_the_docker_engine_roles_own() -> None:
    engine = _ENGINE_DEFAULTS.read_text(encoding="utf-8")
    root = re.search(r"^docker_engine_state_root: (.+)$", engine, re.MULTILINE)
    assert root is not None
    defaults = _DEFAULTS.read_text(encoding="utf-8")
    assert f"docker_sandbox_slice_docker_engine_state_root: {root[1].strip()}" in defaults
    probe = next(task for task in _tasks() if "register: docker_sandbox_slice_guard" in task)
    assert '- "{{ docker_sandbox_slice_docker_engine_state_root }}"' in probe, probe
    assert '- "{{ docker_sandbox_slice_docker_engine_state_root }}/confirmed"' in probe, probe
    assert "check_mode: false" in probe, probe
