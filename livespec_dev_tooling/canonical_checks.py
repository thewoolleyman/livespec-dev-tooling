"""canonical_checks — single source of truth for the canonical check-slug set.

Enumerates which `livespec_dev_tooling.checks.<slug>` modules are
universally wired across the livespec fleet. Discovery is dynamic
(filesystem walk via `pkgutil.iter_modules` over the
`livespec_dev_tooling.checks` package directory) so adding a new
`checks/<name>.py` file automatically extends the canonical set on
next invocation — no second-source-of-truth hardcoded list to drift.

Consumers (downstream in epic li-univck):

- `aggregate_completeness` (Phase 1.3, li-aggchk) — set-membership
  plus ordering comparison against consumer justfiles.
- `livespec/templates/impl-plugin/justfile.jinja` (Phase 2.2,
  li-jnjtpl) — stamping the aggregate at copier-copy time.
- doctor's cross-repo invariant (Phase 2.3, li-dctxr) — fleet-wide
  drift detection.

Exclusions (filtered out before slug-mapping):

- Modules whose name starts with `_` (helper convention; the existing
  `_red_green_replay_modes` helper follows this).
- `__init__.py` (package marker, not a check).

Slug mapping: snake_case module name → kebab-case slug with
`check-` prefix. Examples:

- `keyword_only_args` → `check-keyword-only-args`
- `primary_checkout_commit_refuse_hook_installed`
  → `check-primary-checkout-commit-refuse-hook-installed`

Public API:

- `canonical_check_slugs() -> IOResult[tuple[str, ...],
  ChecksPackageUnreadable]` — the alphabetically-sorted slug tuple
  computed over the live `livespec_dev_tooling.checks` package
  directory, on the railway because the walk IS a filesystem
  boundary (`livespec-dev-tooling-vzwa`). An EMPTY walk is a
  FAILURE, not an empty success: `pkgutil.iter_modules` on a
  missing directory yields nothing rather than raising, and every
  consumer read that empty tuple as "no canonical checks" — a PASS.
- `baseline_check_slugs() -> tuple[str, ...]` — returns the
  alphabetically-sorted tuple of the `baseline` PROFILE slugs: a
  deliberately STATIC, curated SUBSET of the canonical set naming the
  minimal check(s) a repo wires to claim baseline worktree-discipline
  conformance. Unlike the canonical set (filesystem-derived), the
  baseline profile is a hand-maintained registry — a curated product
  decision that is NOT mechanically derivable from the checks directory
  (per the project convention "static enumeration only for typed
  dispatch"). Every entry is asserted to also be a canonical slug.
- `python -m livespec_dev_tooling.canonical_checks --json` — thin-
  transport surface emitting `{"slugs": [...]}` on stdout, exit 0.

Output discipline: this module emits JSON to stdout (thin transport
contract) when invoked via `--json`, and a JSON diagnostic to stderr
when the checks package is unreadable. The file is declared in this
repo's `supervisor_entry_files`, which is what makes both writes
legible rather than `no_write_direct` violations.
"""

from __future__ import annotations

import argparse
import json
import pkgutil
import sys
from dataclasses import dataclass
from pathlib import Path

__all__: list[str] = [
    "baseline_check_slugs",
    "canonical_check_slugs",
    "main",
    "world_gate_check_slugs",
]


_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.io import IOFailure, IOResult, IOSuccess  # noqa: E402  — vendor-path-aware.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware.

_CHECKS_PACKAGE_DIR = Path(__file__).resolve().parent / "checks"
_SLUG_PREFIX = "check-"

# The `baseline` PROFILE: a deliberately STATIC, curated subset of the
# canonical check set. It names the minimal check(s) a repo must wire to
# claim baseline worktree-discipline conformance. Unlike the canonical
# set (filesystem-derived from `checks/<slug>.py`), this is a curated
# product decision that is NOT mechanically derivable from the checks
# directory — so it stays a hand-maintained tuple per the project
# convention "static enumeration only for typed dispatch" (no
# filesystem/import-based profile discovery). Every entry MUST also be a
# real canonical check slug; `baseline_check_slugs()` asserts this
# (an invariant — a baseline slug with no backing check module is a
# registry bug, not an expected runtime condition).
#
# Two baseline concerns, one Verifier each, both shared from this library:
# Worktree-discipline (Conformance-Pattern concern #1,
# `check-primary-checkout-commit-refuse-hook-installed`) and Cross-harness
# plugin-resolution (concern #2, `check-plugin-resolution`).
_BASELINE_CHECK_SLUGS: tuple[str, ...] = (
    "check-plugin-resolution",
    "check-primary-checkout-commit-refuse-hook-installed",
)

