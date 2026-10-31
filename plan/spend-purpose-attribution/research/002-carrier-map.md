# 002 — Scope and carrier map

Owner seat for `spend-purpose-attribution` (epic `livespec-dev-tooling-vf3bqf`), 2026-10-31, under the coordinator
`gitops-fleet-capacity-monitoring` (epic `livespec-dev-tooling-dfixhe`).

Every figure below comes from Honeycomb env `livespec`, dataset `llm-spend`, queried through `hcq.py` with
`HONEYCOMB_MCP_API_KEY_LIVESPEC`, window `-7d` ending 2026-10-31 ~17:20Z, unless stated otherwise.

## What the 7-day spend looks like

Local Anthropic spend, broken down by `consumer.kind`:

| consumer.kind | USD |
|---|---|
| local session | 5,757 |
| claude -p | 2,239 |
| (empty: early-schema events with no consumer) | 565 |

The `local session` figure is too high. **$1,363 of it (23.6%) has an empty `session.name`, and nearly all of that is
headless judge and grader traffic filed as `local session`.** The classifier treats a response as headless when
`terminal.type == non-interactive` or `entrypoint` starts with `sdk`. Older events reached Honeycomb without
`entrypoint`, so a `claude -p` launched from a herdr pane (which has `terminal.type=herdr`) counted as a local session.
In the last 24 h the split is correct: `claude -p` / `sdk-cli` / `herdr` = $87, and no unnamed `local session` rows
appeared. The misfiling is historical and does not affect measurements taken after the fix.

## Assertion 1 — `spend.purpose` on every `claude -p` response

### Who launches `claude -p` (7 days)

I classified 2,375 headless-shaped sessions, $3,605 in total, by their first prompt: the `queue-operation` enqueue
content, or else the first user record.

| Launcher (first-prompt signature) | Sessions | USD | Share |
|---|---|---|---|
| spec-stated judge: "You are judging ONE behaviour statement against a RATIFIED specification" | 1,426 | 2,843 | 78.8% |
| Definition-of-Done gate grader: "# Definition-of-Done gate — grade the brief before anything is built" | 874 | 641 | 17.8% |
| long tail: independent replayers, completeness reviewers, ratification reviewers, PoD verifiers, research briefs, `ok` probes | ~75 | ~121 | ~3.4% |

The judge prompt is `JUDGE_PROMPT` in `livespec-runtime/livespec_runtime/spec_stated.py`, vendored into the
orchestrators. The DoD gate prompt is `.fabro/workflows/implement-work-item/prompts/dod-gate.md` in the orchestrator,
and `dev-tooling/dod-preflight.sh` (around line 255) runs it as `claude -p`.

### Carrier

- **Primary: the launcher names the session.** `claude -p --name purpose:<role>[@<plan-slug|item-id>]`. I verified on
  2026-10-31 that `claude -p --name X` writes `custom-title` and `agent-name` records into the transcript, and
  `emit_spend.local_claude()` already reads those records as `session.name`. The emitter parses the `purpose:` prefix
  into `spend.purpose`, and the `@` suffix into `spend.plan` or `spend.work_item`. This needs no side channel and no
  new emitter input.
- **Fallback: a prompt-signature table in the emitter.** It maps the first prompt to one of `judge`, `dod-gate`,
  `replayer`, `completeness-reviewer`, `ratification-reviewer`, `verifier` or `research`, and to `unclassified`
  otherwise. On the measured mix this alone covers at least 96.6%, which already meets the under-5% target without any
  launcher change. The primary carrier makes that coverage survive prompt rewording, and lets a new launcher declare
  itself.
