"""Unit tests for policy-neutral justfile Bash recipe extraction."""

from __future__ import annotations

import importlib
from pathlib import Path

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[3]
_MODULE_PATH = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "_justfile_bash_recipes.py"
_MODULE_NAME = "livespec_dev_tooling.checks._justfile_bash_recipes"


def _classifier_module() -> object:
    assert _MODULE_PATH.is_file(), "justfile Bash recipe classifier module should exist"
    return importlib.import_module(_MODULE_NAME)


def test_recipe_classifier_identifies_supported_recipe_shapes() -> None:
    module = _classifier_module()
    justfile_text = "\n".join(
        (
            "# Run the fast unit suite.",
            "test-fast:",
            "    pytest tests/unit",
            "",
            "# Run every check in one Bash process.",
            "check-all:",
            "    set -euo pipefail",
            "    pytest",
            "    ruff check .",
            "",
            "# Embedded Bash recipe.",
            "release:",
            "    #!/usr/bin/env bash",
            "    set -euo pipefail",
            "    python -m build",
            "",
            "format:",
            "    just fmt",
        )
    )

    result = module.classify_justfile_bash_recipes(justfile_text=justfile_text)

    assert result.valid is True
    assert [(recipe.name, recipe.shape) for recipe in result.recipes] == [
        ("test-fast", "direct"),
        ("check-all", "multiline"),
        ("release", "shebang"),
        ("format", "direct"),
    ]
    assert result.recipes[0].commands == ("pytest tests/unit",)
    assert result.recipes[1].commands == ("pytest", "ruff check .")
    assert result.recipes[2].commands == ("python -m build",)


def test_recipe_classifier_neutralizes_just_interpolation_but_rejects_malformed_bash() -> None:
    module = _classifier_module()
    justfile_text = "\n".join(
        (
            "interpolated arg:",
            "    echo {{arg}}",
            "",
            "malformed:",
            "    if [[ -n {{arg}} ]]; then",
            "      echo ok",
        )
    )

    result = module.classify_justfile_bash_recipes(justfile_text=justfile_text)

    assert result.valid is False
    assert result.recipes[0].neutralized_body == "echo __JUST_INTERPOLATION__"
    assert result.recipes[0].bash_parseable is True
    assert result.recipes[1].bash_parseable is False
    assert result.recipes[1].malformed_reason is not None


def test_recipe_classifier_preserves_source_coordinates() -> None:
    module = _classifier_module()
    justfile_text = "\n".join(
        (
            "default:",
            "    just check",
            "",
            "# Explain the recipe.",
            "check:",
            "    set -euo pipefail",
            "    pytest",
        )
    )

    result = module.classify_justfile_bash_recipes(justfile_text=justfile_text)

    default, check = result.recipes
    assert (default.header_line, default.body_start_line, default.body_end_line) == (1, 2, 2)
    assert default.evidence[0].line == 2
    assert default.evidence[0].column == 5
    assert (check.header_line, check.body_start_line, check.body_end_line) == (5, 6, 7)
    assert check.evidence[0].line == 6
    assert check.evidence[1].line == 7


def test_recipe_classifier_distinguishes_explanatory_comments_from_absent_documentation() -> None:
    module = _classifier_module()
    justfile_text = "\n".join(
        (
            "# Explain why -e is intentionally absent.",
            "# grep -c returns 1 when there are no matches.",
            "count-zero:",
            "    set -uo pipefail",
            "    grep -c TODO README.md",
            "",
            "silent:",
            "    set -uo pipefail",
            "    grep -c TODO README.md",
        )
    )

    result = module.classify_justfile_bash_recipes(justfile_text=justfile_text)

    assert result.recipes[0].documentation == (
        "Explain why -e is intentionally absent.",
        "grep -c returns 1 when there are no matches.",
    )
    assert result.recipes[0].has_explanatory_comment is True
    assert result.recipes[1].documentation == ()
    assert result.recipes[1].has_explanatory_comment is False


def test_recipe_classifier_reports_malformed_extraction() -> None:
    module = _classifier_module()
    justfile_text = "\n".join(
        (
            "broken:",
            "    echo before",
            "  echo lost indentation",
        )
    )

    result = module.classify_justfile_bash_recipes(justfile_text=justfile_text)

    assert result.valid is False
    assert result.extraction_errors == ("line 3: indented command is not attached to a recipe",)
