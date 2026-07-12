"""Outside-in test for `cross_repo/justfile_canonical_reconcile.py`.

The module reconciles a consumer's `justfile` canonical-check wiring during the
`bump-pin-rewrite` composite Action: it inserts every canonical slug missing
from the `check:` aggregate's `targets=(...)` array and appends a zero-arg
`check-<slug>:` recipe for each missing slug that has NO recipe header yet.

The load-bearing regression this suite guards (per `livespec-dev-tooling-3vq`):
the pre-extraction guard recognized a canonical slug's recipe ONLY in the BARE
`check-<slug>:` header form, so when a consumer hand-defined the check in a
PARAMETERIZED form (`check-red-green-replay *args:`, as both Driver repos do) it
appended a SECOND `check-red-green-replay:` recipe — a `just`-parse-breaking
redefinition. `_recipe_header_present` now recognizes every recipe-header form.

Coverage target: 100% line + branch of `justfile_canonical_reconcile.py`.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from livespec_dev_tooling.cross_repo import justfile_canonical_reconcile

__all__: list[str] = []


# ---------------------------------------------------------------------------
# Fixtures — partial-but-representative consumer justfiles.
# ---------------------------------------------------------------------------

# A `check-red-green-replay *args:` recipe is defined (parameterized form) but
# NOT listed in `targets=(...)`. This is the exact real regression stranding
# both Driver repos.
_JUSTFILE_PARAM_RECIPE_UNWIRED = """check:
    targets=(
        check-aggregate-completeness
        check-wrapper-shape
    )

check-aggregate-completeness:
    uv run python -m livespec_dev_tooling.checks.aggregate_completeness

check-red-green-replay *args:
    uv run python -m livespec_dev_tooling.checks.red_green_replay {{args}}

check-wrapper-shape:
    uv run python -m livespec_dev_tooling.checks.wrapper_shape
"""

# A canonical slug (`check-new-thing`) is absent everywhere — neither wired nor
# recipe-defined.
_JUSTFILE_SLUG_ABSENT = """check:
    targets=(
        check-aggregate-completeness
    )

check-aggregate-completeness:
    uv run python -m livespec_dev_tooling.checks.aggregate_completeness
"""

# `check-existing-bare` already has a BARE recipe header but is unwired.
_JUSTFILE_BARE_RECIPE_UNWIRED = """check:
    targets=(
        check-aggregate-completeness
    )

check-aggregate-completeness:
    uv run python -m livespec_dev_tooling.checks.aggregate_completeness

check-existing-bare:
    uv run python -m livespec_dev_tooling.checks.existing_bare
"""

# `check-foo-bar:` is defined; the canonical set names `check-foo` — a shorter
# name that must NOT be treated as already-present (prefix-collision guard).
_JUSTFILE_PREFIX_COLLISION = """check:
    targets=(
        check-aggregate-completeness
    )

check-aggregate-completeness:
    uv run python -m livespec_dev_tooling.checks.aggregate_completeness

check-foo-bar:
    uv run python -m livespec_dev_tooling.checks.foo_bar
"""

# Kitchen-sink: an EMPTY `targets=(...)` array (default-indent branch) with the
# aggregate slug present only as a recipe.
_JUSTFILE_EMPTY_TARGETS = """check:
    targets=(
    )

check-aggregate-completeness:
    uv run python -m livespec_dev_tooling.checks.aggregate_completeness
"""

# Kitchen-sink: a `targets=(...)` array carrying a comment line, a blank line, a
# non-`check-`-prefixed target, and a consumer-local (non-canonical) `check-`
# target; `check:` is the LAST recipe (no trailing recipe header).
_JUSTFILE_MIXED_ARRAY_TRAILING_CHECK = """check-aggregate-completeness:
    uv run python -m livespec_dev_tooling.checks.aggregate_completeness

check:
    targets=(
        # local + canonical checks
        check-aggregate-completeness

        prettier-check
        check-local-custom
    )
"""

# Fully-wired-and-recipe'd justfile: no reconcile applies.
_JUSTFILE_FULLY_CURRENT = """check:
    targets=(
        check-aggregate-completeness
    )

check-aggregate-completeness:
    uv run python -m livespec_dev_tooling.checks.aggregate_completeness
