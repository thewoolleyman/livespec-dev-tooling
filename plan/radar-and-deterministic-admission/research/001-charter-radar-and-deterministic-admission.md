## The maintainer's statement of what done means

"I would like it represented in some sort of code form as an array so that the ordering cannot be corrupted or misinterpreted with duplicated items" ... "There should be a single source of truth, and it should be this type-safe, ordered list of only the things I have told you to have on your radar." ... "The priority should be a direct printout of this and not limited to 10 items, but list everything that I have on them. This will also be a visual gate when I have given you too many priorities and we need to drop some things." ... "re override - No ... Overrides will be represented by changing the order." ... "The hard rule needs to be that work isn't canceled unless it is runaway or of no value, but it is allowed to naturally finish what is in progress and then wrap itself to completion if it is deprioritized." ... "the data going into this function should always come from Honeycomb unless Honeycomb is actually down or inaccessible ... All of the inputs to the pure function are also codified and not non-deterministic via LLMs." ... "making all of the Honeycomb data available and codifying it so that the API is extremely clear and doesn't drift or get broken should be a prerequisite of this plan. There should be clear integration tests and unit tests ..." ... "the cam rotation still is the source of truth ... the throughput should be managed so the factory never stalls out, and local inference never stalls out ... the one part of it about token spend can be deferred to the end." ... "make this one plan and possibly pull in existing or new issues or plans from Cam for its dependencies, but make those a low priority compared to the rest of the stuff." (attended, 2026-11-02)

## Definition of Done assertions derived from that statement

