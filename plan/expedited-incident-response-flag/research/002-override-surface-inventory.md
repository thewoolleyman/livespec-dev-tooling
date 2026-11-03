# Override surface inventory and adversarial review

## Purpose and completeness rule

This is the implementation inventory for the incident contract in research note
001. It lists distinct launch, authorization, evidence and lifecycle surfaces;
changing just the pre-push script and CI matrix is insufficient.

At implementation, expand this inventory against the current committed
`livespec/.livespec-fleet-manifest.jsonc`, including declared adopters. For EVERY
surface and consumer record one explicit disposition: implemented, deliberately
normal, or not applicable, with its source path, installed/released build and
execution proof. No unclassified surface remains at completion. Instruction-only
adopters have the applicable operator/driver guidance obligation, not imaginary
tenant, hook or CI jobs. Custom workflows and alternate stores require their own
inventory rather than inheriting a claim of coverage from the shared package.

Expedited repair, emergency revert, normal master, normal factory follow-up and
ordinary work are separate execution contexts. Only the first two reduce work.
Normal contexts explicitly remove inherited incident flags before resolution.

Path abbreviations: DT = livespec-dev-tooling; CORE = livespec; BF =
livespec-orchestrator-beads-fabro; OS = livespec-overseer. BF Python commands
below live under `.claude-plugin/scripts/livespec_orchestrator_beads_fabro/`.

## Required source and behavior matrix

