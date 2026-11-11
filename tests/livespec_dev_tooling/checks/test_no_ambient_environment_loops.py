"""Tests for the ambient-environment loop guard."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Protocol, cast

import pytest

__all__: list[str] = []

_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / "livespec_dev_tooling"
    / "checks"
    / "no_ambient_environment_loops.py"
)


class CheckModule(Protocol):
    """The callable surface exposed by the check module."""

    def main(self) -> int: ...


def _findings(*, stderr: str) -> list[dict[str, object]]:
    """Return the check's structured findings from its stderr stream."""
    return [json.loads(line) for line in stderr.splitlines() if line.startswith("{")]


def _without_timestamps(*, findings: list[dict[str, object]]) -> list[dict[str, object]]:
    """Compare the host-independent parts of structured check findings."""
    return [
        {key: value for key, value in finding.items() if key != "timestamp"} for finding in findings
    ]


def _run_check(
    *,
    check: CheckModule,
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> tuple[int, list[dict[str, object]]]:
    """Run the check in a fixture consumer repository."""
    monkeypatch.chdir(root)
    result = check.main()
    return result, _findings(stderr=capsys.readouterr().err)


def test_environment_loops_are_rejected_independently_of_host_environment(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Direct, aliased, and locally-bound environment loops always fail."""
    tests = tmp_path / "tests"
    tests.mkdir()
    _ = (tests / "test_bad.py").write_text(
        """import os
import os as operating_system
from os import environ as imported_environ

for name in os.environ:
    del name
for name in operating_system.environ:
    del name
for name in imported_environ:
    del name
for name in os.environ.copy():
    del name
snapshot = dict(os.environ)
for name in snapshot:
    del name
copied_environment = os.environ.copy()
for name in copied_environment:
    del name

async def drain() -> None:
    local_environment = operating_system.environ
    async for name in local_environment:
        del name
""",
        encoding="utf-8",
    )
    _ = (tests / "test_good.py").write_text(
        "_ = [monkeypatch.delenv(name) for name in os.environ if name.startswith('GIT_')]\n",
        encoding="utf-8",
    )

    assert _MODULE_PATH.is_file()
    check = cast(
        "CheckModule",
        importlib.import_module("livespec_dev_tooling.checks.no_ambient_environment_loops"),
    )
    monkeypatch.delenv("GIT_AMBIENT_LOOP_TEST", raising=False)
    empty_result, empty_findings = _run_check(
        check=check, root=tmp_path, monkeypatch=monkeypatch, capsys=capsys
    )
    monkeypatch.setenv("GIT_AMBIENT_LOOP_TEST", "present")
    git_result, git_findings = _run_check(
        check=check, root=tmp_path, monkeypatch=monkeypatch, capsys=capsys
    )

    assert empty_result == git_result == 4
    assert _without_timestamps(findings=empty_findings) == _without_timestamps(
        findings=git_findings
    )
    assert [(finding["file"], finding["line"]) for finding in git_findings] == [
        ("tests/test_bad.py", 5),
        ("tests/test_bad.py", 7),
        ("tests/test_bad.py", 9),
        ("tests/test_bad.py", 11),
        ("tests/test_bad.py", 14),
        ("tests/test_bad.py", 17),
        ("tests/test_bad.py", 22),
    ]
    assert all(
        finding["rewrite"] == "replace the loop with a single-expression rewrite"
        for finding in git_findings
    )


def test_invalid_consumer_configuration_is_a_check_error(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Configuration failures retain the shared check's conventional exit code."""
    _ = (tmp_path / "pyproject.toml").write_text(
        "[tool.livespec_dev_tooling]\ntests_tree_prefix = 1\n",
        encoding="utf-8",
    )
    check = cast(
        "CheckModule",
        importlib.import_module("livespec_dev_tooling.checks.no_ambient_environment_loops"),
    )
    result, findings = _run_check(
        check=check,
        root=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
    )

    assert result == 1
    assert findings[0]["check_id"] == "no_ambient_environment_loops"