"""


def _header_count(*, text: str, slug: str) -> int:
    """Count column-0 `<slug>` recipe headers (any parameter form) in `text`.

    A duplicate redefinition — the `just`-parse-breaking bug — shows up as a
    count > 1. The lookahead `(?=[ \\t:])` keeps `check-foo` from matching a
    longer `check-foo-bar:` header.
    """
    return len(re.findall(rf"^{re.escape(slug)}(?=[ \t:])[^\n]*?:", text, re.MULTILINE))


def _target_present(*, text: str, slug: str) -> bool:
    """Return True when `slug` appears as an indented lone entry in a targets array."""
    return re.search(rf"^[ \t]+{re.escape(slug)}[ \t]*$", text, re.MULTILINE) is not None


# ---------------------------------------------------------------------------
# reconcile_justfile_text — the real regression + behavior-preservation cases.
# ---------------------------------------------------------------------------


def test_param_recipe_unwired_is_wired_without_duplicate_recipe() -> None:
    """A parameterized recipe unwired in targets is wired WITHOUT a duplicate recipe.

    The load-bearing regression: `check-red-green-replay *args:` is defined but
    absent from `targets=(...)`. Reconcile MUST insert it into the array yet
    append NO second `check-red-green-replay:` recipe — the result keeps exactly
    one column-0 recipe header, so `just` still parses.
    """
    result = justfile_canonical_reconcile.reconcile_justfile_text(
        justfile_text=_JUSTFILE_PARAM_RECIPE_UNWIRED,
        canonical_slugs=[
            "check-aggregate-completeness",
            "check-red-green-replay",
            "check-wrapper-shape",
        ],
    )
    assert _target_present(
        text=result, slug="check-red-green-replay"
    ), "the missing canonical slug must be inserted into targets=(...)"
    assert (
        _header_count(text=result, slug="check-red-green-replay") == 1
    ), "a duplicate check-red-green-replay: recipe was appended — the just-parse bug"
    # The parameterized recipe body is preserved verbatim (not replaced).
    assert "check-red-green-replay *args:" in result


def test_absent_slug_gets_target_and_zero_arg_recipe() -> None:
    """A canonical slug absent everywhere gets both a target entry and a zero-arg recipe."""
    result = justfile_canonical_reconcile.reconcile_justfile_text(
        justfile_text=_JUSTFILE_SLUG_ABSENT,
        canonical_slugs=["check-aggregate-completeness", "check-new-thing"],
    )
    assert _target_present(text=result, slug="check-new-thing")
    # The appended recipe uses the kebab→snake shared-module invocation.
    assert (
        "\ncheck-new-thing:\n    uv run python -m livespec_dev_tooling.checks.new_thing\n" in result
    )


def test_bare_recipe_unwired_is_wired_without_duplicate_recipe() -> None:
    """A slug with a BARE recipe header, unwired in targets, is wired with no duplicate."""
    result = justfile_canonical_reconcile.reconcile_justfile_text(
        justfile_text=_JUSTFILE_BARE_RECIPE_UNWIRED,
        canonical_slugs=["check-aggregate-completeness", "check-existing-bare"],
    )
    assert _target_present(text=result, slug="check-existing-bare")
    assert _header_count(text=result, slug="check-existing-bare") == 1


def test_prefix_collision_does_not_suppress_shorter_slug_recipe() -> None:
    """`check-foo-bar:` present must NOT count as `check-foo` present (prefix guard)."""
    result = justfile_canonical_reconcile.reconcile_justfile_text(
        justfile_text=_JUSTFILE_PREFIX_COLLISION,
        canonical_slugs=["check-aggregate-completeness", "check-foo"],
    )
    assert _target_present(text=result, slug="check-foo")
    # `check-foo` had no recipe of its own, so one IS appended...
    assert "\ncheck-foo:\n    uv run python -m livespec_dev_tooling.checks.foo\n" in result
    # ...and the longer `check-foo-bar:` recipe is untouched (still exactly one).
    assert _header_count(text=result, slug="check-foo-bar") == 1


def test_empty_targets_array_uses_default_indent() -> None:
    """An empty `targets=(...)` array gets the missing slug at the default 8-space indent."""
    result = justfile_canonical_reconcile.reconcile_justfile_text(
        justfile_text=_JUSTFILE_EMPTY_TARGETS,
        canonical_slugs=["check-aggregate-completeness"],
    )
    assert "        check-aggregate-completeness\n" in result
    # The aggregate slug already has a bare recipe → none appended.
    assert _header_count(text=result, slug="check-aggregate-completeness") == 1


def test_mixed_array_and_trailing_check_recipe_reconcile() -> None:
    """Comments, blanks, non-check and non-canonical targets are skipped; append still lands.

    This drives the `_token_for` None/non-canonical branches, the
    insert-after-last-canonical position (the new slug sorts after every wired
    canonical token), and the no-trailing-recipe-header (`recipe_end` runs to
    EOF) append path.
    """
    result = justfile_canonical_reconcile.reconcile_justfile_text(
        justfile_text=_JUSTFILE_MIXED_ARRAY_TRAILING_CHECK,
        canonical_slugs=["check-aggregate-completeness", "check-new"],
    )
    assert _target_present(text=result, slug="check-new")
    assert "\ncheck-new:\n    uv run python -m livespec_dev_tooling.checks.new\n" in result
    # The consumer-local, non-check, comment, and blank array lines survive.
    assert "prettier-check" in result
    assert "check-local-custom" in result
    assert "# local + canonical checks" in result


# ---------------------------------------------------------------------------
# reconcile_justfile_text — the non-reconcilable-shape skip branches.
# ---------------------------------------------------------------------------


def test_missing_aggregate_returns_input_unchanged() -> None:
    """A justfile without check-aggregate-completeness is returned unchanged."""
    text = "check-lint:\n    uv run ruff check .\n"
    result = justfile_canonical_reconcile.reconcile_justfile_text(
        justfile_text=text, canonical_slugs=["check-anything"]
    )
    assert result == text


def test_no_bare_check_header_returns_input_unchanged() -> None:
    """A justfile with the aggregate slug but no bare `check:` recipe is unchanged."""
    text = (
        "check-aggregate-completeness:\n"
        "    uv run python -m livespec_dev_tooling.checks.aggregate_completeness\n"
    )
    result = justfile_canonical_reconcile.reconcile_justfile_text(
        justfile_text=text, canonical_slugs=["check-aggregate-completeness", "check-new"]
    )
    assert result == text


def test_no_targets_array_returns_input_unchanged() -> None:
    """A `check:` recipe with no `targets=(...)` array is unchanged."""
    text = (
        "check:\n"
        "    just check-aggregate-completeness\n"
        "\n"
        "check-aggregate-completeness:\n"
        "    uv run python -m livespec_dev_tooling.checks.aggregate_completeness\n"
    )
    result = justfile_canonical_reconcile.reconcile_justfile_text(
        justfile_text=text, canonical_slugs=["check-aggregate-completeness", "check-new"]
    )
    assert result == text


def test_unterminated_targets_array_returns_input_unchanged() -> None:
    """A `targets=(` array with no closing `)` before the next recipe is unchanged."""
    text = (
        "check:\n"
        "    targets=(\n"
        "        check-aggregate-completeness\n"
        "\n"
        "check-aggregate-completeness:\n"
        "    uv run python -m livespec_dev_tooling.checks.aggregate_completeness\n"
    )
    result = justfile_canonical_reconcile.reconcile_justfile_text(
        justfile_text=text, canonical_slugs=["check-aggregate-completeness", "check-new"]
    )
    assert result == text


def test_all_canonical_already_wired_is_a_noop() -> None:
    """When every canonical slug is wired and recipe'd, the text is unchanged."""
    result = justfile_canonical_reconcile.reconcile_justfile_text(
        justfile_text=_JUSTFILE_FULLY_CURRENT,
        canonical_slugs=["check-aggregate-completeness"],
    )
    assert result == _JUSTFILE_FULLY_CURRENT


