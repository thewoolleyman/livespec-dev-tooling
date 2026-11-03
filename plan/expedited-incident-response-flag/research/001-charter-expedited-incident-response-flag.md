## The maintainer's statement of what done means

Read the recent turns on claude session legacy-coordinator-agent, and its associated priorities.  There's a huge problem with various incidents blocking factory because the mitigations have to go through the whole entier slow test process.

I want you to help me draft a plan where there is an EXPEDITED_INCIDENT_RESPONSE ENV var observed flag in the livespec ecosystem tooling, that will bypass most of the slow work involved in pushing out a fix.

This will involve BYPASSING the factory to make the fix locally and push it through CI.

Slow work should be bypassed in both areas/levels:  in the local work like pre-push gates and in CI . 

The goal should be managing the tradeoff between speed nad risk.  

So ONLY  the fast gates should be run at all areas for LOCAL - if they can run in less than a minute, run them. Otherwise, do a best effort to skip them. 

The locally run  tests should also be minimal, only run the ones which changed or are directly related to the fix.  Then run per-file coverage just for the files which were touched. And then a single manual test.  If spec changes are needed, then they can be deferred.

Then on CI, just skip the coverage tests, they are too slow.  And skip all other tests that are related to spec enforcement, etc. Get the PR done asap and merged asap.

