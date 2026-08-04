# Supervisor Handoff - fleet-shell-quality-enforcement

## Shared Protocol

Read `.ai/supervisor-protocol.md` before driving. Validate this binder together
with that shared layer; this binder is intentionally incomplete by itself.

Regeneration MUST preserve both Corrections layers byte-for-byte: the shared
role-level Corrections in `.ai/supervisor-protocol.md` and this binder's
thread-specific Corrections. Preserve spelling, punctuation, code formatting,
blank lines, and ordering exactly; do not normalize markdown or code spans.

Run this cold-open boot block before driving:

```sh
test -f ".ai/supervisor-protocol.md" \
  || { echo "HALT: missing shared supervisor protocol .ai/supervisor-protocol.md"; echo "REMEDY: regenerate the two-layer supervisor handoff before driving"; exit 1; }
printf '%s\n' "BOOT: read .ai/supervisor-protocol.md, this binder, and the supervisor marker if it exists"
[ -n "${supervisor_marker:-}" ] \
  || { echo "HALT: supervisor_marker is unset or empty"; echo "REMEDY: resolve it from this binder's bindings table before running this block — an unset marker makes the read below display NOTHING and still exit 0"; exit 1; }
if [ ! -f "$supervisor_marker" ]; then
  printf '%s\n' "NOTE: no supervisor marker at $supervisor_marker yet — nothing to read."
else
  marker_lines=$(wc -l < "$supervisor_marker")
  if [ "$marker_lines" -le 400 ]; then
    cat "$supervisor_marker"
  else
    sed -n '1,160p' "$supervisor_marker"
    printf '\n*** TRUNCATED: lines 161-%d of %d NOT SHOWN (%d hidden). A claim above may be RETRACTED in the hidden range. Read %s in full before acting on anything above. ***\n\n' \
      "$((marker_lines - 160))" "$marker_lines" "$((marker_lines - 320))" "$supervisor_marker"
    sed -n "$((marker_lines - 159)),${marker_lines}p" "$supervisor_marker"
  fi
fi
```

The marker read is whole-file through 400 lines and head-and-tail beyond that.
The truncation notice is mandatory whenever content is hidden: a fixed cap goes
stale, can separate a claim from its later retraction, and drops the corrections
that append at the highest-value end of the file.

## Bindings

Resolve and report these startup bindings before driving. They carry no live
status, next action, or date-gated behavior.

| Binding | Expression | Resolved value |
|---|---|---|
| `repo_primary` | concrete | `/data/projects/livespec-dev-tooling` |
| `thread_dir` | concrete | `/data/projects/livespec-dev-tooling/plan/fleet-shell-quality-enforcement/` |
| `topic` | concrete | `fleet-shell-quality-enforcement` |
| `worker_session` | concrete | `fleet-shell-quality-enforcement` |
| `supervisor_session` | concrete | `fleet-shell-quality-enforcement-supervisor` |
| `WORKER_TARGET` | concrete | `'=fleet-shell-quality-enforcement:'` |
| `SUPERVISOR_TARGET` | concrete | `'=fleet-shell-quality-enforcement-supervisor:'` |
| `runtime_dir` | `<repo_primary>/tmp/overseer/<topic>/` | `/data/projects/livespec-dev-tooling/tmp/overseer/fleet-shell-quality-enforcement/` |
| `supervisor_marker` | `<runtime_dir>/.supervisor-state` | `/data/projects/livespec-dev-tooling/tmp/overseer/fleet-shell-quality-enforcement/.supervisor-state` |
| `wait_channel` | `<runtime_dir>/worker-status.log` | `/data/projects/livespec-dev-tooling/tmp/overseer/fleet-shell-quality-enforcement/worker-status.log` |
| `ledger_anchor` | concrete | `livespec-dev-tooling-42t4az` |

Complete placeholder declaration for the two-layer charter:

- Concretely bound generation placeholders: `<repo-primary>` and
  `<absolute-target-repo>` are `/data/projects/livespec-dev-tooling`;
  `<topic>` is `fleet-shell-quality-enforcement`; `<worker-session>` is
  `fleet-shell-quality-enforcement`; `<supervisor-session>` is
  `fleet-shell-quality-enforcement-supervisor`; and `<ledger-anchor>` is
  `livespec-dev-tooling-42t4az`.
