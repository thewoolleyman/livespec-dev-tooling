---
topic: bug-check-primary-checkout-commit
author: claude-opus-5-5
created_at: 2026-11-05T02:57:29Z
---

## Proposal: A non_canonical_body finding names the differing hook and both bodies, and the tail digest restates them

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

When `primary_checkout_commit_refuse_hook_installed` reports `non_canonical_body`, each finding MUST name the differing hook's absolute path, the sha256 of the installed bytes, the sha256 of `CANONICAL_HOOK_BODY`, and the 1-based first line on which the two differ. `just check`'s tail failure-mode digest MUST restate each such hook's path with both digests. A matching hook still passes with no new output, and the `missing` and `not_executable` modes are reported as before.

### Motivation

livespec-dev-tooling-oonqhx. On 2026-11-04, factory runs 01M6KQ3M9Y7W (n6vnhp) and 01M6K8RKNRZY (q4zynn) failed this check on every janitor visit and on the publish_draft pre-push with `non_canonical_body` (3 findings) and nothing else. The finding carries only `hook`, `hooks_dir`, `failure_mode` and `hint`, and `path` is empty, so the digest printed one count line. Nobody reading a janitor's failure output could tell a stale installed body (an install that predates the refresh onto the default branch) from a canonical constant changed by the run's own tree. Diagnosing it took a `fabro dump` and a live read of the sandbox's hooks from the node. The cause was a missing re-install after `publish_draft`'s refresh (bd-ib-v4gghg). Two sha256 values and a line number in the finding, restated at the tail, would have answered it from the failure output alone.

### Proposed Changes

In `contracts.md` §"Shared check inventory" → §"`primary_checkout_commit_refuse_hook_installed` check", amend the finding-field list and add a tail-digest paragraph:

```diff
-- `path`: empty
+- `path`: for the `non_canonical_body` failure mode, the absolute path of the offending hook file (`<hooks_dir>/<hook>`); empty for every other failure mode
+- `installed_sha256`, `canonical_sha256`, `first_differing_line`: present ONLY on a `non_canonical_body` finding. `installed_sha256` MUST be the lowercase hex sha256 of the installed hook's bytes as read. `canonical_sha256` MUST be the lowercase hex sha256 of the `CANONICAL_HOOK_BODY` bytes the comparison used — the body carried by the running check, not a recomputed or remembered one. `first_differing_line` MUST be the 1-based number of the first line at which the two byte sequences, split on `\n`, differ. When one sequence is a strict prefix of the other, it MUST be the number of the first line the shorter one lacks. An empty installed file therefore reports line `1`.
```

Add, after the finding-field list:

> **Tail digest.** When this check fails with `non_canonical_body`, the failure-mode digest that `just check` restates at the TAIL of its output MUST carry, for EACH `non_canonical_body` finding of this check, one line naming that finding's `path`, `installed_sha256` and `canonical_sha256`. Grouping by `(failure_mode, hint)` MUST NOT collapse these to the group's first path, so a reader of only the last lines of a janitor's or pre-push's failure output can tell a stale installed body (installed digest differs from canonical, with the same canonical digest on every hook) from a changed canonical constant without the scrolled-off findings. The digest MUST NOT add a detection or change a verdict: every value it prints MUST come from the check's own `fail` records.

The `missing` and `not_executable` failure modes MUST keep their present fields, with `path` empty and none of the three new fields. The contract-level rule that all three hook-installation modes are corrected by the same bootstrap invocation is unchanged. A hook that exists, is executable and is byte-identical to `CANONICAL_HOOK_BODY` MUST still pass with exit `0` and emit no new output.

In `scenarios.md`, add:

```markdown
## Scenario: a stale installed commit-refuse hook names both bodies at the tail of the check output

Given a primary checkout whose `.git/hooks/pre-push` holds bytes that differ from `CANONICAL_HOOK_BODY` from line 12 onward, and whose `.git/hooks/pre-commit` is byte-identical to it

When `just check` runs `check-primary-checkout-commit-refuse-hook-installed`

Then the check MUST exit 4 with exactly one `non_canonical_body` finding, whose `path` is the absolute path of `pre-push`, whose `installed_sha256` and `canonical_sha256` are the sha256 of the installed bytes and of `CANONICAL_HOOK_BODY`, and whose `first_differing_line` is 12

And the last lines of the `just check` output MUST name that `pre-push` path with both sha256 values

And with both hooks byte-identical to `CANONICAL_HOOK_BODY` the check MUST exit 0 with no finding
```

