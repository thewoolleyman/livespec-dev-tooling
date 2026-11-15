"""Regression coverage for extracted flake-retry path-analysis helpers."""

from __future__ import annotations

import ast
import importlib
from pathlib import Path


def test_path_analysis_refactors_preserve_the_supported_and_unknown_forms() -> None:
    """The extracted helpers leave every supported path form conservative."""
    package = Path(__file__).parents[2] / "livespec_dev_tooling"
    assert (package / "_flake_retry_function_terms.py").is_file()
    assert (package / "_flake_retry_request_indirection.py").is_file()

    divisions = importlib.import_module("livespec_dev_tooling.flake_retry_divisions")
    paths = importlib.import_module("livespec_dev_tooling.flake_retry_paths")

    join = ast.parse("os.path.join(root, 'data')", mode="eval").body
    formatted = ast.parse("Path(f'{root}/data')", mode="eval").body
    literal_only_name = ast.parse(
        "PART = os.path.join('config', 'data')\ntarget = Path(__file__).parent / PART"
    )
    assert divisions.path_operands(expression=join) is not None
    assert divisions.path_operands(expression=formatted) is not None
    assert divisions.path_operands(expression=ast.Name(id="plain")) is None
    assert paths.path_literals(tree=formatted) == (set(), True)
    assert paths.path_literals(tree=literal_only_name)[0] == {"config", "config/data", "data"}