- **Relay R1 (orchestrator, through petri's queue):** the spec-stated judge launcher and the DoD-gate grader pass
  `--name purpose:judge@<item>` and `--name purpose:dod-gate@<item>`. The R1 item must first find the call site that
  produced the `sdk-cli` judge transcripts.
- **Finding F1 (spend that no emitter sees):** the dispatcher's host DoD judge
  (`_dispatcher_dod_judgement_prompt.judgement_argv`) runs `claude -p ... --no-session-persistence`. That call writes
  no transcript, so its spend never reaches `llm-spend` at all. Assertion 1 is untouched, because it covers only
  responses that are sent. Assertion 4's per-plan total is understated by whatever these calls cost. Relay R2
  (orchestrator) has two options: emit the usage that the `stream_usage` path already reports, or drop
  `--no-session-persistence` for the judge.

  **F1 sized (2026-10-31 ~18:00Z): the loss has not happened yet. It will happen silently.** On a probe, `claude -p
  --no-session-persistence` wrote no transcript at all. Yet DoD-gate transcripts that carry the dispatcher's own
  `HOST_ENDING_CONTRACT` were still being written at 17:58Z. They also show no `--add-dir` directory, so the dispatcher
  builds running now predate `e501307e4` (2026-10-28), the commit that added the flag. When a dispatcher restarts on a
  build that has it, the DoD-gate spend leaves `llm-spend` with no error. That spend is $641 over 7 days: 874 sessions,
  about $0.73 each, 17.8% of headless spend. It was measured from the transcripts, not estimated. For comparison, the
  ledger holds 319 `livespec-dod-judgement` records over the same 7 days across 7 tenants (orchestrator 213, dev-tooling
  46, overseer 35, livespec 14, runtime 6, console 4, dolt-server 1). A judgement can run several candidates, which
  explains why there are more sessions than records. R2 is therefore a priority relay, and it must land BEFORE the
  newer builds take over.

## Assertion 2 — plan, work item or standing role on every local session response

Measured over local session spend ($5,757):

| How `session.name` resolves | USD | Share |
|---|---|---|
| equals a plan directory slug in a fleet repo (`/data/projects/*/plan/{,archive/}*`, 17 repos) | 3,624 | 62.9% |
| named, but not after any plan: `github-app-checks-read` 406, `caam-anthropic-loop-runner` 291, `caam-reserve-release` 60, `overseerd` 14 | 771 | 13.4% |
| empty (mostly misfiled headless traffic; see above) | 1,362 | 23.6% |

### Carrier

The carrier is emitter-side and host-only. No launcher change is needed.

1. If `session.name` is a fleet plan slug, set `spend.plan` to it.
2. If `session.name` is in the standing-role table (`caam-anthropic-loop-runner`, `caam-reserve-release`, `overseerd`,
   plus coordinator and overseer seats that do not carry a plan name), set `spend.role` to it.
   `github-app-checks-read` must first be confirmed as a plan in a repo outside the scan, or as a role.
3. Otherwise, if the first prompt matches `resume plan epic <id>` or names a work item id, resolve it through each
   repo's `plan/*/associated_work_item_id` and set `spend.plan`, or set `spend.work_item`.
4. Otherwise nothing is set, and the response counts against the under-10% target.

Projected coverage: 62.9% + 13.4% of today's base, with the empty bucket mostly leaving the denominator once headless
traffic classifies correctly. The 7-day number cannot be read off honestly until it is measured on a full day after the
fix. Unnamed interactive seats remain as a residual. The coordinator owns seat-naming discipline: every herdr seat is
named after its plan or role.

## Assertion 3 — plan slug on every factory spend event

`emit_factory.py` already sends each factory Codex and Claude response with `work.item.id` and `livespec.dispatch.id`.
The carrier is a host join: work item, then parent epic (the union of the dotted-id prefix and the `parent-child`
edge, per CLAUDE.md), then that epic's `metadata.plan_slug`, read per tenant through `bd` under the wrapper. Results
are cached per item, because the MCP query budget (100/h) is shared with the dispatcher's reflector, and `bd` reads
cost no Honeycomb queries. The sibling plan `factory-spend-accuracy` edits `emit_factory.py` too, so this change lands
on top of its commits, never alongside an uncommitted edit.

## Assertion 4 — spend per plan in one query, and the board panel

This follows assertions 1–3. One query: `SUM(cost_usd)` broken down by `spend.plan`, filtered to `spend.schema` in
(2, 6) so that factory Claude (schema 6) and the rest (schema 2) both count and nothing is counted twice. It becomes a
panel on the llm-spend board through `build_board.py`.

## Assertion 5 — context size and compaction marker

**Done on the host: commit `8c5e119` in `~/token-spend-report`.** Every local Claude response now carries
`context_tokens` (input + cache read + cache write). The first real response after a `compact_boundary` carries
`context.compacted=true`, `context.compact_trigger`, `context.compact_pre_tokens` and `context.compact_post_tokens`.
Verified against transcript `7571a4e1`: 6 boundaries gave 6 marks, and context fell from 529,721 to 96,527 at the first
one. Live verification is the first marked event in Honeycomb after the next compaction anywhere in the fleet.

## Children and relays

Filing waits on `capture-work-item`: orchestrator build `02278cbd1e01` cannot import `livespec_runtime`, and the fix is
in flight under `anthropic-burn-mitigation`. The sibling plan made the same choice. Until filing works, this table is
the plan of record.

| # | Kind | Work | Depends on |
|---|---|---|---|
| H1 | host | emitter `spend.purpose` (name prefix, then signature fallback) | DONE (`e1d1d68`) |
| H2 | host | emitter `spend.plan` / `spend.role` / `spend.work_item` for local sessions | DONE (`e1d1d68`) |
| H3 | host | factory join from work item to plan slug in `emit_factory.py` | the sibling plan's commits |
| H4 | host | per-plan query and board panel | H1–H3 |
| H5 | host | context size and compaction marker | DONE (`8c5e119`) |
| R1 | orchestrator, through petri | `--name purpose:…` on the judge and DoD-gate launchers | — |
| R2 | orchestrator, through petri | make the `--no-session-persistence` host-judge spend visible (F1) | sizing |

## H1 and H2 landed (host commit `e1d1d68`, `scripts/attribution.py`)

I replayed the last 24 h of transcripts through `local_claude()` without sending anything:

- `claude -p`: $88.4 in total, 0% `unclassified`. The DoD gate was $70.6, replayers $15.5, `/livespec` commands $2.4.
- Local sessions: $980.8 in total, 0.2% unattributed. 76.4% resolved by plan name, 18.9% by role name and 4.6% by a
  plan named in the first prompt.

Both are well inside the under-5% and under-10% targets. The assertions are judged on a full UTC day of live events
after the fix, the first being 2026-11-01.
