"""Tests for the rebase-merge commit-metadata invariance detector.

The property under test is work-item livespec-dev-tooling-yfqvqm's first
assertion: for every check in the shared check inventory, a commit and its
rebase-merge replay that differ ONLY in SHA, committer date and committer
timezone receive the same verdict.

Two tests carry that assertion over the real tree and the rest pin the
detector's own behaviour:

- `test_every_shared_check_in_the_inventory_is_inside_the_scanned_universe`
  establishes COVERAGE — every canonical check module and every workflow-check
  module is inside the file set the detector scans, so a clean scan is a
  statement about the whole inventory rather than about whichever files the
  scan happened to reach.
- `test_the_shipped_library_carries_no_banned_or_unproven_metadata_read`
  establishes the VERDICT — no module in that set reads a rebase-merge-variant
  commit field without a recorded invariance proof.

The detector is imported through `importlib` behind a `Protocol`, the pattern
`tests/livespec_dev_tooling/charters/test_charters.py` established: the first
assertion of `_invariance_module` is a genuine `is_file()` check on the
module's expected path, so the Red leg of this change failed on an assertion
rather than at collection.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Protocol, cast

from returns.unsafe import unsafe_perform_io

from livespec_dev_tooling.canonical_checks import canonical_check_slugs

PACKAGE_ROOT = Path("livespec_dev_tooling")
MODULE_NAME = "commit_metadata_invariance"


class MetadataRead(Protocol):
    """One rebase-merge-variant commit-metadata read found in a source file."""

    @property
    def path(self) -> Path: ...

    @property
    def line(self) -> int: ...

    @property
    def specifier(self) -> str: ...


class MetadataProof(Protocol):
    """A registered invariance proof for one (module, specifier) pair."""

    @property
    def module(self) -> str: ...

    @property
    def specifier(self) -> str: ...

    @property
    def reason(self) -> str: ...


class MetadataFindings(Protocol):
    """The three ways the invariance rule can be violated."""

    @property
    def banned(self) -> tuple[MetadataRead, ...]: ...

    @property
    def unproven(self) -> tuple[MetadataRead, ...]: ...

    @property
    def stale_proofs(self) -> tuple[MetadataProof, ...]: ...


class InvarianceModule(Protocol):
    """The detector surface this test exercises."""

    INVARIANCE_PROOFS: tuple[MetadataProof, ...]
    TIMEZONE_DEPENDENT_COMMITTER_SPECIFIERS: tuple[str, ...]

    def commit_metadata_reads(self, *, source: str, path: Path) -> tuple[MetadataRead, ...]: ...

    def invariance_findings(self, *, package_root: Path) -> MetadataFindings: ...

    def shipped_library_sources(self, *, package_root: Path) -> tuple[Path, ...]: ...


def _invariance_module() -> InvarianceModule:
    module_path = PACKAGE_ROOT / f"{MODULE_NAME}.py"
    assert module_path.is_file(), f"{module_path} does not exist"
    return cast("InvarianceModule", importlib.import_module(f"livespec_dev_tooling.{MODULE_NAME}"))


def _specifiers(*, source: str) -> list[str]:
    reads = _invariance_module().commit_metadata_reads(source=source, path=Path("probe.py"))
    return [read.specifier for read in reads]


def _proofs_by_module() -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for proof in _invariance_module().INVARIANCE_PROOFS:
        grouped.setdefault(proof.module, []).append(proof.specifier)
    return grouped


def test_the_detector_stays_outside_the_checks_package() -> None:
    """The detector is NOT a canonical slug, and the placement is load-bearing.

    A module under `checks/` becomes a canonical check slug, and a canonical
    slug obliges EVERY consumer to wire it into `just check` AND its CI matrix,
    the obligation this repository's `SPECIFICATION/contracts.md` records where
    it partitions the shared check inventory. That inventory ships from this
    repository alone, so this repository's own test
    suite is the enforcement point — the same reasoning that keeps
    `charters/` out of `checks/`.
    """
    assert (PACKAGE_ROOT / "checks" / f"{MODULE_NAME}.py").exists() is False
    assert (PACKAGE_ROOT / f"{MODULE_NAME}.py").is_file()


def test_a_timezone_dependent_committer_date_read_is_banned() -> None:
    """`%cs` is the spelling that reddened master on 2026-10-14."""
    assert _specifiers(source='ARGS = ["log", "-1", "--format=%cs"]\n') == ["%cs"]


def test_a_specifier_split_from_its_introducer_in_one_vector_is_read() -> None:
    """A format argument split across two list elements is still a read."""
    assert _specifiers(source='ARGS = ["log", "--format", "%cd"]\n') == ["%cd"]


def test_a_tuple_argument_vector_is_read() -> None:
    """A tuple argv is as much a vector as a list one; both spellings ship."""
    assert _specifiers(source='ARGS = ("git", "show", "-s", "--format=%cD")\n') == ["%cD"]


def test_a_call_argument_vector_is_read() -> None:
    """Positional and keyword call arguments are an argument vector too."""
    assert _specifiers(source='run("git", "log", "--pretty", "%ci")\n') == ["%ci"]
    assert _specifiers(source='run(args="--format", fmt="%cr")\n') == ["%cr"]


def test_a_docstring_or_comment_discussing_the_spelling_is_not_a_read() -> None:
    """Prose naming the defect is the DESIGN RECORD, never a read.

    `heading_coverage_debt.py` documents the `%cs` defect it was repaired of,
    at length and on purpose. A text-level matcher would convict that prose and
    the only way to go green would be to delete the rationale, so the detector
    reads the AST and skips docstrings; comments never reach the AST at all.
    """
    assert _specifiers(source='"""Until 2026-10-14 this read `git log --format=%cs`."""\n') == []
    assert _specifiers(source="# never: git log --format=%cs\nARGS = []\n") == []


def test_a_nested_docstring_is_skipped_too() -> None:
    """A class or function docstring is prose for the same reason a module's is."""
    source = 'class C:\n    """Reads `git log --format=%cs`."""\n\n    def m(self):\n        """And `--format=%ci`."""\n'
    assert _specifiers(source=source) == []


