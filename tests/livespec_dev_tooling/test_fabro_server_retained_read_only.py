"""`fabro_server` — the `retained_read_only` disposition of a parked instance.

WHY IT EXISTS (2026-11-02). Plan gmktec-factory-placement (epic
livespec-dev-tooling-me5aqz, item livespec-dev-tooling-yw7via) retires hp-xubuntu's
legacy fleet instance. The unit is stopped and disabled, and its binary and state
directory stay on disk as the rollback path, but they must be READ-ONLY. The fleet host
guard forbids a hand `chmod`, so the read-only state needs to be something a committed
mapping can declare and the play can converge.

WHAT THESE TESTS HOLD IT TO, BY RUNNING IT. File modes are decided by what
`ansible.builtin.file` does with a symbolic mode on a recursive walk, and whether a
second converge is a no-op depends on the role's own directory task not adding the
owner's write bit back. Reading the YAML cannot settle either question, so the committed
tasks are RUN under the same `ansible-core` pin `just ansible-apply` uses. Each task is
lifted verbatim out of the role. The only change is `become: true` → `become: false`,
so the run stays inside a temporary directory owned by the test's own user. No host is
reached and no unit is touched.
"""

from __future__ import annotations

import getpass
import grp
import json
import os
import re
import stat
import subprocess
from collections.abc import Iterator
from itertools import pairwise
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[2]
_JUSTFILE = _REPO_ROOT / "justfile"
_TASKS = _REPO_ROOT / "ansible" / "roles" / "fabro_server" / "tasks" / "main.yml"
_ANSIBLE_CORE_PIN = re.compile(r"ansible-core==[0-9][0-9A-Za-z.]*")
_TIMEOUT_SECONDS = 600

_LIFTED = (
    "Resolve this instance's axes",
    "Refuse a retained instance that version control does not park",
    "Create this instance's state root, storage directory and binary directory",
    "Make a retained instance's binary and state directory read-only",
)
_WRITE_BITS = stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH


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


def _role_tasks() -> dict[str, str]:
    """Every column-zero task of the role's main.yml, keyed by its name."""
    text = _TASKS.read_text(encoding="utf-8")
    openings = [match.start() for match in re.finditer(r"^- name: ", text, re.MULTILINE)]
    tasks: dict[str, str] = {}
    for start, end in pairwise([*openings, len(text)]):
        body = text[start:end]
        tasks[body.splitlines()[0].removeprefix("- name: ").strip()] = body
    return tasks


def _lifted_tasks() -> str:
    tasks = _role_tasks()
    missing = [name for name in _LIFTED if name not in tasks]
    assert not missing, f"the fabro_server role must carry the task(s) {missing}"
    lifted = "".join(tasks[name] for name in _LIFTED)
    return lifted.replace("  become: true\n", "  become: false\n")


def _instance(*, unit: str, home: Path, **extra: object) -> dict[str, object]:
    return {
        "unit_name": unit,
        "home_dir": str(home),
        "port": 32276 if unit == "fabro-server" else 32277,
        "canonical_host": f"example.invalid:{32276 if unit == 'fabro-server' else 32277}",
        "cli_target_url": "http://127.0.0.1:32276",
        "max_concurrent_runs": 1,
        "github_app_id": "1",
        "otel_dropin": "unmanaged",
        **extra,
    }


