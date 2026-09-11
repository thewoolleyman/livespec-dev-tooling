"""Regression coverage for the operator audit Just boundary."""

from pathlib import Path

__all__: list[str] = []


def test_recipe_forwards_declared_positional_arguments() -> None:
    root = Path(__file__).resolve().parents[3]
    justfile = (root / "justfile").read_text(encoding="utf-8")
    recipe = justfile.split("git-identity-audit output fabro_evidence:", maxsplit=1)[1]
    command = recipe.split("\n\n", maxsplit=1)[0]

    assert '"$1" "$2"' in command
    assert '"$output"' not in command
    assert '"$fabro_evidence"' not in command
