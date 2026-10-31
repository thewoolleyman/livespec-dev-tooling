# Carrier map: where each factory-spend field can be measured

Scoping by the owner seat, 2026-10-31 (~18:30Z), under the coordinator
(gitops-fleet-capacity-monitoring). Every claim below was checked against the
Honeycomb `livespec` environment's column lists and live queries, against the
orchestrator source at `origin/master` (3da35b8bd), or against upstream Codex
source at the pinned tags. Nothing here is taken from the charter's guesses.

## Assertion 1: factory Codex cached-input count

- **The producer already emits it.** Codex `codex-rs/otel/src/events/session_telemetry.rs`
  records `gen_ai.usage.cache_read.input_tokens` (and
  `gen_ai.usage.cache_write.input_tokens`) on the `handle_responses` span, next
  to the `gen_ai.usage.input_tokens` we already read. This holds at tags
  `rust-v0.153.0` and `rust-v0.153.3` (line 539). The sandbox pins
  `@openai/codex@^0.153.3`.
- **The receiver strips it.** The `codex-app-server` dataset has 79 columns and
  neither cache key is among them. The orchestrator's
  `_otel_scrub.ATTRIBUTE_ALLOWLIST` lists `gen_ai.usage.input_tokens` and
  `gen_ai.usage.output_tokens` but not the two cache keys. A `git grep` of
  `origin/master` finds them nowhere in the scrub. This is the same shape as the
  2026-09-07 sccache case (`.ai/factory-span-receiver.md`): the receiver
  allowlist strips the attribute, and the producer is fine.
- **Carrier:** a relay to livespec-orchestrator-beads-fabro to add both keys to
  the allowlist. It reaches Honeycomb only after a release, `ensure-plugins` in
  each DISPATCHING project, and a restart of that project's dispatcher loop.
  Then a host child here: `emit_factory.py` reads the measured count, prices
  from it, and drops `CACHED_SHARE` for spans that carry it. A span without it
  keeps the assumed share and is marked as assumed.

## Assertion 2: factory Claude 5-minute and 1-hour cache-write split

- **No factory carrier exists today.** The `claude-code` dataset (35 columns)
  has only `cache_creation_tokens`. Claude Code's native OTel `llm_request`
  span carries no TTL split. Local transcripts carry it
  (`usage.cache_creation.ephemeral_5m_input_tokens` / `ephemeral_1h_input_tokens`),
  but the factory's transcripts live in the sandbox on the factory host and are
  never exported.
- **Carrier, to be designed in the owning repo:** a relay to
  livespec-orchestrator-beads-fabro. It must carry the split per response,
  either by exporting it from the sandbox transcript at turn end with the
  dispatch id, or from the ACP usage stream if the adapter reports it. The
  orchestrator owns the sandbox and the receiver, so it picks the mechanism.
  Then a host child: `cev()` prices each lifetime at its own list rate.

## Assertion 3: dispatch id, run outcome and fallback on every factory spend event

- **The dispatch id is already present.** Every factory event `emit_factory.py`
  sends carries `livespec.dispatch.id`.
- **No queryable run outcome exists.** The fabro `run` span (121 in 24 h, 63
  dispatches) has `status_code` 0 on every span and no status, reason or error
  attribute. `run_turn.status` (ok 346 / error 24 / cancelled 1 over 24 h) is
  per node turn, not per run. In `livespec-dispatcher`, `livespec.outcome`
  appears only on `reflection.stall` spans. The reconcile-runs spans cover
  cancellations only. Whether a run succeeded, failed, was cancelled or went to
  rework is known to the dispatcher and the ledger, but no span says so.
- **No fallback-served flag exists.** The orchestrator knows which attempt
  served each window (`_dispatcher_cost_attempts.py`, ACP fallback priority),
  but nothing per response says a fallback model served it.
  `livespec.cost.model_resolved` is a model-resolution flag
  (`default:claude-opus-4-8`, `false` on all 2,184 `cost.report` spans in 48 h),
  not a fallback flag.
- **Carrier:** a relay to livespec-orchestrator-beads-fabro for one terminal span
  per dispatch on `livespec-dispatcher`. It carries `livespec.dispatch.id`, the
  run outcome as a bounded enum, and each attempt's window with its model and a
  fallback flag, all allowlisted. Then a host child: `emit_factory.py` joins
  each response to that span by dispatch id and time window, and restates its
  events the same way it already restates `pending` node attribution.

## Assertion 4: board panel for cost per run per day by outcome

Host only (`build_board.py`, board abHcUYvjaYf). It is blocked on assertion 3's
host child.

## Assertion 5: staleness triggers

Host only (`build_triggers.py`), and it can start now. Two findings shape it:

- Factory Claude is the fallback and factory Codex goes quiet whenever the
  factory is idle. Local Codex can also be idle for hours. A plain "no spend
  event for 2 h" trigger on those sources would fire on normal idleness, and a
  trigger that fires all the time gets ignored. So each emitter sends one
  heartbeat event per source per run to llm-spend
  (`kind=spend-source-heartbeat`, `spend.source=<one of the five>`, with the
  count of upstream records it read). The 2-hour trigger watches each source's
  heartbeat. That catches a stopped emitter or a stopped source read, and a
  quiet factory does not fire it. The existing upstream-span quiet triggers
  (factory Codex 3 h, factory Claude 24 h) still catch a producer that stops.
- The only Honeycomb recipients in env livespec are two email addresses. The
  coordinator is a session and cannot read email, so the trigger's `triggered`
  state is also exposed through a host check the coordinator runs each tick
  (`spend_staleness.py`). Reported to the coordinator for objection.

## Assertion 6: machine-readable time series from hcq.py

Host only (`hcq.py`), and it can start now. The MCP `run_query` result renders
time series as ASCII charts. The helper will issue the query with
`granularity` and return one row per bucket and group, using the endpoint's
raw-row or table form, so that no caller parses a chart.

## Routing

| Assertion | Owner | Kind |
|---|---|---|
| 1 producer side | livespec-orchestrator-beads-fabro | relay (allowlist two keys) |
| 1 host side | this plan | host child, after the relay ships |
| 2 producer side | livespec-orchestrator-beads-fabro | relay (design and carry the TTL split) |
| 2 host side | this plan | host child, after the relay ships |
| 3 producer side | livespec-orchestrator-beads-fabro | relay (terminal dispatch span) |
| 3 host side, 4 | this plan | host children, after the relay ships |
| 5, 6 | this plan | host children, start now |

Host children run in `~/token-spend-report` on this host. That is not a
factory-dispatchable repository, so the owner seat does them directly. The
orchestrator relays go through petri's factory queue.
