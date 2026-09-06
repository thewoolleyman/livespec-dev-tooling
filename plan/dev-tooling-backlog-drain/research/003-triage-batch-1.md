# 003 — Triage batch 1: superseded-by-transport, factory-path defects, stuck states

Proposed 2026-09-06 for the maintainer's ruling. Every disposition below is a
PROPOSAL until the ruling is recorded as a scope event on the plan epic
(`livespec-dev-tooling-kcoslm`); the ledger actions in §5 execute only after
that. Facts marked *measured* were read from the authoritative source named;
everything else is a reading of the item's own text.

## 0. Facts this batch rests on (measured 2026-09-06)

- **The factory lands work in this repo.** The dispatch journal
  (`tmp/fabro-dispatch-journal.jsonl`) records `efqeip.2` merged green through
  a fabro run on 2026-09-04 (PR 1733, post-merge janitor green) and `efqeip.1`
  merged the same day with a red post-merge janitor. Both ran on the
  `@agentclientprotocol/codex-acp` adapter the sandbox Dockerfile now bakes.
- **A run is in flight now**: `x2ju4a`, admitted 04:36Z, still `running` at
  05:25Z. Its outcome is the next factory measurement.
- **Two recent runs failed before the agent started**: `npsqeu` twice on
  2026-09-04 at `goal-minijinja-preflight`, because a ledger comment on the
  item contained a literal `{{`. That is the defect item `9yb4` describes.
- **Five items read `active`; the journal calls four of them abandoned
  claims** (`dispatch-claim-abandoned`): `y6m2xn.1` and `3u3gm2.2` with
  no outcome since admit, `4s2sey` with a terminal non-green outcome, and
  `hmv2bo` (which has a live hand-driven session in the ci-runner-cache-tiers
  plan and is not phantom). `3u3gm2.2` landed by hand as PR 1760 on
  2026-09-06 and is done.
- **Twelve items sit at `pending-approval`**, filed between 2026-07-19 and
  2026-09-06 (eight of them on 2026-08-20/21, the foreman-act period).
  `auto_approve_ready` is `true` in `.livespec.jsonc`; item `3nsap6` records
  that the `approve` valve cannot clear a foreman-filed pending-approval item.
  Whatever the cause, nothing has moved them in weeks.
- **The open PR list has no parked factory PRs.** Open PRs are hand-authored
  or bot bumps; the only ripe one is PR 1741 (codex-acp pin 1.6→1.10, all
  checks green).

## 1. Superseded-by-transport — CLOSE

Console plan decisions D1 and D5 retire tmux as the transport and freeze the
overseer repo whole. Each item below exists only to serve that transport.

| id | title (abridged) | why superseded |
|---|---|---|
| `50xi` (epic) | foreman seat anchor — ledger-held foreman handoff timeline | the foreman seat no longer exists for this repo (charter §2) |
| `yez0` (epic) | grooming seat anchor | the grooming seat is dropped outright (D5); grooming is the `groom` operation |
| `vrl5fo` | FOREMAN HANDOFF 2026-08-19: session wind-down resume state | a handoff for a seat that will not resume |
| `3nsap6` | foreman-act files items at pending-approval, which `approve` cannot clear | `foreman-act` is retired; the STUCK ITEMS it left are handled in §4, the filer is not fixed |
| `h5uwnx` | Foreman contract pins the runtime to the harness binding | foreman contract retired |
| `vvfsao` | `work_item_session_start` refuses when needs_attention is unconfigured | a `foreman-act` action id; retired with it |
| `3iizsd` | relocate livespec-overseer's nested worktree (blocked on owning session) | overseer repo frozen whole; host housekeeping for a frozen repo is not this plan's work |
| `ta5jy4` | Self-wire the charter gate in livespec-dev-tooling | the charter detector's globs are `.ai/supervisor-protocol.md` and `plan/**/supervisor-handoff.md` — tmux supervisor artifacts (v197 already forbids live handoff files) |
| `iaxmyy` | Charter detector (d) flags a correct search accumulator | same detector, same reason |
| `8o8e.7` | ROP arming child: livespec-overseer — 213 raw / 112 distinct | overseer frozen; the fleet arming under `8o8e` must EXCLUDE the frozen repo or accept it red — that is a decision inside `8o8e`, recorded there, not a reason to keep converting overseer code |
| `oip9` | livespec-overseer keeps 49 test_*.py inside its product tree | overseer frozen; no further edits to it |

Eleven closures. `vod6` (is livespec-overseer a release PRODUCER or a consumer
to drop from the release-dispatch obligation?) is **re-scope**, not close: the
answer is "drop it" but only once the console plan's overseer-freeze scope
event lands (its phase 0, still pending). Re-title to the one-line consequence
and hold on that cross-tenant event, recorded by reference.

## 2. Factory-path defects — KEEP, tier 1, with consolidations

These make a factory run or a hand commit in this repo fail for reasons
unrelated to the item it carries. They are worked first (charter §6).