- Composed bindings, resolved transitively to the fixed values in the table:
  `<runtime-dir>`, `runtime_dir`, `supervisor_marker`, and `wait_channel`.
- Runtime slots deliberately left unsubstituted: `<condition-command>`,
  `<short-slug>`, and `<branch>`.
- Illustrative placeholders occur only in prose or the obligation-schema YAML,
  never as unresolved generation-time values in fenced shell commands.

## Live restart state — 2026-08-04T15:10Z

This section is the authoritative handoff from the outgoing supervisor and has
been rewritten to current reality; earlier restart-state text was deleted rather
than layered, because stale layers in THIS file have twice sent a supervisor down
a dead path. Re-read the shared protocol, this whole file, the worker's
`handoff.md`, and the runtime worker log before acting. **Re-measure everything.**
Timestamps below are evidence, not permission — three separate times this session
something changed between two of my own measurements.

The richer running record is
`tmp/overseer/fleet-shell-quality-enforcement/worker-status.log` (~270 lines) and
the obligation record `.supervisor-state` in the same directory. Both are on disk,
NOT in git, so they survive a restart but not a machine loss.

### THE ONE THING THAT MATTERS FIRST: your worker is CLAUDE, and it is healthy

A maintainer-directed runtime switch replaced the Codex worker with `claude` in
the SAME tmux session and repo cwd, so overseer per-session tracking continuity
holds. **The Codex exit was deliberate, not a crash.** Do not "recover" it, and do
not let an owner/release chain respawn a Codex worker over the Claude one. The
HALT-first precondition accepts a live `claude` OR `codex` driver, so a green
precondition proves NOTHING about which runtime is present — read the process tree.

The worker is driving well and does not need rescuing. At 15:05Z it was at 77%
context, had answered both of its blocking questions, and was working the
`42t4az` children. See "How to inspect and drive" for the steering mechanics —
in particular that steering QUEUES to the next turn boundary and does NOT preempt
a long turn.

### Where the epic actually stands

Measured 15:06Z. Re-measure before acting on any of it.

- **P0 `42t4az.1`, `jtrjzk`: CLOSED.** v1.18.7 was the corrected release.
- **Rollouts: 6 of 8 CLOSED** — driver-claude, driver-codex, bd-gj-uworva,
  console-6yii4r, `overseer-cdhdlv` (PR 686 at `9825253d`, merge CI green,
  ledger closed, primary refreshed), and runtime's implementation.
- **`livespec-akg7k5`: the last live rollout, and it is a HOLD, not a stall.**
  Its durable run `01KZ6GBEPR5QMAXMQD3W9X3VYK` was `cancelled` while HEALTHY —
  implement had succeeded — and the worker could not attribute the cancel (no
  fabro CLI cancel logged, no watchdog entry, and the engine's zero-event
  watchdog is a 2h timer against 37m elapsed). The item is `active`/`fabro` with
  the claim DELIBERATELY held.
- **`livespec-runtime-ohlb4f`: rollout DONE, ledger not closeable.** PR 467
  merged at `25d300f9` carrying the recipe→`.sh` migration, the aggregate slug
  and its ci.yml matrix job. `reconcile-merged` then exited red at
  `janitor-post-merge` on ONE target, `check-master-ci-green` — an unrelated red
  master, NOT our rollout. The dispatcher's diagnostic checkout
  `~/.worktrees/livespec-runtime/janitor-reconcile-livespec-runtime-ohlb4f` is
  retained ON PURPOSE; do not delete it, force-close the ledger, or redispatch.
- **Epic children**: `.2` backlog (retire the legacy mirror ONLY once every
  pinned consumer reads `check-targets.txt` at the version it pins); `.3` open P1
  and `.4` open P2. Closeout `qgw7gb` pending-approval; epic `42t4az` backlog.
- **New this session**: `bd-ib-zp3u7y` filed — the pre-branch stranded-dispatch
  visibility defect, with a live reproduction. It explicitly states the fix must
  NOT merely widen the payload tuple.

### The two blockers, and neither is ours to fix