- A committed radar file in livespec-dev-tooling is parsed by code into a typed, ordered array whose entries carry exactly: `kind` (`plan` | `item`), `tenant`, `id`, `words` (the maintainer's words), `said_at` (a date), and optional `blocked_by` (a list of `tenant:id`). The schema has no priority number, no override, no slot 0, and no length limit; the array index is the only order.
- The radar validator runs in `just check` and refuses a file that has (a) an id listed twice, (b) an item listed directly that is also a child of a listed plan, (c) an id that does not resolve in its tenant, (d) a closed target, (e) a plan entry whose epic has no `plan/<slug>/` directory in its repository, or (f) a `blocked_by` target that fails (c) or (d); a fixture for each defect fails, and the committed file passes.
- Every consumer of the radar (report printout, admission function, ticket generator) runs the same validator at load time and exits non-zero with the defect named when it fails; a test proves none of them falls back to a cached or partial order.
- A readiness reader computes an item's blockers from Beads `blocks` edges only, computes a plan's children as the UNION of the dotted-id prefix and the `parent-child` edge, and declared radar `blocked_by` entries; tests prove that `parent-child`, `relates-to`, `discovered-from`, `related` and `duplicates` edges never block, on fixtures taken from both `bd list` and `bd show` key spellings.
- Every Honeycomb query the admission function uses is a named query spec in code (dataset, calculations, filters, breakdowns, window, expected columns and column types), the full set per tick is fixed and counted, and a unit test fails if the per-tick set exceeds the budget constant (initially 20 queries per tick at one tick per 15 minutes, leaving the rest of the shared 100-per-hour MCP budget to other callers).
- The Honeycomb board `scheduler inputs` in the `livespec` environment is generated from those specs by a committed applier, and a read-only drift mode of that applier reports zero differences between the live board and the generated definition on the day of capture.
- For every query spec, a contract test run against live Honeycomb under `with-livespec-env.sh` through `https://mcp.honeycomb.io/mcp` fails on a missing column, a column whose parsed type differs from the spec, or data whose newest row is older than the spec's staleness bound; the capture records one green run and one deliberately broken spec that was refused.
- PSI `some` and `full` for cpu, memory and io (avg10, avg60, avg300) arrive in the `livespec` environment's `metrics` dataset keyed by `host.name` for gmktec-xubuntu, hp-xubuntu, poweredge-xubuntu and the dev VPS, with datapoints in every 15-minute window of a 24-hour capture; the dev VPS's host metrics (including `system.linux.memory.available`) arrive in `livespec`, not only in `agent-activity`.
- Every factory run emits one terminal span to Honeycomb carrying the run id, the work item id, the execution target, the run class, start and end time, outcome, CPU-seconds and peak memory of its sandbox, and those keys are in the orchestrator's OTel attribute allowlist; a 24-hour capture shows every run listed on the gmktec factory in that window has exactly one such span.
- A gate on master in the orchestrator repository fails when a change removes or renames an emitted attribute, or drops an allowlist key, that a query spec in the contract depends on; the contract's required attribute set is read by that gate from one committed file, not duplicated.
- The Honeycomb reader has a fallback: when the MCP endpoint is unreachable, returns an error, or exhausts its budget, the reader returns fixed conservative defaults from a committed table, every decision made from them carries `inputs: fallback` with the failure reason, and unit tests cover the parser and each fallback path with no network.
- On a tick taken with Honeycomb unreachable (simulated by an unresolvable endpoint override), the report prints a `HONEYCOMB UNREACHABLE since <UTC>` line above radar entry 1, every decision in that tick is flagged `inputs: fallback`, and a work item for the outage exists in the ledger within one tick.
- The admission function is pure: its inputs are the radar array, the readiness snapshot, the inventory file, the thresholds file and the Honeycomb snapshot; it performs no I/O; the same inputs give the same output byte for byte; and its output names every ready item with `admit` (target and rule id) or `refuse` (rule id and the numbers compared), with no silent omission.
- Property tests prove the two placement rules: the highest-ordered ready item is admitted to any execution target whose measured headroom covers that item's run-class p90 CPU-seconds, peak memory and concurrency cost; a lower-ordered item is admitted only to an execution target the higher item cannot use.
- Thresholds live in a committed data file with enter and exit values (hysteresis) per observable and per execution target, every cap is derived from a measured throughput figure named in that file (never from a utilisation percentage alone), and adding an execution target is one inventory entry: a test adds a host to the inventory fixture and shows it admissible with no diff outside the inventory file.
- The coordinator's tick report is produced by code from the radar: PRIORITIES prints every radar entry in index order (title then id), DEPENDENCIES uses the same numbering with each entry expanded from the ledger (children with status word and hold reason), and a fixture test fails on any slot 0, repeated number or truncation.
- A live tick report on the coordinator's epic, captured after cutover, matches the generator's output for the same radar and ledger state, and the `priorities-record` scope events are no longer the source of the list.
- The dispatcher's ticket order on the dispatching host is generated from the radar (index, then topological order of `blocks` within an entry); `fill-queue.txt`, `ordered-feeder.list`, hand-numbered ticket namespaces and `cap-rule.txt` are not read by any running launcher process, and `ps` on the host shows no process reading them.
- A hold set after a launcher has taken the launch mutex and before `drive.py` starts refuses that launch; the capture records a hold set during that window and the launcher log line that refused it, with the gap between the hold and the refusal.
- On the dev VPS, `just gate-start`, a host-replay launcher and a new interactive seat each call the admission function before starting, and the function's recorded decision for each (admit or refuse, rule and numbers) is readable in the decision log on that host.
- An item that is running when it is moved down or off the radar runs to completion including its wrap-up (rework, acceptance, proofs); the capture names such an item, the radar edit time, and the run that finished afterwards without a cancel.
- Runaway is defined in code and data: a run past `factor × p90` wall time or `factor × p90` token cost for its run class with no progress event in the configured window; the only cancel paths are that rule and a maintainer ruling recorded on the item; an infrastructure restart's cancel-and-redispatch is recorded as `resume`, never as a cancel; tests cover each path.
- The radar and admission contract (schema, readiness rules, Honeycomb input contract, decision record format) is published as a versioned document on master, and epic bd-ib-k6dqwc (dispatch-control-plane) carries a scope event adopting it as the scheduler's input contract, with no operational duty transferred to that plan.
- caam's reporting skill and data files represent Codex accounts first-class: the vault, the rotation state and the usage reader carry a provider dimension, and a capture shows one Codex account's limit windows read and displayed by the same path as a Claude account's.
- The admission function's provider-quota input is read by code from caam's published selection and remaining-window figures (never by an LLM, never by re-deciding the account), and the function's only quota rule is throughput: it refuses a launch when the selected account's remaining window cannot cover the run-class p90 token cost, and tests prove it never changes which account is selected.
- Over a 7-day capture after assertion 25 is live, no factory launch is refused and no local interactive inference stalls on a provider-quota rule while caam reports a usable account, and every quota refusal in that window names the account, the window and the numbers.

# Charter — radar-and-deterministic-admission

Drafted 2026-11-02 by a Fable subagent for the coordinator legacy-coordinator-agent (epic livespec-dev-tooling-6tgd2z),
reviewed by the coordinator, and opened 2026-11-02 by the radar-and-deterministic-admission seat at the maintainer's
direction as PRIORITY 1 (scope event 2026-11-02T15:16:44Z on 6tgd2z: "Spin up a Fable subagent to draft the plan with
quality and a clear definition of done, and then add it to the top of your priority list to get it rolled out.").
Home repository: livespec-dev-tooling. Source draft: `tmp/coordinator/radar-plan-charter-draft.md` (uncommitted
coordinator scratch); this note is its committed form.

The maintainer's rulings this plan is built on are recorded verbatim as scope events on epic livespec-dev-tooling-6tgd2z
between 2026-11-02T14:54:36Z and 2026-11-02T15:16:44Z (override removed; `blocks` edges; no cancellation of in-flight
work; pure function; Honeycomb inputs by code as a prerequisite; caam rotation is the source of truth; one plan with the
caam dependencies at low priority; "execution target" not "pool"; brainstorm closed).

## Changes from the reviewed draft, and why

- **Proof modes (coordinator ruling 3).** The draft tagged assertions 1-5, 10, 11, 13-16, 22 and 25 `factory_captured`.
  The plan tooling has no `factory_captured` mode for a PLAN assertion: no factory run executes against an epic, and
  every plan assertion that is not `human_attested` is `host_captured` by default (plan prose §"The plan Definition of
  Done"; same convention as `plan/fleet-mutation-testing-rule-26/research/001-*.md` item 4). All 26 assertions are
  therefore `host_captured`. For the 13 that the draft called `factory_captured`, the plan-level capture is a host read
  of master: the merged carrier child's tests and gates, run against the released build, named in the plan record.
  The carrier children themselves keep `factory_captured` in their own Definitions of Done. Assertion text is otherwise
  unchanged; only the leading proof-mode tag was removed.
- **Open questions replaced by coordinator rulings** (R301, below). No assertion or slice changed as a result: rulings
  1 and 2 match the draft's recommendations, 4 and 5 are measured inside their slices.
- The DoD (26 assertions) and the eight slices are otherwise kept as drafted.

## Why this plan exists

Prioritisation and admission are hand-run today. The maintainer's priorities live as verbatim scope events on the
coordinator's epic, capped at ten with a slot 0 override, and are re-read and re-typed by an LLM each tick. Admission is
a 436-line bash launcher plus a feeder script, with caps and floors in loose files and ordering by FIFO ticket. Each of
those layers has already produced a measured failure: duplicated numbering in the dependencies report (2026-11-02), a
launch through a freshly set hold (2026-10-25), and caps set from idle percentages that `.ai/ci-node-capacity-reads.md`
says are the wrong instrument. This plan replaces all of it with one typed source of truth, one pure function with
recorded reasons, and inputs that come from Honeycomb by code.

## Current state (measured 2026-11-02)

- **Priorities record.** `plan/legacy-coordinator-agent` charter: at most 10 entries, set only by the maintainer, each
  a `priorities-record` scope event on epic livespec-dev-tooling-6tgd2z, the latest in timeline order wins. The report
  rule set (`.ai/coordinator-duties.md` §9) adds a "slot 0 stability override" and nested DEPENDENCIES for priorities
  1-3 only. The maintainer corrected the numbering that day ("you have multiple 1a, and 1b, and no 2").
- **The launcher.** `/data/projects/livespec-orchestrator-beads-fabro/tmp/petri-canary/dispatch-dual-r681b.sh`, 436
  lines; its header is a numbered history of coordinator rulings (R138 … R681b). Live-read control files in
  `tmp/petri-canary/`: `fleet-cap` = 10, `gmk-cap` = 10, `gmk-idle-floor` = 3 (percent idle, from whole-host `mpstat 5 2`
  over ssh), `hold-gmktec` (absent today; nine `.lifted-*` snapshots), `cap-rule.txt` (a two-tick raise rule and a
  freeze), `fill-queue.txt` (19 ids), `never-ticket.txt` (17 lines of local-only exclusions), `fill-feature-hold.txt`,
  `capture-veto`. Tickets are files in `/run/user/1000/gmktec-launch-queue.d` (tmpfs); the oldest live ticket wins,
  modified by `server=hl` and `wip-wait=1` lines. A claude-cred-status probe and a master-CI/DoD preflight run at launch.
  Ten launcher instances are running, one per item. The feeder is
  `/data/projects/livespec-dev-tooling/tmp/petri-refill/ordered-feeder.sh` (MAX_LIVE=13) over `ordered-feeder.list`.
  hp-xubuntu is retired as a factory and its branch of the launcher is dead code (`if false`).
- **The hold slip.** The launcher comment at line ~342 records it: "2026-10-25 (quota refusal #4, bd-ib-yzk2h2): the
  hold was checked only BEFORE take_mutex, so a launcher already waiting in the FIFO launched through a hold set
  meanwhile." The fix re-checks under the mutex. The mutex is then released (R277) and the launcher still spends an
  ssh token fetch, a credential probe (timeout 120 s), a git fetch and a ready-set re-check before `drive.py` starts,
  with no hold check in that window. The 59-second figure in the maintainer's brief was not found in any source file.
- **Ordering.** The plugin dispatcher orders `ready` items by `metadata.rank` (per repository; `ready_sort_key` in
  `livespec_runtime/work_items/lifecycle.py`), then aging. The tmp launchers ignore rank and use ticket order. In this
  tenant 113 of 223 non-closed items carry `rank`; Beads `priority` is 142 × P2, 64 × P1, 13 × P3, 2 × P0, 2 × P4, so
  it ranks nothing.
- **Dependency edges in this tenant.** 329 `parent-child`, 205 `blocks`, 44 `discovered-from`, 26 `relates-to`,
  2 `related`, 1 `duplicates`: 64% of rows are not blockers. The two key spellings differ by surface (`depends_on_id` +
  `type` in `bd list`, `id` + `dependency_type` in `bd show`).
- **Honeycomb access.** Pro tier: the configuration key reports `queries: false`; only `HONEYCOMB_MCP_API_KEY_LIVESPEC`
  runs queries, via JSON-RPC `tools/call` `run_query` on `https://mcp.honeycomb.io/mcp`, about 100 queries per hour.
  The helper `~/token-spend-report/scripts/hcq.py` parses the MCP's rendered markdown table ("# Results") and splits
  windows when a result exceeds 100 groups. The dispatcher's reflector (`_reflector_runtime.py`) is an ACP LLM judge
  told to "use the Honeycomb MCP tools"; it has no cache and no per-hour budget. No deterministic Honeycomb reader with
  caching exists in any fleet repository.
- **Honeycomb observables** (collector configs in `/data/projects/otel-collector`, chosen per host by
  `ansible/inventory/host_vars/*.yml`; the `livespec` environment is Metrics 2.0, one `metrics` dataset):

  | Observable | Today | Gap |
  |---|---|---|
  | PSI cpu / memory / io per host | io `full avg300` only, poweredge only (`ci-runner-heartbeat.sh`, `livespec.ci_host.io_stall_pct`) | cpu and memory PSI nowhere; nothing for gmktec, hp, VPS; `otelcol-contrib` 0.147.0 has no PSI scraper |
  | MemAvailable per host | `system.linux.memory.available` on poweredge, gmktec, hp | the dev VPS ships host metrics only to `agent-activity` / `livespec-host-metrics` |
  | k8s allocatable vs requested per node | `k8s.node.allocatable_{cpu,memory}`, `k8s.container.{cpu,memory}_request` by `k8s.node.name` (`config.ci-runner-host.yaml`, board `k8s-node-load.json`) | k3s nodes only; `factory-mi-homelab` not captured on its own |
  | live runs per execution target | `livespec-dispatcher`/`dispatcher.dispatch` launch marker with `livespec.dispatch.factory`; `fabro`/`run` span with run id only on events | no state or end time per run; the terminal per-dispatch span is unfiled relay R3 in `plan/factory-spend-accuracy/research/002-carrier-map.md` |
  | per-run CPU-seconds, peak memory, wall time | `wall_clock_seconds` on `dispatcher.calibration` (per item, not per attempt); `cpu_seconds` written to the local journal only and not allowlisted | no CPU-seconds or peak memory in Honeycomb; Docker sandboxes on gmktec have no per-container stats |

- **caam.** Claude-only: vault `~/.local/share/caam/vault/claude/`, state `~/.local/state/caam-usage-rotate/state.json`
  with no provider dimension, usage reader hard-coded to `api.anthropic.com/api/oauth/usage`
  (`overseer/caam_usage.py:28`), tool hard-coded in `overseer/caam_profile_state.py:57-60`. `caam.db` has a `provider`
  column, every row `claude`. `plan/caam-quota-resets/research/002-reset-mechanisms-measured.md:135`: "caam's vault
  holds ONLY `claude` profiles; it manages no Codex accounts."

## The design (recorded from the maintainer's brief)

1. **The radar file.** One committed, type-safe, ordered array of only what the maintainer has put on the
   coordinator's radar. Entry: `kind` (plan | item), `tenant`, `id`, the maintainer's words with a date, optional
   `blocked_by` (cross-tenant, since Beads cannot express cross-tenant edges). Index is priority. No override, no slot
   0: urgency is expressed by reordering. No length limit: the printout's length is the maintainer's signal to drop
   entries. A validator (CI gate and load-time) refuses duplicates (directly or as a child of a listed plan), ids that
   do not resolve, closed targets, and plan entries without a plan directory. Only the maintainer edits the array; a
   session that has evidence the order should change reports it as a finding.
2. **Dependencies from `blocks` edges only.** Children = union of dotted-id prefix and `parent-child` edge.
   Non-blocking edge types never block. Cross-tenant blockers are declared in the radar and validated.
3. **The Honeycomb input contract — a prerequisite.** Every measured observable the function uses comes from Honeycomb,
   read by code, never by an LLM: PSI per execution target, MemAvailable, k8s allocatable vs requested per node, live
   runs per execution target, per-run-class cost (CPU-seconds, peak memory, wall time; p50 and p90) from run spans.
   Query specs live in code; the `scheduler inputs` board is generated from them so the holistic view and the code
   cannot drift. Contract tests fail on a missing column, a type change or stale data; unit tests cover parsing and
   fallback; a gate proves factory and test changes cannot silently break the emitted data. Missing observables are
   prerequisite slices. Fallback: fixed conservative defaults, every decision flagged, the outage raised above entry 1
   of the printout. Queries go through the MCP endpoint with a small fixed set per tick and a cache; the budget is
   shared with the reflector.
4. **A pure admission function.** Inputs: radar order, readiness (not closed, all `blocks` resolved, not running),
   inventory of execution targets (later provider quotas), Honeycomb snapshot. Output: which ready items launch where,
   plus a recorded reason (rule and numbers) for every admit and refusal. Highest-ordered ready item launches on any
   execution target with headroom for its p90 cost; backfill only onto a target the higher item cannot use. Thresholds
   are data with hysteresis; caps are throughput-derived. Hosts are added by inventory entry. The same function admits
   local VPS work: gate-start, replayers, new interactive seats.
5. **The dispatcher reads the same source.** Ticket order is generated from the radar (index, then topological order
   within an entry), replacing `fill-queue.txt` and hand-numbered tickets. The hold is re-checked immediately before
   launch.
6. **The coordinator report is a direct printout.** PRIORITIES = the array; DEPENDENCIES = the same numbering, each
   entry expanded from the ledger.
7. **Provider quota last, low priority.** caam's rotation is the source of truth and its algorithm selects the account.
   The function's only quota rule is throughput: the factory never stalls, local inference never stalls. Prerequisites:
   Codex first-class in caam's reporting skill and data files; possibly a deterministic code wrapper around caam's
   store.
8. **Deprioritisation never cancels in-flight work.** A started item runs to completion including wrap-up. Cancel only
   for runaway (deterministic: past p90 wall time or token cost by a set factor with no progress event in a window) or
   work the maintainer rules has no value. An infrastructure restart's cancel-and-redispatch is a resume.
9. **dispatch-control-plane adopts the contract.** See "Handover" below.

## Terminology

- **execution target**: a place work runs with its own capacity — the gmktec factory server and its nodes, the hp
  factory, the dev VPS for local work, later the Hetzner host. Never "pool".
- **provider quota**: one LLM provider's token budget across the accounts caam rotates.
- **ARC runners**: GitHub Actions runner pods on the k3s node; a competing consumer of the same host, never a
  scheduling target.
- **run class**: the key the per-run cost percentiles are grouped by (initially the dispatch kind, e.g. implement,
  gate, replay, interactive).

## Proposed slices, in order

1. **Radar file and validator** (assertions 1-4). Schema, parser, validator in `just check`, readiness reader over
   `blocks` edges with the union child rule, load-time check shared by every consumer. No behaviour change yet; the
   coordinator seat may begin printing from it by hand.
2. **Honeycomb input contract and missing observables** (5-12). The deterministic MCP reader with a per-tick cache and
   budget counter (derived from `hcq.py`, not the reflector); query specs; generated board and drift mode; contract
   and unit tests; the attribute gate. Prerequisite emitters, each its own child: PSI cpu/memory/io on all four hosts
   (a small scraper feeding the host collector, since `otelcol-contrib` has none); the dev VPS's host metrics into
   `livespec`; the per-run terminal span with CPU-seconds and peak memory (coordinate with factory-spend-accuracy's
   relay R3 rather than duplicate it); per-sandbox cgroup stats on gmktec. Fallback defaults and the unreachable
   report line.
3. **Pure admission function with recorded decisions** (13-15). The function, the inventory and thresholds files, the
   decision log format, property tests for the two placement rules, hysteresis and throughput-derived caps per
   `.ai/ci-node-capacity-reads.md`. Shadow mode first: it runs beside the launcher and records what it would have
   decided, with no launch authority.
4. **Report printout** (16-17). The generator replaces the hand-typed PRIORITIES and DEPENDENCIES; `priorities-record`
   scope events stop being the source. `.ai/coordinator-duties.md` §9 and the legacy-coordinator charter are amended
   in the same change (drop the 10 cap, slot 0 and the "nested for 1-3 only" rule).
5. **Dispatcher cutover** (18-19). Ticket order generated from the radar; the launcher's launch path calls the function
   and re-checks the hold as the last act before `drive.py`; `fill-queue.txt`, `ordered-feeder.list`,
   `never-ticket.txt`, `cap-rule.txt` and the cap files retired into the inventory and thresholds files. Shadow-mode
   disagreements from slice 3 are resolved before any launch authority moves.
6. **Local-work admission and non-cancellation** (20-22). `gate-start`, the replay launcher and new interactive seats
   call the function; the runaway rule and the resume classification land; the deprioritised-item capture is taken.
7. **Handover to dispatch-control-plane** (23). The contract document and the adopting scope event.
8. **Provider quota, last and low** (24-26). Codex first-class in caam; the code read of caam's published selection;
   the throughput-only quota rule; the 7-day stall capture.

## Handover to dispatch-control-plane (bd-ib-k6dqwc)

That plan's proposal (`research/013-portable-coordination-proposal.md`) already says the fleet scheduler "consumes
public eligibility and Dispatcher admission, current repository routing, priorities and scoped holds" and must "explain
each binding limit instead of creating another hidden host-slot scheduler", and its governing rule is that it "must not
absorb their daily operations". This plan is the supplier of that input: the radar schema, the readiness rules, the
Honeycomb input contract and the decision record format are published as one versioned contract document on master
(slice 7), and dispatch-control-plane records a scope event adopting it as the scheduler's input contract. The
operating seats (legacy-coordinator-agent, legacy-dispatcher-agent) run slices 4 and 5 on today's launcher as break-fix
work under this plan's children, so dispatch-control-plane takes nothing operational. When its scheduler admits gmktec
work it reads the same radar, the same function and the same Honeycomb snapshot; the legacy plans' single exit
("retire when dispatch-control-plane replaces it") is unchanged. This plan does not decide the scheduler's surface,
API, authentication or deployment; those stay with bd-ib-k6dqwc's open decisions.

## Dependencies on other plans and items

- **kubernetes-observability** (livespec-dev-tooling, epic in `plan/kubernetes-observability`): owns node metrics,
  allocatable/requests and the board appliers; the PSI scrapers and the board drift mode build on its appliers.
- **factory-spend-accuracy** (livespec-dev-tooling): relay R3, the terminal per-dispatch span, is the natural carrier
  for assertion 9's attributes; coordinate, do not duplicate.
- **codex-implement-cost-per-run** and **token-spend-analysis**: own `hcq.py` and the `llm-spend` rollups the quota
  slice reads.
- **dispatch-control-plane** (bd-ib-k6dqwc, livespec-orchestrator-beads-fabro): consumer of the contract, slice 7.
- **legacy-coordinator-agent** (livespec-dev-tooling-6tgd2z) and **legacy-dispatcher-agent** (bd-ib-ynnykl): operate
  the report and launcher today; their charters and `.ai/coordinator-duties.md` §9 are amended by slices 4 and 5.
- **otel-collector** repository (`/data/projects/otel-collector`): per-host collector configs; the PSI and VPS
  routing changes land there and roll out through Ansible.
- **dev-host-test-gate-load** (livespec-dev-tooling): owns the VPS load baseline and the steal finding that forbids
  idle-percentage gating on the VPS.
- **caam plans in livespec-overseer**: caam-generic-limit-windows (overseer-rumvpf), caam-quota-resets
  (overseer-pv53ri, Codex adapter explicitly deferred there), llm-provider-manager (overseer-tm2qtw). Items that record
  admission and rotation disagreeing on the same account: overseer-98f3, bd-ib-2n2s7b. These are pulled in as slice 8
  dependencies at low priority.

## Risks

- **The MCP response is rendered text, not JSON.** `hcq.py` parses a markdown table. A rendering change at Honeycomb
  breaks every query at once. Mitigation: the contract test (assertion 7) is the detector; the fallback (11) is the
  response; check whether the MCP exposes a raw-JSON result tool before building on the table parser.
- **The query budget is shared and small.** 100 per hour across the reader, the reflector and hand queries. A tick set
  of 20 at 15-minute ticks spends 80. Mitigation: the per-tick set is a counted constant (assertion 5), the cache
  serves repeat reads inside a tick, and the reflector's unbudgeted use is reported to its owner.
- **PSI has no collector scraper.** A host-side scraper is new code on four hosts. Mitigation: reuse the
  `ci-runner-heartbeat.sh` pattern that already ships io PSI from poweredge.
- **p90 cost needs history that does not exist yet.** Until the terminal span has run for a window, run-class
  percentiles are empty. Mitigation: fallback defaults by run class (assertion 11), flagged, until the window fills.
- **Shadow-mode disagreement.** The function and today's launcher will disagree. Mitigation: no launch authority moves
  until the disagreements are each explained by a rule and number (slice 3 before 5).
- **bd-ib-l3l5 proposes moving rotation into the orchestrator**, which conflicts with "caam stays the source of
  truth". Not resolved here; it is reported to its owner with this charter's premise.
- **Two actors already run admission against this host** (the legacy dispatcher's ten launchers and the drain-backlog
  skill's engines). The cutover must cover both or the second keeps its own order.

## Non-goals

- No new scheduler surface, API, authentication or deployment: those are dispatch-control-plane's decisions.
- No absorption of today's operations by dispatch-control-plane, and no new operational duty for this plan's seat
  beyond its own children.
- No change to caam's rules or account selection (coordinator-duties §12: never change caam rules, never second-guess
  caam selection). The quota slice reads caam; it does not steer it.
- No Honeycomb Enterprise features: no REST Query Data API, no SLO-driven admission.
- No cancellation policy beyond the runaway rule and a maintainer ruling; no "deprioritise cancels".
- No LLM in any input or decision path. An LLM may render the printout's prose but never change its order or content.
- No ARC runner scheduling: ARC pods are read as a competing consumer through k8s requests, never admitted by this
  function.
- No Hetzner host provisioning; it arrives as an inventory entry when it exists.

## Coordinator rulings on the draft's open questions (R301, 2026-11-02)

Recorded from legacy-coordinator-agent's seat brief. They decide the draft's open questions; none of them is a
maintainer question.

1. **Radar file format: a typed Python module** — an immutable, ordered tuple of typed entries, checked by mypy. The
   maintainer asked for "code form as an array ... type-safe". The type checker and the import are the validator's first
   layer; the runtime validator (assertion 2) is the second.
2. **A Honeycomb outage is shown by the printed `HONEYCOMB UNREACHABLE` line plus a filed item, never by auto-editing the
   array.** Only the maintainer orders the radar; a session or the coordinator that has evidence the order should change
   relays a reorder request to the maintainer through the coordinator. Assertion 12 already encodes this.
3. **Proof-mode tags follow this repository's plan convention.** Plan-level assertions default to `host_captured`, so
   every assertion is retagged `host_captured` (see "Changes from the reviewed draft" above).
4. **The hold-slip window is measured inside its slice** (slice 5, assertion 19), not guessed. The 59-second figure in the
   brief was not found in any source; the capture records the actual gap.
5. **The per-tick query budget is measured inside its slice** (slice 2, assertion 5), not guessed. The draft's "20 per
   15-minute tick" is a starting hypothesis; the constant is fixed only after the reflector's and hand queries' share
   of the ~100/hour MCP budget is measured.
6. **bd-ib-l3l5 conflicts with the maintainer's ruling and is NOT absorbed.** bd-ib-l3l5 proposes moving account
   rotation into the orchestrator; the maintainer ruled (2026-11-02T15:09:14Z, attended, verbatim) "the cam rotation
   still is the source of truth, and its algorithm handles everything". The conflict is recorded here and sent to
   bd-ib-l3l5's owner for disposition with the maintainer's words. This plan's quota slice reads caam's selection and
   never re-decides it.

## Constraints carried from the seat brief

- Honeycomb is on the **Pro** plan: there is no REST Query Data API (that requires Enterprise). Every query goes through
  the MCP endpoint `https://mcp.honeycomb.io/mcp` with `HONEYCOMB_MCP_API_KEY_LIVESPEC` (see
  `.ai/honeycomb-query-credential.md`).
- dispatch-control-plane (bd-ib-k6dqwc) ADOPTS this contract and does not absorb today's operations.
- Deprioritisation never cancels in-flight work.
- The caam / Codex provider-quota slice (8) is filed last and at low priority.
