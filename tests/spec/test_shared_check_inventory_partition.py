"""The `SPECIFICATION/contracts.md` §"Shared check inventory" partition, read off the tree.

The section codifies WHICH shipped modules are canonical check slugs, and it
says twice that the placement is "load-bearing, not a filing preference": the
canonical-set derivation walks `checks/*.py`, a canonical slug obliges EVERY
consumer to wire it into `just check` AND its CI matrix per the
wiring-completeness invariant, so a module filed one directory over silently
conscripts the whole fleet. That makes the partition a mechanical property of
the tree, and this asserts it in the three directions it can break.

- **The two non-canonical sibling directories stay non-canonical.** Every
  module under `workflow_checks/` and every module under `charters/` is absent
  from the derived canonical set. Both are named in the section as
  deliberately-placed OUTSIDE `checks/`, and both are per-consumer OPT-IN —
  `charters/` because one governed repo carries neither a `justfile` nor a
  `pyproject.toml` and could not satisfy a canonical obligation by any means.
- **The two declared workflow-check members ship where the section says.**
  `no_stale_revise_branches` (the revise-workflow member) and
  `release_bump_classification` (the release-workflow member) each resolve to a
  module under `workflow_checks/`. The section's "the list is open to further
  kinds admitted by amendment" is why membership is asserted rather than
  equality.
- **The three non-module concerns have no module.** `lint`, `format` and
  `complexity` "appear in the conceptual check coverage but have no `python -m
  livespec_dev_tooling.checks.<slug>` invocation form" — they run through direct
  `ruff` invocation from each consumer's justfile. A `checks/lint.py` appearing
  would make lint a canonical slug and oblige every consumer to wire a second,
  divergent lint gate.
- **The `baseline` profile is a curated SUBSET carrying its two Verifiers.**
  Unlike the filesystem-derived canonical set the profile is hand-maintained, so
  the section's own invariant — "Every entry MUST also be a real canonical check
  slug" — is the thing that rots, and the two Conformance-Pattern concerns it
  names one Verifier each for are what it exists to carry.

The livespec-private half of the partition (the two checks that stay in
livespec-core) is asserted at `tests.consumer.test_non_goals` and is
deliberately not restated here.
"""

from __future__ import annotations

from pathlib import Path

from returns.io import IOSuccess
from returns.unsafe import unsafe_perform_io

from livespec_dev_tooling.canonical_checks import baseline_check_slugs, canonical_check_slugs

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PACKAGE_DIR = _REPO_ROOT / "livespec_dev_tooling"

# The two sibling directories the section places OUTSIDE `checks/` on purpose.
_NON_CANONICAL_DIRS = ("workflow_checks", "charters")

# The declared members of the two workflow-check kinds.
_WORKFLOW_CHECK_MEMBERS = ("no_stale_revise_branches", "release_bump_classification")

# The concerns handled by direct `ruff` invocation rather than by a slug.
_NON_MODULE_CONCERNS = ("lint", "format", "complexity")

# One Verifier per Conformance-Pattern concern with a shared baseline check.
_BASELINE_VERIFIERS = (
    "check-plugin-resolution",
    "check-primary-checkout-commit-refuse-hook-installed",
)


def _canonical_slugs() -> set[str]:
    """The filesystem-derived canonical check set."""
    resolved = canonical_check_slugs()
    assert isinstance(
        resolved, IOSuccess
    ), f"the shipped checks package must be readable; got {resolved}"
    return set(unsafe_perform_io(resolved.unwrap()))


def _module_stems(*, directory: str) -> list[str]:
    """Every shipped slug-shaped module stem directly under `directory`."""
    return sorted(
        path.stem
        for path in (_PACKAGE_DIR / directory).glob("*.py")
        if not path.stem.startswith("_") and path.stem != "__init__"
    )


def test_the_shipped_partition_matches_the_codified_inventory() -> None:
    """The canonical set, its two non-canonical siblings, and the baseline profile hold."""
    canonical = _canonical_slugs()
    assert canonical, "the library must ship at least one canonical check"

    conscripted = {
        directory: sorted(
            stem
            for stem in _module_stems(directory=directory)
            if f"check-{stem.replace('_', '-')}" in canonical
        )
        for directory in _NON_CANONICAL_DIRS
    }
    leaked = {directory: stems for directory, stems in conscripted.items() if stems}
    assert not leaked, (
        f"a canonical slug obliges EVERY consumer to wire it into `just check` AND its "
        f"CI matrix, so a module in either opt-in sibling directory reaching the "
        f"canonical set silently conscripts the fleet; leaked={leaked}"
    )

    misplaced = sorted(
        member
        for member in _WORKFLOW_CHECK_MEMBERS
        if not (_PACKAGE_DIR / "workflow_checks" / f"{member}.py").is_file()
    )
    assert not misplaced, (
        f"each declared workflow-check member must ship under `workflow_checks/`, which "
        f"is what keeps it out of the canonical derivation's walk; misplaced={misplaced}"
    )

    with_modules = sorted(
        concern
        for concern in _NON_MODULE_CONCERNS
        if (_PACKAGE_DIR / "checks" / f"{concern}.py").is_file()
    )
    assert not with_modules, (
        f"`lint`, `format` and `complexity` run through direct `ruff` invocation and have "
        f"NO `python -m livespec_dev_tooling.checks.<slug>` form; a module here would make "
        f"each a canonical slug every consumer must wire; with_modules={with_modules}"
    )

    baseline = set(baseline_check_slugs())
    assert baseline, "the `baseline` profile must name at least one check"
    not_canonical = sorted(baseline - canonical)
    assert not not_canonical, (
        f"the profile is hand-maintained rather than filesystem-derived, so every entry "
        f"must still be a real canonical check slug; stale={not_canonical}"
    )
    missing_verifiers = sorted(slug for slug in _BASELINE_VERIFIERS if slug not in baseline)
    assert not missing_verifiers, (
        f"the profile carries one Verifier per Conformance-Pattern concern with a shared "
        f"baseline check; missing={missing_verifiers}"
    )
