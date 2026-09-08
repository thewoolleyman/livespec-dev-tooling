"""Outside-in tests for `livespec_dev_tooling/shipped_path_release_guard_core.py`.

The module under test is the PURE decision core of the shipped-path release
guard (work-item livespec-dev-tooling-ys2i, slice A of 3): given a commit
subject and body, the changed paths, the repo's releasing-type set, the
shipped-path prefixes, and an override flag, it answers whether the change
edits shipped bytes that no release will carry. Every function is pure, so
these tests need no repository, no fixtures, and no subprocesses.

Test scenarios:

- Every type IN a supplied releasing set releases; every type outside it does
  not — the set is an INPUT, so the same function answers differently for two
  repos, and both directions are asserted below.
- livespec's OWN declared set releases `perf`, `refactor` and `revert`. This
  is the INVERSE of this slice's original (refuted) acceptance, which asserted
  those three are non-releasing. The evidence is livespec's release history:
  `v0.28.2..v0.28.3` held 36 commits — 5 `refactor`, 5 `chore`, 26 `docs`,
  zero `feat`, zero `fix`, zero breaking markers — and `v0.28.3` WAS CUT;
  `v0.21.3`'s only non-`docs` commit was a single `revert` with no breaking
  footer and a release was cut. The negative control is the docs-and-chore-only
  window of 2026-08-30..2026-09-08, 30+ commits, which cut nothing.
- The release-please DEFAULT set does NOT release `refactor` — the per-repo
  behaviour asserted in both directions with one function.
- Any breaking marker releases regardless of the set: a trailing `!` on the
  type, a `!` after a scope, and both the `BREAKING CHANGE:` and
  `BREAKING-CHANGE:` footer spellings.
- A subject that is not a Conventional Commit at all does not release.
- Shipped-path intersection: hit (exact file, nested path, trailing-slash
  prefix), miss (sibling prefix, no changed paths, no shipped prefixes).
- `is_violation` over each combination of (intersects, releases, override).
- `perf`'s treatment AGREES with `release_bump_classification`, which is the
  other module in this package that models release behaviour by commit type.
"""

from __future__ import annotations

from livespec_dev_tooling.shipped_path_release_guard_core import (
    commit_releases,
    is_violation,
    touches_shipped_path,
)
from livespec_dev_tooling.workflow_checks import release_bump_classification

__all__: list[str] = []

# livespec's OWN releasing set: the `hidden: false` entries of the
# `changelog-sections` array in its `release-please-config.json` (an entry with
# no `hidden` key is visible). Held HERE rather than in the module under test
# because the module must never hardcode a releasing set — resolving one from a
# repo's config is slice B's job, and this constant stands in for that
# resolution.
_LIVESPEC_RELEASING_TYPES = frozenset({"feat", "fix", "perf", "revert", "refactor"})

# The release-please DEFAULT set — what a repo that declares NO
# `changelog-sections` gets. `refactor` is hidden by default, which is why the
# same function must answer False for it here and True for it above.
_RELEASE_PLEASE_DEFAULT_RELEASING_TYPES = frozenset({"feat", "feature", "fix", "perf", "revert"})

_NON_RELEASING_ON_LIVESPEC = ("docs", "chore", "ci", "build", "style", "test")

_SHIPPED_PREFIXES = frozenset(
    {
        "livespec/SPECIFICATION",
        ".claude-plugin/",
    }
)


def test_every_type_in_the_supplied_set_releases() -> None:
    """Membership in the supplied set is the whole rule for a non-breaking subject."""
    for commit_type in _LIVESPEC_RELEASING_TYPES:
        assert commit_releases(
            subject=f"{commit_type}(scope): a subject",
            body="",
            releasing_types=_LIVESPEC_RELEASING_TYPES,
        )


def test_every_type_outside_the_supplied_set_does_not_release() -> None:
    """A type absent from the supplied set cuts no release."""
    for commit_type in _NON_RELEASING_ON_LIVESPEC:
        assert not commit_releases(
            subject=f"{commit_type}: a subject",
            body="",
            releasing_types=_LIVESPEC_RELEASING_TYPES,
        )


def test_livespec_declared_set_releases_perf_refactor_and_revert() -> None:
    """v0.28.3 (refactor-only range) and v0.21.3 (revert-only range) both cut releases."""
    for commit_type in ("perf", "refactor", "revert"):
        assert commit_releases(
            subject=f"{commit_type}: a subject",
            body="",
            releasing_types=_LIVESPEC_RELEASING_TYPES,
        )


def test_release_please_default_set_does_not_release_refactor() -> None:
    """The default `changelog-sections` hide `refactor`, so a default repo does not release it."""
    assert not commit_releases(
        subject="refactor: a subject",
        body="",
        releasing_types=_RELEASE_PLEASE_DEFAULT_RELEASING_TYPES,
    )
    assert commit_releases(
        subject="fix: a subject",
        body="",
        releasing_types=_RELEASE_PLEASE_DEFAULT_RELEASING_TYPES,
    )


