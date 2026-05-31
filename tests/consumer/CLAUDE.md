# tests/consumer/

The **consumer-tier** check-runner test suite (node-id prefix
`tests.consumer`, declared in `pyproject.toml`'s
`[tool.livespec_dev_tooling].scenario_tiers`). These tests exercise the
package the way a *downstream consumer* does — invoking a shipped check
as `python -m livespec_dev_tooling.checks.<slug>` (or the
`canonical_checks` thin-transport surface) against a synthetic mini
fixture project under `tmp_path` with a deliberately-injected violation,
asserting the expected diagnostic fires and a clean fixture passes.

This tier is distinct from the repo's self-hosting `just check`
aggregate (which couples to the live repo working tree) and from the
unit-tier `tests/livespec_dev_tooling/checks/` suite (which exercises a
single check's internals). Consumer-tier tests assert the
*consumer-observable contract* — the package entrypoint, the check argv
/ exit-code / diagnostic shape, the semver shape, and the
reusable-check-matrix shape — so they are the registered coverage for
the `SPECIFICATION/scenarios.md` acceptance scenarios (per
`SPECIFICATION/constraints.md` §"Heading taxonomy", the integration-tier
requirement for `scenarios.md` headings).

No source-tree mirror exists for this directory; mirror-pairing is
source→test, so these consumer-only tests carry no paired source module.