1. **Three fleet masters are red on `check-public-api-result-typed`**, and the
   owning ROP chain `livespec-dev-tooling-8o8e` reads backlog/UNASSIGNED. This is
   what blocks `ohlb4f` reconcile and makes `qgw7gb`'s "green master in all nine
   tenants" unsatisfiable today, for non-shell reasons. Ruling chosen and already
   acted on: **escalate, do not absorb.** The measured three-tenant blast radius
   is recorded as a comment on `8o8e`, including the single-commit arming control
   (runtime `25d300f9` SUCCESS → `54abd7c7` FAILURE, where the only content is a
   pin bump). Do NOT convert other tenants' APIs; that is another chain's lane.
   DO keep it escalated — an unassigned chain blocking three tenants should not
   go quiet.
2. **The `akg7k5` re-drive gate is PARTIALLY open.** The foreign livespec run has
   cleared and the blind-spot defect is filed. The zero-collision preflight was
   CLEAN at 15:04Z: no `feat/livespec-akg7k5` on the forge, no implementation PR,
   no worktree, no local branch, lock pid dead/auto-reclaimable. **One condition
   remains:** livespec master advanced to `fba470bc` with CI run `30922077153`
   QUEUED, and the dispatcher refuses to dispatch onto a red master
   (`bd-ib-wefw`). Because the guarded `move:livespec-akg7k5:ready` must land with
   NO gap before the drive, releasing the claim before master is green risks
   leaving the item ready/unassigned and next-rankable while the drive is refused.
   **Order: let livespec master CI settle GREEN, then move + drive as ONE
   uninterrupted sequence.** Never release the claim earlier.

### My own in-flight work — ONE PR, and it carries this handoff

`livespec-dev-tooling` PR **1268**, branch `docs/steering-lands-at-turn-boundary`,
worktree `~/.worktrees/livespec-dev-tooling/steering-correction`. Auto-merge
armed. It carries BOTH the steering-mechanics correction and this rewritten
restart state — deliberately one branch, because a second branch would have
conflicted on this same file. If it has merged, remove that worktree and branch.
If it is open with **zero pending** and red, that is this repo's signature
stale-check trap: REBASE it, never issue an unchanged rerun.

### Hazards this session actually hit — do not re-learn them

- **I shipped a DUPLICATE remedy.** I diagnosed the fabro sandbox image failure
  and authored the whole fix through a Red/Green ritual, only to find PR 1257 had
  already merged the byte-identical change. I HAD checked for competing PRs first
  — the point is that the check has a SHELF LIFE. Re-check IMMEDIATELY BEFORE
  PUSHING whenever the gap is more than a few minutes.
- **A zero-notice cross-lane write.** I wrote to `dolt-server` before notifying
  its lane, and only posted a retrospective claim notice after the monitor
  flagged it. Claim FIRST, then write.
- **The stale-check trap is this repo's signature failure.** A PR parked while
  something else blocked sits with zero pending and stale reds; CI never re-runs
  and auto-merge never fires. Check `pending == 0` before assuming it will land.
- **v1.18.8 was DEAD ON ARRIVAL fleet-wide** — its sandbox images never published
  because the image producer failed on a `gh` apt pin upstream deleted. Such PRs
  fail at Docker pull with `manifest unknown` and ZERO check output. Never triage
  those reds as product findings. Fixed and superseded by the v1.18.9+ wave.
- **A pinned version can fail on the calendar rather than on the artifact.** Both
  the `gh` apt pin and this charter's own `generator_ref` aged out while the thing
  they pinned was unchanged. See Generator provenance for how that was resolved
  WITHOUT weakening the check.
- **`git checkout --ours/--theirs` during a rebase is inverted** from intuition:
  `--ours` is the branch you are rebasing ONTO. Getting it backwards on the
  runtime bump PR would have reverted the migration.
- **A fresh worktree fails `check-primary-checkout-commit-refuse-hook-installed`**
  with `worktree_pack_absent`, because the `dev-tooling/` pack is gitignored. The
  remedy is `just bootstrap` in that worktree — a fix, not a bypass.