| Surface | Concrete source seams | Required incident behavior and normal-path proof |
| --- | --- | --- |
| Hook installation and wiring | DT `install_commit_refuse_hooks.py`, `lefthook.yml`, materialized worktree pack; CORE generated lefthook wiring. | Installed hook version reads mode; no stale copy or reinstall restores a full-only hook. Revert performs no quality gate. Ordinary worktree/branch identity remains intact. |
| Pre-commit before mode selection | DT `scripts/just/check-pre-commit.sh`, `workflow_checks/staged_precheck.py`, lint-autofix and source/test pairing targets. | Resolve mode before staged prechecks and delegation; retain only applicable fast work, and no pre-commit TDD ritual forces a full aggregate. |
| Commit-msg and TDD | DT `checks/red_green_replay.py`, `_red_green_replay_suite.py`, `commit_replay_delegate.py`, trailer/range readers and shipped-path release guard. | Expedited receipts represent deferred replay honestly; no forged normal TDD proof. Normal master checks historical provenance without rejecting a legitimate expedited commit solely for deferred replay. Normal follow-up earns real full evidence. |
| Pre-push | DT `scripts/just/check-pre-push.sh`, green-token branch, live world-reading members, delegation and fallbacks. | Select fast incident work before normal token or delegate logic; red-master may not block the designated repair/revert. No full fallback after an expedited delegation error. |
| Explicit commands and parallel aggregation | DT `scripts/just/check.sh`, `check-changed.sh`, `check-scoped.sh`, `parallel_check_dispatcher.py`, just recipes and check-target registry. | Same mode/scope as hooks; aggregate preflights, dependency closure, parallel children and direct check entry points cannot restore skipped work. Whole command/process-group timing bounds apply. |
| Fast-gate timing | Gate-run evidence and per-target timings. | Skip known slow work and avoid serial one-minute trials of every unknown target. Timeouts/deferred work are not passes. Preserve real fast-check failures. |
| Focused test selection | Changed/directly related tests, `conftest.py`, test fixtures and nested subprocess/in-process enforcement calls. | Exclude broad/spec/coverage launchers, retain relevant behavior tests and fixture negative controls; no blanket success early-return in library code. Shared test support changes do not silently expand back to the full suite. |
| Touched-file coverage | DT `checks/check_coverage_incremental.py`, `checks/per_file_coverage.py`, pytest/coverage config and subprocess instrumentation. | Explicit cumulative touched paths with selected related tests and isolated coverage data; normal thresholds for that scope. No invocation of the full-suite `check-per-file-coverage.sh` producer for local incident coverage. |
| Full coverage producers/consumers | DT `scripts/just/check-per-file-coverage.sh`, `check-coverage.sh`, coverage jobs/artifacts and PBT-coverage enforcement. | Omit PR CI coverage producers, consumers, artifacts and associated tests; full master and factory restore them. No consumer launches a replacement full suite when the producer was intentionally omitted. |
| Normal evidence caches | DT `green_token.py`, `_green_token_evidence.py`, pre-commit writer, `coverage-reuse-id.sh`, `.livespec-coverage-reuse-token`. | Mode/scope-aware reads AND writes; an expedited pass cannot mint a normal token or reusable normal coverage. Test that normal master/follow-up rejects partial evidence. |
| Delegated pre-commit | DT `pre_commit_delegate.py::run_pre_commit`, `_run_remote`, `main`, `_gate_host_authority.py`. | Mode resolved first; success does not write normal pre-commit evidence; full local fallbacks remain impossible in incident mode. Host-authority obligations have explicit incident disposition. |
| Delegated push/replay/explicit gates | DT `gate_remote_delegate.py`, `gate_runner_delegate.py::select_for_repository`, `commit_replay_delegate.py::run_replay`, remote request assembly. | Preserve typed selection in every independent entrance, mirror/ref publication and fallback; targeted commands cannot become a normal aggregate just because cluster credentials exist. |
| Gate renderer and pod | DT `ci-runner/k3s/phase2/gates/render-gate-job.sh`, `gate-job-template.yaml`, rendered check-suite argv and environment. | Explicit mode/scope transport; missing mode/suite cannot choose default installers plus full pre-push for an incident operation. Normal jobs scrub inherited flags. |
| Credential/environment boundaries | `/usr/local/bin/with-livespec-env.sh`, its owning template in 1password-env-wrapper, sudo/env/mise/git/pytest subprocesses, runtime-driver adapters. | Measure propagation and denial lists; portable explicit inner-boundary injection. The installed wrapper currently restores caller env; prove normal cleanup scrubs it rather than assuming the wrapper did. |
| Agent tool and stop guards | DT foreground/background/subagent guards; Claude and Codex livespec footgun hooks; Pi `extensions/livespec-footgun-guard.ts`; installed host hooks. | Sanctioned mode-aware commands remain usable; generic no-verify/unsafe mutation prohibitions do not become broad bypasses. Required evidence/stop guards understand deferred incident obligations and normal repayment. |
| PR mode transport | PR metadata/labels, workflow event subscriptions and trusted mode resolver. | Local env is projected into precisely the intended PR/head; label activation occurs before initial CI and label changes cannot leave old weak verdicts valid for a changed head. Never infer mode from a marker on master. |
| CI matrix/batch/direct action | DT `.github/workflows/ci.yml`, `reusable-check-matrix.yml`, `.github/actions/run-check/action.yml`, consumer-private jobs. | Fast incident selection at each real invocation, including Python modules called without just; no hidden spec/coverage work inside batched jobs. |
| CI dependency/aggregate/merge context | `ci-green`, all `needs` graphs, branch-protection contexts and matrix-fail-fast policies. | Explicit intentionally deferred semantics; no indefinite pending job and no false assertion that skipped jobs ran. Event and SHA identity must match the attempted merge. |
| Parity/completeness enforcement | DT `checks/ci_gate_parity.py`, aggregate/matrix/recipe completeness checks and their canonical copies. | Ratified exact incident shape; do not disable ordinary conformance or allow arbitrary PR-only reductions. Normal master behavior remains complete. |
| Spec enforcement and debt | Heading coverage/debt register, doctor, spec-stated judgments, scenario/reference/debt checks and local fast spec gates. | Incident's declared spec debt does not block local/PR repair; normal master remains normal and follow-up repays debt. A skipped invocation is distinct from tests of a check implementation. |
| Workflow-edit authorization | DT worktree-pack `check-no-workflow-edits.sh`, exemption file, approval labels, `_gate_host_authority.py`, CORE CI discipline. | Explicit scoped incident authorization receipt; flag confers no credentials. Same-carrier authorized host publication for workflow fixes produced by normal factory follow-up, since factory credentials lack workflow scope. |
| PR factory provenance | DT `factory_provenance_gate.py`; BF `commands/factory_provenance_check.py`, `_factory_provenance_event.py`, CI provenance job. | Incident receipt admits the local repair/revert only; normal cleanup must carry normal factory provenance. |
| Retrospective bypass audit | BF `commands/factory_bypass_audit.py::audit_pull_requests`. | Classify declared incident exceptions and outstanding repayment separately; do not suppress via permanent allow-author/allow-label rules. |
| Operator factory routing | OS `.claude-plugin/prose/drain-backlog.md` and factory exemption enum; plan/implement/drive prose; runtime bindings. | Incident local route is explicitly permitted, normal follow-up routes through factory, and background/wait/credential preliminaries cannot reintroduce slow factory admission for the local repair. |
| Incident ownership transfer | Queued dispatch/waiters, BF `_store_dispatch_claim.py::record_claim_stamp`, claim/recovery/cancellation and stale event writers. | One current owner; immutable attempt history, no duplicate dispatch and no old completion writing after transfer. |
| Branch/PR resolution | BF `commands/_dispatcher_plan_build.py`, `_dispatcher_reconcile_merged_pr.py::resolve_merged_pr`. | Attempt/phase-specific carrier branches and PR ids; first merged feat/item branch or bounded item-mention search cannot select an earlier attempt. |
| Acceptance and completion | BF `_dispatcher_acceptance_diff.py::read_merged_diff`, `_dispatcher_completion.py::complete_and_accept`, reconcile and close/no-change paths. | Acceptance receives original cumulative incident change/evidence, not only marker removal. Same-item factory reentry remains possible and no expedited merge closes the item. |
| Normal master context | All master push jobs, reusable workflows and their environment projection. | Force normal before parsing flags, even malformed ambient ones; required-job universe is the normal one for that exact merge SHA. |
| First-failure observer | DT `fleet/_reconciler_shim.py`, `reusable-master-health-reconcile.yml`, hosted controller/event delivery. | Add trusted job/check completion delivery or CI callback; completed-workflow plus five-minute schedule alone is insufficient. Observe while original CI still runs. |
| Emergency revert and merge authority | DT `cross_repo/master_health_*.py`, signing/diff guards, App authorization/rulesets and merge path. | Immediate scoped inverse of the recorded incident change, with no pre-merge tests/check waits. Provision actual no-check merge authority; signed commit creation alone is insufficient. Preserve unrelated later changes. |
| Existing reconciler coordination | Reconcile decision core, workflow gatherer and duplicated generated shim. | Incident event has one action identity; normal rerun/classification/fix-forward hold/green-revert wait cannot delay or duplicate incident revert. Preserve ordinary episode policy. |
| Recovery dependency independence | Tenant ledger, credential wrapper, factory, gates namespace and self-hosted runner pool dependencies. | Trusted operation receipts and action fences remain available outside the broken component; recovery does not require a fresh call through it. Reconcile exact receipts back to the work item when reachable, without a shadow lifecycle or duplicate action. |
| Failed-run retention | Workflow concurrency, superseded-run cancellation, matrix fail-fast and logs/artifacts. | Revert/replacement push cannot cancel the original master run or its remaining required legs; collect final failures before corrected attempt. |
| Late regression/cleanup | Master and other PR observers, affected consumer receipts, same-item recovery and normal cleanup. | Distinguish deferred-proof-only findings from actual related master/other-PR breakages. Monitor through cleanup and retain attribution after closure to reopen a late regression. |
| Release and distribution | Package/plugin releases, pinned callers, ensure-plugins, images, generated Copier templates and existing consumer config. | Release/adopt readers before use; installed build must preserve incident state. Event mode never becomes a repository/image default. |
| Generated projects | CORE `templates/orchestrator-plugin/justfile.jinja` and `lefthook.yml.jinja`, other template variants. | Inline generated gates/coverage recipes honor the same contract; updating DT shell scripts alone is insufficient. |
| Closure/proof/archive | Incident item accept/close, owning plan proof/archive, supervisor completion guards. | Incident closure requires final normal factory/PR/master proof and repaid debt; ordinary plan archive gates remain fully enforced. |

