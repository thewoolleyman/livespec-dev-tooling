# RGR cycle latency + agent-session efficiency — proposal

Written 2026-08-17 against `livespec-dev-tooling-e60` (child of epic
`livespec-dev-tooling-7us`), turning the item from a USER-REQUESTED
placeholder into an actionable proposal. Read directly against this repo's
code (`livespec_dev_tooling/otel_step_timer.py`,
`livespec_dev_tooling/checks/red_green_replay.py`,
`livespec_dev_tooling/parallel_check_dispatcher.py`) and against e60's own
comment history and the sibling `performance-improvements-01` plan's
`research/fleet-throughput-bottlenecks.md`.

**Tool constraint, stated up front:** this session had no Honeycomb MCP tool
bound (the `honeycomb:*` skills are loadable but no `mcp__honeycomb__*`
function appeared in the deferred-tool list), so no fresh Honeycomb query ran
here. Every dataset figure below is either read from e60's own recorded
history or copied from `fleet-throughput-bottlenecks.md`'s already-queried
2026-08-16 figures (with its query permalinks) — none of it is fabricated,
but none of it is freshly re-verified either. The instrumentation gap this
proposal fixes (§3) is exactly what would let this kind of analysis be
Honeycomb-live in a future session instead of code-reading + old query
results.

## 0. Scope — what this item owns and what it does not

e60's 2026-06-14 narrowing comment already resolved the ambiguity in its own
title ("propose Honeycomb agent observability with a reflect loop"): the
observability pipeline (host OTLP receiver, sandbox CC-OTel, the
`claude-code` + family Honeycomb datasets) and the reflect-loop CONSUMER
(headless reviewer filing dedup-first work-items + ratified lessons) are
BOTH already live, delivered by `impl-beads-29f.1`/`.3`/`.4` in the
`livespec` repo's tenant. This item must not re-propose or duplicate that.

What's genuinely left, per that narrowing plus the 2026-08-16 comment:

1. The **RGR-cycle-specific instrumentation gap** — the actual hook legs
   (Red commit, Green amend, pre-push replay) and local/detached `just
   check` gate runs are NOT in the observability pipeline at all (§3).
2. The **six user-enumerated efficiency angles** — LSP, structural grep,
   progressive disclosure, layered instructions, architecture diagrams, RGR
   mechanics (§4).
3. **Metric definitions + baselines** on top of the now-live telemetry,
   flagged missing since the first comment (§5).

Related-but-distinct, per the 2026-08-16 comment, is `livespec-s43svm.20`
in the separate `livespec` repo — Honeycomb/OTel observability for the
fleet's new k8s CI runner infra (Kueue/ARC). That is CI-infra-level
(queue time, pod scheduling, runner contention — see Finding 3 of
`fleet-throughput-bottlenecks.md`); this item is RGR/agent-loop-level (hook
leg timing, local gate runs, agent-turn efficiency). §3.3 below names the
one place they'd share a surface (a `ci.job` queue-time attribute) and
explicitly leaves that to s43svm.20 rather than duplicating it here.

## 1. What an RGR cycle costs today — the evidence that exists

e60's own filing already carries the best available numbers, from the
2026-06-12 night session:

- Multi-RGR items are heavyweight: `dgu` = 7 RGR cycles, ~97 min, ~397K
  tokens, 196 tool calls; `tenpup` = 3 cycles, ~310K tokens, 150 calls;
  `8m2` = ~222K tokens, 120 calls.
- Sandboxed (Fabro/ACP) runs of multi-RGR items hit the ~2h ACP turn
  ceiling and DIED (`p60`, `tenpup`, `kgq`); the same items completed fine
  as host sub-agents — so per-cycle latency, not per-cycle correctness, is
  what pushes sandbox runs over the ceiling.
- One observed Red pass cost ~3 min of pytest alone; one sub-agent ended
  its turn just to wait for the Green-amend hook (a full resume
  round-trip).

This session (2026-08-16/17, `ci-gate-latency`/`performance-improvements-01`
epic dispatches) reproduced the same qualitative pattern live: repeated
multi-minute `just check` gates, agents ending turns to wait on a
background gate rather than continuing other work, and — per the sibling
research note's Finding 1 — the full pytest+coverage suite running TWICE
per gate (`check-coverage` + `check-per-file-coverage`, ~2,434s of a
~2,446s local gate wall on the measured run). That finding is filed as
`livespec-dev-tooling-7us` epic work via `performance-improvements-01`, not
duplicated here — it's cited because it's direct, fresh evidence that gate
wall-time (which RGR pays three times: Red, Green, pre-push) is dominated
by one fixable duplication, not by inherent pytest cost.

**The gap:** none of the above is queryable. It's all reconstructed from
ticket prose and manual `tmp/gate-runs/*/output.log` reads (plain text:
`started_at`, `finished_at`, `exit_code`, a log blob — no structured
per-target timing, no OTLP). `git log` timestamps in dispatcher journals are
the only other source. There is no dataset today where "show me every RGR
cycle in the last 14 days ranked by Red→Green wall time" is a query instead
of an archaeology project.

