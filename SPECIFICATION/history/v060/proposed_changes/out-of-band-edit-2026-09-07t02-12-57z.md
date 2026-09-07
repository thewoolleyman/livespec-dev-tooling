---
topic: out-of-band-edit-2026-09-07t02-12-57z
author: livespec-doctor
created_at: 2026-09-07T02:12:57Z
---

## Proposal: out-of-band-edit-2026-09-07t02-12-57z

doctor detected drift between HEAD-active spec content and the
HEAD-history-vN snapshot; this auto-backfill records the active
state as the new canonical version.

### Proposed Changes

```diff
--- history/vN/contracts.md
+++ active/contracts.md
@@ -68,9 +68,9 @@
 
 - `required_status_checks.strict` is TRUE → ERROR; the check FAILS (exit `4`) with one `fail` finding (`failure_mode` `strict_enabled`). Strict (require-branches-up-to-date) MUST be OFF: per `livespec/SPECIFICATION/non-functional-requirements.md` §"CI as a merge gate (branch protection)", `strict` makes GitHub keep a behind PR current by merging `master` into its branch, injecting a `Merge branch 'master'` commit that violates `required_linear_history` and buries the per-commit Red-Green-Replay TDD trailers. Since `master` accepts only rebase-merges, `strict` adds no correctness guarantee.
 - A required check with no matching `ci.yml` job → ERROR; the check FAILS (exit `4`) with one `fail` finding per offending check (`failure_mode` `required_check_missing_from_ci`). This is the v039-D1-style drift: GitHub blocks merges because the required check never reports.
-- A `ci.yml` job NOT in the required list → WARNING only (exit `0` contribution); some jobs are intentionally not required (e.g., experimental workflows).
-
-Exit codes: `0` on protection-present-and-aligned OR any graceful skip; `1` on the legacy precondition failure (ci.yml present but `matrix.target` empty or unparseable); `4` on any fail branch (`protection_absent`, `strict_enabled`, or `required_check_missing_from_ci`).
+- A `ci.yml` matrix leg NOT in the required list → WARNING only (exit `0` contribution) WHEN a required aggregate gate is present; some jobs are intentionally not required (e.g., experimental workflows). Otherwise → ERROR; the check FAILS (exit `4`) with one `fail` finding per uncovered leg (`failure_mode` `unrequired_leg_without_aggregate_gate`). The leniency is CONDITIONAL and the check MUST evaluate its condition rather than assume it: an unrequired leg is benign only under the SINGLE-GATE model, where the required aggregate goes red in the leg's place. Under the many-contexts model with the aggregate unrequired, a red leg blocks nothing — the leg is not required and neither is the aggregate that would have caught it. The condition is read from the required-checks list the check already fetched, at no extra API cost: a required context is an aggregate gate when it matches a top-level `ci.yml` job and is NOT itself a matrix leg — the same grammar the missing-from-CI rule uses to accept a required top-level gate as a valid target, so the two rules cannot drift about what counts as a gate. An EMPTY required list is the limit case (no required context, hence no gate) and every leg is reported. Top-level jobs are still never flagged as should-be-required.
+
+Exit codes: `0` on protection-present-and-aligned OR any graceful skip; `1` on the legacy precondition failure (ci.yml present but `matrix.target` empty or unparseable); `4` on any fail branch (`protection_absent`, `strict_enabled`, `required_check_missing_from_ci`, or `unrequired_leg_without_aggregate_gate`).
 
 CI-token caveat: the default GitHub Actions `GITHUB_TOKEN` lacks the admin scope needed to READ branch protection, so in a stock Actions job this check always lands on the outcome-3 graceful-skip path (it receives an ambiguous `Not Found`, never the canonical `Branch not protected`) and does NOT enforce. The check is therefore wired into the `just check` aggregate / pre-push — where a maintainer's admin-scoped `gh` token CAN read protection and the fail-on-absent branch actually fires — and is intentionally NOT a required CI matrix entry, which would always-skip and be pointless. A consumer whose CI provides an admin-scoped token (e.g., a PAT secret) MAY additionally wire the check into its CI matrix.
 
@@ -78,23 +78,35 @@
 
 This is a **revise-workflow check** (per §"Shared check inventory"), NOT a canonical per-commit aggregate check: it lives under `livespec_dev_tooling/workflow_checks/` and is invoked by the `/livespec:revise` pre-step, never wired into the `just check` aggregate.
 
-Invocation: `python -m livespec_dev_tooling.workflow_checks.no_stale_revise_branches`. Exit `0` on no stale branches, exit `4` with structured stderr findings on any stale branch.
+Invocation: `python -m livespec_dev_tooling.workflow_checks.no_stale_revise_branches`. Exit `0` on no stale branches, exit `4` with structured stderr findings on any stale branch. "Stale" means the branch carries commits that have NOT LANDED on the canonical branch — NOT that its tip is ahead of it.
+
+**The discriminator is patch-id equivalence, and the distinction between the two is the whole of this section.** Landed-ness was judged by ANCESTRY until v060: `git rev-list --left-right --count` against `origin/<canonical>`, failing any branch ahead by one or more. On a rebase-merge-only fleet that check cannot SUCCEED. A rebase-merge REWRITES a branch's commits, so a landed branch's local tip is never an ancestor of the canonical branch, and every landed-but-undeleted branch is reported forever. Measured 2026-08-22 in livespec-overseer: eleven fail findings, all eleven already on `origin/master`, two of them confirmed merged through the forge and the other nine landed without a pull request at all. This is the mirror of the check-that-cannot-fail hazard, and its practical damage is larger than noise: of the three remedies the check's prose offers — merge, abandon, re-invoke with the skip flag — the first two are inapplicable to a branch that IS merged, so the precondition trains the operator to skip it, and the twelfth finding, the real one, gets skipped with the eleven.
 
 Algorithm:
 
 1. Read the canonical branch name from `.livespec.jsonc`'s `livespec-impl-git-jsonl.canonical_branch` config key (or any other configured impl plugin's equivalent key). Default: `git symbolic-ref --short refs/remotes/origin/HEAD`, with hard-coded fallback `master`.
 2. Enumerate local refs: `git for-each-ref --format='%(refname:short)' refs/heads/spec/`.
 3. For each branch in the enumeration:
-    - Run `git rev-list --left-right --count origin/<canonical>...<branch>`.
-    - Parse the output as `behind\tahead`.
-    - If `ahead > 0`: emit a finding with severity `fail`.
+    - Run `git cherry origin/<canonical> <branch>`.
+    - Count the `+ <sha>` lines — commits with no patch-equivalent on the canonical branch. A `- <sha>` line is git's own verdict that an equivalent patch IS upstream, computed from `git patch-id` digests and therefore intact across the rewrite a rebase performs.
+    - If that count is `> 0`: emit a finding with severity `fail`.
+    - If `git cherry` FAILS, or emits a line in neither form, the branch is SKIPPED with a structured warning and contributes no finding. Refusing to guess is the fail-safe direction here: reading an unparseable answer as "nothing unlanded" would wave a genuinely stale branch through, which is the one direction this check must never fail in.
 4. Exit `0` on zero findings, `4` on one or more.
+
+**The discriminator MUST be named in the check's own output** — in the `discriminator` field of every finding and in its `message` — as well as in the module docstring. An operator reading a finding cannot judge it without knowing what it rests on, because each candidate discriminator has different failure modes, and this one's are:
+
+- **Conservative, not silent.** A land that CHANGED the patch — a squash-merge, or a rebase that resolved a conflict — yields a different patch-id and is still reported. The check over-reports, never under-reports.
+- **Not free.** `git cherry` digests every commit on both sides of the merge base, so an old branch costs a patch-id walk of the canonical branch's commits since the branch point. That is more than the ancestry count it replaced, and it is bounded by how long the branch was left undeleted.
+
+The two alternatives are recorded as REJECTED rather than left implicit. Subject-match against the canonical branch's history is cheaper and is what the 2026-08-22 measurement used by hand, but subjects collide, so it can call an unlanded branch landed — a false negative, the forbidden direction. A forge query for a merged pull request on the head is authoritative where it applies, but it costs an API call, requires credentials at what is a local pre-step, and misses content that landed without a pull request — nine of the eleven branches in that measurement.
 
 Each finding carries:
 
 - `check_id`: `no_stale_revise_branches`
 - `status`: `fail`
-- `message`: `branch '<name>' is <ahead> commit(s) ahead of origin/<canonical>; last commit <short-sha> "<subject>"`
+- `message`: `branch '<name>' has <unlanded> unlanded commit(s) not present on origin/<canonical> (discriminator: patch-id equivalence (`git cherry`)); last commit <short-sha> "<subject>"`
+- `unlanded`: the count of `+` lines from `git cherry` — commits with no patch-equivalent on the canonical branch
+- `discriminator`: `patch-id equivalence (`git cherry`)`
 - `path`: empty (the finding is git-topology, not file-system)
 - `line`: 0
 
```
