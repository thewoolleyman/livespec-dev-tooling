"""`_ci_matrix_parse`'s three public readers put their failures on the railway.

Triage rows 1-3 of `plan/rop-railway-enforcement/qndn-75-triage.md`. Each is
asserted at its OWN seam rather than through `ci_matrix_completeness`, which
short-circuits on the first precondition and so can only ever reach one of
them per run.

The load-bearing assertion is `test_unterminated_targets_array_is_its_own_failure`:
an unterminated `targets=(...)` array and an ABSENT one returned the same
`None`, and every caller reported only the absent case — so a justfile whose
array is merely unclosed was diagnosed as one carrying no array at all.
"""

from __future__ import annotations

import json
import textwrap
from typing import TYPE_CHECKING

from returns.io import IOFailure, IOSuccess
from returns.result import Failure, Success

from livespec_dev_tooling.checks._check_aggregate_failures import (
    CanonicalOverrideUnparseable,
    CanonicalOverrideUnreadable,
    CheckRecipeAbsent,
    TargetsArrayAbsent,
    TargetsArrayUnterminated,
)
from livespec_dev_tooling.checks._ci_matrix_parse import (
    extract_check_recipe_body,
    extract_targets_array_tokens,
    load_canonical,
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
        echo "${targets[@]}"

    build:
        echo build
    """
)


def test_check_recipe_body_reaches_the_caller() -> None:
    body = extract_check_recipe_body(justfile_text=_JUSTFILE)
    assert isinstance(body, Success)
    assert "targets=(" in body.unwrap()
    # The body stops at the next recipe header rather than running to EOF.
    assert "echo build" not in body.unwrap()


def test_absent_check_recipe_is_a_typed_failure() -> None:
    result = extract_check_recipe_body(justfile_text="build:\n    echo build\n")
    assert result == Failure(CheckRecipeAbsent())


def test_targets_array_tokens_reach_the_caller() -> None:
    body = extract_check_recipe_body(justfile_text=_JUSTFILE)
    assert isinstance(body, Success)
    assert extract_targets_array_tokens(recipe_body=body.unwrap()) == Success(
        ["check-lint", "check-format"]
    )


def test_absent_targets_array_is_a_typed_failure() -> None:
    result = extract_targets_array_tokens(recipe_body="    echo no-array\n")
    assert result == Failure(TargetsArrayAbsent())


def test_unterminated_targets_array_is_its_own_failure() -> None:
    """An unclosed array is NOT an absent one, and it used to be spelled that way.

    The two share nothing operationally: an absent array means "add a
    `targets=(...)` array", an unterminated one means "close the array you
    already have". One `None` carried both, and the callers only ever named
    the first.
    """
    body = "    targets=(\n      check-lint\n"
    result = extract_targets_array_tokens(recipe_body=body)
    assert result == Failure(TargetsArrayUnterminated())


def test_load_canonical_reads_an_override_file(*, tmp_path: Path) -> None:
    override = tmp_path / "canonical.json"
    _ = override.write_text(json.dumps({"slugs": ["check-a", "check-b"]}), encoding="utf-8")

    result = load_canonical(canonical_from="canonical.json", cwd=tmp_path)

    assert result == IOSuccess(("check-a", "check-b"))


def test_load_canonical_fails_when_the_override_file_cannot_be_read(*, tmp_path: Path) -> None:
    result = load_canonical(canonical_from="absent.json", cwd=tmp_path)

    assert isinstance(result, IOFailure)
    failure = result.failure()._inner_value  # noqa: SLF001  — IOResult failure unwrap.
    assert isinstance(failure, CanonicalOverrideUnreadable)
    assert failure.path.endswith("absent.json")


def test_load_canonical_fails_when_the_override_file_is_not_json(*, tmp_path: Path) -> None:
    override = tmp_path / "canonical.json"
    _ = override.write_text("{ not json at all :::", encoding="utf-8")

    result = load_canonical(canonical_from="canonical.json", cwd=tmp_path)

    assert isinstance(result, IOFailure)
    failure = result.failure()._inner_value  # noqa: SLF001  — IOResult failure unwrap.
    assert isinstance(failure, CanonicalOverrideUnparseable)
    assert failure.path.endswith("canonical.json")


def test_load_canonical_keeps_the_empty_tuple_for_a_malformed_slugs_field(
    *, tmp_path: Path
) -> None:
    """A readable, parseable override whose `slugs` is not a list still answers `()`.

    Deliberately UNCHANGED by the conversion. The empty tuple is already
    load-bearing here and `()` is also what a legitimately-empty `slugs: []`
    yields, so collapsing a READ failure onto it was the thing to remove —
    not the two success-track meanings, which are a separate question filed
    rather than settled inside a conversion.
    """
    override = tmp_path / "canonical.json"
    _ = override.write_text(json.dumps({"slugs": "check-a"}), encoding="utf-8")

    assert load_canonical(canonical_from="canonical.json", cwd=tmp_path) == IOSuccess(())
