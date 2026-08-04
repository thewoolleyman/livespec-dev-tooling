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

## Live restart state — 2026-08-04T02:34Z

This section is the authoritative handoff from the outgoing supervisor. Re-read
the shared protocol, this whole file, `handoff.md`, the maintainer inbox, and the
runtime worker log before acting. Re-measure all external state; timestamps and
CI status below are evidence, not permission to assume they remain current.

### Superseding measurements — 2026-08-04T02:41Z

Taken by the restarted supervisor on a cold open. Where these disagree with the
02:34Z record below, these win; the older text is kept as evidence, not as
instruction.

- **The wind-down HANDOFF-CORRECTION was NOT consumed before its PR merged.**
  PR 1236 merged at `ba41f414cdbd0bf9056b57339d6668b36a9fed04`, and the
  `handoff.md` it published still said a maintainer must choose a sanctioned
  route. The correction was still sitting in the worker pane's "Queued follow-up
  inputs" at 02:38Z. It was consumed at ~02:46Z, and the worker then corrected
  the paragraph itself in PR 1237 (`c1774af`), which supersedes it with a
  numbered bounded restart sequence. **`handoff.md` stays worker-owned**: the
  supervisor had prepared a competing correction on this branch and dropped it
  once PR 1237 appeared, so the two PRs touch disjoint files. This is the third
  time stale worker-pane text has driven this thread's state: **verify
  consumption, never assume it.**
- The fleet worker is ALIVE, not wound down: a live `codex` driver in
  `'=fleet-shell-quality-enforcement:'`, reading "Working" with queued input.
  Its `.overseer-state` still says `winding-down`. Do not interrupt or kill it.
- The `move:<id>:ready` route is VERIFIED against installed 0.50.1 code, not
  assumed, and verified TWICE INDEPENDENTLY — the supervisor read the modules at
  02:40Z and the worker reached the identical conclusion at 02:48Z from its own
  read. `commands/_drive_valves.py` dispatches the `move:` prefix and parses
  `move:<item>:<target>` as three parts, so the dotted child id resolves;
  `commands/_drive_policy_valves.py::move_item` restricts targets to
  `_MOVE_ALLOWED = {backlog, ready, blocked}`, refuses `done`, `acceptance`, and
  `pending-approval` with `forbidden-move-target`, imposes no source-status
  restriction, and writes `clear_assignee=True`. There is no pending maintainer
  decision. The bounded restart sequence lives in `handoff.md`.
- The supervisor deliberately did NOT fire the valve itself, though it was
  mechanically available and proven safe. `backlog` is acting as a dispatch
  interlock: moving the P0 to `ready`/unassigned with an indeterminate gap before
  dispatch would make it eligible for another session's `next`-ranked autonomous
  pickup — the duplicate-run hazard this thread has repeatedly fought. The move
  must stay immediately adjacent to its zero-run/master-green preflight and its
  single `impl:` drive, in one owner chain.
- Ledger re-measured 02:38:57Z: `livespec-dev-tooling-42t4az.1` is `backlog`,
  priority 0, labels `intake:triaged`/`origin:freeform`, no Fabro assignee, one
  parent-child dependency on the reopened epic. Still zero run, claim, branch,
  worktree, or implementation PR.
- Master advanced to `ba41f414cdbd0bf9056b57339d6668b36a9fed04`. The primary
  checkout was one commit behind at measurement time.
- PR 1232 re-measured OPEN, `BLOCKED`, 65 checks with **zero** not-green and one
  pending `check-fleet-conformance`. The maintainer-directed monitor session
  issued exactly ONE failed-jobs-only rerun of run `30869349064` at ~02:45Z
  after App installation `131208965` rate-limited it at 01:39–01:41Z. **Do not
  issue a second rerun**; measure that one. Positive control for the check
  itself: PR 1236's `check-fleet-conformance` completed SUCCESS at ~02:35Z, so a
  failure there is not evidence the check is permanently broken.
- Binder provenance was re-stamped `0.15.0` → `0.27.1` with the digest
  unchanged; see the Generator provenance section for why that is a re-stamp
  rather than a weakening.
- **All three open plan PRs are BLOCKED on the same infrastructure**, not on
  their own content: GitHub App installation `131208965` is exhausted and
  returned `rate_limited` HTTP 403 for `repo_metadata` at 02:44:47Z and a
  `contents` retry at 02:46:15Z, failing only `check-fleet-conformance`/
  `ci-green` on PRs 1232, 1237, and 1238. The worker recorded this in
  `.overseer-state` and correctly refused an unchanged rerun. That remedy is
  owned by the `rop-railway-enforcement` chain — do NOT duplicate it, and do not
  add reruns on top of the monitor's single authorized one. This is a WAIT, not
  a maintainer question.

### Immediate critical path

1. Do **not** revert livespec PR #1179. The livespec repo is already unblocked.
2. Maintainer-directed P0 `livespec-dev-tooling-42t4az.1` is the current fleet
   blocker. It fixes `check-shell-quality` crashing with a `TypeError` when the
   `shellcheck` executable is absent. The remedy must be an actionable typed
   check failure naming the missing tool/provisioning remedy; never skip,
   weaken, or silently mark the check unavailable.
