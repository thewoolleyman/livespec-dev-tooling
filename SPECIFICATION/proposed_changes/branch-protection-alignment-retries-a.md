---
topic: branch-protection-alignment-retries-a
author: claude-opus-5-5
created_at: 2026-11-13T06:32:13Z
---

## Proposal: branch_protection_alignment retries a transient ruleset read and refuses only on a stable unreadable answer

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Give the two ruleset reads of the `branch_protection_alignment` check (the rules read of the default branch and each contributing ruleset's read) a bounded retry with growing backoff, and make `ruleset_unreadable` the verdict only when every attempt in that budget fails. Today the clause reads literally as failing on a single failed read, so one transient forge answer refuses a gate whose configuration is correct.

### Motivation

Work item livespec-dev-tooling-zx2ouv. Measured 2026-11-12 12:53:39Z on the dev host: the delegated pre-commit aggregate was refused by check-branch-protection-alignment with `ruleset_unreadable` ("ruleset 26758787 has no readable bypass list") while the gate Job's own verdict was green. Seconds later, `gh api repos/thewoolleyman/livespec-dev-tooling/rulesets/26758787` returned `bypass_actors` (one Integration, always), the check run alone exited 0, and the retried commit passed. It was a transient forge read, the same class as a 429. The single read is in `livespec_dev_tooling/checks/_branch_protection_rulesets.py` `_fetch_ruleset_requirements`; `budgeted_gh.gh_read` is built with `max_attempts=1` and documents that retry policy belongs to the caller, so the retry belongs in this check. Under legacy-coordinator-agent's rule an intermittent check failure is a defect at its first occurrence, and this is that root fix, ruled 2026-11-12. Nine fleet repositories run this check through the shared module and receive the fix through their livespec-dev-tooling pin. Found by the gate-job-resources plan seat (epic livespec-dev-tooling-ukoeah) while committing livespec-dev-tooling#4321; it is not part of that plan's scope.

### Proposed Changes

In `contracts.md` §"Shared check inventory", `branch_protection_alignment` check, ALIGNMENT gate, in the bullet that begins "A ruleset that contributes a required check MUST bind every actor except GitHub Apps", make three edits.

First, replace "A contributing ruleset that cannot be read (including an organization-level ruleset the repository endpoint does not serve), or whose body carries no `bypass_actors` list, MUST FAIL (`failure_mode` `ruleset_unreadable`)" with "A contributing ruleset whose read fails on every attempt of the retry below (including an organization-level ruleset the repository endpoint does not serve, or one whose body carries no `bypass_actors` list on every attempt) MUST FAIL (`failure_mode` `ruleset_unreadable`)".

Second, replace "A rules read that fails for any reason MUST be treated as the ruleset contribution being unreadable, never as an empty contribution, and MUST FAIL with `ruleset_unreadable`." with "A rules read that fails on every attempt of the retry below MUST be treated as the ruleset contribution being unreadable, never as an empty contribution, and MUST FAIL with `ruleset_unreadable`."

Third, append:

A ruleset read is the rules read of the default branch (`repos/{owner}/{repo}/rules/branches/{branch}`, each of its pages) or the read of one contributing ruleset (`repos/{owner}/{repo}/rulesets/{ruleset_id}`). A ruleset read FAILS when the call exits non-zero, when its body is not the expected JSON shape, or, for a ruleset read, when the body carries no `bypass_actors` list. A failed ruleset read MUST be retried before it decides a verdict: the check MUST make at most four attempts of that read, MUST wait between attempts, each wait MUST be longer than the one before it, and the waits of one read MUST sum to at most 30 seconds. The first attempt that succeeds MUST be used exactly as a first-time success would be, so a configuration whose only bypass actor is a GitHub App exits `0` after a read that failed once. `ruleset_unreadable` MUST be reported only when every attempt of a read has failed; its logged detail MUST name the endpoint and the failure of the first and of the last failed attempt. A ruleset read that succeeds and carries a disallowed bypass actor is an answer, not a failure, and MUST NOT be retried. The `enforce_admins` read and the classic required-checks read keep their single-read rules.

In `scenarios.md` §"Scenario: branch protection alignment accepts a required gate held by a ruleset whose only bypass is a GitHub App", replace the last line and add two lines, so the block ends:

```gherkin
And a ruleset read that fails once and then returns the ruleset retries after a wait and the check exits 0.
And a rules read of the default branch that fails once and then succeeds retries after a wait and the check completes its alignment verdict rather than reporting ruleset_unreadable.
And a ruleset read that fails on every attempt of its bounded retry fails with failure_mode ruleset_unreadable rather than skipping, naming its first and last failed attempt.
```

The heading set does not change, so no `tests/heading-coverage.json` row is added or removed.