- **`bd update --set-metadata k=v` stores the value as a STRING**, silently
  turning a list into JSON text. The success tick does not mean the shape is
  right. Recover with `bd update --metadata @file.json`.
- **Tool-budget order**: `git ls-remote` costs no GitHub budget; GraphQL
  (`gh pr view/list --json`) is plentiful; reserve REST (`gh run view/list`) for
  when a job log is genuinely needed. `fabro ps` costs no GitHub budget. Bare
  `fabro` is not on PATH — use `/home/ubuntu/.local/bin/fabro` under the wrapper.

### Repo/worktree hygiene

Primary measured clean and equal to `origin/master` apart from the user's
untracked `install-livespec-pr-bot.png` (sha256
`a3e2d35997c60459df71fd16d608c71560eeea16d0aee11422db7eecba204fe5`) — preserve it
byte-for-byte. `just bootstrap` leaves a stray `uv.lock` version bump; it is a
local `uv` artifact, not an intended change, so restore it.

⛔ **If `plan/fleet-shell-quality-enforcement/handoff.md` reads modified in the
primary, that is the WORKER writing its own handoff. Do NOT discard it.**

The only worktree I own is the PR 1268 one named above. Every other dev-tooling
worktree in this thread was cleaned. Preserve unrelated worktrees belonging to
other sessions, and never touch another session's branches.

### Security follow-up

Earlier tool output in a prior supervisor session exposed provider and Cloudflare
connector secret values. Never repeat them. Before final closeout, tell the
maintainer to rotate the Claude/Codex provider credentials and Cloudflare
connector tokens, update the Claude 1Password Environment, and redact the
affected transcript.


## Generator provenance

The digest is the generator identity. Plugin name, cache ref, and version are
human-readable companions; they do not replace the digest. This charter was
emitted from the installed Codex plugin root actually read by the generator:

```sh
generator_plugin='livespec-overseer'
generator_prose_md5='eaebe06065b3efa0053d6ea5932d52c0'
cache_root="$HOME/.codex/plugins/cache/$generator_plugin/$generator_plugin"
# The ref is DETECTED, never hard-coded — the same rule this charter already
# applies to the `bd` credential wrapper, and for the same reason. This host
# republishes the plugin often and its cache keeps only the newest ref: the
# recorded companion went 0.15.0 -> 0.27.1 -> 0.27.6 -> 0.29.0, twice HALTing a
# cold-open supervisor, while `prose/supervise-plan.md` digested to the SAME
# value throughout. A pinned ref therefore fails on the calendar rather than on
# the artifact, and a check that cries wolf every cold open teaches supervisors
# to wave it through. The DIGEST remains the sole identity and still HALTs on a
# real mismatch, so this removes a false positive without weakening the gate.
if [ ! -d "$cache_root" ]; then
  printf '%s\n' "UNVERIFIED: no plugin cache at $cache_root, so this is not a host that generates charters and provenance cannot be checked here. Recorded generator: $generator_prose_md5"
else
  matched=''
  found=''
  for candidate in "$cache_root"/*/prose/supervise-plan.md; do
    [ -f "$candidate" ] || continue
    found="$found $candidate"
    candidate_md5=$(md5sum "$candidate" 2>/dev/null | cut -d' ' -f1)
    [ -n "$candidate_md5" ] \
      || { echo "HALT: cannot digest the installed generator prose at $candidate"; echo "REMEDY: fix read access before trusting anything this charter says about its own currency"; exit 1; }
    if [ "$candidate_md5" = "$generator_prose_md5" ]; then
      matched="$candidate"
      break
    fi
  done
  if [ -z "$found" ]; then
    echo "HALT: the cache at $cache_root holds NO prose/supervise-plan.md at any ref, so the generator that emitted this charter is gone"
    echo "REMEDY: regenerate this charter with supervise-plan, or reinstall the generator plugin before driving"
    exit 1
  fi
  if [ -z "$matched" ]; then
    echo "HALT: this charter was emitted by generator $generator_prose_md5 but NO installed ref digests to that value"
    for candidate in $found; do printf '  installed: %s\n' "$(md5sum "$candidate")"; done
    echo "REMEDY: regenerate this charter before driving, or re-stamp generator_prose_md5 deliberately after reading what changed between the two"
    exit 1
  fi
  printf '%s\n' "PASS: charter provenance matches the installed generator ($generator_prose_md5) at $matched"
fi
```

