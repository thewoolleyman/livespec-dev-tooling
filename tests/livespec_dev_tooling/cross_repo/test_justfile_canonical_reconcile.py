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

# A wired slug (`check-plan-thread-anchor-declared`) whose auto-generated
# recipe names a module `042a7854` deleted upstream after renaming it to
# `check-plan-anchor-declared`. Left as-is, the bump PR's CI runs
# `just check-plan-thread-anchor-declared` and dies with `ModuleNotFoundError`
# (livespec-dev-tooling-3gy1) — the reconcile must rewrite BOTH the wired
# target token and the auto-generated recipe to the new slug/module.
_JUSTFILE_STRANDED_RENAMED_SLUG = """check:
    targets=(
        check-aggregate-completeness
        check-plan-thread-anchor-declared
    )

check-aggregate-completeness:
    uv run python -m livespec_dev_tooling.checks.aggregate_completeness

check-plan-thread-anchor-declared:
    uv run python -m livespec_dev_tooling.checks.plan_thread_anchor_declared
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


def test_stranded_renamed_slug_is_rewritten_to_new_slug_and_module() -> None:
    """A wired slug renamed upstream is rewritten to its new slug/module, not left stranded.

    Reproduces the exact `livespec-dev-tooling-3gy1` failure: the OLD slug's
    module no longer exists at the bumped pin, so leaving it wired guarantees a
    `ModuleNotFoundError` in CI. The rename map rewrites the wired target token
    AND the auto-generated recipe body/header to the new slug/module, and drops
    the old (now-orphaned) recipe entirely.
    """
    result = justfile_canonical_reconcile.reconcile_justfile_text(
        justfile_text=_JUSTFILE_STRANDED_RENAMED_SLUG,
        canonical_slugs=["check-aggregate-completeness", "check-plan-anchor-declared"],
        renames=[("check-plan-thread-anchor-declared", "check-plan-anchor-declared")],
    )
    assert _target_present(text=result, slug="check-plan-anchor-declared")
    assert not _target_present(
        text=result, slug="check-plan-thread-anchor-declared"
    ), "the old, now-non-canonical slug must not remain wired"
    assert (
        "check-plan-anchor-declared:\n"
        "    uv run python -m livespec_dev_tooling.checks.plan_anchor_declared\n" in result
    )
    assert _header_count(text=result, slug="check-plan-anchor-declared") == 1
    assert (
        _header_count(text=result, slug="check-plan-thread-anchor-declared") == 0
    ), "the orphaned old recipe (importing a deleted module) must not remain"


def test_rename_whose_old_slug_is_not_wired_is_a_noop() -> None:
    """A rename entry whose OLD slug is not actually wired changes nothing.

    The rename map is curated fleet-wide and consulted unconditionally; most
    consumers never wired the retired slug in the first place — this consumer
    already wires the NEW slug directly (never having carried the old one) —
    so the rewrite's `re.subn` finds nothing to replace and must be a no-op
    rather than injecting anything out of nowhere.
    """
    justfile_text = """check:
    targets=(
        check-aggregate-completeness
        check-plan-anchor-declared
    )

check-aggregate-completeness:
    uv run python -m livespec_dev_tooling.checks.aggregate_completeness

check-plan-anchor-declared:
    uv run python -m livespec_dev_tooling.checks.plan_anchor_declared
