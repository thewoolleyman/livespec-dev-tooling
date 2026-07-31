"""`_tool_backed_surfaces`'s three public readers put their failures on the railway.

Triage rows 14-16. Rows 14 and 15 are the deliberately duplicated twins of
`_ci_matrix_parse`'s recipe parsers — permitted under the package's bounded
parser-duplication convention because they are mechanical extractors carrying
no spec citation — so they convert to the SAME failure types, shared from
`_check_aggregate_failures`. This closes the split #972 opened.

Asserted at each function's own seam: the parent check short-circuits on the
first precondition, so it can only ever reach one of the three per run.
"""

from __future__ import annotations

import textwrap
from typing import TYPE_CHECKING

from returns.io import IOFailure, IOSuccess
from returns.result import Failure, Success

from livespec_dev_tooling.checks._check_aggregate_failures import (
    CheckRecipeAbsent,
    TargetsArrayAbsent,
    TargetsArrayUnterminated,
    WorkflowFileUnreadable,
)
from livespec_dev_tooling.checks._tool_backed_surfaces import (
    collect_ci_matrix_targets,
    extract_check_recipe_body,
    extract_targets_array_tokens,
)

if TYPE_CHECKING:
    from pathlib import Path

_JUSTFILE = textwrap.dedent(
    """\
    check:
        #!/usr/bin/env bash
        targets=(
          check-lint
          check-format
        )

    build:
        echo build
    """
)

_WORKFLOW = textwrap.dedent(
    """\
    jobs:
      checks:
        strategy:
          matrix:
            target:
              - check-lint
    """
)


def test_check_recipe_body_reaches_the_caller() -> None:
    body = extract_check_recipe_body(justfile_text=_JUSTFILE)
    assert isinstance(body, Success)
    assert "targets=(" in body.unwrap()
    assert "echo build" not in body.unwrap()


def test_absent_check_recipe_is_a_typed_failure() -> None:
    assert extract_check_recipe_body(justfile_text="build:\n    echo build\n") == Failure(
        CheckRecipeAbsent()
    )


def test_targets_array_tokens_reach_the_caller() -> None:
    body = extract_check_recipe_body(justfile_text=_JUSTFILE)
    assert isinstance(body, Success)
    assert extract_targets_array_tokens(recipe_body=body.unwrap()) == Success(
        ["check-lint", "check-format"]
    )


def test_absent_targets_array_is_a_typed_failure() -> None:
    assert extract_targets_array_tokens(recipe_body="    echo no-array\n") == Failure(
        TargetsArrayAbsent()
    )


def test_unterminated_targets_array_is_its_own_failure() -> None:
    """The same collapse this module's twin carried, fixed the same way."""
    body = "    targets=(\n      check-lint\n"
    assert extract_targets_array_tokens(recipe_body=body) == Failure(TargetsArrayUnterminated())


def test_ci_matrix_targets_union_yml_and_yaml(*, tmp_path: Path) -> None:
    _ = (tmp_path / "ci.yml").write_text(_WORKFLOW, encoding="utf-8")
    _ = (tmp_path / "other.yaml").write_text(
        _WORKFLOW.replace("check-lint", "check-format"), encoding="utf-8"
    )

    assert collect_ci_matrix_targets(workflows_dir=tmp_path) == IOSuccess(
        {"check-lint", "check-format"}
    )


def test_empty_workflows_dir_is_an_answer(*, tmp_path: Path) -> None:
    """An empty directory ANSWERS with no targets — the ratified tolerance."""
    assert collect_ci_matrix_targets(workflows_dir=tmp_path) == IOSuccess(set())


def test_unreadable_workflow_file_is_a_failure_not_an_empty_contribution(*, tmp_path: Path) -> None:
    """A workflow whose bytes cannot be decoded fails rather than contributing nothing.

    ⛔ INVALID UTF-8 RATHER THAN `chmod 000`. This suite runs as ROOT, where a
    permission-stripped file is still readable and the assertion would never
    fire — a fixture that cannot fail is a green that means nothing, inside the
    epic that exists to remove them. Undecodable bytes fail identically for
    every user.

    Reading it as an empty contribution would be the worse failure here: the
    parent asserts CI RUNS what the justfile WIRES, so a silently skipped
    workflow makes a slug that IS run look unrun.
    """
    _ = (tmp_path / "ci.yml").write_bytes(b"jobs:\n  \xff\xfe not utf-8\n")

    result = collect_ci_matrix_targets(workflows_dir=tmp_path)

    assert isinstance(result, IOFailure)
    failure = result.failure()._inner_value  # noqa: SLF001  — IOResult failure unwrap.
    assert isinstance(failure, WorkflowFileUnreadable)
    assert failure.path.endswith("ci.yml")
