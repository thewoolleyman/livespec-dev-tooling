# Shipped-basis offender inventory, 2026-08-19 — the remediation is shovel-ready, with three surprises

The plan recorded per-repo COUNTS but never the offender LISTS, so whoever picks up remediation would have to re-derive them. This is the inventory.

| repo | shipped-basis offenders | note |
|------|------------------------|------|
| livespec-driver-codex | 3 | ALL in one file, `dev-tooling/codex_hook_cache_reconcile.py` (codex_home:72, state_file:89, reconcile:152). |
| livespec-orchestrator-git-jsonl | 4 | `resolve_canonical_branch`, `impl_next`, `rank_candidates`, `discover_merge_sha`. |
| livespec | 14 | Concentrated in `spec_governance/` and `io/`. |
| livespec-runtime | 15 | — |
| livespec-orchestrator-beads-fabro | 20 | — |
| livespec-overseer | 162 | — |
| livespec-dev-tooling | 3 | Already in progress in another session. |

## Surprise 1 — POSITIVE CONTROL

The livespec-runtime list reproduces, EXACTLY, the eleven offenders independently recorded in work-item livespec-dev-tooling-irtt's description months earlier: `resolve_ref`, `parse_depends_on_entry`, `parse_cross_repo_manifest`, `load_github_app_config`, `run` (credential_helper), `scan_hygiene`, `main` and `run` (hygiene_scan_cli), `detect_stale_worktrees`, `lane_of`, `is_item_ready`. Two independent derivations agreeing is evidence the harness measures what it claims.

## Surprise 2 — SOME "OFFENDERS" ARE NOT PRODUCT CODE AT ALL

- livespec-overseer: 14 of its 162 are in THREE test-shaped modules that live INSIDE the product package rather than under tests/: `overseer/test_supervisor_builders.py`, `overseer/test_signals_fakes.py`, `overseer/test_codex_sessions_fakes.py`. The universe excludes `tests/` but these are inside the package, so they are scanned.
- livespec-orchestrator-beads-fabro: 2 of its 20 are throwaway rehearsal wrappers under `plan/beads-v1-1-2-upgrade/rehearsal-package/wrappers/` (`anchor-probe.py`, `identity-probe.py`).

For these, railway CONVERSION is the wrong remedy. The right question is whether they belong in the scan universe at all — relocation or universe scoping, not conversion.

## Surprise 3 — THE COUNTS DRIFT WITHIN HOURS

Measured earlier the same day, overseer was 156 and beads-fabro 19; hours later they are 162 and 20. The fleet is actively committing. Every count must be quoted with its timestamp; a count without one is already wrong.

## How to use this

Start with **livespec-driver-codex**, because all 3 offenders sit in a single file (`dev-tooling/codex_hook_cache_reconcile.py`). Remediation here is the lowest-effort, highest-certainty unit of work and will validate the approach before tackling larger repos.

## The inventory itself

Shipped basis (the `_`-prefixed FILE skip RETAINED), each repo at its checkout tip
on 2026-08-19. `path:line` then function name. Re-derive with the harness in
`underscore-file-skip-remeasure-2026-08-19.md`, setting `skip_underscore_files=True`.

