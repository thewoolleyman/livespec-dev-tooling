"""Consumer scenario for declared delegated gate-suite final recipes.

The declared suite is shared by the pre-commit and pre-push delegated gates,
but only the pre-commit route rewrites its final entry.  A pre-commit recipe
left in that final pre-push slot therefore lets a push run the wrong aggregate.
This drives the shipped check in a fixture consumer process, the same boundary
at which pinning repositories use it.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MODULE = "livespec_dev_tooling.checks.delegated_gate_check_suite"


def _run_check(*, root: Path) -> subprocess.CompletedProcess[str]:
    """Run the shipped consumer check without inheriting coverage instrumentation."""
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("COVERAGE_", "COV_CORE_"))
    }
    environment["PYTHONPATH"] = str(_REPO_ROOT)
    return subprocess.run(
        [sys.executable, "-m", _MODULE],
        cwd=str(root),
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize(
    ("delegated_gate", "final_entry", "expected_code"),
    [
        (True, "check-pre-commit", 4),
        (True, "hook_gate=1 check-pre-commit-gated-tree", 4),
        (True, "check-pre-push", 0),
        (True, "hook_gate=1 check", 0),
        (True, None, 0),
        (False, "check-pre-commit", 0),
    ],
)
def test_shared_gate_aggregates_refuse_only_pre_commit_recipes_in_the_final_slot(
    *, tmp_path: Path, delegated_gate: bool, final_entry: str | None, expected_code: int
) -> None:
    """The pre-push slot is refused only for the two pre-commit aggregate recipes."""
    suite = "" if final_entry is None else f'gate_check_suite = ["bootstrap", "{final_entry}"]\n'
    _ = (tmp_path / "pyproject.toml").write_text(
        f"[tool.livespec_dev_tooling]\ndelegated_gate = {str(delegated_gate).lower()}\n{suite}",
        encoding="utf-8",
    )

    completed = _run_check(root=tmp_path)
    output = completed.stdout + completed.stderr

    assert completed.returncode == expected_code, output
    if expected_code != 0:
        assert "pyproject.toml" in output
        assert "gate_check_suite" in output
        assert final_entry is not None and final_entry in output
        assert "check-pre-push" in output