def test_a_strftime_pattern_naming_the_hour_is_not_a_sha_read() -> None:
    """`%H` means the hour in `strftime` and the commit SHA in git.

    Three live call sites stamp `"%Y-%m-%dT%H:%M:%SZ"`. Requiring a git format
    INTRODUCER in the same argument vector is what tells the two apart; a bare
    specifier scan would convict all three.
    """
    assert _specifiers(source='STAMP = "%Y-%m-%dT%H:%M:%SZ"\n') == []


def test_an_invariant_format_is_not_a_read() -> None:
    """A vector that announces a format but names no variant field is clean.

    `--format=%B` (the raw commit message) is the single most common git read in
    this library, and rebase-merge preserves the message verbatim.
    """
    assert _specifiers(source='ARGS = ["log", "-1", "--format=%B"]\n') == []
    assert _specifiers(source='ARGS = ["for-each-ref", "--format=%(refname:short)"]\n') == []


def test_a_format_resolved_through_a_module_constant_is_read() -> None:
    """A specifier reached through a module-level constant is still a read."""
    assert _specifiers(source='_FMT = "%ct"\nARGS = ["log", f"--format={_FMT}"]\n') == ["%ct"]
    assert _specifiers(source='_FMT = "--format=%h"\nARGS = ["log", _FMT]\n') == ["%h"]


def test_an_unresolvable_vector_element_is_skipped_rather_than_guessed() -> None:
    """What the scan cannot render it declines to read — the documented scope limit."""
    assert _specifiers(source='ARGS = ["log", "--format", _UNKNOWN]\n') == []
    assert _specifiers(source='ARGS = ["log", "--format", build()]\n') == []
    assert _specifiers(source='ARGS = ["log", "--format", 7]\n') == []


def test_a_vector_read_reports_every_variant_field_it_names() -> None:
    """One format string, two variant fields, two reads — the live shape."""
    assert _specifiers(source='ARGS = ["log", "--format=%H %cI"]\n') == ["%H", "%cI"]


def test_the_banned_specifiers_are_never_registrable() -> None:
    """No proof may sanction a read in the commit's OWN timezone.

    The committer timezone carries no verdict-bearing information: one instant
    renders as two different calendar dates depending on the offset the
    committer's clock was set to. There is no invariance argument to record, so
    the registry MUST NOT name one of these specifiers.
    """
    module = _invariance_module()
    registered = {proof.specifier for proof in module.INVARIANCE_PROOFS}
    assert registered.isdisjoint(set(module.TIMEZONE_DEPENDENT_COMMITTER_SPECIFIERS))


