"""Consumer-tier scenario for the on-demand `just mutation-kill-matrix` recipe."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]

# A stand-in for mutmut's public command line, first on PYTHONPATH so the
# engine's `python -m mutmut` resolves to it. Real mutmut forks a worker per
# mutant, which crashes on macOS hosts; the recipe and the engine are what this
# scenario exercises, so only the mutant source is fixed.
_FAKE_MUTMUT = """\
import pathlib
import sys


def read_config():
    pass


def create_mutants():
    pass


def copy_also_copy_files():
    pass


if __name__ == "__main__":
    command = sys.argv[1]
    if command == "results":
        print("    tiny.x_add__mutmut_1: not checked")
    elif command == "apply":
        pathlib.Path("src/tiny/__init__.py").write_text(
            "def add(a, b):\\n    return a - b\\n", encoding="utf-8"
        )
"""

_FIXTURE_PYPROJECT = """\
[project]
name = "tiny"
version = "0.0.0"

[tool.pytest.ini_options]
testpaths = ["tests"]
"""

_FIXTURE_TEST = """\
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from tiny import add


def test_add():
    assert add(2, 3) == 5
"""


def _fixture_package(*, root: Path) -> Path:
    """Write a one-function package whose single test kills the one mutant."""
    package = root / "tiny-package"
    (package / "src" / "tiny").mkdir(parents=True)
    (package / "tests").mkdir()
    _ = (package / "pyproject.toml").write_text(_FIXTURE_PYPROJECT, encoding="utf-8")
    _ = (package / "src" / "tiny" / "__init__.py").write_text(
        "def add(a, b):\n    return a + b\n", encoding="utf-8"
    )
    _ = (package / "tests" / "test_tiny.py").write_text(_FIXTURE_TEST, encoding="utf-8")
    return package


def _child_env(*, stubs: Path) -> dict[str, str]:
    """Build a coverage-safe child environment with the mutmut stand-in first.

    The applied mutant has the same size as the source and lands within the same
    second, so a cached `.pyc` would pass its mtime-and-size check and hide the
    mutant; the children therefore write no bytecode.
    """
    removed = {"COVERAGE_PROCESS_START", "COV_CORE_CONFIG", "COV_CORE_DATAFILE", "COV_CORE_SOURCE"}
    inherited = {key: value for key, value in os.environ.items() if key not in removed}
    return inherited | {
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": os.pathsep.join(filter(None, (str(stubs), inherited.get("PYTHONPATH")))),
    }


def test_mutation_kill_matrix_recipe_writes_the_package_report(*, tmp_path: Path) -> None:
    """`just mutation-kill-matrix <package>` runs the engine and writes the package's report."""
    stubs = tmp_path / "stubs"
    (stubs / "mutmut").mkdir(parents=True)
    _ = (stubs / "mutmut" / "__init__.py").write_text("", encoding="utf-8")
    _ = (stubs / "mutmut" / "__main__.py").write_text(_FAKE_MUTMUT, encoding="utf-8")
    package = _fixture_package(root=tmp_path)

    completed = subprocess.run(
        ["just", "mutation-kill-matrix", str(package)],
        cwd=_REPO_ROOT,
        capture_output=True,
        check=False,
        env=_child_env(stubs=stubs),
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    report = json.loads(
        (package / "reports" / "mutation-kill-matrix.json").read_text(encoding="utf-8")
    )
    assert [mutant["identifier"] for mutant in report["mutants"]] == ["tiny.x_add__mutmut_1"]
    assert report["mutants"][0]["killed_by"] == ["tests/test_tiny.py::test_add"]
    assert (package / "src" / "tiny" / "__init__.py").read_text(encoding="utf-8") == (
        "def add(a, b):\n    return a + b\n"
    )


def test_mutation_kill_matrix_recipe_names_a_missing_target(*, tmp_path: Path) -> None:
    """With no package path the recipe fails and its usage names the missing target."""
    completed = subprocess.run(
        ["just", "mutation-kill-matrix"],
        cwd=_REPO_ROOT,
        capture_output=True,
        check=False,
        env=_child_env(stubs=tmp_path),
        text=True,
    )

    assert completed.returncode != 0
    assert "just mutation-kill-matrix target" in completed.stderr