3. The P0 currently has lifecycle status `backlog`, priority 0, no assignee, and
   labels `intake:triaged` plus `origin:freeform`. Two normal `impl:` attempts
   stopped before admission and created **no** Fabro run, claim, branch,
   worktree, or PR:
   - first stop: master CI run `30870621857` was red only because PyPI timed out
     downloading `packaging==26.2` after five retries;
   - second stop: on green master, the dispatcher normalized beads-native
     `open` to livespec lifecycle `backlog` (`beads-native intake default`).
4. This is not a grooming problem. The item is already triaged and is a narrow
   bug. Installed drive code exposes the guarded operator valve
   `move:livespec-dev-tooling-42t4az.1:ready`; `backlog` is an allowed source,
   `ready` is an allowed target, the valve clears the assignee, and it cannot
   force `acceptance` or `done`. The maintainer explicitly directed autonomous
   completion, and the outgoing supervisor authorized this safe route.
5. The existing fleet worker is winding down at its lease boundary and is
   publishing a fresh durable `handoff.md`. Do not interrupt or kill it. The
   supervisor queued this exact wind-down correction in its TUI: the handoff
   must not say a new maintainer decision is required; on restart the **same
   owner chain** should remeasure zero-run/current-master-green state, execute
   exactly one guarded `move:...:ready`, verify ready/unassigned, then execute
   exactly one normal `impl:` drive and attach to the admitted run. Verify that
   queued input was consumed and submitted, because stale text in worker panes
   has been a real failure mode in this thread.

### Live sessions and files

- Worker target: `'=fleet-shell-quality-enforcement:'`.
- Acting overseer target: `'=livespec-overseer:'`; never kill or restart the
  acting overseer. Its normal owner/release chain must restart the fleet worker.
- Worker marker at handoff time:
  `tmp/overseer/fleet-shell-quality-enforcement/.overseer-state` contained
  `winding-down`.
- Runtime evidence:
  `tmp/overseer/fleet-shell-quality-enforcement/worker-status.log`; its latest
  relevant line was `P0-LIFECYCLE-BLOCK` at `2026-08-04T02:29:58Z`.
- Maintainer inbox, read in full:
  `tmp/overseer/fleet-shell-quality-enforcement/INBOX-from-livespec-spec-side-autonomy.md`.
- The worker created the owned wrap-up worktree
  `/home/ubuntu/.worktrees/livespec-dev-tooling/wrapup-fleet-shell-quality-enforcement`
  on branch `wrapup-fleet-shell-quality-enforcement` from `8cdfebb6`; at the
  instant of this supervisor handoff it was validating the copied `handoff.md`
  and had not yet reported a commit/PR/merge. Let it finish, then remeasure and
  remove only through its own janitor path.

### Parked projection correction

- Supervisor-owned worktree:
  `/home/ubuntu/.worktrees/livespec-dev-tooling/feat/livespec-dev-tooling-jtrjzk`
- Branch: `fix/jtrjzk-release-tag-tool-pin-v3`
- PR: <https://github.com/thewoolleyman/livespec-dev-tooling/pull/1232>
- Commit: `f65363e78eed20fcc4e8a3e86afe42391713d41d`
- It implements typed exact-release-tag ShellCheck-pin projection and preserves
  an honest one-commit Red/Green Replay. Full hooks passed: 65/65 targets,
  2,619 tests, 100% coverage. Do not amend or unchanged-rerun it.
- PR #1232's only failure was fleet-conformance installation-rate exhaustion,
  not its code. Keep it parked until the P0 lands; then meaningfully rebase it
  onto P0-containing master and let fresh CI validate the combined release.
- Corrected release identity is the first tag whose commit contains **both**
  the P0 merge and PR #1232 merge. Do not treat v1.18.6 as corrected.

### CI/rate state

- Last measured green master before wind-down was
  `8cdfebb6e9fa3104bf430f8c20bfbe8cc272033e`, run `30871628988`, including
  fleet conformance. Fetch and remeasure; master may advance during restart.
- Never request or trigger an unchanged paid rerun of livespec PR #1954. It was
  fixed through the core parser compatibility chain and merged without one.
- Avoid unchanged reruns generally. Fleet GitHub App installation exhaustion
  and cross-run contention are owned by the existing `rop-railway-enforcement`
  owner/release chain; do not duplicate that remedy.

### Release and fleet completion after the P0

1. Land the P0 factory PR through honest Red/Green Replay and required checks.
   Close `livespec-dev-tooling-42t4az.1`, then append the required one-line
   landed notification to
   `/data/projects/livespec/tmp/overseer/spec-side-autonomy/worker-status.log`.
