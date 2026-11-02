"""Consumer-tier: a retained read-only instance's settings.toml is neither judged nor written.

WHY IT EXISTS (2026-11-02). The `retained_read_only` axis of the `fabro_server` role
clears every write bit under a parked instance's state root (livespec-dev-tooling-yw7via).
The settings drift report is a check-mode `template` task that also compares the file's
MODE. After the converge, `settings.toml` reads 0400 where the role would render 0600, so
every later drift read of hp-xubuntu reported one change. That change is precisely the
retained state the converge had just established. The install task would also rewrite the
frozen file for a host that manages settings. A retained instance is frozen as the
rollback path, so both tasks skip it.

Text-sliced, for the reason the sibling axis modules give: neither Jinja nor a YAML
library is importable in this suite.
"""

from __future__ import annotations

import re
from itertools import pairwise
from pathlib import Path

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_TASKS = (
    Path(__file__).resolve().parents[2]
    / "ansible"
    / "roles"
    / "fabro_server"
    / "tasks"
    / "main.yml"
)
_GUARD = "not (fabro_server_retained_read_only | bool)"
_SETTINGS_TASKS = (
    "Report drift between the instance's settings.toml and version control",
    "Install the instance's settings.toml",
)


def _task_bodies() -> dict[str, str]:
    text = _TASKS.read_text(encoding="utf-8")
    openings = [match.start() for match in re.finditer(r"^- name: ", text, re.MULTILINE)]
    bodies: dict[str, str] = {}
    for start, end in pairwise([*openings, len(text)]):
        body = text[start:end]
        bodies[body.splitlines()[0].removeprefix("- name: ").strip()] = body
    return bodies


@pytest.mark.parametrize("name", _SETTINGS_TASKS)
def test_a_settings_task_skips_a_retained_read_only_instance(*, name: str) -> None:
    bodies = _task_bodies()
    assert name in bodies, f"the fabro_server role must carry the task {name!r}"
    when = bodies[name].split("\n  when:", 1)
    assert len(when) == 2, f"{name!r} must carry a `when`"
    assert _GUARD in when[1], (
        f"{name!r} must skip a retained read-only instance with `{_GUARD}` in its `when`, "
        "or every drift read reports the cleared write bit as a mode change"
    )
