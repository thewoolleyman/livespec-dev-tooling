---
topic: a-failing-test-the-run
author: claude-opus-5-5
created_at: 2026-11-02T19:01:48Z
---

## Proposal: Untouched-test retry

### Target specification files

- SPECIFICATION/non-functional-requirements.md

### Summary

Add an 'Untouched-test retry' bullet to §'Testing approach': a failing test the run's change did not touch is re-run on its own up to 3 times, 60 s apart; a touched or undeterminable test fails at once; every retried failure is reported loudly and gets a root-fix work item.

### Motivation

Maintainer rulings on livespec-dev-tooling-6tgd2z, 2026-11-02: 18:38:21Z (verbatim: 'We can't block everything for hours on a single flaky test ... 1. Every flake MUST be immediately assigned to a plan to fix as a priority 2. The flake CAN be retried up to 3 times, with a 1 minute pause between ... NOT a full rerun, just a rerun of the single failing one.') and 18:39:54Z, superseding the 18:38:23Z qualifier (verbatim: 'THE FLAKY RETRY IS NOT FOR ANY TEST. ONLY FOR TESTS THAT THE RUN DID NOT TOUCH.'). Two intermittent shared-gate failures on 2026-11-02 (livespec-dev-tooling-alvhwt, -b2mnrq) each blocked unrelated PRs for hours. Implementation item livespec-dev-tooling-crxcy4 is held at the spec-change tier (unstated under this heading) until this is ratified.

### Proposed Changes

In SPECIFICATION/non-functional-requirements.md §'Testing approach', append this bullet after the '**Import-Linter.**' bullet:

- **Untouched-test retry.** A pytest session of a repository that loads this library's flake-retry plugin MUST re-run a failing test on its own, up to 3 times with 60 seconds between attempts, ONLY when the run's change set touches neither the test nor anything it exercises; the session passes when a re-run passes. The change set is the files changed between `HEAD` and its merge-base with the remote default branch (`HEAD`'s parent when that merge-base is `HEAD`), plus staged and untracked files. A test is touched when the change set contains its test file, a `conftest.py` on its directory chain, a module in its transitive in-repository import closure, or a file whose basename appears as a string literal in that closure. A touched test MUST fail at once with no re-run. A change set touching `pyproject.toml`, `uv.lock`, `justfile`, any `conftest.py` or the plugin itself, a closure module that cannot be parsed, or a change set that cannot be computed MUST disable re-runs for the whole session: undeterminable means touched. A re-run MUST NEVER be a whole-job, whole-suite or factory-run re-run. Every re-run test MUST be reported loudly: a `FLAKE-RETRIED` block in the terminal summary naming the node id, attempts and final outcome, one JSON line per node id under `tmp/flake-retries/`, and in GitHub Actions a `::warning` annotation; and every retried failure MUST be assigned at once to a root-fix work item, one per node id, deduplicated against an open one. The red-green-replay Red leg MUST NEVER re-run a test; the Green and suite-green replay legs accept a summary that reports re-runs and still refuse a suite whose final outcome is a failure.