## Source-grounded review findings incorporated

The first independent OpenAI Astra audit identified eight material gaps in the
initial draft. Its observations included DT 0bef21f8 and BF e49aacfe3.

1. Repair, revert and cleanup cannot all require the marker in the resulting
   tree. Note 001 now defines identity and marker rules by mode, including normal
   context precedence over ambient flags.
2. Branch/merged-PR resolution assumes a narrower item-to-PR relation than this
   lifecycle needs. Distinct attempt/phase/carrier identities and cumulative
   acceptance evidence are now required, along with stale-completion rejection.
3. Completed-workflow and five-minute schedule triggers cannot revert on the
   first required job failure. Independent trusted early event delivery is now
   required explicitly.
4. A normal factory worker cannot publish workflow edits with its existing
   credential. The plan now requires scoped host authorization and same-carrier
   normal factory publication without broadening sandbox credentials.
5. Blanket early-return inside a check breaks in-process negative controls; for
   example Codex driver's `tests/integration/test_spec_conformance.py` calls
   heading_coverage.main() expecting both 0 and 1. Selection versus implementation
   semantics and nested enforcement are now explicit.
6. Selection must precede every token, delegation and fallback branch, including
   the gate renderer's unspecified-suite default. Both evidence writers and
   readers must respect mode/scope.
