"""Guard the directories that dev_host_memory_bounds templates write into."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_ROLE = Path(__file__).resolve().parents[2] / "ansible" / "roles" / "dev_host_memory_bounds"


def _tasks() -> list[dict[str, Any]]:
    loaded = yaml.safe_load((_ROLE / "tasks" / "main.yml").read_text(encoding="utf-8"))
    assert isinstance(loaded, list)
    tasks = [task for task in loaded if isinstance(task, dict)]
    assert tasks, "the role must contain tasks"
    return tasks


def _directory_created_by(*, task: dict[str, Any]) -> str | None:
    file_task = task.get("ansible.builtin.file")
    if not isinstance(file_task, dict) or file_task.get("state") != "directory":
        return None
    path = file_task.get("path")
    return path if isinstance(path, str) else None


def test_every_template_destination_directory_is_created_before_its_template() -> None:
    created_directories: set[str] = set()
    template_directories: list[str] = []
    missing_directories: list[str] = []

    for task in _tasks():
        template_task = task.get("ansible.builtin.template")
        if isinstance(template_task, dict):
            destination = template_task.get("dest")
            assert isinstance(destination, str), "each template task must name a string destination"
            directory = destination.rsplit("/", 1)[0]
            template_directories.append(directory)
            if directory not in created_directories:
                missing_directories.append(directory)

        directory_created = _directory_created_by(task=task)
        if directory_created is not None:
            created_directories.add(directory_created)

    assert template_directories, "the role must template at least one destination"
    assert missing_directories == [], (
        "each template destination directory must be created by an earlier role task: "
        f"{missing_directories}"
    )