## 2. What's already instrumented (read from code, not assumed)

`livespec_dev_tooling/otel_step_timer.py` is the ONE piece of RGR-adjacent
OTel instrumentation that exists. It:

- wraps a single Fabro **sandbox prepare step** (`livespec-step-timer
  <step-name> -- <command...>`), baked onto the sandbox image PATH;
- times it with `time.time_ns()`, runs the command with stdio passed
  through unchanged, and best-effort POSTs one OTLP/HTTP-JSON span to
  `$LIVESPEC_SANDBOX_OTEL_ENDPOINT` (default `http://172.17.0.1:4318`)
  into the `fabro-sandbox` Honeycomb dataset;
- is deliberately stdlib-only (runs before `uv sync`) and swallows every
  network failure so a telemetry outage never changes the wrapped
  command's exit code or timing — "a broken stopwatch never breaks the
  run."

It does NOT cover: the RGR hook itself (`red_green_replay.py` — grepped,
zero references to `otel`/`OTLP`/`honeycomb`/`step-timer` in that module),
`just check`'s own per-target run (see §3.2), or anything running on the
HOST outside a Fabro sandbox (a local dev session, a host sub-agent
dispatch). This matches `fleet-throughput-bottlenecks.md`'s telemetry-gaps
section, queried live in that session: `claude_code.tool.execution` MAX
duration is 3.5s in Honeycomb — i.e. long-running gates never appear in
that dataset at all, because nothing spans the whole gate; only
per-tool-call spans exist, capped at the length of one tool call.

## 3. Minimum instrumentation to close the gap

Three concrete, additive changes — no new infra, no new dataset design,
reusing the exact pattern `otel_step_timer.py` already proved out.

### 3.1 Span the three RGR hook legs

