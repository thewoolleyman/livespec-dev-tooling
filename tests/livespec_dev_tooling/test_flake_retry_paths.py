"""The flake-retry path analyzer is shipped as a mirrored source module."""

from __future__ import annotations

import ast
import importlib
from pathlib import Path


def test_the_path_analyzer_module_is_shipped() -> None:
    """The focused analyzer module remains available to the retry plugin."""
    assert (
        Path(__file__).resolve().parents[2] / "livespec_dev_tooling/flake_retry_paths.py"
    ).is_file()


def test_the_path_analyzer_joins_consecutive_literal_segments() -> None:
    """A path expression exposes its complete literal directory prefixes."""
    module_path = Path(__file__).resolve().parents[2] / "livespec_dev_tooling/flake_retry_paths.py"

    assert module_path.is_file()

    analyzer = importlib.import_module("livespec_dev_tooling.flake_retry_paths")

    paths, undeterminable = analyzer.path_literals(
        tree=ast.parse("_ROOT / 'ci-runner' / 'k3s' / 'phase2' / 'gates' / 'gate.sh'")
    )

    assert paths == {"ci-runner/k3s/phase2/gates", "ci-runner/k3s/phase2/gates/gate.sh"}
    assert not undeterminable


def test_a_dynamic_operand_after_the_first_operand_and_before_a_literal_is_undeterminable() -> None:
    """Only the first operand may be a dynamic root; a later one hides path components."""
    analyzer = importlib.import_module("livespec_dev_tooling.flake_retry_paths")

    _, undeterminable = analyzer.path_literals(tree=ast.parse("_ROOT / segment / 'gates'"))

    assert undeterminable


def test_a_dynamic_first_operand_is_a_root_and_stays_determinable() -> None:
    """A dynamic root before the literal components is the normal repository-root shape."""
    analyzer = importlib.import_module("livespec_dev_tooling.flake_retry_paths")

    _, undeterminable = analyzer.path_literals(tree=ast.parse("_ROOT / 'ci-runner' / 'gates'"))

    assert not undeterminable


def test_a_suffixless_terminal_component_names_its_own_directory() -> None:
    """A terminal such as Makefile may be a file, so it names its directory too."""
    analyzer = importlib.import_module("livespec_dev_tooling.flake_retry_paths")

    paths, _ = analyzer.path_literals(tree=ast.parse("_ROOT / 'ci-runner' / 'gates' / 'Makefile'"))

    assert "ci-runner/gates" in paths
    assert "ci-runner/gates/Makefile" in paths


def test_a_suffixless_terminal_component_is_also_a_file_name_literal() -> None:
    """A terminal such as Makefile touches a changed file of that name anywhere."""
    analyzer = importlib.import_module("livespec_dev_tooling.flake_retry_paths")

    paths, _ = analyzer.path_literals(tree=ast.parse("_ROOT / 'ci-runner' / 'gates' / 'Makefile'"))

    assert "Makefile" in paths


def test_a_dynamic_terminal_operand_adds_no_file_name_literal() -> None:
    """Only a literal final operand can be a file name."""
    analyzer = importlib.import_module("livespec_dev_tooling.flake_retry_paths")

    paths, _ = analyzer.path_literals(tree=ast.parse("_ROOT / 'ci-runner' / 'gates' / name"))

    assert "gates" not in paths


def test_ordinary_arithmetic_division_is_not_an_undeterminable_path() -> None:
    """A division with no string-literal operand is arithmetic, not a path expression."""
    analyzer = importlib.import_module("livespec_dev_tooling.flake_retry_paths")

    paths, undeterminable = analyzer.path_literals(tree=ast.parse("elapsed.total_seconds() / 60"))

    assert not undeterminable
    assert paths == set()


def test_a_fully_dynamic_division_chain_is_not_an_undeterminable_path() -> None:
    """Without any string literal operand a chain cannot be identified as a path."""
    analyzer = importlib.import_module("livespec_dev_tooling.flake_retry_paths")

    _, undeterminable = analyzer.path_literals(tree=ast.parse("total / count / 2"))

    assert not undeterminable
