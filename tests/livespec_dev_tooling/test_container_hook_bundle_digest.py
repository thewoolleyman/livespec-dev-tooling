"""The container_hook role verifies the hook bundle with SHA-256, the algorithm its manifest is written in.

`ansible.builtin.copy`'s `checksum` parameter is SHA-1. Passing it the bundle's
SHA-256 manifest refused every real transfer, which first stranded hp-xubuntu's
runner pods in ContainerCreating on 2026-11-03 (livespec-dev-tooling-zreev4).
"""

from pathlib import Path

import yaml

_TASKS = (
    Path(__file__).resolve().parents[2]
    / "ansible"
    / "roles"
    / "container_hook"
    / "tasks"
    / "main.yml"
)


def _tasks() -> list[dict[str, object]]:
    loaded = yaml.safe_load(_TASKS.read_text(encoding="utf-8"))
    assert isinstance(loaded, list)
    return [task for task in loaded if isinstance(task, dict)]


def test_no_copy_task_passes_a_checksum() -> None:
    for task in _tasks():
        copy = task.get("ansible.builtin.copy")
        if isinstance(copy, dict):
            assert "checksum" not in copy, task.get("name")


def test_the_bundle_is_hashed_with_sha256_before_and_after_the_copy() -> None:
    names = [str(task.get("name")) for task in _tasks()]
    install = names.index("Install the fleet-patched container hook bundle")
    stats = [
        (index, task["ansible.builtin.stat"])
        for index, task in enumerate(_tasks())
        if isinstance(task.get("ansible.builtin.stat"), dict)
    ]
    sha256_stats = [index for index, stat in stats if stat.get("checksum_algorithm") == "sha256"]
    assert any(index < install for index in sha256_stats)
    assert any(index > install for index in sha256_stats)
