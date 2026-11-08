"""ci.yml ships the coverage producer's data file AND its receipt to the consumer.

Work-item livespec-dev-tooling-cj5dg5 (post-mortem livespec-dev-tooling-npysxq,
candidates B and E). 34f370e1 changed check-coverage's reuse precondition to
require `.livespec-coverage-reuse-token` beside `.coverage`, while `ci.yml` kept
shipping `.coverage` alone, so every CI run silently fell back to a second full
suite. No test read `ci.yml` for that wiring. These tests do: the producer job
must upload both files with hidden files included and a missing file an error,
and the consumer job must download both before it runs `just check-coverage`.
Each broken copy below proves the reader names the step that went missing.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from pathlib import Path

import pytest
import yaml

__all__: list[str] = []

_CI = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"
_PRODUCER = "check-per-file-coverage"
_CONSUMER = "check-coverage"
_FILES = (".coverage", ".livespec-coverage-reuse-token")
_UPLOAD = "actions/upload-artifact"
_DOWNLOAD = "actions/download-artifact"

Workflow = dict[str, dict[str, dict[str, list[dict[str, object]]]]]


def _load() -> Workflow:
    return yaml.safe_load(_CI.read_text(encoding="utf-8"))


def _steps(*, workflow: Workflow, job: str) -> list[dict[str, object]]:
    return workflow["jobs"][job]["steps"]


def _with(*, step: dict[str, object]) -> dict[str, object]:
    block = step.get("with", {})
    assert isinstance(block, dict)
    return {str(key): value for key, value in block.items()}


def _uses(*, step: dict[str, object], action: str) -> bool:
    return str(step.get("uses", "")).startswith(action)


def _runs_consumer(*, workflow: Workflow, step: dict[str, object]) -> bool:
    run = str(step.get("run", ""))
    targets = workflow["jobs"][_CONSUMER].get("strategy", {}).get("matrix", {}).get("target", [])
    via_matrix = "just ${{ matrix.target }}" in run and _CONSUMER in targets
    return f"just {_CONSUMER}" in run or via_matrix


def _upload_names(*, workflow: Workflow) -> dict[str, str]:
    """Map each shipped file to its artifact name, for well-formed uploads only."""
    names: dict[str, str] = {}
    for step in _steps(workflow=workflow, job=_PRODUCER):
        block = _with(step=step)
        well_formed = (
            _uses(step=step, action=_UPLOAD)
            and block.get("include-hidden-files") is True
            and block.get("if-no-files-found") == "error"
        )
        names.update({str(block["path"]): str(block["name"])} if well_formed else {})
    return names


def missing_wiring(*, workflow: Workflow) -> list[str]:
    """Name every producer upload or consumer download step the workflow lacks."""
    names = _upload_names(workflow=workflow)
    steps = _steps(workflow=workflow, job=_CONSUMER)
    run_at = next(
        (at for at, step in enumerate(steps) if _runs_consumer(workflow=workflow, step=step)),
        len(steps),
    )
    downloaded = {
        str(_with(step=step).get("name"))
        for step in steps[:run_at]
        if _uses(step=step, action=_DOWNLOAD)
    }
    upload_gaps = [
        f"{_PRODUCER}: no upload-artifact step ships {file} with include-hidden-files: true"
        " and if-no-files-found: error"
        for file in _FILES
        if file not in names
    ]
    download_gaps = [
        f"{_CONSUMER}: no download-artifact step restores {file} before just {_CONSUMER}"
        for file in _FILES
        if names.get(file, file) not in downloaded
    ]
    return upload_gaps + download_gaps


def _drop_hidden_files_on_receipt(*, workflow: Workflow) -> None:
    for step in _steps(workflow=workflow, job=_PRODUCER):
        if _with(step=step).get("path") == _FILES[1]:
            del step["with"]["include-hidden-files"]


def _ignore_missing_data_file(*, workflow: Workflow) -> None:
    for step in _steps(workflow=workflow, job=_PRODUCER):
        if _with(step=step).get("path") == _FILES[0]:
            step["with"]["if-no-files-found"] = "ignore"


def _drop_receipt_download(*, workflow: Workflow) -> None:
    steps = _steps(workflow=workflow, job=_CONSUMER)
    steps[:] = [step for step in steps if _with(step=step).get("name") != "coverage-reuse-token"]


def _download_data_after_the_run(*, workflow: Workflow) -> None:
    steps = _steps(workflow=workflow, job=_CONSUMER)
    [data] = [step for step in steps if _with(step=step).get("name") == "coverage-data"]
    steps.remove(data)
    steps.append(data)


def test_the_real_ci_yml_ships_and_restores_both_coverage_files() -> None:
    assert missing_wiring(workflow=_load()) == []


_UPLOAD_GAP = f"{_PRODUCER}: no upload-artifact step ships"
_DOWNLOAD_GAP = f"{_CONSUMER}: no download-artifact step restores"


@pytest.mark.parametrize(
    ("break_it", "expected"),
    [
        # A malformed upload ships nothing the consumer can restore, so the
        # same file is also named as a missing download.
        (
            _drop_hidden_files_on_receipt,
            [f"{_UPLOAD_GAP} {_FILES[1]}", f"{_DOWNLOAD_GAP} {_FILES[1]}"],
        ),
        (_ignore_missing_data_file, [f"{_UPLOAD_GAP} {_FILES[0]}", f"{_DOWNLOAD_GAP} {_FILES[0]}"]),
        (_drop_receipt_download, [f"{_DOWNLOAD_GAP} {_FILES[1]}"]),
        (_download_data_after_the_run, [f"{_DOWNLOAD_GAP} {_FILES[0]}"]),
    ],
)
def test_a_broken_copy_names_the_missing_step(
    *, break_it: Callable[..., None], expected: list[str]
) -> None:
    workflow = copy.deepcopy(_load())
    break_it(workflow=workflow)

    gaps = missing_wiring(workflow=workflow)

    facts = [
        len(gaps) == len(expected),
        all(gap.startswith(prefix) for gap, prefix in zip(gaps, expected, strict=True)),
    ]
    assert all(facts), gaps