`red_green_replay.py`'s commit-msg hook already knows exactly when each
leg starts and ends (it invokes pytest itself and inspects the result to
write the `TDD-Red-*`/`TDD-Green-*` trailers) and already runs on the HOST,
not in a sandbox, so it can talk to the host OTLP receiver directly with no
network hop through `172.17.0.1`. Proposal: factor `otel_step_timer.py`'s
`build_trace_payload`/`post_span` pair (or a near-identical stdlib-only
twin, since the hook already runs inside the repo's venv and isn't under
the sandbox's before-`uv-sync` constraint) into a tiny shared emitter, and
wrap each leg:

- `rgr.red` — staged test file, pytest exit code, wall time, failure
  reason (already computed for the `TDD-Red-*` trailer).
- `rgr.green` — staged impl paths, pytest exit code, wall time.
- `rgr.push_replay` — the pre-push range-replay check's re-run, same
  shape.

Route to a NEW `service.name` (`rgr-hook` or similar) so it lands in its
own Honeycomb dataset rather than overloading `fabro-sandbox`, which is
scoped to sandbox prepare steps by name. Each span should carry
`work_item_id` (already read from env by the sandbox timer's pattern) and
`repo` so cross-repo RGR latency becomes one query.

### 3.2 Export the per-target timing `parallel_check_dispatcher.py` already computes

`parallel_check_dispatcher.py` (landed under `7us.3`) already builds a
`TargetResult` per check target with `wall_time_s` and already emits
"machine-readable per-target timing events on stderr (structlog JSON)" —
this is the CHEAPEST lever in this proposal: no new measurement, only a new
export. Add an OTLP emit call alongside the existing structlog write (same
best-effort, non-blocking pattern — a telemetry POST failure must not
affect the check's exit code), one span per target: `check.target` with
`target.name`, `wall_time_s`, `exit_code`. This directly answers "which
check target is slow on THIS run" without reconstructing it from
`tmp/gate-runs/*/output.log`, and gives `just check`'s local/detached runs
(currently invisible per §2) a Honeycomb presence for the first time.

### 3.3 Fix the two dataset gaps `fleet-throughput-bottlenecks.md` already flagged as this item's scope

Both read directly from that research note's "Cross-references and
telemetry gaps" section, queried live 2026-08-16:

- `ci.run` spans carry an empty `ci.conclusion` attribute (query
  `m7Vh1wwuwkh`) — populate it from the workflow run's actual conclusion so
  CI-run-level success/failure is queryable without joining to GitHub.
- No queue-time attribute exists on `ci.job.*` spans, so CI-side
  queue-wait can't be separated from execution-slowdown (this is the ONE
  point of potential surface overlap with `livespec-s43svm.20`'s k8s
  Kueue/ARC observability work — that item owns the runner-pool side of
  queue time; this item's interest is narrower, just wanting the
  attribute to exist on the job span so an RGR pre-push CI wait can be
  decomposed. Coordinate rather than duplicate when either is picked up,
  per the 2026-08-16 comment.)

### Non-goals (explicitly, to prevent scope creep on re-read)

No new reflect-loop consumer, no new headless reviewer, no new
lessons-file mechanism — all shipped by `impl-beads-29f.4`. No new
dataset design beyond routing (§3.1's new `service.name`) — reuse the
existing OTLP receiver + Honeycomb `livespec` environment. No k3s/podman/
runner-pool changes — that's `s43svm.20`'s surface.

## 4. The six efficiency angles — triage

Quick assessment of each, since e60's filing enumerated them without
prioritization:

1. **Language servers for agent sessions.** High potential value (turns
   grep-and-read into targeted symbol lookups) but genuinely large scope —
   needs its own investigation of which LSP a headless coding agent can
   drive non-interactively. **Defer**; not shaped enough to file as a
   ready work-item from this pass.
2. **Structural/AST grep + indexed search.** Smaller, more mechanical:
   `ast-grep` or similar could replace some of the "burn ~150K tokens
   reverse-engineering the hook" pattern e60 itself records. **Worth a
   scoped follow-up item** — narrower than #1, testable in one repo first.
3. **Progressive disclosure of prompts/briefs.** This is a prompt-authoring
   discipline, not a tooling change — applies today, needs no new
   infrastructure. **Recommend as an authoring practice**, not a
   work-item: briefs/skills should load detail on demand rather than
   front-loading it, consistent with the `.ai/<topic>.md` progressive-load
   convention this repo's `AGENTS.md` already documents for maintainer
   docs. The same discipline should extend to agent-facing prose (skill
   bodies, dispatch briefs).
4. **Layered instruction files.** Already substantially DONE in this repo
   (the `.ai/<topic>.md` convention referenced throughout `AGENTS.md`) —
   what's not yet verified is whether it extends to every directory level
   the six angles imply (family/package/dir, not just repo-root). **Defer
   to a fleet-wide audit**, not new mechanism.
5. **In-repo agent-readable architecture diagrams.** Also already
   underway (the Mermaid convention in `SPECIFICATION/spec.md`, the W0
   standard cited in e60). **No new item** — track via existing
   diagram-coverage work, not this item.
6. **RGR-mechanics options** (scoped pytest at Red/Green, persistent test
   daemon, stub-tolerant lint profile). Scoped pytest at Red/Green is
   ALREADY DONE (`7us.6`, closed). A persistent test daemon is a genuinely
   new, moderate-risk mechanism (state leakage across runs is the risk to
   design against) — **worth a scoped research spike**, but only after
   §3's instrumentation ships, since a daemon's benefit is unmeasurable
   without the Red/Green span timing this proposal adds.

Net: of six angles, two are effectively already delivered by sibling work
(#4, #5), one is a practice not a project (#3), and three are real
candidates for follow-up work-items (#1 deferred/large, #2 and 6-daemon
scoped) — but none should be filed as READY work until §3's instrumentation
exists to measure them against, per this plan family's binding
exit-criteria protocol (every child needs a hard Honeycomb baseline+target,
not "the change merged").

## 5. Metric definitions (the piece flagged missing since 2026-06-13)

Once §3 ships, these become live Honeycomb queries instead of aspirations.
Defining them now so the instrumentation's attribute names are chosen to
support them directly:

| Metric | Definition | Source span(s) once §3 ships |
| --- | --- | --- |
| Median Red→Green wall time | `rgr.green.start - rgr.red.end` per work-item, P50 | `rgr.red` + `rgr.green` (§3.1), joined on `work_item_id` |
| Dispatch wall-clock | Dispatcher journal start → merge-confirmed, per item | existing `livespec-dispatcher` dataset (already live) |
| First-pass-green rate | fraction of items whose FIRST `rgr.green` span has `exit_code=0` (no re-Red needed) | `rgr.green` (§3.1) |
| Rescue rate | fraction of dispatched items needing a Codex-rescue or human intervention before merge | existing dispatcher journal, needs a `rescue` event tag if not already present — check before assuming it's missing |
| Cost/green-item | fabro `cost.usd` (already captured per e60's 2026-06-13 comment) summed per work-item over its full RGR history | existing `fabro.total_usd_micros` spans, joined on `work_item_id` |

Baselines are NOT filled in above because they require the §3
instrumentation (or, at minimum, the archived `tmp/otel-runtime-spans.jsonl`
historical replay e60's first comment describes) to compute against a real
population — filling in placeholder numbers here would be exactly the kind
of unverified claim `.ai/verifying-against-the-right-source.md` warns
against.

## 6. Recommended disposition

This item stays a research/proposal deliverable, not a code-RGR, per its
own 2026-06-14 narrowing note ("commit the analysis under research/ when
worked... not a code-RGR for the reflector"). Recommended next steps, in
order, for the maintainer to authorize as separate child work-items (not
filed by this pass — each needs the binding Honeycomb-metric exit-criteria
treatment `performance-improvements-01` established):

1. §3.1 + §3.2 (RGR hook leg spans + check-dispatcher export) — smallest,
   highest-leverage, reuses proven code.
2. §3.3's `ci.conclusion` populate (cheap, no coordination needed);
   defer the queue-time attribute until `s43svm.20` is picked up.
3. §4's AST-grep spike and persistent-test-daemon spike, gated on §3's
   spans existing to measure them against.
4. Re-baseline §5's metric table once §3.1/.2 have run for a comparable
   window, and record it as a follow-up comment on this item.