def _run(*, tmp_path: Path, instances: list[dict[str, object]], visit: str) -> tuple[int, str]:
    """Run the lifted tasks for the instance named `visit`; return exit code and output."""
    play_vars = {
        "fabro_server_host_user": getpass.getuser(),
        "fabro_server_host_group": grp.getgrgid(os.getgid()).gr_name,
        "fabro_server_host_home": str(tmp_path),
        "fabro_server_otel_dropin_default": "unmanaged",
        "fabro_server_instances": instances,
        "fabro_server_instance": next(one for one in instances if one["unit_name"] == visit),
    }
    playbook = tmp_path / "retained.yml"
    header = "\n".join(
        (
            "- hosts: localhost",
            "  connection: local",
            "  gather_facts: false",
            f"  vars: {json.dumps(play_vars)}",
            "  tasks:",
        )
    )
    body = "".join(f"    {line}\n" if line else "\n" for line in _lifted_tasks().splitlines())
    _ = playbook.write_text(f"{header}\n{body}", encoding="utf-8")
    completed = subprocess.run(
        [
            "uvx",
            "--from",
            _ansible_core_pin(),
            "ansible-playbook",
            "-i",
            "localhost,",
            str(playbook),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=_TIMEOUT_SECONDS,
        check=False,
    )
    return completed.returncode, completed.stdout + completed.stderr


@pytest.fixture
def legacy_home(tmp_path: Path) -> Iterator[Path]:
    """A legacy instance's state root holding a binary and a stored file, writable."""
    home = tmp_path / ".fabro"
    (home / "bin").mkdir(parents=True)
    (home / "storage").mkdir()
    binary = home / "bin" / "fabro"
    _ = binary.write_text("#!/bin/sh\n", encoding="utf-8")
    binary.chmod(0o755)
    stored = home / "storage" / "run.json"
    _ = stored.write_text("{}\n", encoding="utf-8")
    stored.chmod(0o644)
    yield home
    # Hand write access back so pytest can remove the temporary tree. The fixture
    # creates no symlink, so every entry is a file or a directory to chmod.
    for path in [home, *home.rglob("*")]:
        path.chmod(path.stat().st_mode | stat.S_IWUSR)


def _write_bits(home: Path) -> dict[str, int]:
    return {
        str(path.relative_to(home.parent)): path.stat().st_mode & _WRITE_BITS
        for path in [home, *home.rglob("*")]
    }


def _changed_count(output: str) -> int:
    recap = re.search(r"localhost\s*:\s*ok=\d+\s+changed=(?P<changed>\d+)", output)
    assert recap is not None, output
    return int(recap["changed"])


def test_a_retained_parked_instance_has_every_write_bit_cleared(
    *, tmp_path: Path, legacy_home: Path
) -> None:
    instances = [
        _instance(
            unit="fabro-server", home=legacy_home, service_state="stopped", retained_read_only=True
        )
    ]
    code, output = _run(tmp_path=tmp_path, instances=instances, visit="fabro-server")
    assert code == 0, output
    assert set(_write_bits(legacy_home).values()) == {0}, _write_bits(legacy_home)
    assert os.access(
        legacy_home / "bin" / "fabro", os.X_OK
    ), "read-only keeps the binary executable, so a rollback only flips the disposition"


def test_a_second_converge_of_a_retained_instance_changes_nothing(
    *, tmp_path: Path, legacy_home: Path
) -> None:
    instances = [
        _instance(
            unit="fabro-server", home=legacy_home, service_state="stopped", retained_read_only=True
        )
    ]
    first, output = _run(tmp_path=tmp_path, instances=instances, visit="fabro-server")
    assert first == 0, output
    second, output = _run(tmp_path=tmp_path, instances=instances, visit="fabro-server")
    assert second == 0, output
    assert _changed_count(output) == 0, (
        "the directory task must not hand the owner's write bit back for the read-only "
        f"task to take away again on every converge:\n{output}"
    )


def test_a_parked_instance_that_is_not_retained_keeps_its_modes(
    *, tmp_path: Path, legacy_home: Path
) -> None:
    before = _write_bits(legacy_home)
    instances = [_instance(unit="fabro-server", home=legacy_home, service_state="stopped")]
    code, output = _run(tmp_path=tmp_path, instances=instances, visit="fabro-server")
    assert code == 0, output
    assert _write_bits(legacy_home) == before, "omitting the axis must change nothing"


def test_a_retained_instance_that_is_not_parked_is_refused_before_any_write(
    *, tmp_path: Path, legacy_home: Path
) -> None:
    before = _write_bits(legacy_home)
    instances = [
        _instance(
            unit="fabro-server", home=legacy_home, service_state="running", retained_read_only=True
        )
    ]
    code, output = _run(tmp_path=tmp_path, instances=instances, visit="fabro-server")
    assert code != 0, f"a running instance cannot also be read-only:\n{output}"
    assert "retained_read_only" in output, output
    assert _write_bits(legacy_home) == before


def test_a_sibling_sharing_the_retained_binary_directory_leaves_it_read_only(
    *, tmp_path: Path, legacy_home: Path
) -> None:
    sibling_home = tmp_path / ".fabro-sibling"
    instances = [
        _instance(
            unit="fabro-server", home=legacy_home, service_state="stopped", retained_read_only=True
        ),
        # No binary_path, so it shares fabro_server_host_home/.fabro/bin/fabro, which is
        # inside the retained instance's state root — hp's parked mi-homelab instance.
        _instance(unit="fabro-server-mi-homelab", home=sibling_home, service_state="stopped"),
    ]
    code, output = _run(tmp_path=tmp_path, instances=instances, visit="fabro-server")
    assert code == 0, output
    code, output = _run(tmp_path=tmp_path, instances=instances, visit="fabro-server-mi-homelab")
    assert code == 0, output
    assert (sibling_home / "storage").is_dir(), "the sibling's own state root is still created"
    assert set(_write_bits(legacy_home).values()) == {0}, _write_bits(legacy_home)
