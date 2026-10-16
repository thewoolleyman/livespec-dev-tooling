"""`ansible/fabro-hosts.yml` — `fabro_server_target_units`, the per-invocation instance selector.

WHY IT EXISTS (2026-10-16). With `fabro_server_restart_allowed=true` the
`fabro_server` role asks EVERY instance it visits whether it is carrying runs and
refuses the play if any is. That breadth is deliberate — when the probe runs the
role cannot know whether a later task will change that instance's unit, drop-in or
settings, and the restart handler trusts the flag — so the fix is not to narrow the
probe but to narrow the LOOP. Measured on hp-xubuntu: restarting the idle :32278
candidate onto a production-web-UI rebuild was refused because fabro-server (:32276)
carried 9 runs, so no sibling of a never-idle fleet instance could be restarted
through the committed play at all.

WHAT THESE TESTS HOLD IT TO, BY RUNNING IT. The selector is Jinja (`default`,
`selectattr`, `difference`, the `sequence` / `string` tests), and whether an unset
selector still means "every instance" or a typo silently matches nothing is decided
by those semantics, so the committed tasks are RUN under the same `ansible-core` pin
`just ansible-apply` uses rather than read. Each play's two tasks are lifted out of
the committed file verbatim; only `include_role: fabro_server` is swapped for a
`debug` that names the instance it would have installed, so the loop the operator
gets is the loop measured here. No host is reached.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[2]
_JUSTFILE = _REPO_ROOT / "justfile"
_PLAYBOOK = _REPO_ROOT / "ansible" / "fabro-hosts.yml"
_ANSIBLE_CORE_PIN = re.compile(r"ansible-core==[0-9][0-9A-Za-z.]*")

# From the selector's refusal through the end of the include task it narrows.
_SELECTOR_TASKS = re.compile(
    r"^    - name: Refuse a Fabro target unit this host does not declare\n"
    r"(?:(?!^    - name: |^- name: ).*\n)*"
    r"^    - name: Install every Fabro instance on this host\n"
    r"(?:(?!^    - name: |^- name: |^$).*\n)*",
    re.MULTILINE,
)
_INCLUDE = "      ansible.builtin.include_role:\n        name: fabro_server\n"
_VISIT = (
    '      ansible.builtin.debug:\n        msg: "visit {{ fabro_server_instance.unit_name }}"\n'
)
_VISITED = re.compile(r'"msg": "visit (?P<unit>[^"]+)"')

_UNITS = ("fabro-server", "fabro-server-mi-homelab", "fabro-server-candidate")
_TIMEOUT_SECONDS = 600


def _ansible_core_pin() -> str:
    """The `ansible-core==<version>` pin the `ansible-apply` recipe resolves."""
    recipe = re.search(
        r"^ansible-apply \*args:\n(?P<body>(?:    .*\n)+)",
        _JUSTFILE.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    assert recipe is not None, f"{_JUSTFILE} must carry the `ansible-apply *args:` recipe"
    pin = _ANSIBLE_CORE_PIN.search(recipe["body"])
    assert pin is not None, "the `ansible-apply` recipe must pin ansible-core exactly"
    return pin[0]


def _committed_selector_tasks() -> list[str]:
    return [match[0] for match in _SELECTOR_TASKS.finditer(_PLAYBOOK.read_text(encoding="utf-8"))]


def _run(*, tmp_path: Path, extra_vars: list[str]) -> tuple[int, list[str], str]:
    """Run the committed selector tasks on localhost; return exit code, visited units, output."""
    tasks = _committed_selector_tasks()[0]
    assert _INCLUDE in tasks, "the selector must narrow the loop that includes fabro_server"
    instances = "\n".join(f"      - unit_name: {unit}" for unit in _UNITS)
    playbook = tmp_path / "selector.yml"
    playbook.write_text(
        "- hosts: localhost\n"
        "  connection: local\n"
        "  gather_facts: false\n"
        "  vars:\n"
        "    fabro_server_instances:\n"
        f"{instances}\n"
        "  tasks:\n"
        f"{tasks.replace(_INCLUDE, _VISIT)}",
        encoding="utf-8",
    )
    argv = ["uvx", "--from", _ansible_core_pin(), "ansible-playbook", "-i", "localhost,"]
    for value in extra_vars:
        argv += ["-e", value]
    completed = subprocess.run(
        [*argv, str(playbook)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=_TIMEOUT_SECONDS,
        check=False,
    )
    output = completed.stdout + completed.stderr
    return completed.returncode, [m["unit"] for m in _VISITED.finditer(output)], output


def test_both_plays_carry_the_same_selector_in_front_of_the_fabro_server_loop() -> None:
    tasks = _committed_selector_tasks()
    assert len(tasks) == 2, (
        "the sandbox-host play and the dev-host play both loop fabro_server, so both "
        f"must carry the selector; found it {len(tasks)} time(s)"
    )
    assert tasks[0] == tasks[1], "the two plays' selectors must not drift apart"


@pytest.mark.parametrize(
    "extra_vars",
    [[], [json.dumps({"fabro_server_target_units": []})]],
    ids=["unset", "empty-list"],
)
def test_an_unset_or_empty_selector_visits_every_instance(
    *, tmp_path: Path, extra_vars: list[str]
) -> None:
    code, visited, output = _run(tmp_path=tmp_path, extra_vars=extra_vars)
    assert code == 0, output
    assert visited == list(
        _UNITS
    ), "no selector must mean every instance, the behaviour before the selector existed"


def test_the_named_instance_is_the_only_one_visited(*, tmp_path: Path) -> None:
    code, visited, output = _run(
        tmp_path=tmp_path,
        extra_vars=[json.dumps({"fabro_server_target_units": ["fabro-server-candidate"]})],
    )
    assert code == 0, output
    assert visited == ["fabro-server-candidate"], (
        "a restart-allowed run targeting one instance must not visit its siblings, or "
        "a busy sibling's carrying-runs refusal halts the play"
    )


@pytest.mark.parametrize(
    "extra_vars",
    [
        [json.dumps({"fabro_server_target_units": ["fabro-server-typo"]})],
        ["fabro_server_target_units=fabro-server-candidate"],
    ],
    ids=["undeclared-unit", "string-not-list"],
)
def test_a_selector_the_host_cannot_honour_is_refused_before_any_instance(
    *, tmp_path: Path, extra_vars: list[str]
) -> None:
    code, visited, output = _run(tmp_path=tmp_path, extra_vars=extra_vars)
    assert code != 0, f"an unusable selector must fail the play, not match nothing:\n{output}"
    assert visited == [], "the refusal must come before the loop visits any instance"
    assert "fabro_server_target_units must be a LIST" in output, output
