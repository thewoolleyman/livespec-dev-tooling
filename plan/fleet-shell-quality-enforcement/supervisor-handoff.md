# Supervisor Handoff - fleet-shell-quality-enforcement

## ⛳ READ THIS FIRST: THE THREAD IS COMPLETE AND ARCHIVED. DO NOT DRIVE IT.

**Closeout `livespec-dev-tooling-qgw7gb` CLOSED 2026-08-05T05:34:57Z. Epic
`livespec-dev-tooling-42t4az` CLOSED 2026-08-05T05:18:09Z. All eight rollouts
closed with merge evidence. The plan thread is ARCHIVED to
`plan/archive/fleet-shell-quality-enforcement/` by merged PR 1296.**

**WHY THIS FILE EXISTS AT ALL, since the thread it describes is archived:** the
overseer respawns this pane with exactly one prompt — *read
`plan/fleet-shell-quality-enforcement/supervisor-handoff.md` and follow it*. That
path was REMOVED by the archive (the real binder now lives at
`plan/archive/fleet-shell-quality-enforcement/supervisor-handoff.md`, 488 lines,
byte-identical to its pre-archive content). Had this file not been recreated, the
next supervisor would have booted into a dangling path with NOTHING. So this is a
deliberate terminal stub, not an un-archiving of the thread.

**It is safe:** `check-plan-thread-epic-parity` globs `*/handoff.md`, not
`supervisor-handoff.md`, so this file does not make the archived thread read as
active. Verified at `livespec_dev_tooling/checks/plan_thread_epic_parity.py:49`.

**THE CORRECT ACTION FOR A COLD-OPEN SUPERVISOR IS TO VERIFY AND STOP, NOT TO
DRIVE.** Re-measure the five lines under "Verify, then stand down" below. If they
hold, there is no supervision work left: write `ready` to
`tmp/overseer/fleet-shell-quality-enforcement-supervisor/.overseer-state` and
stop. Do not restart the worker, do not reopen items, do not re-archive anything.
**Once the maintainer stops respawning this track, DELETE this stub file** — it
is scaffolding for a boot path, not a record.

## Shared Protocol

Read `.ai/supervisor-protocol.md` before doing anything, including the verify
pass. Its Corrections section now carries an entry this session added
(PR 1273, merge `e8e34fcc`) requiring a supervisor to read EVERY cold-open input
its binder enumerates and to verify the input COUNT — written because this
supervisor drove for five hours having never opened the worker's `handoff.md`,
and so issued an instruction violating a hard rule it had never seen.

## Verify, then stand down

Re-measure these five. Every one was measured at the time given; **a timestamp is
evidence, not permission.**

| # | Claim | Measured | How to re-check |
|---|---|---|---|
| 1 | `qgw7gb` closed | 05:34:57Z | `bd show livespec-dev-tooling-qgw7gb --json` under the wrapper |
| 2 | `42t4az` closed, all 5 children closed | 05:18:09Z | `bd show livespec-dev-tooling-42t4az` + `.1`–`.4`, `acawse` |
| 3 | Archive on master, old path gone | 05:32Z | `git cat-file -e origin/master:plan/archive/fleet-shell-quality-enforcement/handoff.md` |
| 4 | `.4`'s deliverable survived the archive | 05:32Z | archived `why-this-shape.md` must be **232 lines** and contain `Worktree pack scope decision` **once** |
| 5 | Primary clean | 05:36Z | `master == origin/master`, only `install-livespec-pr-bot.png` untracked at sha256 `a3e2d35997c60459df71fd16d608c71560eeea16d0aee11422db7eecba204fe5` |

Row 4 is not ceremony. The staged archive was built on a stale base and **would
have silently reverted `.4`'s entire deliverable** — a `git mv` archive carries
file content from its base, and because it presents as a PURE RENAME the diff
looks clean. It was caught by byte comparison, by nothing else. If row 4 fails,
that is a real regression and the only thing in this thread worth reopening.