There must also be a comment somewhere in the code or tests alongide the change which says "EXPEDITED_INCIDENT_RESPONSE flag: <work item id>" (with the work item of the incedent. The purpose of this is to have a change to remove, which will force a full run through the entire factory for the same work item once the expedited change is merged, without anything being skipped.

THEN, after the PR Merge do the following:

1. VERIFY THAT THE MASTER CI BUILD AFTER THE MERGE PASSES. IT WILL NOT HQAVE THE EXPEDITED_INCIDENT_RESPONSE flag set, so it runs everything normally (which is a subset of the PR).  If not, IMMEDIATELY REVERT THE CHANGE WITH NO CHECKS.  THis can be a separate flag EXPEDITED_INCIDENT_RESPONSE_REVERT, that skips everything and just does the revert asap."

2. If the revert was necessary, let the original  master build finish, fix everything that was broken, then re-submit a new PR with the proper fixes and the EXPEDITED_INCIDENT_RESPONSE flag.

3. If the merge goes green on master, then REMOVE THE "EXPEDITED_INCIDENT_RESPONSE flag: ..." line in a NEW UNEXPEDITED PR.  And run it through the factory NORMALLY with NO EXPEDITED_INCIDENT_RESPONSE flag set, so we get full factory and PR coverage.  If anything that was not caught by the original expedited PR or master build is found, then FIX IT IMMEDIATELY as part of the new PR, but DO NOT REVERT THE ORIGINAL MASTER MERGE.

4. Continue to monitor master and all other PRS for breakages related to the original expedited change, if so go ahead and revert and do another expedited fix PR, then continue on with the UNEXPEDITED version.

Confirm this makes sense, then create the plan and definition of done.  Plan slug is expedited-incident-response-flag

## Definition of Done assertions derived from that statement

- An operator can activate EXPEDITED_INCIDENT_RESPONSE for one identified incident work item and deliver its fix from a local worktree through an expedited PR without a factory run or a green-master precondition blocking that repair.
- An expedited local commit and push execute applicable gates that finish in less than sixty seconds each and record slower or timed-out gates as deferred without launching the normal full aggregate or a delegated full gate job.
- An expedited fix records the results of changed or directly related local tests, coverage scoped to touched product files, and one manual incident reproduction before its PR is merged.
- An expedited PR omits coverage execution and spec-enforcement work while retaining its declared fast checks and showing every omission explicitly in its required aggregate result.
- An expedited fix contains the exact comment EXPEDITED_INCIDENT_RESPONSE flag: followed by its incident work-item id alongside the changed code or tests.
- A master push runs the repository's normal complete master CI policy with both incident flags disabled regardless of PR labels, retained comments, ambient environment, or repository variables.
- The first failing required master job after an expedited merge triggers an immediate revert of that incident change without local tests, factory work, or pre-merge CI checks delaying the revert.
- A reverted incident retains the original master CI run to completion and uses its complete failure evidence to prepare a corrected expedited PR on the same incident work item.
- A successful master run causes a new unexpedited factory PR on the same incident work item that removes the marker and exercises normal factory and PR validation over the original incident change scope.
- A defect found only by the unexpedited factory follow-up is fixed within that follow-up PR without reverting the original successful master merge solely for that deferred-verification finding.
- A related regression observed on master or another PR triggers an incident revert and a corrected expedited attempt while preserving the obligation for a final unexpedited factory PR.
- Incident monitoring and follow-up ownership survive process restarts and prevent the incident work item from closing before its unexpedited factory PR and subsequent normal master CI succeed.
- The installed fleet tooling preserves incident context through hooks, credential wrappers, delegated execution and PR event boundaries while preventing expedited verdicts or cached coverage from satisfying normal validation.
- Operators can inspect each incident's skipped work, verification evidence, attempts, merge and revert SHAs, CI runs, deferred spec work and final factory proof using the incident work item as the durable identity.

# Expedited incident response flag

## Outcome and scope

Provide an explicit incident recovery path throughout the livespec ecosystem.
The incident owner implements locally, pays only for fast gates and focused
verification, and merges an expedited PR. Normal master CI runs immediately.
A failure causes an immediate unchecked revert; success starts a normal factory
follow-up on the SAME incident work item. The follow-up removes a required code
comment and repays all deferred verification and specification work.

This plan creates the design and Definition of Done. Creating it does not enable
either flag, change a workflow, reduce an existing gate, or start implementation.
The author's assertions above are derived from the maintainer's supplied request;
they are draft plan acceptance criteria, not a claim of delivered behavior.

Scope covers livespec core's contracts and agent guidance, dev-tooling's shipped
hooks/check dispatcher and workflow templates, orchestrator lifecycle/provenance
and factory follow-up behavior, overseer/operator guidance, runtime driver
bindings where needed, and adoption by every governed fleet consumer. Discover
the actual consumer set from core's committed fleet manifest at implementation
time; a dev-tooling-only implementation does not satisfy this plan.

## Evidence and priority context

Read on 2026-11-03: Claude session legacy-coordinator-agent,
9da1ad7f-1c5a-4e9d-80c4-91decba8839b, especially 15:19–15:51Z, and the current
priorities-record on legacy-coordinator-agent (livespec-dev-tooling-6tgd2z),
comment 01a1a1f2-53be-754e-95d4-5e050a0ecb8f, recorded 15:06:13Z with set-at
15:08Z. These are observations of that window, not current incident status.

- Priorities 1–5 were the flaky-test retry plugin, fleet-flaky-tests,
  ci-runtime-and-cost, early commit-gate/mechanical-refusal improvements, and
  ci-cache-optimization. This plan complements those efforts without changing
  their order or claiming ownership of their fixes.
- At 15:19Z the gate watcher race fix (livespec-dev-tooling-lndv2l, PR #3284)
  had a factory run about sixty minutes old with per-file coverage pending.
  The SIGPIPE fix (livespec-dev-tooling-ftgiu4, PR #3207) had green checks but
  a roughly seventy-three-minute factory run. An RBAC overlap flake
  (livespec-dev-tooling-alvhwt, PR #3173) had turned master red.
- At 15:20Z the Fabro restart cancelled the carrying runs. The owning seat
  moved to hand-landing and the dispatcher disarmed conflicting resumptions.
  This exposes both the need for a local repair route and exclusive ownership
  while it is used.
- By 15:37Z the coordinator reported a green dev-tooling master on 1625b9ca.
  The gmktec restart hold remained a separate constraint. Expedited response
  must not become a reason to bypass unrelated host maintenance or safety.
- The latest coordinator turn read was the maintainer's 15:51:32Z notice that
  this expedited-incident-response-flag session had been started.

Relevant source surfaces read: lefthook.yml; scripts/just/check-pre-push.sh;
scripts/just/check.sh; scripts/just/check-per-file-coverage.sh; justfile;
.github/workflows/ci.yml; the orchestrator's check-factory-provenance workflow;
AGENTS.md; .ai/fleet-and-secrets.md; .ai/coordinator-duties.md; core's
.ai/ci-gate-discipline.md. Existing per-file coverage launches the full pytest
suite, so merely selecting that target would defeat the requested fast path.

## Flag and identity contract

Use EXPEDITED_INCIDENT_RESPONSE=1 for the repair path and
EXPEDITED_INCIDENT_RESPONSE_REVERT=1 for its emergency revert. Unset, empty and
false values select normal behavior; publish one parser for documented truthy
values across bindings. Malformed values produce a clear configuration error.
The revert mode has precedence when both are set, and is permitted only for a
revert of a recorded incident merge. An ordinary feature cannot use it.

Every invocation resolves the incident work-item id from explicit command/PR
metadata using the mode-specific evidence below. The same id follows local
work, PR attempts, reverts, and the eventual factory run. No separate repair or
marker-removal item substitutes for the incident id. A general implementation
task for this plan is distinct from a future incident using the feature.

| Mode | Identity evidence | Marker rule |
| --- | --- | --- |
| Expedited repair | Incident id, attempt id, repository, base/head and authorized PR metadata. | Required in the resulting code/test tree. |
| Emergency revert | Recorded attempt, incident merge SHA, current target and inverse change. | Validate the original marker/provenance; resulting tree may remove it. |
| Normal master | Exact push SHA and normal workflow identity. | May remain, with no effect on execution mode. |
| Normal factory follow-up | Incident id, successful attempt, fresh dispatch/run/PR and cumulative original scope. | Remove the original attempt's marker, with both flags absent. |
| Ordinary work | Existing normal identity. | Historical markers confer no exemption. |

Resolve trusted event/phase context BEFORE parsing ambient flags: normal master
and normal factory follow-up force both flags off, including malformed inherited
values. Keep the incident id stable but give every repair/revert/follow-up its own
attempt/phase/operation and carrier PR identity. Branch recovery, merged-PR lookup,
claim stamps, proof pointers, acceptance and completion must use that current
identity, never the first merged PR found for feat/<item> or a title/body mention.
Preserve the attempt history when replacing a current dispatch claim. Distinguish
incident recovery attempts from normal acceptance rework/nonconvergence budgets.

Flags are invocation-scoped. Never export them host-wide, store them as repository
defaults, or bake them into an image. Measure environment propagation across each
installed credential wrapper instead of trusting older guidance: the installed
with-livespec-env.sh now captures and restores the caller environment, while
.ai/fleet-and-secrets.md describes its earlier scrubbing behavior. Explicitly
passing the selected flag and nonsecret incident context AFTER the wrapper
boundary remains a portable route. Instrument hook/dispatcher/delegated boundaries so operators
can see the effective mode, item, head SHA and skipped work. Do not launch the
normal remote/delegated full aggregate merely because it runs off the local host.

A local environment variable does not propagate to GitHub Actions. Use a
dedicated PR-scoped expedited-incident-response label plus structured incident
metadata, validated by trusted workflow control, to project the flag into that
PR's jobs only. Apply the signal before the first CI run and handle label events
without requiring a close/reopen ritual. Head changes invalidate prior evidence.
Labels must not select expedited behavior on push, schedule, release or factory
events. A marker alone NEVER activates either flag. Keep required aggregate check
names stable and adapt their dependency logic so intentionally omitted jobs do
not leave the expedited PR permanently pending or falsely counted as executed.

## Verification policy

| Surface | Expedited fix | Emergency revert | Normal/follow-up |
| --- | --- | --- | --- |
| Factory | Bypass for local incident repair; take ownership from any live run first. | Bypass. | Required normal factory route. |
| Local hooks and explicit gate commands | Applicable fast gates only; each under 60 seconds. | Skip all quality/test gates. | Existing full policy. |
| Local tests | Changed tests and tests directly related to the fix. | None. | Existing full policy. |
| Local coverage | Touched product files only, using focused tests and isolated data. | None. | Existing full policy. |
| Manual verification | One incident-specific manual scenario with expected/actual results. | None before revert. | Normal proof requirements. |
| PR CI | Fast change checks and focused relevant tests; no coverage or spec enforcement. | No pre-merge CI wait or check requirement. | Existing complete PR policy. |
| Master CI | Complete normal master policy, both flags forcibly disabled. | Complete normal master policy after revert. | Existing complete master policy. |
| Spec changes | May defer; record exact debt on incident. | None before revert. | Repay before final closure. |

Inventory all entry points, including commit-msg replay, source/test pairing,
pre-commit, pre-push, explicit just check, agent hook guards, the check dispatcher,
delegated Jobs, range checks, PR provenance, CI matrices, acceptance and aggregate
jobs. Avoid a hidden slow gate behind a fast wrapper or a second whole-suite run.
Resolve a typed execution plan BEFORE staged prechecks, autofix, source/test
pairing, normal token reads, delegation, replay or fallback. Every entry point
receives the same mode and scope. A delegated failure must retain that selection,
never fall back to a full local aggregate or the renderer's default check-pre-push.
Measure gate duration from existing evidence or a bounded trial; skip known slow
gates before launching. Prefer skipping unclassified gates to dozens of serial
one-minute exploratory trials. Time out unknown gates at sixty seconds, stop their owned
children, and report deferred-timeout rather than passed. Unknown timing must not
fall back to the full aggregate. Run real fast gates, including inexpensive
correctness/style checks, and honor their failures. The one-minute rule is per
gate, not a reason to split a slow suite into many nominally fast wrappers.

Focused validation remains the minimum evidence: run changed/directly related
tests, measure existing per-file coverage criteria only for touched executable
files, and perform one manual incident test. Do not expand to the repository
suite to collect that coverage. Keep generated/removed/non-executable-file
handling explicit. Select small runs; if a required focused measurement cannot
complete quickly, expose the exact time and missing evidence as incident risk
instead of silently claiming it passed or substituting a full run. Record the
operator's disposition on the same incident. Preserve failing focused assertions
as failures requiring a fix, not as optional skipped work.

CI skips BOTH coverage producers and consumers, coverage artifacts, per-file and
aggregate thresholds, coverage tests, spec/heading/debt conformance, spec doctor,
and related enforcement even when a spec check happens to be quick. Retain the
declared fast change checks; do not replace coverage with another full test suite.
Inventory and remove indirect spec/coverage dependencies from the expedited path.
Logs and the aggregate distinguish executed/pass, failed and intentionally deferred.

Select enforcement invocations and tests explicitly; do not turn check library
implementations into unconditional successes when the flag is inherited. A test
may call heading_coverage.main() in-process expecting both a clean pass and a
broken-fixture failure. Classify governed-tree enforcement, fixture-based tests of
an enforcement implementation, and tests that launch broad/spec/coverage checks
separately, including fixtures, nested pytest and subprocesses. Local fast spec
checks may report deliberately deferred incident spec debt, but cannot hold the
repair for that declared debt; normal factory follow-up restores enforcement.

Expedited evidence never creates a normal green token, normal TDD/factory proof,
or reusable normal coverage artifact. Cache identity includes mode and validation
scope, or caches are disabled for expedited results. Full master cannot inherit a
PR skip list. Commit replay/range enforcement must recognize historical expedited
provenance without invented TDD trailers or refusing master merely because expensive
pre-merge replay was deferred; its normal runtime test/coverage work still runs.

Define a distinct incident commit receipt carrying item, attempt and phase;
its semantics are deferred verification, never full TDD success. The local
provenance hook also records `Factory-Override: EXPEDITED_INCIDENT_RESPONSE flag:
<id>` on the commit as its audited explanation. The range checker validates the
incident receipt against exact recorded PR/head/landed-commit evidence rather than
accepting a bare forgeable trailer, a currently set environment variable or only
the PR label. That historical evidence remains readable on normal master after
merge; reading it does not enable expedited execution there.

Expedited repair and revert choose HOST LOCAL before any cluster eligibility
probe, mirror-ref publication or Job submission, including the detached runner's
independent venue selector. Their focused tests and touched-file coverage also
remain local. Normal delegated jobs explicitly remove both flags. Keeping mode
and scope explicit at remote boundaries remains necessary to reject leaks and
prevent a failed or stale selector from falling back to full work.

For mixed CI batches, pass the shared typed selected-target plan into each batch
loop and direct action; do not skip an entire mixed job containing retained fast
checks or run its whole body accidentally. Include incremental coverage, rate-
budget/network conformance, doctor-static, e2e/acceptance and pre-tag/release gates
in each repository's timing and applicability inventory. Define the incident
shape in the CI matrix parser and parity/completeness checks; an accidental
mechanical pass is not conformance to the new policy.

Provision the incident labels in every applicable consumer, subscribe to the
relevant label events, and explicitly arm ordinary expedited PR merge when the
existing auto-enable workflow admits only maintainer-authored PRs. The emergency
revert uses the controller's direct scoped capability instead of auto-merge.

Reuse an existing incident work item where possible. A new incident needs fast
canonical filing with its identity, scope and behavioral intent; slow model-backed
DoD/governing-heading admission cannot sit in front of local incident work.
Defer that admission judgment to the normal factory follow-up without changing
the item's identity. If its tenant is unavailable, use an already recorded
incident id/receipt rather than manufacturing an untracked item or querying the
broken store before every recovery action.

## Incident lifecycle and mandatory follow-through

1. **Claim and prepare locally.** Record incident impact, owner and scope. Locate
   any live factory attempt or pending waiter for the same item; use sanctioned
   cancellation/ownership transition and disarm duplicate dispatch before editing.
   Make a minimal change in a worktree. Include an actual code/test comment:

   ```text
   EXPEDITED_INCIDENT_RESPONSE flag: <work item id>
   ```

   Replace the placeholder with the incident's real id. Keep the comment next to
   the change, not only in a PR body or plan note. Preserve it through squash or
   rebase. A deletion-only or non-commentable config change uses a legal adjacent
   existing code/test carrier; the marker cannot break the format being repaired
   or serve as its own behavioral evidence. Record touched paths, original
   base/head and focused evidence. Deferred
   spec changes do not hold the incident fix behind propose-change/revise.

2. **Merge the expedited PR promptly.** Project incident mode into this PR's CI,
   bypass factory provenance through the explicit incident contract, and merge
   as soon as the retained checks pass. Do not wait for an unavailable factory,
   a full pre-push aggregate, or a green-master precondition that blocks the
   repair itself. Preserve normal worktree/PR identity and authentication.

3. **Watch the exact merge on master.** Record the resulting master merge SHA,
   complete landed commit set, pre-incident and resulting trees, normalized full
   PR patch, workflow run and all required job conclusions. Rebase merging can
   land several commits; the terminal merge SHA alone is not the rollback unit.
   Master unconditionally disables
   both flags and runs its existing complete policy; master may normally run
   fewer checks than a normal PR, which is why the factory follow-up is required.
   Missing, cancelled or unreadable runs are unresolved evidence, never green.

4. **On the first required master failure, revert immediately.** Trigger at the
   first failing required job rather than waiting for the aggregate or other
   jobs to finish. Deliver a trusted job/check-completion event or explicit CI
   failure callback to an independently hosted controller. Required failure
   producers mean all leaf jobs/matrix legs contributing to the protected
   aggregate, not only the final ci-green context. Establish a durable observer
   receipt before merge; its control code and authorization use a known-good
   released build independent of the incident tree being repaired. The existing
   completed-workflow trigger and five-minute reconciler schedule cannot meet
   this requirement. EXPEDITED_INCIDENT_RESPONSE_REVERT bypasses all local gates,
   factory work and pre-merge CI waits, including red-master and TDD barriers.
   Revert the COMPLETE recorded incident patch against current master with an
   expected-head compare-and-swap, preserving later work. Recompute on head
   movement; never restore whole old files over descendants or revert only the
   last commit of a multi-commit incident.
   Verify target identity and construct the inverse diff; those operations are
   necessary to perform the revert and must not launch a validation aggregate.
   If branch protection requires a special App merge path, provision it during
   implementation; opening a revert PR with auto-merge waiting on CI does NOT
   satisfy this requirement. No global disable of branch protection. Resolve an
   overlap explicitly in a rollback-conflict phase with an identified owner,
   rather than resetting unrelated changes away. Resolving the inverse diff is
   necessary revert construction, not a reason to run pre-merge quality checks.

5. **Keep the failed run alive; then repair all failures.** Do not cancel the
   original master run when the revert or replacement push arrives. Adjust
   concurrency/cancel/fail-fast behavior as needed to collect the remaining job
   results. Do not let the existing master-health reconciler race or double-revert
   the same incident. Record revert SHA and its normal master run. After the
   original run finishes, fix all revealed breakages, re-run focused local
   verification, and submit a NEW expedited PR on the SAME item with the marker.
   Keep an attempt chain rather than replacing the failed attempt's evidence.

   First failure always triggers rollback without classification delay. After
   collection, classify failures as incident defects, pre-existing defects,
   infrastructure failures or unresolved, with an owner for each. Do not repeatedly
   reland unchanged code to retry a still-broken base or infrastructure; a new
   attempt needs a repair or measured resolution evidence.

   Workflow completion does not prove every check ran: dependents may be skipped
   after a prerequisite fails. Record the expected normal job graph and distinguish
   completed, failed, blocked-by-prerequisite, cancelled and never-created legs.
   Leave the original run untouched. After rollback, collect missing evidence in
   an explicitly identified continuation on the original incident tree where
   feasible, or retain each missing check as unresolved follow-up debt.

6. **On master success, repay through factory.** Keep the incident item open and
   dispatch a NEW normal factory run for it. A new PR removes the marker with BOTH
   flags absent from the dispatcher, sandbox, local hooks, PR and merge path.
   The factory must accept this unfinished item after its expedited PR merged;
   normal reconcile/accept cannot close it early or decide it is already done.
   The item retains its original behavioral Definition of Done. Marker removal
   is the real diff that forces another PR, not a substitute for incident proof.

   Crucially, validation scope includes the cumulative original incident paths,
   tests and deferred debt, not only the comment-removal diff. Normal factory,
   integration, review, full PR coverage and spec enforcement all execute. If this
   deferred verification discovers a missed defect, fix it immediately IN THIS
   follow-up PR. Do not revert the healthy original master merge solely because
   the follow-up exposed an uncaught case.

   The cumulative original diff, focused evidence and attempt history also feed
   acceptance's evidence corpus. Its input cannot be only the marker-removal
   patch. Close/no-change-needed and reconcile-merged paths may not consume an
   old expedited merge as completion, and stale run completions after an ownership
   transfer may not write proof or close the item.

7. **Monitor master and other PRs concurrently.** Monitor every open PR and new
   PR runs in the affected repository and affected fleet consumers for failures
   attributable to the incident. Record attribution with failing job/test and
   change evidence; an unrelated flaky failure is not enough. If a related
   breakage appears in deployed master or another PR, revert the incident promptly,
   prepare another expedited attempt, and continue the normal follow-up after
   recovery. This rule differs from a finding isolated to deferred factory proof.
   Invalidate stale cleanup attempts when their incident attempt was reverted.

8. **Close only after normal proof.** Require the final unexpedited factory PR
   merged, normal master CI green, the manual incident outcome still correct,
   all markers removed and recorded spec debt repaid. Monitor throughout recovery
   and follow-up, and perform a final scan of master and other PR failures before
   closure. Persist unresolved attribution or affected consumer rollout as an
   owned obligation rather than silently ending monitoring. The installed observer
   retains incident-to-change attribution after closure so a later related master
   or PR regression can reopen the same incident and its recovery cycle.

Monitoring runs independently of the interactive session, using existing durable
workflow/observer mechanisms with a ledger-owned incident phase and run identity.
Restart reconciles observed SHA/run/PR state and resumes the same operation.
Deduplicate revert events, follow-up dispatch and completion so a restart, webhook
redelivery or the existing reconciler cannot create two reverts or factory runs.
Use an atomic per-repository action lease and per-incident generation/phase fence
shared with master-health reconciliation. Revalidate that fence immediately before
each dispatch, merge or revert. Persist intent before the forge call and reconcile
its exact receipt after timeout before retrying. A reverted generation cannot
merge a previously green cleanup PR; a delayed failure from an old attempt cannot
revert its corrected replacement. Fence concurrent incident episodes independently
while serializing conflicting repository mutations.
No new notification-only cron, foreground polling loop, or unbounded live agent
session is the supervision design. Record actual action receipts, not promises
that an owner will check later.

Recovery must remain executable when the failing component is the tenant ledger,
credential projection, factory, gates namespace or self-hosted runner pool. Keep
the trusted operation receipt and action fence on an independently available
control surface; do not require a fresh call through the failed component just to
select incident mode or revert. Reconcile receipts back to the incident work item
when its tenant becomes reachable, without inventing a second lifecycle truth or
allowing duplicate side effects. Exercise the ledger-unavailable and credential-
wrapper-unavailable cases in the controlled recovery proof.

## Speed, risk and policy decisions

Accepted risk is a shorter pre-merge validation window and temporary spec debt.
Controls are incident identity, focused local evidence, visible skips, mandatory
normal master CI, immediate revert, broad regression monitoring and full normal
factory repayment. Record time to first fix, local/PR gate durations, skip reasons,
master verdict/revert latency and eventual factory completion; report measured
results without claiming a fixed CI queue or network latency.

This is an explicit maintainer-directed policy change. Implementation must
reconcile core's ci-gate-discipline prohibition on environment escape gates,
the factory-only/provenance rules, PR/master gate parity, pre-commit TDD replay,
agent no-bypass hooks, and the reconciler's current rerun/fix-forward rules.
The incident path supersedes them only for the named incident repair/revert.
Ordinary work retains those rules. Existing server-side revert signing helps
with provenance but does not itself provide an unchecked merge capability.
Inspect the current forge merge authorization before promising no-check reverts.

Chosen revert design: a dedicated recovery-controller identity, with forge
ruleset authorization scoped to the incident revert controller and its validated
inverse patch. Provision it in the normal rollout and adapt branch-protection
alignment, fleet reconcile and canonical specs to this narrow principal while
retaining required checks for ordinary actors. If classic branch protection would
still refuse the operation, migrate the overlapping protections under the same
normally tested rollout rather than toggling them off during an incident. A
label-skipped green stub job is not the no-check revert: it still waits for CI
scheduling, contrary to the requested immediate path. This design grants the
controller a specific recovery capability, not the factory worker or arbitrary
flag-bearing shell a general merge bypass.

The incident contract must explicitly admit a scoped workflow-edit authorization
receipt at the local host-authority gate, which currently says no flag changes
its tiers. An incident flag alone is not a new credential. Factory workers retain
their existing lack of workflow write scope. If normal factory follow-up must
repair a workflow, an authorized host publisher applies the normally validated
factory tree to the SAME incident carrier PR with its required workflow-edit
receipt. This is publication transport, not another work item, a factory bypass,
or a permanent workflow credential grant to sandboxes.

Retrospective factory-bypass audits must recognize recorded incident repair and
revert receipts as declared exceptions with outstanding normal repayment, without
adding an unrestricted allow-label. Generated Copier justfiles, lefthook wiring,
reusable CI matrices and direct run-check actions are separate adoption surfaces.
Ratify the specific incident exception in parity/completeness guards rather than
turning those guards off or relaxing them for ordinary PRs.

Deferring a spec amendment does not disable normal master conformance checks.
If master exposes a deferred spec discrepancy, revert, collect the full result,
and include its required correction in the next attempt; no permanent waiver
or silent master skip is introduced to make the expedited merge stay green.

Source rollback is only one recovery leg. Track source commits to release tags,
images, pin bumps and installed consumers. On incident rollback, stop queued
adoption of the bad artifact, supersede its pending pin carriers and repair
consumers that already adopted it through owned rollback or corrective releases.
Keep the original master CI alive while doing so. A green source master does not
close deployed recovery. Irreversible external-state changes are ineligible for
unattended automatic rollback under this path unless a safe compensating operation
is already recorded; this is a draft risk-control decision for objection, not a
new blanket approval gate for reversible code fixes.

The implementation rollout must be normal and unexpedited. Land the shared
contract and readers, release, adopt consumers, verify the serving versions, then
enable use. Coordinate edits to ci.yml with ci-runtime-and-cost and cache owners;
do not consume their PRs or silently reorder the coordinator's priorities.
The user authorized drafting this path; this plan itself does not use it to skip
the present documentation change's checks.

Verify controller installation repository by repository rather than assuming the
existing reconciler is live everywhere. At audit time only the livespec checkout
of the four main repos had a master-health-reconcile.yml shim; the other three
had reusable/canonical source but no installed local shim. The rollout must install
the applicable observation/control path and prove it is serving before enabling
an incident merge. Release prefixes, plugin/package release, sandbox-image builds,
queued fan-out and consumer pin CI remain measured recovery dependencies; a merged
source PR is not evidence that the running factory uses the repaired build.

## Implementation sequence

1. Inventory fleet consumers and all gate/identity/cache entry points; define the
   shared mode parser, PR transport, evidence, lifecycle and policy amendments.
2. Implement local fast selection, focused coverage, hook/replay integration and
   explicit wrapper propagation in dev-tooling; publish normal/expedited/revert
   execution plans before activation.
3. Implement PR CI selection and stable aggregate semantics in shipped templates
   and consumers; force complete normal master behavior on every push.
4. Implement durable monitoring, unchecked scoped revert, failed-run retention,
   reconciler coordination and corrected expedited attempts.
5. Implement same-item factory re-entry and marker-removal follow-up with original
   change scope, deferred-spec repayment and closure prevention.
6. Release through the normal channel, adopt fleet consumers, exercise successful
   recovery, failure/revert/reland and late-regression paths, obtain independent
   plan proof and completeness review, and archive only after all assertions hold.

These are design slices, not newly admitted implementation work items. Capture
ripe children through the public filing operation after recording their carrier
map and concrete behavioral DoD against the agreed spec. Cross-repo carriers
belong in their owning tenants. Do not spawn incident fixes or a factory run as a
side effect of creating this draft.

## Proof and completion requirements

All plan assertions use host-captured proof against released, normally installed
tooling. Preserve exact repo/tag/build identities, local execution logs, changed
test selections, touched-file coverage, manual result, PR/merge/revert SHAs, job
conclusions, skip reasons and the SAME incident id across attempts. Exercise:

- Unset/false mode, expedited local fix, expedited PR, normal master, revert,
  and unexpedited factory follow-up; no ambient flag or cached result may leak.
- A gate over sixty seconds, a nested/delegated slow gate, a real fast-check
  failure and an unrelated test; prove intended omissions without fake success.
- Master success leading to marker removal and full original-scope verification.
- First master failure causing the unchecked revert before the original run
  finishes, followed by complete failure collection and corrected expedited PR.
- A defect found only in factory cleanup repaired in that PR without reverting
  healthy master, and a related failure on another PR causing the revert cycle.
- Observer restart, duplicate events, competing reconciler, intervening commits,
  comment-only diff optimization and attempted premature work-item closure.
- Multi-commit rebase merge, a later unrelated edit to the same file, overlapping
  incidents, stale observer events and a crash after merge but before receipt.
- Release/image fan-out and queued consumer adoption between incident merge and
  failure, including adoption arriving after the source revert.
- First leaf failure while a sibling still runs, broken incident-tree observer
  code, prerequisite-skipped normal checks, and an already-red base that must not
  trigger an unchanged reland loop.

Retain the existing plan archive requirements: all children disposed, independent
completeness review, captured then independently verified plan Proof of Done,
released-artifact evidence where applicable, and no unresolved assertion. The
plan remains live while any consumer, incident lifecycle leg or proof is missing.
