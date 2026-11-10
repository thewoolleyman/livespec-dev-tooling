---
topic: range-gate-collects-recorded-test
author: claude-opus-5-5
created_at: 2026-11-10T02:45:45Z
---

## Proposal: The commit-range validation collects a Red+Green commit's recorded test on that commit's own tree

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Make the commit-range validation of check-red-green-replay collect each in-scope Red+Green commit's recorded test module on that commit's own tree. In scope are commits that touch product impl .py and carry the pair shape, after the existing shape checks and exemptions. Collection executes no test and uses the head environment's interpreter, with the commit's tree as the working directory, rootdir and first PYTHONPATH entry. The validation fails, under a distinct check_id naming each commit, module and first error, when collection errors, collects nothing, or the recorded trailer is missing or points outside the test tree. It reconciles the adjacent 'judged exactly as before' sentence, adds one new scenario, and is spec-first and owned by livespec-dev-tooling-5be65c.

### Motivation

Measured 2026-11-10 by expedited-incident-response-flag, and re-measured by the dev-host-test-gate-load seat, which owns the replay gate:

- livespec-dev-tooling#3913, head b9e21ef8. Commits 31d49d7a and 42f3537a carry TDD-Red-* and TDD-Green-* trailers naming tests/livespec_dev_tooling/test_incident_strict_json.py. On each commit's own tree, that module imports `decode_historical_reply`, which master's 5bdc3b9b (an ancestor after the replay) removed. Running `pytest --collect-only` on 31d49d7a's tree gives "ImportError: cannot import name 'decode_historical_reply'" and "no tests collected, 1 error" (reproduced 02:4xZ in a detached worktree).
- CI run 42738231037's check-red-green-replay job PASSED that range in about 2 s. `_validate_range` -> `_commit_violates` checks only that the trailer keys appear as substrings of the message.
- The recorded test-file checksums MATCHED the bytes on both trees, because the test file was unchanged and the tree around it changed. So checksum verification alone would not catch this case.

Design chosen by measured cost on this repository:
- Collect-only with the range head's venv and the commit's tree first on PYTHONPATH: 1.6 s for the worktree plus 2.0-4.3 s for collection, per Red+Green commit.
- Re-running a sample recorded module took 16.4 s, about 4x, and re-proves what the commit-msg Green leg and the head's full suite already establish.
- Collection with a fresh per-worktree `uv run` took 12.2 s, most of it environment setup, so reusing the head environment is the cheap form.

The range gate's own docstring calls it "the load-bearing branch-level gate behind the per-commit commit-msg hook (which a rebase, a squash, or a history rewrite can bypass)". Today it cannot detect a rewrite that keeps the trailers while changing the tree around the test. Fleet scope: every repository that consumes the worktree pack's range gate gets this through its livespec-dev-tooling pin.

### Proposed Changes

**1. contracts.md §"Suite-green replay leg", **Behaviour-preserving claim** bullet.** Replace its sentence "A commit carrying both `TDD-Red-*` and `TDD-Green-*` trailers MUST be judged exactly as before this bullet." with:

> A commit carrying both `TDD-Red-*` and `TDD-Green-*` trailers is judged by the trailer-shape rules unchanged by this bullet, and additionally by the **Range validation collects a Red+Green commit's recorded test** bullet.

**2. contracts.md §"Suite-green replay leg".** Immediately after the **Behaviour-preserving claim** bullet, add this bullet:

> - **Range validation collects a Red+Green commit's recorded test.**
>   - *Scope.* The commit-range validation of `check-red-green-replay` (the no-argument path, which judges every non-merge commit in `origin/master..HEAD`) applies this rule to each commit that meets all three conditions: it touches product impl `.py`, it carries the pair shape (both a `TDD-Red-Test-File-Checksum` and a `TDD-Green-Verified-At` trailer), and it passes the existing trailer-shape checks. A commit that fails a trailer-shape check is reported as before, without collection. A commit the range validation already exempts is not collected. Those are a forge-authored revert verified under the server-side revert exemption, and an expedited commit the incident chain records. This rule adds no other exemption: no lever, flag or subject prefix MAY exempt a collection failure.
>   - *Recorded module.* The commit's `TDD-Red-Test` trailer value is a repository-relative path, optionally followed by `::` and a node id, which is dropped. A pair-shaped commit in scope MUST fail the range when it has no `TDD-Red-Test` trailer. It MUST also fail when the path is not a `.py` file under the consumer's `tests_tree_prefix` or a `mirror_pairings` `test_tree`, or does not exist in the commit's tree.
>   - *Collection.* The validation MUST run pytest collection of that module against the commit's tree, executing no test, without modifying the caller's working tree or index. It does so with the interpreter running `check-red-green-replay` (the range head's project environment), the working directory and `--rootdir` set to the commit's tree, and that tree prepended to `PYTHONPATH`. That way the commit's own first-party packages, `conftest.py` files and pytest configuration are the ones in effect, not the installed or editable copy. The validation MUST fail the range when that collection reports an error or collects no test. It MUST also fail when a dependency that the commit's test needs is absent from the head's environment. Each collection is bounded by the stall window of the **Progress bound** bullet, with that bullet's default and `LIVESPEC_SUITE_GREEN_STALL_SECONDS` override, and a collection ended by it fails the range.
>   - *Finding.* A collection failure MUST carry a `check_id` distinct from the missing-trailers failure. It MUST list each failing commit with its sha, the module, and the first collection error line. The remedy it names is to rewrite the range so that every in-scope commit's recorded module collects.
>   - *No re-run.* The validation MUST NOT re-run the recorded test, because the commit-msg Green leg ran it and the range head's full suite covers the final tree.
>   - *Fleet scope.* Every consumer whose CI runs the shared `red_green_replay` check.
>   - *Spec-first.* The shipped range path checks only that the trailer keys are present. Work item livespec-dev-tooling-5be65c owns the change.

**3. scenarios.md.** Immediately after the scenario `## Scenario: a suite-green leg reuses a passing full pre-commit aggregate on the same tree`, add:

```
## Scenario: the commit-range validation fails a Red+Green commit whose recorded test cannot be collected on its own tree

Given a branch whose range from origin/master holds a commit that touches product impl .py and carries the TDD-Red-Test-File-Checksum and TDD-Green-Verified-At trailers

And the test module named by that commit's TDD-Red-Test trailer fails pytest collection on that commit's own tree with an ImportError

When check-red-green-replay validates the range

Then the check MUST fail with a finding whose check_id differs from the missing-trailers finding

And the finding MUST name that commit's sha, that test module and the first collection error line

And a recorded test module that collects no test on its commit's tree MUST fail the check the same way

And a range in which every such commit's recorded test module collects at least one test with no error MUST pass this check
```

The new H2 scenario heading MUST be registered in `tests/heading-coverage.json` in the revise commit that accepts this proposal. It is a `"test": "TODO"` row whose `reason` names the integration tier and work item livespec-dev-tooling-5be65c, and it carries `"work_item": "livespec-dev-tooling-5be65c"`. Run `just generate-heading-coverage-debt-register` and stage `tests/heading-coverage-debt.json`. No contracts.md H2 heading changes.