# The `world-gate` set: canonical checks that verify the WORLD the change
# lands on (master CI state, master branch-protection config, or ledger-state
# parity read from the beads ledger) rather than the CHANGE in a pull request.
# Per `livespec/.ai/ci-gate-discipline.md` §"verify the CHANGE vs verify the
# WORLD", these gates enforce at PRE-PUSH under the maintainer's admin-scoped
# credentials — where they can actually read master's state or the ledger — and
# are deliberately NOT required to run in per-PR CI. The category is thus not
# only master-CI/branch-protection: any check that reads external world state
# unavailable to the credential-less per-PR CI runner belongs here.
#
# - `check-branch-protection-alignment` — its own docstring states it "is
#   intentionally NOT a required CI matrix entry, which would always-skip
#   and be pointless" (the default Actions token cannot read protection).
# - `check-master-ci-green` — token-less it self-skips; token-gated in
#   per-PR CI it would fail every PR whenever master is red, deadlocking
#   even the master-repair PR (an escape mechanism the ci-gate discipline
#   forbids).
# - `check-plan-thread-epic-parity` — reads the beads LEDGER (an active plan
#   thread must not point at a done/closed epic) under the maintainer's
#   credentials; the credential-less per-PR CI runner cannot read the ledger,
#   so it self-skips there and would always-skip-and-be-pointless as a matrix
#   entry. Its STATIC sibling `check-plan-thread-anchor-declared` needs no
#   ledger and REMAINS a required CI matrix entry.
#
# `check-ci-matrix-completeness` subtracts this set from its "CI must run
# every aggregate slug" requirement (assertion (a)). Like the baseline
# profile, this is a curated PRODUCT decision (which checks verify the
# world), NOT a filesystem derivation — so it stays a hand-maintained
# tuple per "static enumeration only for typed dispatch". These slugs
# REMAIN canonical and REMAIN wired in the `just check` aggregate
# (pre-push enforcement is untouched); only the CI-mirror requirement
# excludes them. Every entry MUST also be a canonical slug;
# `world_gate_check_slugs()` asserts this.
_WORLD_GATE_CHECK_SLUGS: tuple[str, ...] = (
    "check-branch-protection-alignment",
    "check-master-ci-green",
    "check-plan-thread-epic-parity",
)


def _discover_slugs(*, package_path: Path) -> tuple[str, ...]:
    """Discover canonical check slugs from a checks-package directory.

    Walks `package_path` via `pkgutil.iter_modules`, filters out
    underscore-prefixed module names (helpers) and the implicit
    `__init__` entry, then maps each remaining `snake_case` module
    name to its `check-kebab-case` slug. Returns the result as an
    alphabetically-sorted tuple.

    The argument is the package's directory `Path`, not the
    importable name, so tests can point the discovery at a
    synthetic fixture tree without monkeypatching the live
    `livespec_dev_tooling.checks` package.
    """
    discovered: list[str] = []
    for module_info in pkgutil.iter_modules([str(package_path)]):
        name = module_info.name
        if name.startswith("_"):
            continue
        slug = _SLUG_PREFIX + name.replace("_", "-")
        discovered.append(slug)
    return tuple(sorted(discovered))


@dataclass(frozen=True, kw_only=True)
class ChecksPackageUnreadable:
    """The checks package directory yielded NO modules — a failure, not an answer.

    `livespec-dev-tooling-vzwa`. `pkgutil.iter_modules` on a MISSING directory
    yields no entries rather than raising, so the pre-conversion
    `canonical_check_slugs()` returned an EMPTY tuple and every consumer read that
    as "this repo has no canonical checks" — which PASSES. That is the fail-open
    this type removes.

    **ZERO DISCOVERED MODULES IS NEVER A LEGITIMATE ANSWER, and that is why the
    failure track is genuinely inhabited rather than ceremonial.**
    `canonical_checks.py` ships INSIDE the same installed package as `checks/`, so
    `_CHECKS_PACKAGE_DIR` is present whenever this module imported at all. Zero
    modules therefore means the directory is missing, unreadable, or the path is
    wrong — a broken install, not an empty one.
    """

    package_path: Path
    reason: str


