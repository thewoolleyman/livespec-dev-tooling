"""The merge unit's environment gets the credential wrapper past its stage-1 guard.

Work-item livespec-dev-tooling-o6u7jm. The first live probe of the installed unit failed in the
credential wrapper, before `bd` ran: stage 1 of /usr/local/bin/with-livespec-env.sh requires
SUDO_UID, SUDO_GID and SUDO_USER from an external sudo BEFORE it reaches the
OPENV_KEEP_PRIVILEGES branch, and a root systemd unit has no sudo parent. Three earlier tests had
passed on that unit by checking strings in the rendered file.

This test runs the REAL installed wrapper with exactly the environment the rendered unit sets.
It cannot be root, so a stand-in `id` that reports uid 0 sends the wrapper down its root branch,
which is the branch under test. A control run without the three variables must hit the guard,
which proves the stand-in drives stage 1 and the assertion is not vacuous. The wrapper then stops
at the encrypted credential, which only the real host holds; the step after that, `bd` under the
unit's sandbox, is the host probe recorded on the work item, not this test. The test skips, with
its reason, on a host that does not carry the wrapper.
"""

from __future__ import annotations

import shutil
import stat
import subprocess
from pathlib import Path

import jinja2
import pytest

__all__: list[str] = []
pytestmark = pytest.mark.integration

# This module concerns work item livespec-dev-tooling-o6u7jm, an ordinary pull request.

_ROOT = Path(__file__).resolve().parents[2]
_ROLE = _ROOT / "ansible" / "roles" / "incident_observer"
_GUARD = "stage 1 expected SUDO_UID"
_ROOT_ID = '#!/bin/sh\ncase "$1" in -u) echo 0;; *) exec /usr/bin/id "$@";; esac\n'


def _unit_environment() -> dict[str, str]:
    environment = jinja2.Environment(undefined=jinja2.StrictUndefined, keep_trailing_newline=True)
    template = environment.from_string(
        (_ROLE / "templates" / "livespec-incident-merge@.service.j2").read_text()
    )
    rendered = template.render(
        ansible_managed="Ansible managed",
        incident_observer_merge_app_path="/etc/livespec-incident/merge-app.json",
        incident_observer_reference_dir="/var/lib/livespec-incident/reference",
        incident_observer_state_dir="/var/lib/livespec-incident/receipts",
        incident_observer_venv="/opt/livespec-incident/venv",
        incident_observer_merge_authority_script="/declared/reader/incident_authority.py",
        incident_observer_merge_workdir="/declared/merge-workdir",
    )
    pairs = [
        line.removeprefix("Environment=").partition("=")
        for line in rendered.splitlines()
        if line.startswith("Environment=")
    ]
    return {name: value for name, _, value in pairs}


def _run_wrapper(*, wrapper: str, tmp_path: Path, unit_environment: dict[str, str]) -> str:
    stand_in = tmp_path / "id"
    _ = stand_in.write_text(_ROOT_ID)
    stand_in.chmod(stand_in.stat().st_mode | stat.S_IXUSR)
    # A fresh environment: nothing of this process, including any coverage startup variable,
    # reaches the child.
    environment = {"HOME": "/root", "PATH": f"{tmp_path}:/usr/bin:/bin", **unit_environment}
    done = subprocess.run(  # The installed wrapper, a fixed argv, no shell.
        [wrapper, "--", "/bin/true"],
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    return done.stderr


def test_the_units_environment_passes_the_wrappers_stage_one_guard_and_its_absence_does_not(
    tmp_path,
):
    wrapper = shutil.which("with-livespec-env.sh")
    if wrapper is None:
        pytest.skip("this host carries no with-livespec-env.sh, so the real wrapper cannot run")
    unit = _unit_environment()
    bare = {name: value for name, value in unit.items() if not name.startswith("SUDO_")}
    with_unit = _run_wrapper(wrapper=wrapper, tmp_path=tmp_path, unit_environment=unit)
    without = _run_wrapper(wrapper=wrapper, tmp_path=tmp_path, unit_environment=bare)
    facts = [
        unit.get("OPENV_KEEP_PRIVILEGES") == "1",
        {unit.get("SUDO_UID"), unit.get("SUDO_GID")} == {"0"},
        unit.get("SUDO_USER") == "root",
        _GUARD in without,
        _GUARD not in with_unit,
    ]
    assert all(facts)