7. The retrospective factory-bypass audit and overseer exemption enum are
   independent of the PR provenance check; both are now in scope.
8. Copier templates and direct run-check actions are distinct launchers; their
   inclusion and per-consumer applicability are required for inventory closure.

The author also inspected the actual installed credential wrapper. A nonsecret
`LIVESPEC_INCIDENT_CONTEXT_PROBE=observed` passed through the wrapper and read
back as `caller_probe=observed` on 2026-11-03. This contradicts older guidance
that all caller environment is scrubbed. Note 001 now requires measured
propagation and deliberate clearing for normal contexts.

## General adversarial Astra review incorporated

The separately commissioned OpenAI Astra general review found these failure
cases in addition to the surface audit. Note 001 now carries the corresponding
contracts and controlled proof scenarios.

- Multi-commit rebase merges require the complete landed incident patch and tree
  identities. The existing `master_health_revert_commit.py` restores old parent
  bytes and `master_health_revert_guard.py` rejects later overlapping paths. The
  incident route therefore needs an inverse patch on current master, an expected
  head comparison, and an explicit owned conflict state rather than whole-file
  restoration or reverting only the terminal SHA.
- `release-please.yml` and `reusable-release-dispatch.yml` can publish/fan out
  independently. Record source-to-artifact-to-consumer attribution and stop stale
  adoption on rollback. Repair already-adopted consumers; source green alone is
  not deployed recovery. An irreversible-state change needs an existing safe
  compensating operation for unattended rollback eligibility.
- Protected `ci-green` waits for its dependency graph. Define the actual required
  failure producers as its leaf jobs/matrix legs. The observer must be armed
  before merge and execute known-good released code independently of the very
  incident tree it may need to revert.
- Deduplication alone does not fence stale actors. Use atomic per-repository
  action ownership and per-incident generation/phase validation immediately
  before side effects, with durable intent and post-timeout receipt recovery.
  A reverted attempt's old cleanup must never merge later.
- Keep work-item identity stable but make PR resolution, claims, runs and proof
  receipts attempt/role-specific. Repeated expedited attempts and later reopen
  cannot select the old merged carrier or grade only comment removal.
- Preserve unconditional first-failure rollback, then classify all failures after
  collection. Do not repeatedly reland unchanged code onto a pre-existing test or
  infrastructure failure without new repair/resolution evidence.
- A finished workflow can have skipped dependents. Record the expected job graph,
  preserve the original run, and explicitly collect missing original-tree evidence
  after rollback or keep it as unresolved debt.
- Marker validation differs for repair input/output, revert and cleanup. A
  deletion-only or strict config-format fix needs a legal adjacent existing
  code/test comment carrier without breaking the artifact's syntax.

## Anthropic Fable review incorporated

Anthropic Fable 5.1 (`claude-fable-5-1`, no fallback) reviewed the draft through
read-only tools in session 710166c3-c9dd-4fa0-8c66-8e45df726ba3. Its completed
result is stored in the ignored host evidence directory
`tmp/expedited-incident-review/fable-output.json`. It reported sixteen findings;
several described the initial text before the two Astra revisions. Dispositions:

1. **Commit replay, range and pairing:** accepted. Name the commit-msg suite leg,
   `red_green_replay.py::_commit_violates`, and source/test-pair enforcement.
   Distinct incident receipts are not full TDD trailers; historical verification
   must work on normal master without relying on the old PR event label.
