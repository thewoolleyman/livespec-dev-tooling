"""livespec-runtime's `github_budget*` modules, vendored under an ISOLATED name.

Upstream these modules live in the `livespec_runtime` package — shared
runtime code consumed by canonical livespec skills, impl-plugin skills,
doctor invariants, hooks, and CI workflows, and NOT enforcement-suite code
(that lives in livespec-dev-tooling, which vendors this subset). Provenance
is recorded in this repo's `.vendor.jsonc`, whose `livespec_runtime` entry
pins the upstream commit these bytes were taken from.

⚠️ WHY THE PACKAGE NAME DIFFERS FROM UPSTREAM'S. The copy is PARTIAL by
design — `github_budget*` and nothing else, per that manifest entry — while
every module in livespec-dev-tooling prepends `_vendor/` to `sys.path`. Held
under the upstream name, that prepend bound `livespec_runtime` to a package
missing `spec_governance`, `cross_repo` and `hygiene_scan`, so a consumer
that imported dev-tooling first lost its own COMPLETE runtime, and one that
imported its runtime first lost the budget client (livespec core PR #2791
paid for both halves; livespec-dev-tooling-r44po2 isolated the name).

So this package occupies `livespec_runtime_budget`, which no distribution
publishes, and the only deviation from the upstream bytes is the mechanical
substitution of that name in each module's own absolute imports — a
re-vendoring is still a byte copy followed by one `s/livespec_runtime\\./
livespec_runtime_budget./` pass. Do NOT restore the upstream name here, and
do NOT run `vendor_update` for the `livespec_runtime` entry: it writes to
`_vendor/<name>`, which puts the shadow back silently.
"""

__all__: list[str] = []