def canonical_check_slugs() -> IOResult[tuple[str, ...], ChecksPackageUnreadable]:
    """The alphabetically-sorted canonical check slugs, or why they are unreadable.

    Computed over the live `livespec_dev_tooling.checks` package directory at every
    invocation. Adding a new `checks/<name>.py` file automatically extends the
    returned tuple on the next call; no second source of truth.

    `IOResult` because the walk IS a filesystem boundary — ratified livespec v179
    member 1 clause (c), and the same clause that reached this function
    TRANSITIVELY through `_discover_slugs` while its own body looked total. Its
    body being clean is exactly why a hand reading called it exempt and the
    mechanical fixpoint did not.

    ⛔ AN EMPTY WALK IS A **FAILURE**, NOT AN EMPTY SUCCESS. Returning
    `IOSuccess(())` would move the sentinel instead of removing it: every consumer
    reads an empty slug set as "no canonical checks" and passes. See
    `ChecksPackageUnreadable`.

    ⛔ AND DO NOT "SIMPLIFY" THIS BY HOISTING THE WALK TO A MODULE-LEVEL CONSTANT.
    `_SLUGS = _discover_slugs(...)` at import time would make this function
    MECHANICALLY TOTAL — clauses (c) and (d) analyse function bodies and callees,
    and a module-level assignment is in neither — so the check would go green and
    the result would be STRICTLY WORSE: the I/O moves where the analysis cannot see
    it, the failure becomes implicit again, and an import-time empty walk is more
    invisible than a call-time one. That is the manufactured-confidence shape this
    epic exists to remove.
    """
    discovered = _discover_slugs(package_path=_CHECKS_PACKAGE_DIR)
    if not discovered:
        return IOFailure(
            ChecksPackageUnreadable(
                package_path=_CHECKS_PACKAGE_DIR,
                reason=(
                    "pkgutil.iter_modules yielded no modules; the checks package "
                    "directory is missing or unreadable. It ships inside this "
                    "installed package, so an empty walk is a broken install "
                    "rather than a repo with no checks"
                ),
            )
        )
    return IOSuccess(discovered)


def _validate_baseline_subset(*, baseline: tuple[str, ...], canonical: tuple[str, ...]) -> None:
    """Assert every baseline-profile slug is also a canonical check slug.

    Invariant guard: the baseline profile is a curated SUBSET of the
    canonical check set. A baseline slug with no backing
    `checks/<slug>.py` module is a registry bug (a typo, or a check
    removed without updating the profile), not an expected runtime
    condition — so it trips an `assert` rather than the Result failure
    track.
    """
    for slug in baseline:
        assert slug in canonical, (  # noqa: S101  — invariant guard; `raise` is banned outside io/
            f"baseline check slug {slug!r} has no canonical check module; "
            "every baseline-profile slug MUST also appear in canonical_check_slugs()"
        )


def _validate_world_gate_subset(
    *, world_gates: tuple[str, ...], canonical: tuple[str, ...]
) -> None:
    """Assert every world-gate slug is also a canonical check slug.

    Invariant guard mirroring `_validate_baseline_subset`: the world-gate
    set is a curated SUBSET of the canonical check set. A world-gate slug
    with no backing `checks/<slug>.py` module is a registry bug (a typo,
    or a check renamed/removed without updating the world-gate tuple), not
    an expected runtime condition — so it trips an `assert` rather than
    the Result failure track.
    """
    for slug in world_gates:
        assert slug in canonical, (  # noqa: S101  — invariant guard; `raise` is banned outside io/
            f"world-gate check slug {slug!r} has no canonical check module; "
            "every world-gate slug MUST also appear in canonical_check_slugs()"
        )


