"""The deferred Fabro binary path stages a build without unlinking the live server.

`fabro_server_restart_allowed` defaults to false because the role may converge a
busy factory.  A running Fabro server launches every new run worker from its
own executable path, so replacing that path before the server restarts leaves
the server running but unable to spawn workers.  The role must retain the
current binary at `binary_path`, stage the requested build beside it, and only
promote that staged build in a run that can safely restart (or start) the
instance.
"""

from __future__ import annotations

import re
from itertools import pairwise
from pathlib import Path

__all__: list[str] = []

_TASKS = (
    Path(__file__).resolve().parents[2]
    / "ansible"
    / "roles"
    / "fabro_server"
    / "tasks"
    / "main.yml"
)
_PROMOTE_NOW = "fabro_server_binary_install_now"
_NOTIFY = "Fabro instance files changed"
_STAGE = "Stage this instance's binary beside the one it replaces"
_KEEP = "Keep the outgoing binary beside the one that replaces it"
_PROMOTE = "Rename the staged copy onto this instance's binary path"


def _task_bodies() -> dict[str, str]:
    """Return every task keyed by its literal task name."""
    text = _TASKS.read_text(encoding="utf-8")
    openings = [match.start() for match in re.finditer(r"^- name: ", text, re.MULTILINE)]
    bodies: dict[str, str] = {}
    for start, end in pairwise([*openings, len(text)]):
        body = text[start:end]
        bodies[body.splitlines()[0].removeprefix("- name: ").strip()] = body
    return bodies


def test_a_deferred_binary_change_only_stages_the_candidate() -> None:
    """A live executable stays linked while its replacement waits for restart."""
    text = _TASKS.read_text(encoding="utf-8")
    tasks = _task_bodies()

    assert _PROMOTE_NOW in text, (
        "the role must explicitly decide when it may promote a staged binary; a binary "
        "difference alone is not permission to replace a running server's executable"
    )
    assert f"notify: {_NOTIFY}" in tasks[_STAGE], (
        "staging a deferred binary must record the restart debt even though binary_path "
        "was deliberately left unchanged"
    )
    assert (
        f"when: {_PROMOTE_NOW} | bool" in tasks[_KEEP]
    ), "the outgoing binary must be kept only when this run can promote the candidate"
    assert f"when: {_PROMOTE_NOW} | bool" in tasks[_PROMOTE], (
        "a deferred converge must not rename a staged candidate over a live server's " "binary_path"
    )


def test_promotion_remains_available_for_an_allowed_restart_or_safe_start() -> None:
    """The candidate reaches binary_path before a restart starts the declared build."""
    text = _TASKS.read_text(encoding="utf-8")

    assert "fabro_server_restart_allowed | bool" in text, (
        "an explicitly allowed restart must still promote the staged build before the "
        "restart handler starts the unit"
    )
    assert "not (fabro_server_binary.stat.exists)" in text, (
        "a first install has no live executable to preserve and must promote its staged "
        "binary before systemd starts the unit"
    )


def test_parking_an_instance_does_not_promote_before_the_stop() -> None:
    """The stop task runs after promotion, so a parked-but-live server keeps its path."""
    decision = _task_bodies()["Decide whether this run may promote this instance's staged binary"]
    expression = decision[decision.index("fabro_server_binary_install_now:") :]

    assert "service_state" not in expression, (
        "promotion must not key on service_state: stopped, because the stop task runs after "
        "the rename and a still-active server would lose its executable path before it stops"
    )