## What is deliberately LEFT OPEN — do not "tidy" these

- **`livespec-dev-tooling-62jh` — P0, `ready`, EXTERNAL, NOT OURS.** "Pin
  distribution is DOWN to livespec-runtime and livespec-driver-codex." Filed
  2026-08-04T20:34:32Z, eight hours before this thread independently rediscovered
  it. Its fix is **PR 1290** (`fix/62jh-shellcheck-gate-aggregate-layout`), which
  at 04:53Z read rollup **SUCCESS with auto-merge NOT ARMED**. That was flagged to
  the maintainer and deliberately NOT acted on — it is their PR. If it is still
  open and green, flag it again; do not arm or merge it.
- **`livespec-dev-tooling-qn3pgi`** — `blocked`/`needs-human` by design. Carries
  the mirror-retirement condition. `blocked`+`needs-human` is SURFACED by
  needs-attention; `backlog`+`intake:triaged` is NOT. That routing is the point.
- **`bd-ib-zp3u7y`, `bd-ib-zp2axi`, `bd-ib-gajho2`** (orchestrator tenant) —
  filed, not absorbed. Dispatch blind spot, factory-boundary silent drop, and the
  empty-second-PR defect.

## Residue and hazards a cold-open supervisor could trip on

- **`acawse` was a DUPLICATE of `62jh` and is closed as such.** This supervisor
  ORDERED A FIX for it without checking whether it was already filed or already
  fixed — it was both — and the worker had already committed a competing patch to
  `shellcheck_pin_gate.py`, the file controlling fleet pin distribution. Stopped
  by an `Esc` interrupt; the branch never reached the forge. **A duplicate search
  belongs at FILING time, not only before pushing.**
- **Two safeguards caught their own authors.** The pre-commit aggregate refused
  the duplicate patch; `livespec_footgun_guard` refused a `--no-verify` the worker
  typed reflexively while chaining commands — after the supervisor had ended every
  message with that clause. **Stated convention lost to mechanical enforcement
  twice in one morning, on the two people who wrote the convention.** That is this
  epic's thesis, tested on itself.
- **Gate runtime vs harness patience.** `.claude/CLAUDE.md` now points at
  `.ai/gate-runtime-vs-harness-patience.md`: the commit/push aggregate can outlast
  the harness's 20-minute ceiling, and a kill with NO verdict is **not** a hook
  refusal. Use `just gate-start` / `gate-wait` (exit **75** = `DIED_WITHOUT_VERDICT`).
  Doc-only changes take the reduced gate and are quick.
- **Empty results nearly became findings four times** across both operators — a
  path that never existed, a `bd show` in the wrong tenant, a `check-targets.txt`
  zero that meant file-absent, and a `jq` filter that could not match because
  `status` is an object (`{"kind":"running"}`), not a string. Run a positive
  control before treating silence as evidence.
- **Tenant occupancy is a property of live processes and locks, not ledger
  status**, and **a finished run is not a finished dispatcher.** Both were learned
  the hard way here.

## Bindings

Resolve and report these startup bindings before driving. They carry no live
status, next action, or date-gated behavior.