def test_every_proof_records_a_reason() -> None:
    """A registry entry with no argument in it is an exemption wearing a proof's name."""
    for proof in _invariance_module().INVARIANCE_PROOFS:
        assert len(proof.reason.strip()) > 40, proof.module


def test_an_unregistered_absolute_committer_instant_is_unproven(tmp_path: Path) -> None:
    """`%cI` is one instant on one basis — and a replay re-stamps it anyway."""
    (tmp_path / "rogue.py").write_text('ARGS = ["log", "--format=%cI"]\n', encoding="utf-8")
    findings = _invariance_module().invariance_findings(package_root=tmp_path)
    assert [read.specifier for read in findings.unproven] == ["%cI"]
    assert findings.banned == ()


def test_a_banned_read_is_reported_as_banned_not_unproven(tmp_path: Path) -> None:
    """The two channels are distinct because their remedies are."""
    (tmp_path / "rogue.py").write_text('ARGS = ["log", "--format=%cs"]\n', encoding="utf-8")
    findings = _invariance_module().invariance_findings(package_root=tmp_path)
    assert [read.specifier for read in findings.banned] == ["%cs"]
    assert findings.unproven == ()


def test_a_proof_whose_read_no_longer_exists_is_stale(tmp_path: Path) -> None:
    """A registry that outlives its reads stops being evidence of anything."""
    findings = _invariance_module().invariance_findings(package_root=tmp_path)
    assert findings.stale_proofs == _invariance_module().INVARIANCE_PROOFS


def test_a_registered_read_is_neither_banned_nor_unproven(tmp_path: Path) -> None:
    """The registered reads of the real tree, replayed under a throwaway root.

    One file per registered MODULE carrying all of that module's registered
    specifiers — which is how the live tree holds them: `%H` and `%cI` reach git
    in a single `--format=%H %cI` argument.
    """
    module = _invariance_module()
    for name, specifiers in _proofs_by_module().items():
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        fmt = " ".join(specifiers)
        target.write_text(f'ARGS = ["log", "--format={fmt}"]\n', encoding="utf-8")
    findings = module.invariance_findings(package_root=tmp_path)
    assert findings.banned == ()
    assert findings.unproven == ()
    assert findings.stale_proofs == ()


def test_every_shared_check_in_the_inventory_is_inside_the_scanned_universe() -> None:
    """COVERAGE: the scan reaches every check the inventory names.

    The scan universe is the whole shipped library rather than the check
    modules alone, because a check's verdict is computed by whatever it
    delegates to — `heading_coverage_debt_register` reads its git evidence
    through `_heading_coverage_first_seen` and `heading_coverage_debt`, neither
    of which is a slug. A superset is the only sound universe, and this test is
    what proves it IS a superset.
    """
    sources = set(_invariance_module().shipped_library_sources(package_root=PACKAGE_ROOT))
    inventory = [
        PACKAGE_ROOT / "checks" / f"{slug.removeprefix('check-').replace('-', '_')}.py"
        for slug in unsafe_perform_io(canonical_check_slugs().unwrap())
    ]
    inventory.extend(
        path
        for path in sorted((PACKAGE_ROOT / "workflow_checks").glob("*.py"))
        if not path.name.startswith("_")
    )
    assert inventory
    assert [path for path in inventory if path not in sources] == []


def test_the_shipped_library_carries_no_banned_or_unproven_metadata_read() -> None:
    """VERDICT: the invariance assertion itself, over the real tree.

    Every rebase-merge-variant commit-metadata read in the shipped library is
    either absent or registered with a recorded reason it cannot move a
    verdict. With the coverage test above, that is assertion 1 of
    livespec-dev-tooling-yfqvqm.
    """
    findings = _invariance_module().invariance_findings(package_root=PACKAGE_ROOT)
    assert [(read.path, read.line, read.specifier) for read in findings.banned] == []
    assert [(read.path, read.line, read.specifier) for read in findings.unproven] == []
    assert [proof.module for proof in findings.stale_proofs] == []
