"""Shared branch-protection payload fixtures for the fleet test suite.

The "aligned" master branch-protection payload (the green path that
`assert_branch_protection` accepts) is used by several fleet test
modules — `test_fleet_conformance.py` and `test_wire_fleet_member.py`
both build a green `FleetContext` around it. Centralizing the payload
in this one non-`test_*` helper means a change to what "aligned" means
(e.g. the strict-off merge-gate flip) is a ONE-LINE edit here, and no
behavior-Red commit needs to touch those two test modules.

The leading-underscore filename marks this as a private test-helper
module (not a `test_*.py` pytest module and not a paired-source
mirror): the mirror-pairing invariant pairs SOURCE files to test
files, never the reverse, so a helper module that lives only under
`tests/` carries no pairing obligation.
"""

from __future__ import annotations

from livespec_dev_tooling.fleet._rows_github import REQUIRED_MERGE_SETTINGS

__all__: list[str] = [
    "ALIGNED_PROTECTION_STRICT",
    "aligned_merge_settings_payload",
    "aligned_protection_payload",
]


# The `strict` flag the aligned (green-path) branch-protection payload
# carries. Per livespec NFR §"CI as a merge gate (branch protection)",
# strict (require-branches-up-to-date) MUST be OFF, so the aligned
# payload carries strict-off — the state `assert_branch_protection`
# now accepts.
ALIGNED_PROTECTION_STRICT: bool = False


def aligned_protection_payload(*, contexts: list[str] | None = None) -> dict[str, object]:
    """Return the aligned master branch-protection payload.

    `enforce_admins` enabled, `required_status_checks` carrying the
    shared `ALIGNED_PROTECTION_STRICT` flag and the given required-check
    `contexts` (default a single `check-a`, matching the fleet fixtures'
    one-job ci.yml matrix).
    """
    return {
        "enforce_admins": {"enabled": True},
        "required_status_checks": {
            "strict": ALIGNED_PROTECTION_STRICT,
            "contexts": contexts if contexts is not None else ["check-a"],
        },
    }


def aligned_merge_settings_payload() -> dict[str, object]:
    """Return the aligned (green-path) repo-object merge-settings payload.

    The rebase-only-plus-auto-merge state `assert_merge_settings`
    accepts, shared by the `test_fleet_conformance.py` and
    `test_wire_fleet_member.py` green tables so a change to what the
    fleet mandates is a one-line edit at `REQUIRED_MERGE_SETTINGS`.
    """
    return dict(REQUIRED_MERGE_SETTINGS)