A missing cache root means provenance is UNVERIFIED on a non-generating host
and execution may continue. A cache root that holds NO `supervise-plan.md` at
any ref means the generator is gone and is a HALT. A cache root whose installed
prose digests to something other than the recorded value means the generator was
genuinely REPLACED and is a HALT.

**2026-08-04T10:31Z — the pinned `generator_ref` was REMOVED, and this is a
strengthening rather than a re-stamp.** The pin had to be re-stamped twice in one
morning, and the third churn happened DURING this session: the installed ref went
`0.15.0` → `0.27.1` → `0.27.6` → `0.29.0`, the last two roughly ten minutes
apart, while `prose/supervise-plan.md` digested to
`eaebe06065b3efa0053d6ea5932d52c0` at every single one. So the pin was failing on
the calendar, never on the artifact, and each false HALT stopped a cold-open
supervisor on a charter that was in fact authentic. A gate that cries wolf on
every cold open does not stay respected; it gets waved through, and then it
protects nothing on the day it is right.

The ref is therefore DETECTED across whatever refs the cache holds, and the
DIGEST — which never moved — remains the sole identity. **This does not weaken
the check, and that was verified with controls rather than asserted:** with the
recorded digest altered the block still HALTs `rc=1` and prints what it actually
found; with the cache root emptied of prose it HALTs `rc=1`; with no cache root
it reports UNVERIFIED `rc=0`; and on this host it PASSes naming the detected ref.
The mismatch path is the one that matters, and it still fires. Had the digest
ever differed, the correct action would still have been to regenerate.

Earlier re-stamp, retained as evidence: 2026-08-04T02:40Z, digest deliberately
untouched. The recorded ref `0.15.0` had disappeared from the cache and the block
HALTed a cold-open supervisor. The only installed ref was then `0.27.1`, and its
`prose/supervise-plan.md` digests to `eaebe06065b3efa0053d6ea5932d52c0` — byte
for byte the recorded `generator_prose_md5`. The generator prose was therefore
NOT replaced; only the human-readable version companions moved, so the two
companions were advanced to `0.27.1` and the digest left exactly as emitted.
This is the documented re-stamp path, not a weakening of the check: had the
digest differed, the correct action would still have been to regenerate.

## Thread-specific Valves

- `livespec` plan thread `fleet-shell-discipline` owns what the shell convention
  is. This thread owns building and shipping its mechanical enforcement from
  `livespec-dev-tooling`; do not silently absorb or redefine the sibling's
  design authority.
- Cover the population that triggered the defect: bash recipes embedded in
  `justfile`s, not only tracked `.sh` files. Recipe extraction and `just`
  interpolation handling are part of the evidence boundary.
- Do not promote every `set -uo pipefail` occurrence to an error. Existing
  intentional omissions show that enforcement must distinguish a documented
  deviation from an accidental one without weakening any existing check.
- Run a positive control before accepting an empty shellcheck result, empty
  corpus query, or clean recipe extraction. Measure the full fleet corpus before
  generalizing from the motivating recipe.
- The adjacent `ci-green` branch-protection finding is not automatically in
  scope. Re-measure the ledger before assigning it to this thread.

## How to inspect and drive

The shared protocol owns the role-level rules. These commands substitute this
thread's ledger and tmux bindings so they run as written.

### The worker pane runs CLAUDE, not Codex — steering mechanics changed

Maintainer-directed runtime switch, 2026-08-04. The Codex TUI in session
`fleet-shell-quality-enforcement` was quit deliberately after it published its
restart handoff, and `claude` was launched in the SAME session name and repo cwd
so overseer tracking continuity holds (it detects runtime per session).

**The Codex exit is NOT a crash.** Do not report it as one, do not "recover" the
pane, and do not let the overseer owner/release chain respawn a Codex worker over
the Claude one. The HALT-first precondition above already passes either way — it
accepts a live `claude` OR `codex` driver — so a green precondition is not
evidence about which runtime is present. Read the process tree if you need to
know.

