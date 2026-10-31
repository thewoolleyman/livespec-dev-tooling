# 001 — Two more children: green-token staleness and gate monitoring (2026-10-13)

Its second independent completeness review (evidence id k3s-on-gmktec-completeness-2026-10-13b, 2026-10-13T07:58:26Z) of the archived livespec plan k3s-on-gmktec-for-vps-usage (epic livespec-sab5gn) found two delegated-gate obligations that plan left without a home; both are now children of this plan.

- livespec-dev-tooling-aape (P1, filed by the archived plan): the green token, the marker that lets a push skip the full check, memoizes checks that are not pure functions of the tree and never expires, so a passing token can assert a verdict that is no longer true. The archived plan's own handoffs called it "a de facto precondition" for the delegated gate to mean anything. Rolling the gate out to more repositories multiplies its reach, so it belongs here.
- livespec-dev-tooling-cmgqnz: the delegated gate has no monitoring signal. The archived plan's R4.R7 required monitoring to ride along with R4's topology changes and a no-verdict refusal to be distinguishable from a red tree; only the push log tells them apart today, and the deferred "first gate trigger" had nowhere to go.
