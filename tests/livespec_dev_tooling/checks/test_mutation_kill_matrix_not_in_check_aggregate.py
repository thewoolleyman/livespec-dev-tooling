"""Tests for the Rule-26 on-demand recipe aggregate guard."""

from __future__ import annotations

import importlib
from pathlib import Path

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[3]


def test_guard_refuses_wiring_the_on_demand_recipe_into_check(
    *, monkeypatch: object, tmp_path: Path
) -> None:
    """The named finding keeps exhaustive mutation analysis out of the aggregate."""
    module_path = (
        _REPO_ROOT
        / "livespec_dev_tooling"
        / "checks"
        / "mutation_kill_matrix_not_in_check_aggregate.py"
    )
    assert module_path.is_file()

    module = importlib.import_module(
        "livespec_dev_tooling.checks.mutation_kill_matrix_not_in_check_aggregate"
    )
    justfile = tmp_path / "justfile"
    _ = justfile.write_text(
        "check:\n    #!/usr/bin/env bash\n    targets=(\n        check-example\n        mutation-kill-matrix\n    )\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    assert module.main() == 4