| Binding | Expression | Resolved value |
|---|---|---|
| `repo_primary` | concrete | `/data/projects/livespec-dev-tooling` |
| `thread_dir` | ARCHIVED | `/data/projects/livespec-dev-tooling/plan/archive/fleet-shell-quality-enforcement/` |
| `topic` | concrete | `fleet-shell-quality-enforcement` |
| `worker_session` | concrete | `fleet-shell-quality-enforcement` |
| `supervisor_session` | concrete | `fleet-shell-quality-enforcement-supervisor` |
| `WORKER_TARGET` | concrete | `'=fleet-shell-quality-enforcement:'` |
| `SUPERVISOR_TARGET` | concrete | `'=fleet-shell-quality-enforcement-supervisor:'` |
| `runtime_dir` | `<repo_primary>/tmp/overseer/<topic>/` | `/data/projects/livespec-dev-tooling/tmp/overseer/fleet-shell-quality-enforcement/` |
| `supervisor_marker` | `<runtime_dir>/.supervisor-state` | `/data/projects/livespec-dev-tooling/tmp/overseer/fleet-shell-quality-enforcement/.supervisor-state` |
| `wait_channel` | `<runtime_dir>/worker-status.log` | `/data/projects/livespec-dev-tooling/tmp/overseer/fleet-shell-quality-enforcement/worker-status.log` |
| `ledger_anchor` | concrete | `livespec-dev-tooling-42t4az` (CLOSED) |

The richer running record is `worker-status.log` (~323 lines) and the obligation
record `.supervisor-state` in the same directory, plus
`.supervisor-state.archive-20260804T1531Z`. **All are on disk, NOT in git** — they
survive a restart but not a machine loss, and the next session inherits only THIS
file.

## HALT-first preconditions

Run these before touching anything, even for a verify-only pass. Stop on the
first failure and act on the literal `REMEDY:`.

```bash
WORKER_TARGET='=fleet-shell-quality-enforcement:'
tmux has-session -t "$WORKER_TARGET" \
  || { echo "HALT: expected worker session 'fleet-shell-quality-enforcement'"; echo "REMEDY: the thread is COMPLETE — a missing worker is EXPECTED at this point, not an error. Verify the five rows above from the ledger and forge alone, then declare ready."; exit 1; }
pane_pid=$(tmux display-message -p -t "$WORKER_TARGET" '#{pane_pid}')
[ -n "$pane_pid" ] \
  || { echo "HALT: empty pane_pid"; echo "REMEDY: re-check the exact worker target"; exit 1; }
ps -o pid=,comm=,args= --ppid "$pane_pid" --pid "$pane_pid" -H
# A live `claude` or `codex` child is PASS. A lone shell is acceptable HERE ONLY
# because the thread is complete; do NOT restart the worker to satisfy this.
```

```bash
SUPERVISOR_TARGET='=fleet-shell-quality-enforcement-supervisor:'
tmux has-session -t "$SUPERVISOR_TARGET" \
  || { echo "HALT: expected supervisor session 'fleet-shell-quality-enforcement-supervisor'"; echo "REMEDY: switch to the correct supervisor session or ask the maintainer to bootstrap it"; exit 1; }
sup_pid=$(tmux display-message -p -t "$SUPERVISOR_TARGET" '#{pane_pid}')
worker_pid=$(tmux display-message -p -t '=fleet-shell-quality-enforcement:' '#{pane_pid}' 2>/dev/null)
[ "$sup_pid" != "$worker_pid" ] \
  || { echo "HALT: supervisor and worker resolve to the SAME pane"; echo "REMEDY: re-check both exact targets — a prefix match puts both names on one pane"; exit 1; }
```

```bash
test -d "/data/projects/livespec-dev-tooling/plan/archive/fleet-shell-quality-enforcement" \
  || { echo "HALT: archived plan thread MISSING at plan/archive/fleet-shell-quality-enforcement"; echo "REMEDY: this is a real regression — the archive merged in PR 1296; investigate before doing anything else"; exit 1; }
```

## Ledger re-measure

