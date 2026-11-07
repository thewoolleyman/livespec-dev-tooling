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