"""
    result = justfile_canonical_reconcile.reconcile_justfile_text(
        justfile_text=justfile_text,
        canonical_slugs=["check-aggregate-completeness", "check-plan-anchor-declared"],
        renames=[("check-plan-thread-anchor-declared", "check-plan-anchor-declared")],
    )
    assert result == justfile_text


def test_rename_leaves_a_non_autogenerated_old_recipe_untouched() -> None:
    """A wired OLD slug with a HAND-AUTHORED (non-bare) recipe has its target renamed,

    but the recipe body is left alone — this module never overwrites content it
    did not itself generate. The consumer is on notice via the renamed wired
    target; a hand-authored recipe under the OLD name is a maintainer fix-up,
    not something an automated rewrite should guess at.
    """
    justfile_text = (
        "check:\n"
        "    targets=(\n"
        "        check-aggregate-completeness\n"
        "        check-plan-thread-anchor-declared\n"
        "    )\n"
        "\n"
        "check-aggregate-completeness:\n"
        "    uv run python -m livespec_dev_tooling.checks.aggregate_completeness\n"
        "\n"
        "check-plan-thread-anchor-declared custom_arg:\n"
        "    echo hand-authored {{custom_arg}}\n"
    )
    result = justfile_canonical_reconcile.reconcile_justfile_text(
        justfile_text=justfile_text,
        canonical_slugs=["check-aggregate-completeness", "check-plan-anchor-declared"],
        renames=[("check-plan-thread-anchor-declared", "check-plan-anchor-declared")],
    )
    assert _target_present(text=result, slug="check-plan-anchor-declared")
    assert not _target_present(text=result, slug="check-plan-thread-anchor-declared")
    assert (
        "check-plan-thread-anchor-declared custom_arg:\n    echo hand-authored" in result
    ), "the hand-authored recipe body must be left untouched"


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


# ---------------------------------------------------------------------------
# Inventory reconcile — the three-consumer blind spot (livespec-s43svm.33).
#
# `aggregate_completeness` reads a committed `check-targets.txt` FIRST and
# parses the justfile `targets=(...)` array only in its absence. Reconciling the
# array alone therefore left three of the fleet's eight Python consumers
# untouched, and each failed the gate on the very bump meant to wire it.
# ---------------------------------------------------------------------------

# `livespec-driver-codex` / `livespec-driver-pi` shape: the aggregate delegates
# to a shell script, so there is NO inline array for the old reconcile to find.
_JUSTFILE_SCRIPT_DELEGATING = """check:
    bash dev-tooling/check-aggregate.sh

check-aggregate-completeness:
    uv run python -m livespec_dev_tooling.checks.aggregate_completeness
"""

# `livespec-runtime` shape: a PARAMETERIZED aggregate header, which the
# bare-only match reported as `no_check_header`.
_JUSTFILE_PARAM_AGGREGATE = """check *skip_targets:
    targets=(
        check-aggregate-completeness
    )
    echo "${skip_targets}"

check-aggregate-completeness:
    uv run python -m livespec_dev_tooling.checks.aggregate_completeness