def baseline_check_slugs() -> tuple[str, ...]:
    """Return the alphabetically-sorted tuple of baseline-profile check slugs.

    The baseline profile is the curated minimal check set a repo wires
    to claim baseline worktree-discipline conformance — a static,
    hand-maintained registry (`_BASELINE_CHECK_SLUGS`), NOT a
    filesystem-derived set. Returns it sorted alphabetically, after
    asserting every entry is a real canonical check slug.
    """
    baseline = tuple(sorted(_BASELINE_CHECK_SLUGS))
    # `.unwrap()` is FAIL-CLOSED and deliberate: this function is not consumed
    # across any boundary (tests only), so v178 does not make it public and the
    # Result-return rule does not reach it. An unreadable checks package here is a
    # broken install, and raising beats inventing an answer — `#846`'s precedent
    # for an unreachable failure at a call site, where a `match` arm could never be
    # covered under this repo's 100%-per-file gate.
    _validate_baseline_subset(
        baseline=baseline, canonical=unsafe_perform_io(canonical_check_slugs().unwrap())
    )
    return baseline


def world_gate_check_slugs() -> IOResult[tuple[str, ...], ChecksPackageUnreadable]:
    """Return the alphabetically-sorted tuple of world-gate check slugs.

    World-gate checks verify the WORLD the change lands on (master CI
    green, master branch-protection config) rather than the change
    itself, so they enforce at pre-push under the maintainer's
    admin-scoped `gh` token and are excluded from
    `check-ci-matrix-completeness`'s "CI must run every aggregate slug"
    requirement (assertion (a)). A curated static registry
    (`_WORLD_GATE_CHECK_SLUGS`), NOT filesystem-derived; returns it sorted
    alphabetically, after asserting every entry is a real canonical check
    slug. The slugs stay canonical and stay wired in the `just check`
    aggregate — only the CI-mirror requirement excludes them.

    `IOResult` because it CANNOT be total while `canonical_check_slugs` is not:
    v179 clause (d) reaches a caller through its callees as a FIXPOINT, so this
    function is two hops from `pkgutil.iter_modules` and disqualified however clean
    its own body looks. **Converting only the inner function would leave this one
    still reported, so the pair converts together** — a split would measure 2 → 2
    and read as a failed conversion.

    The failure is FORWARDED unchanged rather than re-wrapped: this function adds
    no failure mode of its own, and a second error type for the same condition
    would make a caller distinguish two things that are one thing.
    """
    canonical = canonical_check_slugs()
    if isinstance(canonical, IOFailure):
        return canonical
    world_gates = tuple(sorted(_WORLD_GATE_CHECK_SLUGS))
    _validate_world_gate_subset(
        world_gates=world_gates, canonical=unsafe_perform_io(canonical.unwrap())
    )
    return IOSuccess(world_gates)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="canonical-checks",
        description=(
            "Emit the canonical-check slug set as JSON on stdout. "
            "Thin-transport surface consumed by aggregate-completeness, "
            "the impl-plugin justfile.jinja template, and doctor's "
            "cross-repo invariant (epic li-univck Phases 1.3 / 2.2 / 2.3)."
        ),
    )
    _ = parser.add_argument(
        "--json",
        action="store_true",
        help=(
            'Emit `{"slugs": [...]}` to stdout. Required flag; '
            "reserved for a future plain-text mode if a consumer "
            "needs one. Today JSON is the only supported output."
        ),
    )
    return parser


def main() -> int:
    parser = _build_parser()
    # Parse args for argparse-driven `--help` handling and to reserve
    # the `--json` flag namespace; the parsed value is not consulted
    # because JSON is currently the only supported emission mode.
    _ = parser.parse_args()
    canonical = canonical_check_slugs()
    if isinstance(canonical, IOFailure):
        # The module docstring used to say no diagnostic surface existed because
        # "successful discovery is the only path". That is no longer true: the
        # failure track is what `livespec-dev-tooling-vzwa` added, and emitting
        # NOTHING here would hand a consumer an exit code with no reason. This file
        # is declared in `supervisor_entry_files`, which is what makes a direct
        # stderr write legible rather than a `no_write_direct` violation.
        unreadable = unsafe_perform_io(canonical.failure())
        _ = sys.stderr.write(
            json.dumps(
                {
                    "check_id": "canonical-checks-package-unreadable",
                    "package_path": str(unreadable.package_path),
                    "reason": unreadable.reason,
                }
            )
            + "\n"
        )
        return 1
    payload = {"slugs": list(unsafe_perform_io(canonical.unwrap()))}
    _ = sys.stdout.write(json.dumps(payload) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
