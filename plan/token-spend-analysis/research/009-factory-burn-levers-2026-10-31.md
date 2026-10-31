# Factory burn levers, measured (2026-10-31)

This note records spend findings measured on 2026-10-31 for the capacity coordinator (gitops-fleet-capacity-monitoring, epic
`livespec-dev-tooling-dfixhe`). The 07:12Z handoff on this plan's epic said they were worth keeping. It commissions no work: the
maintainer is still reviewing notes 006-008, and nothing is to be filed from this plan until they reply.

Sources, all on the vps under user `ubuntu`:

- The queries are in `~/token-spend-report/scripts/burn_levers_q.py`. They read the `livespec/llm-spend` dataset, schemas 2 and 6.
- The raw results are in `~/token-spend-report/node/burn-levers-2026-10-31.json`. It holds keys `q1` (factory, per node and
  provider, 48 h), `q1_runs` and `q1_node_runs` (distinct dispatches), `q3` (headless `claude -p`, per consumer and model, 7 d)
  and `q4` (all consumers, 7 d).

The figures below were re-read from that file at 07:30Z while this note was written. Where a figure was only reported in the
handoff and is not in the file, the note says so.

## Factory cost per run (48 h)

There were 83 distinct dispatches and $551 of factory spend: $360 Anthropic and $191 OpenAI. That is about $6.65 per run.

| Node | Anthropic | OpenAI | Dispatches touching it |
|---|---:|---:|---:|
| implement | $167.51 | $134.85 | 75 |
| proof_capture | $63.86 | — | 61 |
| proof_verify | $43.60 | — | 60 |
| review | $41.84 | $3.47 | 61 |
| dod_gate | $27.47 | — | 81 |
| fix | $11.11 | — | 9 |
| pending (no node yet) | $0.00 | $52.86 | 78 |
| review_fix, disposition, unattributed | $4.67 | — | — |

Per touching dispatch, implement costs about $4.00, proof_capture $1.05, proof_verify $0.73, review $0.74 and dod_gate $0.34.

`pending` is not a workflow node. It is spend `emit_factory.py` recorded with no node attached; why those responses carry none
was not investigated for this note.

**Implement on Claude was old routing draining out.** The $167.51 of Anthropic implement spend came from dispatches routed
before implement moved to Codex. The handoff reports it at zero since 2026-10-31T02Z. `llm-spend` carries no field recording that
a turn ran on a fallback model, so this cannot be queried directly. A fallback field is a candidate emitter improvement.

## The qbtf7s inline scripts are a small lever

The handoff measured the inline scripts that `bd-ib-qbtf7s` targets at 62.7 KB, about 16-21k tokens. The Claude nodes late in a
run start 15-25k tokens higher than implement does. That costs about $0.30-0.40 per run, which is about 5% of $6.65. It is worth
doing, but it is not where the money is. (These context-size figures come from the handoff and are not in the raw file.)

## Host DoD judges

Headless `claude -p` from the orchestrator checkout cost $1,500.39 on `opus-4.8` (750 responses) over the 7 days, against
$337.48 on `sonnet-5.5` (1,347 responses). The handoff puts the daily rate at $966/day on 2026-10-25 and about $18-24/day now.
The cause is the model change to `sonnet-5.5`. `bd-ib-55vxu5` has not been shown to have caused the drop, so do not credit it
with the saving.

## Where the 7-day money went

The total for all consumers over 7 days was $14,377.02.

| Sink | 7-day USD |
|---|---:|
| Factory Codex `implement` | $2,313.13 |
| Headless `claude -p` (judges; now on sonnet) | $2,215.31 |
| Local Claude sessions, all rows | $5,506.53 |
| — of which session name unset | $1,342.29 |
| — of which `petri-factory-on-gmktec` (including its correction row) | $1,426.43 |
| — of which `gitops-fleet-capacity-monitoring` | $484.20 |
| Factory Anthropic `implement` | $536.88 |
| Local Codex sessions | $396.75 |
| Factory Codex `review_fix` / `proof_capture` / `review` / `fix` | $322.58 / $290.12 / $206.35 / $177.98 |

The handoff gave local seats as "about $4k". The file's local-session rows total $5.5k. The difference is mostly the $1,342
of session-unnamed spend, which the handoff appears to have left out. That row is a coverage gap in `session.name`, and it is
the same kind of gap assertion 8's reconciliation is meant to surface.

## Long-context seats

These figures come from the handoff and are not in the raw file.

- A seat costs about $0.022 per 100k tokens of context, per response.
- A ledger-handoff restart pays for itself above about 300k tokens of context. The recommended threshold is about 400k when 50
  or more turns remain.
- Petri spends 54% of its cost above 600k tokens of context.
- When a seat sits idle for more than an hour, the prompt cache expires. The next response re-writes a 600k+ prefix for about
  $3-5. The spikes on `github-app-checks-read` are this.

## Late-node cache writes: once per session, not re-written (lever 3)

The coordinator asked whether proof_capture, proof_verify and review re-write their prompt cache. Each of them writes 10-12M
cache tokens per 48 h. The answer is no: each session writes its prefix once.

The query is `~/token-spend-report/scripts/cache_rewrite_q.py`, summarised by `cache_rewrite_report.py`. It reads schema 6,
factory, `cost_usd > 0`, per response (`trace.span_id`), over 48 h. The raw rows are in
`~/token-spend-report/node/cache-rewrite-2026-10-31.json`: 5,186 responses, all on `sonnet-5.5`.

| Node | Runs | Sessions | Cache write $ | $/run | First write per session, P50 tokens |
|---|---:|---:|---:|---:|---:|
| proof_capture | 62 | 104 | $31.11 | $0.50 | 109k |
| review | 51 | 83 | $25.43 | $0.50 | 103k |
| proof_verify | 59 | 92 | $25.03 | $0.42 | 103k |
| implement | 59 | 60 | $22.87 | $0.39 | 88k |
| dod_gate | 82 | 95 | $19.32 | $0.24 | 86k |

- A session reads a shared 22,104-token prefix from cache, then writes 85-111k tokens on its first response, for about
  $0.25. After that, each response writes only the new turn: the per-response P50 is 2-4k tokens.
- Only 8 of about 470 sessions had a second write over 50k tokens, and each of those came with a large cache read. They are
  large mid-session additions, not misses.
- First writes are 82-86% of the late nodes' cache-write cost. Cutting writes to one per session would therefore save about
  nothing, because they already are.
- The real lever is sessions per run. The late nodes average 1.6-1.7 sessions per run, against implement's 1.0. The extra
  sessions cost about $27 per 48 h. This note does not establish whether they are node re-entries (fix→review loops) or
  subagents with their own session id.
- No TTL split is recorded for factory Claude, so writes are priced at the 5-minute rate. If Claude Code actually writes at
  the 1 h TTL, these dollar figures are about 1.6x too low.

## What this changes for the plan

Nothing in the Definition of Done. These are uses of the board, not repairs to it. Two observations bear on assertions already
on record:

- The $1,342 session-unnamed row is consistent with assertion 8 being graded on surfacing gaps (the 2026-10-28 ruling).
- A fallback-model field would let the board show routing drain directly. It is not an assertion and is not filed. It is a
  candidate for the maintainer's review of notes 006-008.
