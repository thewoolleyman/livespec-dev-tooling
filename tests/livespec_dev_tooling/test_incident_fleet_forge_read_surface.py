"""The forge-read Action's files belong to every incident surface whose workflow uses it.

`SPECIFICATION/contracts.md`, in its expedited incident execution rules
(proposal one-unretried-github-api-answer), makes the composite Action
`forge-read` part of every published surface whose workflows use it, so the
fleet audit counts its files among the files of every surface row whose files
include `.github/workflows/ci.yml` (livespec-dev-tooling-levu6j) or
`.github/workflows/incident-label-ci.yml` (livespec-dev-tooling-pwabtl). The
`uses:` reference reaches at most the Action's `action.yml`; the command it puts
on the job's path is not reached from any text, so the rows name both files.
"""

from __future__ import annotations

from livespec_dev_tooling._incident_fleet_surface_files import SURFACE_ROOTS

__all__: list[str] = []

_CI = ".github/workflows/ci.yml"
_LABEL_CI = ".github/workflows/incident-label-ci.yml"
_FORGE_READ = (
    ".github/actions/forge-read/action.yml",
    ".github/actions/forge-read/livespec-forge-read",
)


def test_every_surface_row_served_from_ci_yml_counts_the_forge_read_files() -> None:
    rows = {surface: roots for surface, roots in SURFACE_ROOTS.items() if _CI in roots}
    facts = (
        sorted(rows) == ["CI dependency/aggregate/merge context", "CI matrix/batch/direct action"],
        all(path in roots for roots in rows.values() for path in _FORGE_READ),
    )
    assert facts == (True, True)


def test_every_surface_row_served_from_the_incident_label_workflow_counts_the_forge_read_files() -> (
    None
):
    rows = {surface: roots for surface, roots in SURFACE_ROOTS.items() if _LABEL_CI in roots}
    facts = (
        sorted(rows) == ["PR mode transport"],
        all(path in roots for roots in rows.values() for path in _FORGE_READ),
    )
    assert facts == (True, True)
