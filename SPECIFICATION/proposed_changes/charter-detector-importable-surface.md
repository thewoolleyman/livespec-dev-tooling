---
topic: charter-detector-importable-surface
author: claude-opus-5
created_at: 2026-08-04T10:30:38Z
---

## Proposal: Declare an importable charter-detector surface outside the check inventory

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Declare a second semver-stable surface for this library: an importable
charter-defect detector API at `livespec_dev_tooling.charters`, deliberately
NOT a module under `livespec_dev_tooling/checks/`, so that consumer repos can
gate their own supervisor charters from a single maintained source without
being conscripted into a new canonical `just check` slug.

### Motivation

**The gate exists in one repo of six and nothing prevents regression.** A fleet
sweep on 2026-08-03 took supervisor-charter defects from 119 to 0 across all six
repos. That result is a snapshot, not a ratchet: `find` for
`test_charters_carry_no_known_defects.py` across the fleet returns exactly one
copy, in `livespec-overseer`, whose `_REPO_ROOT` is its own tree. Re-measured
2026-08-04 by importing that module's own twelve detectors and three globs and
applying them to every fleet repo: 40 charters, 0 defects, every charter clean
against its repo's default branch — but 27 of those 40 are gated by nothing.
Regression in five repos would be silent, which is precisely how the population
reached 119 in the first place.

**The obvious delivery mechanism is unavailable, and the reason is mechanical
rather than stylistic.** `canonical_check_slugs()` computes the canonical slug
tuple by walking the live `livespec_dev_tooling/checks/` package directory at
every invocation — its docstring states the property directly: "Adding a new
`checks/<name>.py` file automatically extends the returned tuple on the next
call; no second source of truth."
`livespec/SPECIFICATION/contracts.md` then requires every consumer to run each
shared check in its `just check` aggregate AND its CI matrix, with a
`wiring-completeness-cross-repo` check as an adversarial-drift backstop. So
shipping the detectors as `checks/charter_defects.py` would oblige six
repositories to wire a new canonical slug and a new CI matrix entry — including
one repository (`homelab`) that has no `justfile`, no `pyproject.toml` and no
Python surface at all, and therefore cannot satisfy the obligation by any
means.

**The author of the existing gate rejected the slug form for this exact
reason**, and recorded it in the module's own docstring: "It is a pytest module
rather than a new `just check-<slug>` deliberately —
`check-aggregate-completeness` means wiring one canonical slug forces wiring
every other, and `tests/prompts/` is already an enforced surface." That
reasoning was re-examined on 2026-08-04 against the current code rather than
inherited, and it holds.

**Nothing in the declared surface permits the alternative.** §"CLI surface"
states that the `python -m` invocation form IS the semver-stable contract and
that "consumers MUST NOT call internal helper modules directly", and §"Semver
discipline" enumerates five surface elements, none of which is an importable
Python API. A consumer importing detector functions today would be reaching
into an internal helper, with no stability guarantee and in tension with an
explicit MUST NOT. The capability is wanted, so the contract should say so
rather than leave adopters to violate it quietly.

**The relocation is small and already demonstrated.** The 2026-08-04 re-measure
imported the detectors and scored six foreign repository trees with only a
repo-root substitution, so what this proposal enables is a relocation plus
parameterization, not a rewrite.

### Proposed Changes

Amend §"Semver discipline" to add a sixth element to the canonical enumeration
of the library's semver-stable surface: the importable charter-defect detector
API exposed by the `livespec_dev_tooling.charters` module — its exported
detector registry, its charter-path glob set, and the signature and return
shape of its per-document scoring entry point. The enumeration is canonical, so
the surface MUST be listed there and not only described elsewhere.

Amend §"CLI surface" so that its "consumers MUST NOT call internal helper
modules directly" prohibition is scoped explicitly to modules that the
semver-stable enumeration does not name. A module named in §"Semver discipline"
is a declared surface and consumers MAY import it; every other module remains an
internal helper and the prohibition is unchanged for it.

Amend §"Shared check inventory" to record the boundary and the reason for it:
the charter-detector module MUST NOT live under `livespec_dev_tooling/checks/`,
because membership of that directory is what
`livespec_dev_tooling.canonical_checks.canonical_check_slugs` walks to compute
canonical membership, and canonical membership obliges every consumer to wire a
`just check` slug and a CI matrix entry. Placing the detectors outside `checks/`
is therefore load-bearing rather than a filing preference, and the specification
should state it so that a later change does not silently relocate the module and
conscript the fleet.

State the bump rules for the new surface consistently with the existing ones:
adding a detector to the registry, or adding a glob to the charter-path set, is
MINOR; removing or renaming a detector, changing the scoring entry point's
signature or return shape, or narrowing the glob set is MAJOR; a pure
implementation change that preserves every detector's verdict on the same input
is PATCH.

The specification MUST NOT require any consumer to adopt the gate. The
importable surface makes per-repo adoption possible from one maintained source;
whether a given repository gates its charters remains that repository's
decision, which is what keeps this distinct from the canonical-check obligation
it deliberately avoids.

### Provenance

Filed by the groom of `livespec-overseer:overseer-x1q` ("Charter gate enforces
in ONE repo of six — the 119->0 sweep is a snapshot, not a ratchet"), now closed
regroomed-out into eight factory slices across five repositories. This is the
one human-gated slice of that cut. The factory slice that implements the module
is `livespec-dev-tooling-lwzbh5`, whose acceptance requires a test asserting
that `canonical_check_slugs()` returns an identical tuple before and after the
change — so the boundary this proposal describes is guarded mechanically rather
than by comment.