# ---------------------------------------------------------------------------
# main() — the IO + `::notice::` surface.
# ---------------------------------------------------------------------------


def test_main_no_justfile_emits_skip_notice(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """With no cwd justfile, main() emits the skip notice and exits 0 without reading env."""
    monkeypatch.chdir(tmp_path)
    rc = justfile_canonical_reconcile.main()
    assert rc == 0
    assert "::notice::no justfile found" in capsys.readouterr().out


def test_main_skips_non_aggregate_justfile_unchanged(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A justfile without the aggregate slug is left byte-identical; a skip notice fires."""
    justfile = tmp_path / "justfile"
    original = "check-lint:\n    uv run ruff check .\n"
    justfile.write_text(original, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CANONICAL_JSON", '{"slugs": ["check-anything"]}')
    rc = justfile_canonical_reconcile.main()
    assert rc == 0
    assert "consumer does not carry check-aggregate-completeness" in capsys.readouterr().out
    assert justfile.read_text(encoding="utf-8") == original


def test_main_reconciles_and_writes_justfile(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """main() rewrites the justfile in place and names the reconciled slug in a notice.

    The `CANONICAL_JSON` payload carries a non-string element (`123`) alongside
    the string slugs to exercise the defensive `isinstance(s, str)` filter.
    """
    justfile = tmp_path / "justfile"
    justfile.write_text(_JUSTFILE_SLUG_ABSENT, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(
        "CANONICAL_JSON",
        '{"slugs": ["check-aggregate-completeness", "check-new-thing", 123]}',
    )
    rc = justfile_canonical_reconcile.main()
    assert rc == 0
    out = capsys.readouterr().out
    assert "reconciled canonical check wiring for: check-new-thing" in out
    written = justfile.read_text(encoding="utf-8")
    assert _target_present(text=written, slug="check-new-thing")
    assert (
        "\ncheck-new-thing:\n    uv run python -m livespec_dev_tooling.checks.new_thing\n"
        in written
    )


def test_main_already_current_emits_notice_without_write(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """When nothing needs reconciling, main() emits the already-current notice, no rewrite."""
    justfile = tmp_path / "justfile"
    justfile.write_text(_JUSTFILE_FULLY_CURRENT, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CANONICAL_JSON", '{"slugs": ["check-aggregate-completeness"]}')
    rc = justfile_canonical_reconcile.main()
    assert rc == 0
    assert "canonical check wiring already current" in capsys.readouterr().out
    assert justfile.read_text(encoding="utf-8") == _JUSTFILE_FULLY_CURRENT


def test_main_non_dict_payload_yields_empty_canonical_set(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A non-dict `CANONICAL_JSON` payload defensively yields an empty slug set (no reconcile)."""
    justfile = tmp_path / "justfile"
    justfile.write_text(_JUSTFILE_FULLY_CURRENT, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CANONICAL_JSON", "[]")
    rc = justfile_canonical_reconcile.main()
    assert rc == 0
    assert "canonical check wiring already current" in capsys.readouterr().out
    assert justfile.read_text(encoding="utf-8") == _JUSTFILE_FULLY_CURRENT
