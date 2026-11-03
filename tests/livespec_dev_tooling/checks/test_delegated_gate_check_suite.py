"""Unit coverage for the declared delegated gate-suite final-recipe check."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Protocol, cast

import pytest

__all__: list[str] = []

_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / "livespec_dev_tooling"
    / "checks"
    / "delegated_gate_check_suite.py"
)


class _CheckModule(Protocol):
    """The check entrypoint the test invokes after the Red file assertion."""

    def main(self) -> int:
        """Return the check's process exit status."""
        ...


def _module() -> _CheckModule:
    """Import the check only after the Red assertion has established its file exists."""
    return cast(
        _CheckModule,
        importlib.import_module("livespec_dev_tooling.checks.delegated_gate_check_suite"),
    )


def _write_config(*, root: Path, body: str) -> None:
    """Write a consumer declaration under test."""
    _ = (root / "pyproject.toml").write_text(body, encoding="utf-8")


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("not [toml", 0),
        ("[tool.livespec_dev_tooling]\ndelegated_gate = false\n", 0),
        ("[tool.livespec_dev_tooling]\ndelegated_gate = true\n", 0),
        (
            "\n".join(
                ("[tool.livespec_dev_tooling]", "delegated_gate = true", "gate_check_suite = []")
            )
            + "\n",
            0,
        ),
        (
            "\n".join(
                (
                    "[tool.livespec_dev_tooling]",
                    "delegated_gate = true",
                    'gate_check_suite = ["hook_gate=1"]',
                )
            )
            + "\n",
            0,
        ),
        (
            "\n".join(
                (
                    "[tool.livespec_dev_tooling]",
                    "delegated_gate = true",
                    'gate_check_suite = ["first=1 second=2 check-pre-push"]',
                )
            )
            + "\n",
            0,
        ),
        (
            "\n".join(
                (
                    "[tool.livespec_dev_tooling]",
                    "delegated_gate = true",
                    'gate_check_suite = ["check-pre-commit"]',
                )
            )
            + "\n",
            4,
        ),
        (
            "\n".join(
                (
                    "[tool.livespec_dev_tooling]",
                    "delegated_gate = true",
                    'gate_check_suite = ["hook_gate=1 check-pre-commit-gated-tree"]',
                )
            )
            + "\n",
            4,
        ),
        (
            "\n".join(
                (
                    "[tool.livespec_dev_tooling]",
                    "delegated_gate = true",
                    'gate_check_suite = ["hook_gate= check-pre-commit"]',
                )
            )
            + "\n",
            4,
        ),
    ],
)
def test_main_checks_only_the_declared_final_pre_push_slot(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    body: str,
    expected: int,
) -> None:
    """Only a delegated suite ending in either pre-commit aggregate is refused."""
    assert _MODULE_PATH.is_file()
    module = _module()
    _write_config(root=tmp_path, body=body)
    monkeypatch.chdir(tmp_path)

    result = module.main()

    assert result == expected
    if expected != 0:
        assert "gate_check_suite" in capsys.readouterr().err