What changes for driving, and it removes two hazards this thread lost real time
to:

- **Steering QUEUES on a plain `Enter` and is delivered at the next turn
  boundary — it does NOT preempt a running turn.** ⛔ An earlier revision of this
  very section claimed it "lands MID-TURN"; that was wrong, and it is corrected
  here from observation rather than left to mislead. What was actually measured:
  submitting while the worker was mid-turn showed
  `Press up to edit queued messages`, the queue did NOT clear while the busy
  indicator was up, and it cleared only once the turn ended — after which the
  worker read the message and acted on it.
  So the good half of the claim holds: there is no Tab dance and **no
  starvation** — the message is reliably delivered and acted on, unlike the
  Codex-era "Queued follow-up inputs" block that drove stale state into
  `handoff.md` through PR 1236. The bad half does not: **an urgent correction
  will NOT interrupt a long-running turn.** If you must stop the worker mid-turn,
  that is `Esc`, not `Enter`. Budget for the wait when a turn is 20+ minutes.
  **Verify consumption either way** — an empty composer alone is not proof the
  message was read; look for the worker acting on it.
- **Long pastes are safe.** The Codex hazard where a pasted buffer rendered as
  several collapsed `[Pasted Content NNNN chars]` placeholders, and where reading
  that counter as truncation led to a C-c/C-u/BSpace "repair" that CHEWED THREE
  CHARACTERS off the real text, does not apply to a Claude pane.

What does NOT change: still send the text, VERIFY it landed with a capture, and
send `Enter` separately. Verify-then-Enter is cheap and catches a mistargeted
pane, which is a hazard of the tmux target, not of the runtime.

```sh
ledger_anchor='livespec-dev-tooling-42t4az'
# The ledger is a per-repo tenant database, so `bd` needs the fleet credential
# wrapper WHERE ONE IS INSTALLED — a bare `bd` returns "Access denied" there.
# DETECTED, never hard-coded: an adopter without the wrapper must still be able
# to re-measure, and a hard-coded path would only trade one false HALT for
# another.
ledger_show() {
  if command -v with-livespec-env.sh >/dev/null 2>&1; then
    with-livespec-env.sh -- bd show "$1" --json
  else
    bd show "$1" --json
  fi
}
if ! ledger_json="$(ledger_show "$ledger_anchor")"; then
  echo "HALT: cannot re-measure ledger item '$ledger_anchor'"
  if command -v with-livespec-env.sh >/dev/null 2>&1; then
    echo "REMEDY: the credential wrapper WAS used, so ledger access is not the suspect — check the anchor id is real and that this repo's tenant is reachable"
  else
    echo "REMEDY: no credential wrapper on PATH, so a BARE 'bd' ran — if this repo's ledger is a tenant database, install/expose the fleet credential wrapper; otherwise check the anchor id"
  fi
  exit 1
fi
[ -n "$ledger_json" ] \
  || { echo "HALT: ledger re-measure for '$ledger_anchor' exited 0 but returned NOTHING"; echo "REMEDY: do not record this as a measurement — an empty success is not a reading; confirm the anchor exists and that the ledger tool is actually reporting"; exit 1; }
printf '%s\n' "$ledger_json"
date -u '+MEASURED_AT: %Y-%m-%dT%H:%M:%SZ'
```

```sh
WORKER_TARGET='=fleet-shell-quality-enforcement:'
pane_pid=$(tmux display-message -p -t "$WORKER_TARGET" '#{pane_pid}')
tmux_rc=$?
[ "$tmux_rc" -eq 0 ] \
  || { echo "HALT: tmux pane lookup failed for 'fleet-shell-quality-enforcement'"; echo "REMEDY: re-check the exact target before filtering its output"; exit 1; }
printf '%s\n' "$pane_pid" | head -1
```

## HALT-first preconditions

Verify the exact worker session `fleet-shell-quality-enforcement`, exact
supervisor session `fleet-shell-quality-enforcement-supervisor`, and exact
target repository `/data/projects/livespec-dev-tooling` before doing anything
else. Stop on the first failure, report the exact expected name, and act on the
literal labelled `REMEDY:`. The process-tree checks pass only when a live
`claude` or `codex` driver appears.

