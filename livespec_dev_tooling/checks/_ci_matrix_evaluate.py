"""_ci_matrix_evaluate — the finding model + limb verdicts for `ci_matrix_completeness`.

Extracted from `ci_matrix_completeness.py` so the parent check's LLOC stays
under the ceiling — the same LLOC-reduction split as `_ci_matrix_parse` and
`_red_green_replay_modes`. The leading underscore marks this a private
sibling module: entry-point check scripts under
`livespec_dev_tooling/checks/` carry no underscore prefix, so this file is
neither a canonical slug (`canonical_check_slugs` skips `_`-prefixed
modules) nor a mirror-paired module.

The cohesion seam is PURITY. Everything here computes a VERDICT from
already-resolved inputs — the justfile aggregate's targets, the parsed CI
jobs, the canonical and world-gate slug sets, the declared repo-local
skips — and touches no filesystem, no environment, and no logger. The
parent keeps the impure half: resolving those inputs from a repo's
committed files, the severity lever, and every diagnostic. `_ci_matrix_parse`
is the same shape one step earlier (pure parsers, parent owns the
diagnostics), so the check now reads as parse → evaluate → report with the
IO confined to the ends.

That split is also what makes the three limbs testable as a unit: `evaluate`
is a total function of its keyword inputs, so a limb's behavior can be
pinned without a fixture repo on disk.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

# Carried even though this module is only ever reached BY IMPORT today: it
# resolves only because each of its importers happens to carry the preamble,
# which is a property of the callers rather than of this file. The module that
# broke the fan-out was in exactly this state until it became an entry point.
_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from livespec_dev_tooling.checks._ci_matrix_parse import CiJob  # noqa: E402
from livespec_dev_tooling.config import RepoLocalCiSkip  # noqa: E402  — vendor-path-aware.

# Names in `__all__` mark this private sibling's public surface to its single
# importer, `ci_matrix_completeness.py`. `Finding` and `finding` are PUBLIC
# rather than `_`-prefixed because they cross a module boundary: pyright
# strict (`reportPrivateUsage`) and the `private_calls` check both reject
# importing a `_`-prefixed name defined in another module, so a shared model
# has to be a real interface.
__all__: list[str] = [
    "Finding",
    "evaluate",
    "finding",
]

_CI_GREEN_JOB = "ci-green"

_MSG_MISSING_SLUG = "canonical `just check` aggregate slug is wired locally but not run in CI"
_MSG_CI_GREEN_MISSING = (
    "no `ci-green` all-green gate job; branch protection cannot require one stable "
    "context over the whole aggregate"
)
_MSG_NEEDS_INCOMPLETE = (
    "gating job is absent from `ci-green.needs`; requiring only `ci-green` "
    "would not gate merges on it"
)
_MSG_MISSING_REPO_LOCAL = (
    "repo-local `just check` aggregate slug is run by no CI job and is not declared "
    "skip-only in `[tool.livespec_dev_tooling] repo_local_ci_skips`; it gates only at "
    "pre-push, so any path to master that runs no local hook bypasses it"
)
_MSG_STALE_REPO_LOCAL_SKIP = (
    "declared `repo_local_ci_skips` slug is not a member of the `just check` aggregate; "
    "the declaration is stale and excuses nothing"
)


@dataclass(frozen=True, kw_only=True)
class Finding:
    """One structured finding: a failure mode plus its diagnostic fields."""

    failure_mode: str
    message: str
    fields: dict[str, object]


def finding(*, mode: str, message: str, **fields: object) -> Finding:
    return Finding(failure_mode=mode, message=message, fields=dict(fields))


def evaluate(
    *,
    canonical: tuple[str, ...],
    world_gates: frozenset[str],
    justfile_targets: list[str],
    jobs: list[CiJob],
    repo_local_skips: tuple[RepoLocalCiSkip, ...] = (),
) -> list[Finding]:
    """Compute (a) missing-in-CI, (a-repo-local) and (b) ci-green-needs findings.

    `repo_local_skips` defaults to EMPTY because empty is this parameter's
    STRICT end, not its lenient one: nothing is excused and every repo-local
    gap is reported. A caller that forgets it therefore gets the strictest
    reading rather than a blinder one — which is why the default is safe here
    and would not be for a role key whose emptiness widens a scan.

    Assertion (a) excludes WORLD-GATE canonical checks (`world_gates`):
    they verify master/world state (not the PR change), enforce at
    pre-push under the maintainer's admin-scoped `gh` token, and are
    deliberately NOT required to run in per-PR CI (see
    `canonical_checks.world_gate_check_slugs` and
    `livespec/.ai/ci-gate-discipline.md`). They stay canonical and stay
    wired in the `just check` aggregate — only the CI-mirror requirement
    drops them. Assertion (b) is unaffected: it classifies JOBS, not
    slugs.
    """
    canonical_set = set(canonical)
    required = [
        slug for slug in justfile_targets if slug in canonical_set and slug not in world_gates
    ]
    ci_covered: set[str] = set()
    check_bearing: list[str] = []
    ci_green: CiJob | None = None
    for job in jobs:
        if job.name == _CI_GREEN_JOB:
            ci_green = job
            continue
        # Every `check-<slug>` the job runs, CANONICAL OR NOT. (a) stays
        # canonical-scoped through `required`, for which the wider set is
        # equivalent; the repo-local arm needs the non-canonical half of the
        # SAME set, and deriving both from one union is what keeps the two
        # arms from disagreeing about what CI covers.
        ci_covered |= job.contributed_check_slugs
        # (b) is BROADER (o6b): every GATING job — canonical or not — must be
        # fanned into `ci-green.needs`, else a red non-canonical gating job
        # (e2e-cli / acceptance / doctor-static) could merge under a
        # require-only-`ci-green` branch protection.
        if job.gating:
            check_bearing.append(job.name)
    findings = [
        finding(mode="ci-matrix-missing-aggregate-slug", message=_MSG_MISSING_SLUG, slug=slug)
        for slug in required
        if slug not in ci_covered
    ]
    repo_local = _repo_local_findings(
        justfile_targets=justfile_targets,
        canonical_set=canonical_set,
        ci_covered=ci_covered,
        declared=repo_local_skips,
    )
    return (
        findings + repo_local + _ci_green_findings(ci_green=ci_green, check_bearing=check_bearing)
    )


def _repo_local_findings(
    *,
    justfile_targets: list[str],
    canonical_set: set[str],
    ci_covered: set[str],
    declared: tuple[RepoLocalCiSkip, ...],
) -> list[Finding]:
    """Findings for the REPO-LOCAL arm of (a): uncovered gaps + stale declarations.

    The two arms are one mechanism read in both directions. A repo-local
    aggregate slug no CI job runs and no declaration excuses is a GAP; a
    declaration whose slug the aggregate no longer wires is STALE. Reporting
    only the first would let the allowlist decay into a permanent exemption
    list nobody re-reads — the failure mode this whole limb exists to remove,
    reappearing one level up.

    `dict.fromkeys` rather than `set` for the gap walk: it dedupes a slug
    listed twice in the inventory while preserving the aggregate's own order,
    so the findings read in the order an operator sees the targets.
    """
    aggregate = set(justfile_targets)
    declared_slugs = {entry.slug for entry in declared}
    gaps = [
        slug
        for slug in dict.fromkeys(justfile_targets)
        if slug not in canonical_set and slug not in declared_slugs and slug not in ci_covered
    ]
    stale = [
        finding(
            mode="ci-matrix-stale-repo-local-skip",
            message=_MSG_STALE_REPO_LOCAL_SKIP,
            slug=entry.slug,
            reason=entry.reason,
        )
        for entry in declared
        if entry.slug not in aggregate
    ]
    return [
        finding(
            mode="ci-matrix-missing-repo-local-slug", message=_MSG_MISSING_REPO_LOCAL, slug=slug
        )
        for slug in gaps
    ] + stale


def _ci_green_findings(*, ci_green: CiJob | None, check_bearing: list[str]) -> list[Finding]:
    """Findings for assertion (b): `ci-green` presence + `needs:` completeness."""
    if ci_green is None:
        return [
            finding(
                mode="ci-green-job-missing",
                message=_MSG_CI_GREEN_MISSING,
                expected_job=_CI_GREEN_JOB,
                check_bearing_jobs=sorted(check_bearing),
            )
        ]
    return [
        finding(mode="ci-green-needs-incomplete", message=_MSG_NEEDS_INCOMPLETE, job=name)
        for name in sorted(set(check_bearing) - ci_green.needs)
    ]
