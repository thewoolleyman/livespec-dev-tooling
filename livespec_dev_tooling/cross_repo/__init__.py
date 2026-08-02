"""Cross-repo coordination support modules.

Per `SPECIFICATION/contracts.md` section "Cross-repo coordination automation
surface", this package hosts the support utilities consumed by the
reusable workflows under `.github/workflows/reusable-release-dispatch.
yml`, `.github/workflows/reusable-bump-pin-from-dispatch.yml`, and
`.github/workflows/reusable-pin-freshness.yml`.

The Python surface is intentionally minimal: the workflow YAML carries
the network-touching logic (gh CLI invocations, repository_dispatch
posts, PR creation), and the modules in this package supply the pure
filesystem-walk primitives those workflows shell out to.

Unlike the `livespec_dev_tooling/checks/` package — which is
constrained to be network-I/O-free per `constraints.md` section "No network
I/O" — modules here are STILL network-I/O-free; the workflows that
consume them are where any network I/O lives.
"""

__all__: list[str] = []