1. Supervised session exists:

```bash
WORKER_TARGET='=fleet-shell-quality-enforcement:'
tmux has-session -t "$WORKER_TARGET" \
  || { echo "HALT: expected worker session 'fleet-shell-quality-enforcement'"; echo "REMEDY: ask the maintainer whether to start that worker session"; exit 1; }
```

2. The supervised session is a live agent session:

```bash
WORKER_TARGET='=fleet-shell-quality-enforcement:'
pane_pid=$(tmux display-message -p -t "$WORKER_TARGET" '#{pane_pid}')
[ -n "$pane_pid" ] \
  || { echo "HALT: empty pane_pid for 'fleet-shell-quality-enforcement'"; echo "REMEDY: re-check the exact worker target and stop if it still resolves empty"; exit 1; }
ps -o pid=,comm=,args= --ppid "$pane_pid" --pid "$pane_pid" -H
# PASS only if a live `claude` or `codex` process appears in that tree.
# A lone shell (zsh/bash) with no agent child is a HALT.
# REMEDY: if no live agent appears, ask the maintainer whether to restart the worker.
```

3. The supervisor session exists, is distinct, and is a live agent session:

```bash
WORKER_TARGET='=fleet-shell-quality-enforcement:'
SUPERVISOR_TARGET='=fleet-shell-quality-enforcement-supervisor:'
tmux has-session -t "$SUPERVISOR_TARGET" \
  || { echo "HALT: expected supervisor session 'fleet-shell-quality-enforcement-supervisor'"; echo "REMEDY: switch to the correct supervisor session or ask the maintainer to bootstrap it"; exit 1; }
pane_pid=$(tmux display-message -p -t "$WORKER_TARGET" '#{pane_pid}')
supervisor_pane_pid=$(tmux display-message -p -t "$SUPERVISOR_TARGET" '#{pane_pid}')
[ -n "$supervisor_pane_pid" ] \
  || { echo "HALT: empty pane_pid for 'fleet-shell-quality-enforcement-supervisor'"; echo "REMEDY: re-check the exact supervisor target and stop if it still resolves empty"; exit 1; }
[ "$supervisor_pane_pid" != "$pane_pid" ] \
  || { echo "HALT: supervisor and worker resolve to the SAME pane"; echo "REMEDY: re-check both exact targets — a prefix match puts both names on one pane, and the worker's agent then reads as the supervisor's"; exit 1; }
ps -o pid=,comm=,args= --ppid "$supervisor_pane_pid" --pid "$supervisor_pane_pid" -H
# PASS only if a live `claude` or `codex` process appears in that tree.
# A lone shell (zsh/bash) with no agent child is a HALT.
# REMEDY: if no live agent appears, ask the maintainer to start the agent in that session.
```

4. The plan thread exists inside the target repository:

```bash
test -d "/data/projects/livespec-dev-tooling/plan/fleet-shell-quality-enforcement" \
  || { echo "HALT: missing plan thread /data/projects/livespec-dev-tooling/plan/fleet-shell-quality-enforcement"; echo "REMEDY: create or choose the correct plan topic before supervising"; exit 1; }
```

5. The worker pane cwd resolves inside the target repository:

```bash
WORKER_TARGET='=fleet-shell-quality-enforcement:'
pane_cwd=$(tmux display-message -p -t "$WORKER_TARGET" '#{pane_current_path}')
[ -n "$pane_cwd" ] \
  || { echo "HALT: empty pane_current_path for 'fleet-shell-quality-enforcement'"; echo "REMEDY: re-check the exact worker target and stop if it still resolves empty"; exit 1; }
case "$(readlink -f -- "$pane_cwd")" in
  /data/projects/livespec-dev-tooling|/data/projects/livespec-dev-tooling/*) echo "PASS: $pane_cwd" ;;
  *) echo "HALT: pane cwd $pane_cwd is outside the target repo"; echo "REMEDY: move the worker into the target repo or start the correct worker session"; exit 1 ;;
esac
```

## Corrections

Thread-specific corrections belong here. Regeneration MUST preserve this
section byte-for-byte, from the heading through the end of the section,
including spelling, punctuation, code formatting, blank lines, and ordering.