```sh
ledger_anchor='livespec-dev-tooling-42t4az'
# The ledger is a per-repo tenant database, so `bd` needs the fleet credential
# wrapper WHERE ONE IS INSTALLED — a bare `bd` returns "Access denied" there.
# DETECTED, never hard-coded. And `bd` is TENANT-SCOPED BY CWD: a bare
# `bd show <id>` from the wrong repo does NOT error, it silently returns NOTHING.
ledger_show() {
  if command -v with-livespec-env.sh >/dev/null 2>&1; then
    with-livespec-env.sh -- bd show "$1" --json
  else
    bd show "$1" --json
  fi
}
if ! ledger_json="$(ledger_show "$ledger_anchor")"; then
  echo "HALT: cannot re-measure ledger item '$ledger_anchor'"
  echo "REMEDY: check the credential wrapper is on PATH and that the cwd is the right tenant"
  exit 1
fi
[ -n "$ledger_json" ] \
  || { echo "HALT: re-measure exited 0 but returned NOTHING"; echo "REMEDY: an empty success is not a reading — confirm the anchor exists and the cwd tenant is correct"; exit 1; }
printf '%s\n' "$ledger_json"
date -u '+MEASURED_AT: %Y-%m-%dT%H:%M:%SZ'
```

## Generator provenance

The digest is the generator identity; the ref is DETECTED, never pinned, because
this host republishes the plugin often and a pinned ref fails on the calendar
rather than on the artifact.

```sh
generator_plugin='livespec-overseer'
generator_prose_md5='eaebe06065b3efa0053d6ea5932d52c0'
cache_root="$HOME/.codex/plugins/cache/$generator_plugin/$generator_plugin"
if [ ! -d "$cache_root" ]; then
  printf '%s\n' "UNVERIFIED: no plugin cache at $cache_root, so provenance cannot be checked here. Recorded generator: $generator_prose_md5"
else
  matched=''; found=''
  for candidate in "$cache_root"/*/prose/supervise-plan.md; do
    [ -f "$candidate" ] || continue
    found="$found $candidate"
    candidate_md5=$(md5sum "$candidate" 2>/dev/null | cut -d' ' -f1)
    [ -n "$candidate_md5" ] \
      || { echo "HALT: cannot digest the installed generator prose at $candidate"; echo "REMEDY: fix read access before trusting anything this charter says about its own currency"; exit 1; }
    if [ "$candidate_md5" = "$generator_prose_md5" ]; then matched="$candidate"; break; fi
  done
  if [ -z "$found" ]; then
    echo "HALT: the cache at $cache_root holds NO prose/supervise-plan.md at any ref"
    echo "REMEDY: regenerate this charter, or reinstall the generator plugin"
    exit 1
  fi
  if [ -z "$matched" ]; then
    echo "HALT: this charter was emitted by generator $generator_prose_md5 but NO installed ref digests to that value"
    for candidate in $found; do printf '  installed: %s\n' "$(md5sum "$candidate")"; done
    echo "REMEDY: regenerate this charter before driving, or re-stamp deliberately after reading what changed"
    exit 1
  fi
  printf '%s\n' "PASS: charter provenance matches the installed generator ($generator_prose_md5) at $matched"
fi
```

Last verified 2026-08-04T15:21Z, matching at ref `0.30.2` — the fourth distinct
ref to carry this same digest, which is why the ref is detected rather than
pinned.

## Thread-specific Valves

Retained because the archived record cites them, and because a future reader may
mistake a closed thread's boundaries for open questions.

- `livespec` plan thread `fleet-shell-discipline` owns what the shell convention
  is. This thread owned building and shipping its mechanical enforcement from
  `livespec-dev-tooling`; it did not redefine the sibling's design authority.
- Coverage included bash recipes embedded in `justfile`s, not only tracked `.sh`
  files.
- Not every `set -uo pipefail` occurrence is an error; distinguishing a documented
  deviation from an accidental one WAS the deliverable — and `gmwckx` proved the
  first implementation of that distinction could be satisfied by a stray hyphen.
- Run a positive control before accepting an empty result. This was violated four
  times and caught four times.
- The `ci-green` branch-protection finding was never absorbed into this thread.

## Corrections

Thread-specific corrections belong here. Regeneration MUST preserve this
section byte-for-byte, from the heading through the end of the section,
including spelling, punctuation, code formatting, blank lines, and ordering.
