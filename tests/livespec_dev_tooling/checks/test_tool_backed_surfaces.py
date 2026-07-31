"""Mirror-paired test for `livespec_dev_tooling/checks/_tool_backed_surfaces.py`.

The private sibling module carries the justfile + CI-matrix parsers extracted
from `tool_backed_check_completeness.py` at the LLOC-reduction split. The
parsers' end-to-end coverage lives in `test_tool_backed_check_completeness.py`
(they are exercised outside-in through the parent check's subprocess contract);
THIS file unit-tests the extracted pure parsers directly, pinning the public
surface and each parser's branch behavior at the module boundary.
"""

from __future__ import annotations

from pathlib import Path

from returns.io import IOSuccess
from returns.result import Failure, Success

from livespec_dev_tooling.checks._check_aggregate_failures import (
    CheckRecipeAbsent,
    TargetsArrayAbsent,
    TargetsArrayUnterminated,
)
from livespec_dev_tooling.checks._tool_backed_surfaces import (
    collect_ci_matrix_targets,
    extract_check_recipe_body,
    extract_targets_array_tokens,
)

__all__: list[str] = []


def test_extract_check_recipe_body_returns_body_until_next_recipe() -> None:
    """The `check:` recipe body extends to the next recipe header, not beyond."""
    justfile = "check:\n    targets=(\n        check-lint\n    )\n\nother:\n    echo hi\n"
    result = extract_check_recipe_body(justfile_text=justfile)
    assert isinstance(result, Success)
    body = result.unwrap()
    assert "targets=(" in body
    assert "check-lint" in body
    # The `other:` recipe header terminates the body — its command is excluded.
    assert "echo hi" not in body


def test_extract_check_recipe_body_absent_recipe_fails() -> None:
    """A justfile with no `check:` recipe fails (parent emits the finding)."""
    assert extract_check_recipe_body(justfile_text="build:\n    echo build\n") == Failure(
        CheckRecipeAbsent()
    )


def test_extract_targets_array_tokens_filters_to_check_slugs() -> None:
    """Only `check-`-prefixed tokens survive; comments and blanks are dropped."""
    body = "    targets=(\n        check-lint\n        # a comment\n\n        check-types # inline\n    )\n"
    assert extract_targets_array_tokens(recipe_body=body) == Success(["check-lint", "check-types"])


def test_extract_targets_array_tokens_unclosed_array_is_unterminated() -> None:
    """An unclosed `targets=(...)` array fails AS UNTERMINATED, not as absent.

    It used to share `None` with the absent case, so the parent reported the
    array as missing when it is present and merely unclosed.
    """
    body = "    targets=(\n        check-lint\n"
    assert extract_targets_array_tokens(recipe_body=body) == Failure(TargetsArrayUnterminated())


def test_extract_targets_array_tokens_absent_array_fails() -> None:
    """A recipe body with no `targets=(...)` fails as ABSENT."""
    assert extract_targets_array_tokens(recipe_body="    echo no-array\n") == Failure(
        TargetsArrayAbsent()
    )


def test_collect_ci_matrix_targets_unions_yml_and_yaml(*, tmp_path: Path) -> None:
    """Matrix targets are unioned across both `*.yml` and `*.yaml` workflow files."""
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    _ = (workflows / "ci.yml").write_text(
        "jobs:\n  gate:\n    strategy:\n      matrix:\n        target:\n"
        "          - check-lint\n          - check-types\n",
        encoding="utf-8",
    )
    _ = (workflows / "extra.yaml").write_text(
        "jobs:\n  more:\n    strategy:\n      matrix:\n        target:\n"
        "          - check-format\n",
        encoding="utf-8",
    )
    assert collect_ci_matrix_targets(workflows_dir=workflows) == IOSuccess(
        {"check-lint", "check-types", "check-format"}
    )
