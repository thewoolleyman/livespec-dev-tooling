"""A refused builder install carries each builder step's evidence in its failure message."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from returns.io import IOSuccess

from livespec_dev_tooling.fleet._local_context import CommandOutcome, CommandResult
from livespec_dev_tooling.fleet._orchestrator_hold import ORCHESTRATOR_PLUGIN
from livespec_dev_tooling.fleet._tag_adopt_build import build_plugin

_TAG = "v0.311.0"
_COMMIT = "e" * 40


def _answers(*, stdout: str, stderr: str) -> list[CommandOutcome]:
    return [
        IOSuccess(CommandResult(returncode=0, stdout=f"{stdout}{step}", stderr=f"{stderr}{step}"))
        for step in ("A", "B", "C")
    ]


def _refusal(*, home: Path, stdout: str = "out", stderr: str = "err") -> str:
    answers = _answers(stdout=stdout, stderr=stderr)

    def run(*, args: list[str], cwd: Path, env: Mapping[str, str]) -> CommandOutcome:
        _ = (args, cwd, env)
        return answers.pop(0)

    built = build_plugin(home=home, tag=_TAG, tag_commit=_COMMIT, base_env={}, run=run)
    return built.failure


def test_a_refusal_names_each_step_with_its_exit_code_and_output(*, tmp_path: Path) -> None:
    failure = _refusal(home=tmp_path)

    assert failure.startswith("the builder installed ")
    assert f"not the tag's commit {_COMMIT}; nothing was moved. builder steps: " in failure
    assert (
        "marketplace add exit 0 [stdout tail: outA] [stderr tail: errA]; "
        "git init exit 0 [stdout tail: outB] [stderr tail: errB]; "
        "install exit 0 [stdout tail: outC] [stderr tail: errC]"
    ) in failure


def test_a_refusal_bounds_each_output_to_its_last_400_characters(*, tmp_path: Path) -> None:
    failure = _refusal(home=tmp_path, stdout="x" * 1000 + "END", stderr="")

    assert "x" * 396 + "ENDA]" in failure
    assert "x" * 397 + "ENDA]" not in failure


def test_a_refusal_says_whether_the_registry_existed_and_its_record_count(
    *, tmp_path: Path
) -> None:
    absent = _refusal(home=tmp_path / "absent")
    registry = tmp_path / "present" / ".claude" / "plugins" / "installed_plugins.json"
    registry.parent.mkdir(parents=True)
    other = {"scope": "project", "projectPath": "/elsewhere", "installPath": "/i"}
    _ = registry.write_text(
        json.dumps({"version": 2, "plugins": {ORCHESTRATOR_PLUGIN: [other, other]}}),
        encoding="utf-8",
    )
    present = _refusal(home=tmp_path / "present")

    assert "registry file absent; 0 records with a projectPath" in absent
    assert "registry file present; 2 records with a projectPath" in present