"""

_INVENTORY = """# Canonical check inventory.
check-aggregate-completeness
check-wrapper-shape
"""


def test_script_delegating_consumer_reconciles_its_inventory() -> None:
    """A consumer whose aggregate delegates to a script still gets wired.

    The old reconcile found no `targets=(...)` array, returned
    `no_targets_array`, and left the repo to fail the gate. The inventory file
    is what the gate reads, so that is what must be reconciled.
    """
    result = justfile_canonical_reconcile.reconcile_sources(
        justfile_text=_JUSTFILE_SCRIPT_DELEGATING,
        inventory_text=_INVENTORY,
        canonical_slugs=["check-aggregate-completeness", "check-new-thing", "check-wrapper-shape"],
    )
    assert result.skipped_reason is None, "a script-delegating consumer must not be skipped"
    assert result.inventory_text is not None
    assert "check-new-thing" in result.inventory_text
    # The recipe is appended too, so `just check-new-thing` resolves.
    assert _header_count(text=result.justfile_text, slug="check-new-thing") == 1


def test_parameterized_aggregate_header_is_recognized() -> None:
    """`check *skip_targets:` is an aggregate header, not an absent one."""
    result = justfile_canonical_reconcile.reconcile_sources(
        justfile_text=_JUSTFILE_PARAM_AGGREGATE,
        inventory_text=None,
        canonical_slugs=["check-aggregate-completeness", "check-new-thing"],
    )
    assert result.skipped_reason is None, "a parameterized aggregate header must reconcile"
    assert _target_present(text=result.justfile_text, slug="check-new-thing")


def test_consumer_carrying_both_sources_updates_both() -> None:
    """A repo with an inventory AND an inline array has both updated.

    The file because it is what the gate reads; the array because such a repo
    may also enforce a literal mirror between the two.
    """
    result = justfile_canonical_reconcile.reconcile_sources(
        justfile_text=_JUSTFILE_PARAM_AGGREGATE,
        inventory_text=_INVENTORY,
        canonical_slugs=["check-aggregate-completeness", "check-new-thing", "check-wrapper-shape"],
    )
    assert result.inventory_text is not None
    assert "check-new-thing" in result.inventory_text
    assert _target_present(text=result.justfile_text, slug="check-new-thing")


def test_inventory_only_repo_leaves_justfile_array_alone_when_absent() -> None:
    """No inline array is not an error when the inventory carries the slugs."""
    result = justfile_canonical_reconcile.reconcile_sources(
        justfile_text=_JUSTFILE_SCRIPT_DELEGATING,
        inventory_text=_INVENTORY,
        canonical_slugs=["check-aggregate-completeness", "check-wrapper-shape"],
    )
    assert result.skipped_reason is None
    assert result.missing == ()


def test_reconcile_inventory_text_preserves_canonical_order() -> None:
    """An inserted slug lands in canonical position, not appended at the end.

    Order is load-bearing: `aggregate_completeness` fails an out-of-order
    inventory as well as an incomplete one.
    """
    result = justfile_canonical_reconcile.reconcile_inventory_text(
        inventory_text=_INVENTORY,
        canonical_slugs=["check-aggregate-completeness", "check-new-thing", "check-wrapper-shape"],
    )
    slugs = [line.strip() for line in result.splitlines() if line.strip().startswith("check-")]
    assert slugs == ["check-aggregate-completeness", "check-new-thing", "check-wrapper-shape"]


def test_reconcile_inventory_text_is_idempotent() -> None:
    """A current inventory is returned byte-identical."""
    canonical = ["check-aggregate-completeness", "check-wrapper-shape"]
    once = justfile_canonical_reconcile.reconcile_inventory_text(
        inventory_text=_INVENTORY, canonical_slugs=canonical
    )
    assert once == _INVENTORY
    twice = justfile_canonical_reconcile.reconcile_inventory_text(
        inventory_text=once, canonical_slugs=canonical
    )
    assert twice == once


def test_empty_inventory_gains_every_canonical_slug() -> None:
    """An inventory declaring nothing is filled rather than skipped."""
    result = justfile_canonical_reconcile.reconcile_inventory_text(
        inventory_text="# nothing yet\n",
        canonical_slugs=["check-a-thing", "check-b-thing"],
    )
    assert "check-a-thing" in result
    assert "check-b-thing" in result


def test_sources_skip_when_neither_source_carries_the_aggregate() -> None:
    """A consumer that does not carry the gate is still a legitimate no-op."""
    result = justfile_canonical_reconcile.reconcile_sources(
        justfile_text="check:\n    echo hi\n",
        inventory_text="check-something-local\n",
        canonical_slugs=["check-anything"],
    )
    assert result.skipped_reason == "no_aggregate"


def test_main_reconciles_the_inventory_file_on_disk(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`main()` writes the reconciled inventory, not only the justfile."""
    _ = (tmp_path / "justfile").write_text(_JUSTFILE_SCRIPT_DELEGATING, encoding="utf-8")
    _ = (tmp_path / "check-targets.txt").write_text(_INVENTORY, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(
        "CANONICAL_JSON",
        '{"slugs": ["check-aggregate-completeness", "check-new-thing", "check-wrapper-shape"]}',
    )
    assert justfile_canonical_reconcile.main() == 0
    assert "check-new-thing" in (tmp_path / "check-targets.txt").read_text(encoding="utf-8")
    assert "reconciled canonical check wiring" in capsys.readouterr().out


def test_main_warns_when_an_aggregate_carrying_consumer_is_skipped(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A skip on a consumer that DOES carry the gate emits a visible warning.

    Silence is what made the blind spot expensive: the module exited 0 with a
    notice nobody reads, and the consequence surfaced later as a red bump PR.
    """
    _ = (tmp_path / "justfile").write_text(
        "check:\n    echo no array\n\ncheck-aggregate-completeness:\n    uv run x\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CANONICAL_JSON", '{"slugs": ["check-aggregate-completeness"]}')
    assert justfile_canonical_reconcile.main() == 0
    assert "::warning::" in capsys.readouterr().out


def test_main_does_not_warn_for_a_legitimate_no_aggregate_skip(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A repo that does not carry the gate is not a problem, so it is not a warning."""
    _ = (tmp_path / "justfile").write_text("check:\n    echo hi\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CANONICAL_JSON", '{"slugs": ["check-anything"]}')
    assert justfile_canonical_reconcile.main() == 0
    assert "::warning::" not in capsys.readouterr().out


def test_inventory_repo_without_any_aggregate_recipe_still_reconciles() -> None:
    """An inventory repo whose justfile declares no `check` aggregate at all.

    The gate reads the inventory, so the absence of an inline aggregate is not
    a reason to skip: the inventory is reconciled and the recipe appended.
    """
    result = justfile_canonical_reconcile.reconcile_sources(
        justfile_text="check-aggregate-completeness:\n    uv run python -m x\n",
        inventory_text=_INVENTORY,
        canonical_slugs=["check-aggregate-completeness", "check-new-thing", "check-wrapper-shape"],
    )
    assert result.skipped_reason is None
    assert result.inventory_text is not None
    assert "check-new-thing" in result.inventory_text
    assert _header_count(text=result.justfile_text, slug="check-new-thing") == 1
