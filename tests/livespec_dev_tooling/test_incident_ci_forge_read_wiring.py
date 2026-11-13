"""The incident CI release and pull-request reads stay on the retrying forge reader."""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[2]
_CI_YML = _REPO_ROOT / ".github" / "workflows" / "ci.yml"
_INCIDENT_JOB = "incident-ci"
_DIRECT_FORGE = re.compile(r"\b(?:gh\s+api|curl)\b")


@dataclass(frozen=True, kw_only=True)
class ForgeReadStep:
    """One incident-CI shell step and the authenticated read it must make."""

    step_name: str
    read_id: str
    path: str


_READ_STEPS = (
    ForgeReadStep(
        step_name="Install the latest released livespec-dev-tooling (never the candidate tree)",
        read_id="incident-ci-latest-release-read",
        path="repos/${GITHUB_REPOSITORY}/releases/latest",
    ),
    ForgeReadStep(
        step_name="Select incident work from an authenticated PR read",
        read_id="incident-ci-pull-request-body-read",
        path="repos/${GITHUB_REPOSITORY}/pulls/${PR_NUMBER}",
    ),
)


def _map(*, value: object) -> dict[str, Any]:
    return cast("dict[str, Any]", value) if isinstance(value, dict) else {}


def _seq(*, value: object) -> list[Any]:
    return cast("list[Any]", value) if isinstance(value, list) else []


def _step_bodies(*, source: str) -> dict[str, str]:
    """Read the incident job's named shell bodies from the workflow YAML."""
    workflow = _map(value=yaml.safe_load(source))
    jobs = _map(value=workflow.get("jobs"))
    incident = _map(value=jobs.get(_INCIDENT_JOB))
    return {
        str(step.get("name")): str(step.get("run"))
        for raw in _seq(value=incident.get("steps"))
        if (step := _map(value=raw)).get("name") in {expected.step_name for expected in _READ_STEPS}
    }


def forge_read_findings(*, source: str) -> list[str]:
    """Report release and PR reads that bypass their required retrying reader."""
    bodies = _step_bodies(source=source)
    findings: list[str] = []
    for expected in _READ_STEPS:
        body = bodies.get(expected.step_name, "")
        invocation = f'livespec-forge-read {expected.read_id} "{expected.path}"'
        if invocation not in body:
            findings.append(f"{expected.step_name} does not invoke {expected.read_id}")
        if _DIRECT_FORGE.search(body) is not None:
            findings.append(f"{expected.step_name} calls the forge directly")
    return findings


def _failed_step(*, body: str, read_id: str, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    """Run one workflow shell body with the reader's named failure contract."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    reader = bin_dir / "livespec-forge-read"
    _ = reader.write_text(
        "#!/usr/bin/env bash\nprintf 'livespec-forge-read: %s ended without an answer\\n' \"$1\" >&2\nexit 1\n",
        encoding="utf-8",
    )
    _ = reader.chmod(0o755)
    environment = os.environ | {
        "GITHUB_EVENT_NAME": "pull_request",
        "GITHUB_REPOSITORY": "owner/repository",
        "PR_NUMBER": "17",
        "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"],
    }
    result = subprocess.run(
        args=["bash", "-euo", "pipefail", "-c", body],
        capture_output=True,
        check=False,
        env=environment,
        text=True,
    )
    assert result.returncode == 1
    assert read_id in result.stderr
    return result


def test_committed_incident_ci_reads_use_the_retrying_reader() -> None:
    assert forge_read_findings(source=_CI_YML.read_text(encoding="utf-8")) == []


@pytest.mark.parametrize("expected", _READ_STEPS)
def test_each_reader_failure_exits_one_and_names_its_read(
    *, expected: ForgeReadStep, tmp_path: Path
) -> None:
    bodies = _step_bodies(source=_CI_YML.read_text(encoding="utf-8"))
    _ = _failed_step(body=bodies[expected.step_name], read_id=expected.read_id, tmp_path=tmp_path)


@pytest.mark.parametrize("expected", _READ_STEPS)
def test_direct_gh_api_replacement_is_detected(*, expected: ForgeReadStep) -> None:
    source = _CI_YML.read_text(encoding="utf-8")
    old = f'livespec-forge-read {expected.read_id} "{expected.path}"'
    assert source.count(old) == 1
    mutated = source.replace(old, f'gh api "{expected.path}"')
    assert forge_read_findings(source=mutated) == [
        f"{expected.step_name} does not invoke {expected.read_id}",
        f"{expected.step_name} calls the forge directly",
    ]