```text
## livespec-driver-codex — 3 shipped-basis offenders
dev-tooling/codex_hook_cache_reconcile.py:72	codex_home
dev-tooling/codex_hook_cache_reconcile.py:89	state_file
dev-tooling/codex_hook_cache_reconcile.py:152	reconcile

## livespec-orchestrator-git-jsonl — 4 shipped-basis offenders
.claude-plugin/scripts/livespec_orchestrator_git_jsonl/checks/work_item_merge_evidence.py:155	resolve_canonical_branch
.claude-plugin/scripts/livespec_orchestrator_git_jsonl/commands/attention_impl.py:19	impl_next
.claude-plugin/scripts/livespec_orchestrator_git_jsonl/commands/next.py:111	rank_candidates
.claude-plugin/scripts/livespec_orchestrator_git_jsonl/migration/merge_evidence_git.py:10	discover_merge_sha

## livespec — 14 shipped-basis offenders
.claude-plugin/scripts/_currency/verify.py:49	verify_currency
.claude-plugin/scripts/livespec/io/cli.py:81	emit_livespec_failure
.claude-plugin/scripts/livespec/io/streams.py:15	write_stdout
.claude-plugin/scripts/livespec/io/streams.py:19	write_stderr
.claude-plugin/scripts/livespec/spec_governance/config_edit.py:18	write_config_value
.claude-plugin/scripts/livespec/spec_governance/config_edit.py:40	write_config_map_entry
.claude-plugin/scripts/livespec/spec_governance/editing.py:51	apply_action
.claude-plugin/scripts/livespec/spec_governance/journal.py:69	append_journal_event
.claude-plugin/scripts/livespec/spec_governance/journal.py:84	append_journal_payload
.claude-plugin/scripts/livespec/spec_governance/proposal_edit.py:12	write_proposal_override
.claude-plugin/scripts/livespec/spec_governance/spec_pr_merge.py:31	effective_spec_pr_merge
dev-tooling/claude_plugin_registry.py:107	prune_dead_project_plugin_entries
dev-tooling/gh_feature_surfaces.py:89	main
dev-tooling/reap_stale_worktrees.py:277	main

## livespec-runtime — 15 shipped-basis offenders
livespec_runtime/cross_repo/resolve.py:57	resolve_ref
livespec_runtime/cross_repo/types.py:174	parse_depends_on_entry
livespec_runtime/cross_repo/types.py:211	parse_cross_repo_manifest
livespec_runtime/github_auth/config.py:46	load_github_app_config
livespec_runtime/github_auth/credential_helper.py:86	run
livespec_runtime/github_budget_client_support.py:58	header_value
livespec_runtime/github_budget_client_support.py:99	mapping_option
livespec_runtime/hygiene_scan.py:42	scan_hygiene
livespec_runtime/hygiene_scan_cli.py:23	main
livespec_runtime/hygiene_scan_cli.py:60	run
livespec_runtime/hygiene_scan_worktrees.py:61	detect_stale_worktrees
livespec_runtime/spec_governance.py:65	manifest_rows
livespec_runtime/spec_governance.py:73	documented_defaults
livespec_runtime/work_items/lifecycle.py:89	lane_of
livespec_runtime/work_items/lifecycle.py:127	is_item_ready

## livespec-orchestrator-beads-fabro — 20 shipped-basis offenders
.claude-plugin/hooks/codex_yolo_gate.py:64	gate_state
.claude-plugin/hooks/codex_yolo_gate.py:199	main
.claude-plugin/scripts/livespec_orchestrator_beads_fabro/acceptance.py:68	run_acceptance
.claude-plugin/scripts/livespec_orchestrator_beads_fabro/acceptance.py:107	run_live_acceptance
.claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/detect_impl_gaps.py:137	detect_rules
.claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/list_plans.py:29	list_plans
.claude-plugin/scripts/livespec_orchestrator_beads_fabro/intake_dor.py:144	apply_intake_dor
.claude-plugin/scripts/livespec_orchestrator_beads_fabro/spec_reader.py:50	read_current_specification
.claude-plugin/scripts/livespec_orchestrator_beads_fabro/spec_reader.py:57	read_specification_history
.claude-plugin/scripts/livespec_orchestrator_beads_fabro/spec_reader.py:66	current_specification_version
.claude-plugin/scripts/livespec_orchestrator_beads_fabro/store.py:114	read_work_items
bd-guard/bd-guard-emit.py:41	main
dev-tooling/checks/closed_item_integrity.py:223	main
dev-tooling/checks/codex_plugin_structure.py:376	main
dev-tooling/checks/pi_plugin_structure.py:286	main
dev-tooling/checks/status_conformance.py:86	main
dev-tooling/checks/work_item_merge_evidence.py:208	main
dev-tooling/checks/work_item_state_invariants.py:176	main
plan/beads-v1-1-2-upgrade/rehearsal-package/wrappers/anchor-probe.py:149	main
plan/beads-v1-1-2-upgrade/rehearsal-package/wrappers/identity-probe.py:71	main

```

## Adjudication — what an owner must NOT do with this list

**Do not treat the count as the work.** Surprise 2 is the reason: at least **16 of the
listed offenders across two repos are not product API** — 14 test-shaped modules inside
`livespec-overseer`'s package, and 2 rehearsal wrappers under `beads-fabro`'s `plan/`.
Converting those to the railway would put a `Result` return on throwaway scaffolding and
call it adoption. **The remedy there is a universe question, not a conversion**, and it
needs the maintainer, because narrowing a scan universe is the RELAXING direction and this
track exists because a check scanned zero files while reporting green.

⚠️ **I hit the same trap from the other side in this very thread.** A measurement harness
committed as a `.py` under `plan/` was refused by the commit gate — because a file under
`plan/` is first-party Python and enters `resolve_check_universe()`. `beads-fabro`'s two
rehearsal wrappers are that same fact, already merged and now convicted. This is a
recurring class, not two one-off files.

**Do not treat any number here as durable.** Surprise 3 measured overseer 156 → 162 and
beads-fabro 19 → 20 within hours of the same day. **Re-measure at the moment you start a
repo**, and quote the figure with its timestamp.

**Do not start with overseer.** Its 162 is 45% of the fleet's shipped-basis total and
roughly half of it is mirrored copies that convert for free once the primaries land — but
only for the mirrored subset, which is 44 files rather than the whole tree.

### The constraints that travel with this work

1. **Smallest repo first, end to end.** `driver-codex` (3, one file) is the right first
   unit — it validates the loop before anything expensive.
2. **Batch per repo; do not open a wide front of PRs.** Local inference zeroes the token
   cost and does nothing about GitHub runner minutes, which was half the reason this track
   was held on 2026-08-04.
3. **Do not arm the check anywhere.** Arming ahead of adoption turned five repos red
   (`46c5dab`, reverted by `f4247110`).
4. **Hold to the shipped basis** while `8zv3.5` is deferred to the panel. Everything on
   this list is convicted under BOTH candidate bases, so no ruling can un-convict it —
   which is exactly why this work is safe to start now.
5. **Route:** in-session `pi-local-llm` on `m4max/qwen3-coder-next`; no Anthropic, no
   Codex. Name the shared failure type in every brief, or the worker invents one per
   function.

### One entry deserves a flag

`git-jsonl`'s `discover_merge_sha` is on this list. The 2026-08-04 legacy handoff named it
as the *next unit* before the hold, with the caution that it "may be a legitimate absence."
It is still convicted and still undecided. And `resolve_canonical_branch`, two rows above
it in the same repo, is the `8o8e.28` subject whose escape is measured but unpriced — so
**two of git-jsonl's four offenders carry open questions rather than mechanical work.**
Its 4 is not as cheap as `driver-codex`'s 3.
