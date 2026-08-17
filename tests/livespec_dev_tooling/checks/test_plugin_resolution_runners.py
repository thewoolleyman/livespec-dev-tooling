"""Tests for plugin-resolution live runner implementations."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from livespec_dev_tooling.checks import _plugin_resolution_runners as runners

__all__: list[str] = []


def _which_none(_cmd: str) -> str | None:
    return None


def _which_path(cmd: str) -> str | None:
    return "/usr/bin/" + cmd


@dataclass(frozen=True, kw_only=True)
class _RecordingPiProcessRunner:
    prompts: list[str] = field(default_factory=list)

    def run(self, *, prompt: str, cwd: Path) -> runners.PiProcessResult:
        _ = cwd
        self.prompts.append(prompt)
        return runners.PiProcessResult(exit_code=0, stdout="", stderr="")


def test_real_pi_process_runner_runs_non_interactive_with_approve(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The real Pi adapter uses `--approve -p` so project packages are trusted."""
    recorded: list[tuple[list[str], Path, dict[str, str]]] = []
    monkeypatch.setenv("COVERAGE_PROCESS_START", "coverage.ini")
    monkeypatch.setenv("COV_CORE_SOURCE", "livespec_dev_tooling")

    def fake_run(
        argv: list[str],
        *,
        cwd: str,
        env: dict[str, str],
        capture_output: bool,
        text: bool,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        assert capture_output is True
        assert text is True
        assert check is False
        recorded.append((argv, Path(cwd), env))
        return subprocess.CompletedProcess(argv, 0, stdout="ok", stderr="")

    monkeypatch.setattr(runners.subprocess, "run", fake_run)
    result = runners.RealPiProcessRunner().run(prompt="/skill:livespec-next", cwd=tmp_path)
    assert result == runners.PiProcessResult(exit_code=0, stdout="ok", stderr="")
    assert recorded[0][0] == ["pi", "--approve", "-p", "/skill:livespec-next"]
    assert recorded[0][1] == tmp_path
    assert "COVERAGE_PROCESS_START" not in recorded[0][2]
    assert "COV_CORE_SOURCE" not in recorded[0][2]


def test_pi_resolution_runner_skips_when_binary_unavailable(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unavailable pi binary skips without invoking the process seam."""
    monkeypatch.setattr(runners.shutil, "which", _which_none)
    process = _RecordingPiProcessRunner()
    outcome = runners.PiResolutionRunner(process_runner=process).resolve(
        harness="pi", canonical_command="livespec:next"
    )
    assert outcome == runners.ResolutionOutcome(available=False, resolved=False)
    assert process.prompts == []


def test_pi_resolution_runner_accepts_flat_skill_name(*, monkeypatch: pytest.MonkeyPatch) -> None:
    """A flat `livespec-next` declaration is issued as a Pi `/skill:` command."""
    monkeypatch.setattr(runners.shutil, "which", _which_path)
    process = _RecordingPiProcessRunner()
    outcome = runners.PiResolutionRunner(process_runner=process).resolve(
        harness="pi", canonical_command="livespec-next"
    )
    assert outcome == runners.ResolutionOutcome(available=True, resolved=True)
    assert process.prompts == ["/skill:livespec-next"]


def test_pi_resolution_runner_leaves_explicit_prompt_verbatim(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fully explicit non-LiveSpec prompt is left untouched."""
    monkeypatch.setattr(runners.shutil, "which", _which_path)
    process = _RecordingPiProcessRunner()
    outcome = runners.PiResolutionRunner(process_runner=process).resolve(
        harness="pi", canonical_command="/skill:custom"
    )
    assert outcome == runners.ResolutionOutcome(available=True, resolved=True)
    assert process.prompts == ["/skill:custom"]
