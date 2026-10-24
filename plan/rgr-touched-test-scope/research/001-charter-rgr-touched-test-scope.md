## The maintainer's statement of what done means

2026-10-24 ~18:5xZ, verbatim: '0. The pre-push should be enabled on all of the livespec repos and any repo for which a CI image already exists that could be used for this. Why is it only on those two repos? 1. Yes we should delegate this work and go ahead and create a plan and work it in a session. Add this to your queue to get done. This is in the theme of moving the load off of the host onto the cluster. Tell me if there's a reason not to do this. 2. Start a subagent to investigate this further. If it's a good idea and won't break anything, then we should do it but just for the live spec ecosystem. 3. Yes if you're only touching a single test file and not any test helper, and not any other configuration or any other code, then you should be able to run only that test. Make a plan to make this change and drive it too. 4. Before you proceed with the above I want you to first explain to me why we needed to modify a test at all for a configuration-only change. This should not be necessary.'

## Definition of Done assertions derived from that statement

- A commit whose staged change touches exactly one test file, and no test helper, fixture, conftest, configuration or other code, runs only that test file in its red-green-replay suite-green leg.
- A commit whose staged change touches a test helper, a fixture, a conftest, any configuration file, any non-test code, or more than one test file runs the full suite in its suite-green leg, as before.
- The suite-green trailer of every commit names which scope ran (the single test file, or the full suite) and why, so the evidence says what it covers.
- After the change is released, a single-test-file commit in livespec-dev-tooling completes its commit hooks in under five minutes on the VPS.

# Charter — rgr-touched-test-scope

## Why

The red-green-replay commit hook's suite-green leg runs the FULL test suite even for a commit that touches one test
file. On 2026-10-24 such a commit sat 21+ minutes in its commit-msg hook on the VPS. The maintainer's rule
(below, item 3) is that a commit touching only a single test file, with no test helper, no configuration and no
other code, runs only that test.

## The rule, exactly

- Touched set = the staged diff's paths.
- Narrow scope applies only when the touched set is exactly one file and that file is a test module (a `test_*.py`
  under the repository's test tree) that is not shared support: not a `conftest.py`, not a fixture or helper module,
  not imported by another test.
- Anything else (helpers, fixtures, conftest, config such as `pyproject.toml` or `.livespec.jsonc`, any product
  code, two or more test files) runs the full suite.
- The pre-push gate still runs the full aggregate (delegated where opted in), so the narrow commit-time scope never
  narrows what reaches master.
- The trailer records the scope, so a reader of the evidence knows what it proves.

## Carrier

livespec-dev-tooling-h3gcs6, re-parented here from the delegated-gate-fleet-rollout plan (livespec-dev-tooling-mvalxq),
which filed it on 2026-10-24.

## Driver

The gitops-fleet-capacity-monitoring coordinator session drives this plan; implementation goes through the factory.

## Derivation note

The assertions were derived by the coordinator session from the maintainer's direction below and created without a
confirmation round under the maintainer's 2026-10-24 direction not to block on prompts; recorded as session-derived
in the first handoff, for objection.
