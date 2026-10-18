## The maintainer's statement of what done means

"I want all this token spend represented as a honeycomb report." / "This needs to be viewable via a direct URL that I can click on and open." / "accomplish the one goal I gave you, which is a pie chart breaking this down by where the tokens are spent: in the factory or locally." / "Now I want pie charts breaking the factory and non-factory subcategories along different axes. One chart that splits them by the model type (Codex versus Anthropic) and the level of the model and thinking intensity" / "Add a chart which shows the LLM spend in tokens, broken down by factory node. This does not have to be split out by provider or model type." / "What I meant was the Graphviz `.step` of the workflow graph. Each node has a different model assigned to it. That is how I want you to break things down. I don't care about which factory installation it's running on. Different factories should be aggregated." / "It's really just a backfill of what you've already done to make it official, get it done and committed."

## Definition of Done assertions derived from that statement

- Opening https://ui.honeycomb.io/thewoolleyweb/environments/livespec/board/abHcUYvjaYf in a browser signed in to the thewoolleyweb Honeycomb team shows a pie of LLM spend in USD split into factory (Fabro sandboxes) and local sessions (vps), for both the last 7 days and the last 24 hours.
- The same board shows factory spend and local spend each split by provider (Anthropic versus OpenAI Codex), model and thinking effort, for both the last 7 days and the last 24 hours.
- The same board shows factory LLM tokens split by Fabro workflow graph node, the .step nodes such as implement, review and dod_gate, with every factory installation aggregated together, for both the last 7 days and the last 24 hours.
- The board keeps updating with no session running: the vps user timer token-spend-local.timer is active, and local Claude Code and Codex responses from the last hour appear in the livespec llm-spend Honeycomb dataset.

# Token spend analysis — charter and backfill (2026-10-18)

This plan makes official work the `token-spend-analysis` session did on 2026-10-17 and 2026-10-18 before any plan existed: an
analysis of LLM spend, factory versus local, published as a live Honeycomb board. The maintainer asked for the backfill on
2026-10-18 ("It's really just a backfill of what you've already done to make it official") and pre-authorized every human
approval for it.

## The deliverable

One Honeycomb board in the `livespec` environment, team `thewoolleyweb`:
<https://ui.honeycomb.io/thewoolleyweb/environments/livespec/board/abHcUYvjaYf> ("LLM spend — factory vs local").

| Row | Panels (7 days and 24 hours each) | Status 2026-10-18 |
|---|---|---|
| 1 | USD spend, factory versus local | live, verified in a browser |
| 2–3 | factory and local USD spend by provider · model · effort | live, verified in a browser |
| 4 | factory tokens by factory node | WRONG AXIS — see "Correction" |
| 5 | method notes (text panel) | live |

One board cannot span Honeycomb environments, so local spend (which the vps collector exports to `agent-activity`) is fed into
`livespec` by a host-local emitter rather than queried in place.

## Sources

- **Factory Claude** — `livespec/claude-code` `claude_code.llm_request` spans: `model`, token fields, `livespec.dispatch.id`.
  Priced in the board's calculated field `spend_usd` from token counts.
- **Factory Codex** — `livespec/codex-app-server` spans carry `gen_ai.usage.*` and the dispatch id but no model and no cache
  split. Factory Codex runs stopped 2026-10-15; they were backfilled once into `llm-spend`, each dispatch attributed to its
  run's main Codex model and effort read from the run spec (`acp.command` / `CODEX_CONFIG`), with a 98.5% cached share
  assumed from local Codex sessions.
- **Local Claude Code** — `~/.claude/projects/**/*.jsonl` transcripts (model and `effort` per response).
- **Local Codex** — `~/.codex/sessions/**/*.jsonl` (`turn_context` model and effort, `token_usage_record` usage).

USD is API list price; actual billing is subscription quota, so read it as relative weight. OpenAI prices came from the OpenAI
ChatGPT rate card (help.openai.com article 20001415); gpt-6.1-sol was unpriced and shows $0.

## The host-local machinery (not in this repository)

Everything runs as the `ubuntu` user on the vps, under `~/token-spend-report/`:

- `scripts/emit_spend.py` — sends local Claude and Codex responses (and, with `--factory-codex`, the one-off factory Codex
  backfill) to `livespec/llm-spend` with the `HONEYCOMB_INGEST_KEY_LIVESPEC` from the otel-collector's `.env`. Idempotent
  through `state/sent-llm-spend.json`.
- `scripts/build_board.py` — rebuilds every board panel through the Honeycomb API with the livespec configuration key
  (`with-livespec-env.sh`); that key can create queries and edit boards but cannot RUN queries, so investigation queries ran in
  the logged-in Honeycomb UI through Playwright.
- `scripts/factory_map.py` — dispatch-to-factory map from each Fabro server's `fabro ps -a --json` (superseded by the
  correction below).
- `~/.config/systemd/user/token-spend-local.{service,timer}` — every 10 minutes: emit, refresh map, rebuild the board only when
  its inputs changed.

## Correction recorded 2026-10-18

The maintainer's request "a chart which shows the LLM spend in tokens, broken down by factory node" was first built as tokens
per factory INSTALLATION (legacy / hp-candidate / petri). The maintainer corrected it:

> You got the factory node feature completely wrong. What I meant was the Graphviz `.step` of the workflow graph. Each node has
> a different model assigned to it. That is how I want you to break things down. I don't care about which factory installation
> it's running on. Different factories should be aggregated.

So the panel must group tokens by workflow graph node (`implement`, `review`, `dod_gate`, `proof_capture`, `proof_verify`,
`review_fix`, `fix`, `disposition`, `pr`, …) summed across every factory. The open question is attribution: the token spans
carry only `livespec.dispatch.id`; the `livespec/fabro` dataset carries `fabro.node` and `trace.trace_id`, and Fabro's own run
records report zero usage per stage. The next step is to find the link (shared trace, session id, or time window per node
within a dispatch) and rebuild the panel on it, removing the installation split.

## Known gaps

- Factory Claude effort is inferred from the run spec (`CLAUDE_CODE_EFFORT_LEVEL`); sonnet-4.6 shows "medium or high".
- `codex-unattributed` factory Codex dispatches are priced as gpt-5.6-sol.