def test_breaking_bang_releases_regardless_of_the_set() -> None:
    """A trailing `!` on the type releases even for a type the set omits."""
    assert commit_releases(
        subject="docs!: drop the documented flag",
        body="",
        releasing_types=_LIVESPEC_RELEASING_TYPES,
    )
    assert commit_releases(
        subject="chore(deps)!: drop python 3.10",
        body="",
        releasing_types=_LIVESPEC_RELEASING_TYPES,
    )


def test_breaking_footer_releases_regardless_of_the_set() -> None:
    """Both footer spellings release, on a type the set omits and on an unparseable subject."""
    assert commit_releases(
        subject="docs: rewrite the contract",
        body="BREAKING CHANGE: the contract changed",
        releasing_types=_LIVESPEC_RELEASING_TYPES,
    )
    assert commit_releases(
        subject="tidied things up",
        body="BREAKING-CHANGE: the contract changed",
        releasing_types=_LIVESPEC_RELEASING_TYPES,
    )


def test_non_conventional_subject_does_not_release() -> None:
    """A subject release-please cannot type cuts no release."""
    assert not commit_releases(
        subject="tidied things up",
        body="",
        releasing_types=_LIVESPEC_RELEASING_TYPES,
    )


def test_touches_shipped_path_hits() -> None:
    """An exact shipped file, a path nested under a prefix, and a trailing-slash prefix all hit."""
    assert touches_shipped_path(
        changed_paths=("livespec/SPECIFICATION",),
        shipped_prefixes=_SHIPPED_PREFIXES,
    )
    assert touches_shipped_path(
        changed_paths=("README.md", "livespec/SPECIFICATION/contracts.md"),
        shipped_prefixes=_SHIPPED_PREFIXES,
    )
    assert touches_shipped_path(
        changed_paths=(".claude-plugin/marketplace.json",),
        shipped_prefixes=_SHIPPED_PREFIXES,
    )


def test_touches_shipped_path_misses() -> None:
    """A sibling path, an empty change set, and an empty shipped set all miss."""
    assert not touches_shipped_path(
        changed_paths=("livespec/SPECIFICATION-notes.md", "docs/ci-runner-failover.md"),
        shipped_prefixes=_SHIPPED_PREFIXES,
    )
    assert not touches_shipped_path(changed_paths=(), shipped_prefixes=_SHIPPED_PREFIXES)
    assert not touches_shipped_path(
        changed_paths=("livespec/SPECIFICATION/contracts.md",),
        shipped_prefixes=frozenset(),
    )


def test_is_violation_when_shipped_path_changes_under_a_non_releasing_type() -> None:
    """The defect the guard exists for: `docs:` bytes that ship and no release to carry them."""
    assert is_violation(
        subject="docs(spec): correct the contract",
        body="",
        changed_paths=("livespec/SPECIFICATION/contracts.md",),
        shipped_prefixes=_SHIPPED_PREFIXES,
        releasing_types=_LIVESPEC_RELEASING_TYPES,
        override=False,
    )


def test_is_not_a_violation_when_the_type_releases() -> None:
    """Shipped bytes under a releasing type reach seats at the next release."""
    assert not is_violation(
        subject="fix(spec): correct the contract",
        body="",
        changed_paths=("livespec/SPECIFICATION/contracts.md",),
        shipped_prefixes=_SHIPPED_PREFIXES,
        releasing_types=_LIVESPEC_RELEASING_TYPES,
        override=False,
    )


def test_is_not_a_violation_when_nothing_shipped_changed() -> None:
    """A non-releasing type outside the shipped set strands nothing."""
    assert not is_violation(
        subject="docs: update the runbook",
        body="",
        changed_paths=("docs/ci-runner-failover.md",),
        shipped_prefixes=_SHIPPED_PREFIXES,
        releasing_types=_LIVESPEC_RELEASING_TYPES,
        override=False,
    )


def test_override_forces_no_violation() -> None:
    """An override answers False on the exact input that is otherwise a violation."""
    assert not is_violation(
        subject="docs(spec): correct the contract",
        body="",
        changed_paths=("livespec/SPECIFICATION/contracts.md",),
        shipped_prefixes=_SHIPPED_PREFIXES,
        releasing_types=_LIVESPEC_RELEASING_TYPES,
        override=True,
    )


def test_perf_agrees_with_release_bump_classification() -> None:
    """Two modules in one package must not model `perf`'s release behaviour oppositely."""
    assert (
        release_bump_classification._subject_classification(subject="perf: speed it up")  # noqa: SLF001  — the sibling model under comparison
        == "patch"
    )
    assert commit_releases(
        subject="perf: speed it up",
        body="",
        releasing_types=_LIVESPEC_RELEASING_TYPES,
    )
    assert (
        release_bump_classification._subject_classification(subject="docs: write it down")  # noqa: SLF001  — the sibling model under comparison
        == "none"
    )
    assert not commit_releases(
        subject="docs: write it down",
        body="",
        releasing_types=_LIVESPEC_RELEASING_TYPES,
    )