2. **Commit-time and PR provenance:** accepted. The canonical installed hook and
   host mode file are independent of PR provenance. Record an audited
   `Factory-Override` explanation, tie it to the incident receipt, and handle
   label events explicitly in each consumer.
3. **Unchecked revert versus branch protection:** accepted as a material design
   conflict; Fable's suggested skipped-green CI stub is NOT adopted, because it
   still waits for CI. The chosen design is an independently authorized recovery
   controller principal and normally rolled out forge/conformance policy changes.
   Inventory `fleet/_rows_github.py`, `fleet/_reconcile.py`,
   `checks/branch_protection_alignment.py` and classic/ruleset overlap. Existing
   signing/revert helpers alone do not grant a no-check merge.
4. **Parity parser versus normative parity:** accepted. A label shape passing a
   parser that never recognized it is insufficient. Add an exact ratified
   incident form to `_ci_matrix_parse`, parity and completeness enforcement.
5. **Batched CI and extra coverage consumers:** accepted. Feed shared selected
   targets into mixed batch loops/direct actions; include incremental coverage,
   network/rate-budget conformance, doctor-static, e2e/acceptance and release gates
   in each consumer's inventory.
6. **Wrapper now restores env:** independently confirmed and already corrected.
   Normal dispatcher/factory/master must explicitly remove inherited flags.
7. **Four delegation entrances:** accepted. Incident repair/revert select host
   local before pre-commit, push, replay or detached-runner cluster submission.
   An environment variable the pod never receives cannot select its mode.
8. **Agent hooks and monitoring:** accepted. Generic no-verify/LEFTHOOK=0 bans
   remain; use sanctioned mode-aware routes and detached execution where required.
   Include driver-claude's GitHub rate-limit guard; no in-session polling design.
9. **Workflow incidents and factory credentials:** accepted. The scoped host
   workflow authorization receipt and normally validated same-carrier publication
   step resolve this without granting workflow credentials to factory workers.
10. **Reconciler deployment not universal:** confirmed. Only the core checkout of
    the four main repos carried an installed master-health shim. Rollout must
    prove each applicable controller is actually installed and running.
11. **Same-item reentry/early closure:** accepted, including resume, stranded-claim
    and recovery-routing surfaces beyond the merged-PR resolver itself.
12. **Hidden model/network admission:** accepted. Reuse the incident item, or
    provide fast canonical incident filing with normal model-backed admission
    deferred to follow-up. Master-CI preflight cannot block the local repair.
13. **Cache protections and focused primitive:** accepted with inspect-before-edit
    discipline. Existing no-skip token guards may already be sufficient at some
    writers; prove mode isolation rather than changing every cache gratuitously.
    Name `check_coverage_incremental.py` as the focused coverage starting point.
14. **Deferred spec versus normal master:** the conflict is accepted; a blanket
    ban on all spec-file edits is NOT adopted. A small complete spec co-edit may
    be needed for normal master to pass. Deferral never grants a master skip;
    exposed discrepancies trigger the ordinary incident revert/corrected attempt.
15. **Release prefix and adoption latency:** accepted. Preserve release-producing
    prefixes on shipped fixes, and track package/plugin release, sandbox build,
    fan-out and consumer CI through serving-version evidence.
16. **Label provisioning/auto-merge/plan routing lint:** accepted as inventory
    obligations; no assumption that App PRs inherit maintainer-only auto-merge.

All three reviews are design reviews, not independent plan Proof of Done. No
reviewer established that the flag is implemented or that runtime override
coverage is exhaustive. Their uninspected surfaces remain in the required
implementation reconnaissance below.

A read-only forge survey during drafting confirmed dev-tooling master currently
has classic protection with enforce_admins=true, required linear history,
strict=false and the required `ci-green` context (App id 15368), and no repository
rulesets. No protection was changed. The immediate no-check revert therefore
requires the explicit normally rolled out recovery authorization/conformance
change; it is not an existing capability the plan can assume.

## Evidence limits and required implementation reconnaissance

This is a static planning audit, not proof that the feature works or that every
installed consumer has been inspected. Complete the manifest expansion, custom
workflow inventory, alternate git-jsonl lifecycle/console writers, live forge
rulesets/App bypass grants, release/deployment triggers, installed build survey,
gate timing measurements and controlled incident drills before claiming the
plan's Definition of Done. No production failure or gate bypass was induced to
review this design.