| survivor | absorbs | disposition | exempt? |
|---|---|---|---|
| `7us` (epic) | `e60` (a "USER-REQUESTED placeholder" for the same investigation → close into `7us`) | keep; children `7us.7`, `675skf`, `py9` stay | no — dispatchable |
| `sc0z` | — | keep; the amend hook kills the Green leg with a per-file coverage floor on imported modules | **yes, `factory-path-defect`**: the fix is to the hook the factory's own commit runs through |
| `9yb4` | — | keep; a `{{` in item text kills the run at preflight — measured on `npsqeu` twice on 2026-09-04 | no |
| `9yrr` | — | keep; a non-`.py` bug fix is forced to `chore:` and never released | no |
| `mmqe` | `tkzf` | consolidate: "fleet-conformance in the local gate blocks unrelated commits — pace the traversal AND move the admin row out of pre-commit" | no |
| `aa7` | `gam8`, `8o8e.22` | consolidate: "check-master-ci-green reads a different signal than branch protection, swallows API outages, and rejected a sandbox Red commit while master was green" | no |
| `el7g` | — | keep; transient uv install failures leave fleet master red, which then freezes every `.py` commit through the check above | no |
| `to6hh2` | — | keep; the stray `embeddeddolt/` at repo root is present in the primary checkout right now | no |
| `7ix8` | `z68f` | consolidate: same defect (`just bootstrap` dirties `.livespec.jsonc`), two filings | no |
| `4j3` | `5g3c`, `nce`, `r5m` | consolidate: one defect (release-please bumps `pyproject` but not `uv.lock`), four filings | no |
| `xx1y` | — | keep; runtime's `.venv` backs the fleet git credential helper | **yes, `infra-in-person`**: host state |
| `h7qp` | `a9xp`, `fj28` | consolidate: "the background guard prescribes `gate-start`, which 6 of 7 arming repos do not ship — ship the runner in the pack or make the prescription conditional" | no |
| `iugc` | `mt24`, `6q5o` | consolidate: "gate-status's evidence probe is blind to the serial emitter and to lefthook's buffering" | no |
| `trfzkw`, `b7dbne`, `k169` | — | keep as filed | no |

Codex adapter cluster, **CLOSE as landed / falsified** (measured):

- `xhaw` (P0, "codex-acp successor rejects the adapter config — every factory
  dispatch parks at the PR stage") — falsified by `efqeip.2` merging green
  through the factory on 2026-09-04.
- `opdc` ("replace the baked adapter with `@agentclientprotocol/codex-acp`") —
  landed: `docker/fabro-sandbox/agent/Dockerfile` bakes it; PR 1741 is already
  a freshness bump of that pin.
- `ql1` ("review node pinned to the deprecated adapter name") — the review
  node lives in the orchestrator's bundled workflow, not this repo. Refer to
  the orchestrator tenant by comment; close here.

## 3. Stale `active` claims — status repair

| id | measured | action |
|---|---|---|
| `3u3gm2.2` | landed by hand, PR 1760, commit `756e218e` | close as done |
| `y6m2xn.1` | `dispatch-claim-abandoned: no-outcome-since-ledger-admit` on every loop pass since 2026-08-30 | move `active` → `ready` so the loop can take it again, or → `backlog` if `y6m2xn`'s sequencing (release cut first) is not yet satisfied — the epic's own text says the rename must land as a `feat:`/`fix:` so release-please cuts a release; that is dispatchable now |
| `4s2sey` | `dispatch-claim-abandoned: terminal-outcome-non-green` | move `active` → `ready`; if the next run fails the same way it goes to `groom` |
| `hmv2bo` | live hand session in `ci-runner-cache-tiers`; PRs 1752, 1757 landed today | leave |
| `x2ju4a` | run in flight | leave |

## 4. Stuck `pending-approval` — status repair

Move all twelve to `backlog` so they enter ordinary triage. Four of them are
closed by §1 anyway (`3nsap6`, `h5uwnx`, `vvfsao`, `ta5jy4`); two are tier 1
in §2 (`to6hh2`, `b7dbne`); the other six (`lptplj`, `bqcj7b`, `i53r33`,
`jaut4y`, `z7wxbd`, `qrunmn`) are triaged in a later batch. If the `approve`
valve turns out to clear them after all, that is the preferred route and the
plain status move is not used.

## 5. Ledger actions this batch authorizes, once ruled

1. Close 14 items with reason `superseded-by-transport (kcoslm batch 1)`:
   the eleven in §1 plus `xhaw`, `opdc`, `ql1` with reason
   `landed-or-falsified (kcoslm batch 1)`.
2. Close `e60` into `7us`, `tkzf` into `mmqe`, `gam8` and `8o8e.22` into
   `aa7`, `z68f` into `7ix8`, `5g3c` `nce` `r5m` into `4j3`, `a9xp` `fj28`
   into `h7qp`, `mt24` `6q5o` into `iugc` — eleven closures, each naming its
   survivor; each survivor gets a comment naming what it absorbed.
3. Re-title `vod6` and record the hold-by-reference on the console freeze.
4. Label `sc0z` `factory-exempt:factory-path-defect` and `xx1y`
   `factory-exempt:infra-in-person`.
5. Close `3u3gm2.2`; move `y6m2xn.1` and `4s2sey` to `ready`.
6. Move the twelve pending-approval items to `backlog`.
7. Merge PR 1741 (codex-acp pin 1.10.0, checks green) — the one ripe PR.

Net effect on the snapshot: 26 of 258 items closed, 5 status repairs, 12
un-stuck. The next batch is tier 2, enforcement-suite correctness (false
greens and half-pairs), and it is proposed only after this one is recorded.

## 6. What this batch does NOT decide

- Nothing in the fleet ROP epic `8o8e` beyond its overseer leg.
- Nothing cross-tenant: `ql1`'s orchestrator half, the livespec CORE items
  (`k4km`, `jzoz`, `4ihw`), the driver items. Those are referred, later.
- The `optimize-gates` worktree-pack cluster (R1–R7) — dispatchable as filed;
  tier 2/3 ordering is a later batch.
