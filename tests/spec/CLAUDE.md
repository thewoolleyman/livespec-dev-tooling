# tests/spec/

Unit-tier coverage for `SPECIFICATION/` headings whose subject is this
repository's own SELF-APPLICATION — the gates a change must satisfy, the
wiring the merge gate runs — rather than a single module's behavior or a
consumer-observable surface.

It exists because neither sibling tree fits such a test. `tests/
livespec_dev_tooling/` mirrors `livespec_dev_tooling/` one-to-one, so a
file there is read as the paired test of a module; these tests pair with
no module. `tests/consumer/` asserts the consumer-observable contract of
the shipped package, and a self-application invariant is not one.

Registered in `tests/heading-coverage.json` like any other coverage. The
tier ceiling applies: `SPECIFICATION/scenarios.md` headings require
integration-tier-or-above coverage, so a scenario's test does NOT belong
here — this tree is for `spec.md` / `contracts.md` / `constraints.md` /
`non-functional-requirements.md` headings, which unit-tier coverage may
satisfy.