2. Rebase, validate, and merge PR #1232 as described above.
3. Hold generated fan-out PRs until the combined corrected release exists.
   v1.18.6 is pre-correction. Open held v1.18.6 PRs measured earlier were:
   livespec #1966, driver-claude #407, driver-codex #386, beads-fabro #1281,
   git-jsonl #536, runtime #465, and overseer #647. Console #630 had already
   merged; supersede it, do not revert it. Re-measure all eight repos.
4. Use one Driver missing ShellCheck today as the real corrected-release
   rehearsal. Prove its projected `.mise.toml` contains the exact released
   ShellCheck version and shell-quality CI is green before admitting the rest.
5. Roll the corrected release through all eight repos by their normal PR/rebase
   merge chains and close: `livespec-akg7k5`, `driver-claude-gtqrzu`,
   `driver-codex-bedeju`, `bd-ib-35qhta`, `bd-gj-uworva`, `runtime-ohlb4f`,
   `console-6yii4r`, and `overseer-cdhdlv`.
6. Only after every pinned consumer reads `check-targets.txt`, implement and
   close `livespec-dev-tooling-42t4az.2` to retire the legacy 65-target justfile
   mirror. Do not remove it early.
7. Close closeout `livespec-dev-tooling-qgw7gb`, then epic
   `livespec-dev-tooling-42t4az`. Archive this plan in a separate PR by moving
   it to `plan/archive/fleet-shell-quality-enforcement`, then merge and clean.

### Repo/worktree hygiene

- Primary was last measured equal to `origin/master` with only the user's
  untracked `install-livespec-pr-bot.png`; preserve it byte-for-byte. Its SHA256
  was `a3e2d35997c60459df71fd16d608c71560eeea16d0aee11422db7eecba204fe5`.
- At supervisor handoff time the fleet worker had intentionally modified
  `plan/fleet-shell-quality-enforcement/handoff.md` in the primary while copying
  it to its wrap-up worktree. This supervisor is also modifying this file at the
  user's explicit request. Do not discard either handoff edit; finish the
  worktree/PR/merge/cleanup protocol after restart.
- Preserve all unrelated worktrees. After PR #1232 merges, clean only its owned
  worktree plus obsolete local branches `feat/livespec-dev-tooling-jtrjzk`,
  `fix/jtrjzk-release-tag-tool-pin`, and
  `fix/jtrjzk-release-tag-tool-pin-v2`, and the owned stash
  `abandon-impossible-nonpy-green`, after re-verifying each target.
- Final state must be primary `master == origin/master`, no owned worktrees or
  branches, and only the preserved PNG untracked.

### Security follow-up

Earlier tool output in this long supervisor session exposed provider and
Cloudflare connector secret values. Never repeat them. Before final closeout,
tell the maintainer to rotate the Claude/Codex provider credentials and
Cloudflare connector tokens, update the Claude 1Password Environment, and
redact the affected transcript.

## Generator provenance

The digest is the generator identity. Plugin name, cache ref, and version are
human-readable companions; they do not replace the digest. This charter was
emitted from the installed Codex plugin root actually read by the generator:

```sh
generator_plugin='livespec-overseer'
generator_ref='0.27.1'
generator_version='0.27.1'
generator_prose_md5='eaebe06065b3efa0053d6ea5932d52c0'
cache_root="$HOME/.codex/plugins/cache/$generator_plugin/$generator_plugin"
generator_prose="$cache_root/$generator_ref/prose/supervise-plan.md"
if [ ! -d "$cache_root" ]; then
  printf '%s\n' "UNVERIFIED: no plugin cache at $cache_root, so this is not a host that generates charters and provenance cannot be checked here. Recorded generator: $generator_prose_md5"
elif [ ! -f "$generator_prose" ]; then
  echo "HALT: the cache at $cache_root no longer holds ref $generator_ref, so the generator that emitted this charter has been replaced"
  echo "REMEDY: regenerate this charter with supervise-plan, or re-point generator_ref at the installed ref and re-stamp generator_prose_md5 from it"
  exit 1
else
  installed=$(md5sum "$generator_prose")
  digest_rc=$?
  [ "$digest_rc" -eq 0 ] \
    || { echo "HALT: cannot digest the installed generator prose at $generator_prose"; echo "REMEDY: fix read access before trusting anything this charter says about its own currency"; exit 1; }
  installed_md5=${installed%% *}
  [ "$installed_md5" = "$generator_prose_md5" ] \
    || { echo "HALT: this charter was emitted by generator $generator_prose_md5 but the installed generator is $installed_md5"; echo "REMEDY: regenerate this charter before driving, or re-stamp generator_prose_md5 deliberately after reading what changed between the two"; exit 1; }
  printf '%s\n' "PASS: charter provenance matches the installed generator ($installed_md5)"
fi
```

A missing cache root means provenance is UNVERIFIED on a non-generating host
and execution may continue. An existing cache root whose recorded ref has
disappeared means the generator was replaced and is a HALT.

Re-stamped 2026-08-04T02:40Z, digest deliberately untouched. The recorded ref
`0.15.0` had disappeared from the cache and the block HALTed a cold-open
supervisor. The only installed ref is now `0.27.1`, and its
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
