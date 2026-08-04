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

## Live restart state — 2026-08-04T10:15Z

This section is the authoritative handoff from the outgoing supervisor. Re-read
the shared protocol, this whole file, `handoff.md`, the maintainer inbox, and the
runtime worker log before acting. Re-measure all external state; timestamps and
CI status below are evidence, not permission to assume they remain current.

The richest running record is
`tmp/overseer/fleet-shell-quality-enforcement/worker-status.log` (~200 lines) and
the obligation record `.supervisor-state`. Both are on disk, NOT in git.

### Superseding measurements — 2026-08-04T10:30Z

Taken by the restarted supervisor on a cold open. Where these disagree with the
10:15Z record below, these win; the older text is kept as evidence, not as
instruction.

- **THE FREEZE IS LIFTED. The section immediately below is HISTORY, not a task.**
  Both legs landed while this supervisor was measuring: `livespec-driver-codex`
  PR 390 (the narrow revert) merged at 10:20:38Z, and `livespec-dev-tooling`
  PR 1248 merged at 10:25:01Z. Master `2aa4187` carries the declaration and has
  since advanced past `d4d4030` (`release 1.18.8`), which is itself the proof
  that merges flow again.
- **LEG 3 NO LONGER NEEDS DECLARATIONS, and that instruction below is WRONG.**
  PR 1248 already added BOTH keys — `cross_repo_public_api` gains
  `shell_quality.py::main`, and `supervisor_entry_files` gains the same path.
  Verified by reading both hunks, not by trusting the note: the guard was read
  before declaring (the consumer binds `rc = shell_quality.main()` and asserts
  the int, so there is no `is None` site for the Result hazard), and the
  whole-file `no_write_direct` cost is stated rather than hidden. It matches the
  nine peers exactly. **A second edit to that key would be the duplicate-remedy
  hazard, not diligence.**
- **LEG 3 WAS EXECUTED BY THE MONITOR LANE, NOT BY US — DO NOT DUPLICATE IT.**
  `livespec-driver-codex` commit `52ee48d` on worktree/branch
  `reland-shell-quality-gate-consumer-test` restores the test byte-identical
  (sha256 `0952b672643c137c288053f5bbb2d94e555d1a80cb12b24174502a61cf432bc8`,
  confirmed against `7382f1f`) and carries real `TDD-Suite-Green-*` trailers, so
  its hooks ran and the full suite passed. It is authored by a DIFFERENT Claude
  session. At 10:29Z it was still unpushed with no PR. **It is that session's
  branch; the standing rule against touching another session's worktrees applies.
  Re-measure it before acting, and coordinate rather than seize.**
- The ritual question that leg raised, resolved from installed code so nobody
  re-derives it: a test-only re-land does NOT need a Red. `_red_green_replay_modes.py`
  carries a SUITE-GREEN leg admitting "a passing test-only cleanup" by running the
  FULL suite, exit 0 only. And `commit_pairs_source_and_test` is ONE-DIRECTIONAL —
  it requires tests when SOURCE changes, so a test-only commit passes it trivially.
- **PR 1249 — this handoff's own PR — was stuck in the documented STALE-CHECK
  TRAP and this supervisor cleared it.** It sat OPEN with auto-merge armed, 65
  checks, ZERO pending, failing only `check-fleet-conformance` and `ci-green` —
  both pure freeze artifacts. With nothing pending, CI would never re-run and
  auto-merge would never fire, exactly as git-jsonl PR 540 sat until rebased. The
  remedy is a REBASE onto post-1248 master, which is a real base change rather
  than a forbidden unchanged rerun. Any other PR parked during the freeze is
  likely in the same trap — check `pending == 0` before assuming it will land.
- **The provenance block's pinned `generator_ref` is GONE — detected now, not
  hard-coded.** It HALTed this cold open, would have HALTed the next one, and the
  ref churned a THIRD time mid-session (`0.27.1` → `0.27.6` → `0.29.0`, ten
  minutes apart) with the digest identical at every step. The digest is still the
  only identity and still HALTs on mismatch, verified with negative controls. See
  the Generator provenance section; do not re-pin it.
- Re-measured 10:24Z: `42t4az.1` CLOSED, `.2` backlog, `.3` open P1, `.4` open
  P2, closeout `qgw7gb` pending-approval, epic `42t4az` backlog. Rollouts —
  `bd-ib-35qhta` active with run `01KZ6125R9X62VMGXBNYSXGYNV` genuinely RUNNING
  (confirmed via safe `fabro ps`, and the worker is attached to it),
  `livespec-runtime-ohlb4f` active with NO live run (its run
  `01KZ5W1JTRDHQNN50GNG31M4QB` reads succeeded — the stale claim is REAL, not
  dispatch latency), `livespec-akg7k5` and `overseer-cdhdlv` pending-approval.
- **Do NOT release `ohlb4f`'s stale claim to `ready` yet.** Releasing it while
  the runtime route is undecided makes it eligible for another session's
  `next`-ranked autonomous pickup, straight back into the same deadlock. That is
  the identical dispatch-interlock reasoning this thread ratified for the P0.
- Three Fabro runs are live host-wide and one is ours, so a second tenant
  dispatch stays off the table until `bd-ib-35qhta` clears.

### THE ONE THING THAT MATTERED FIRST, NOW DISCHARGED: the repo was MERGE-FROZEN, by my artifact

`livespec-dev-tooling` is merge-frozen at `a4a6646`. Nothing merges — not
`42t4az.3`, not `42t4az.4`, not the closeout, not this handoff's own PR, not any
other lane.

Cause, and it is this thread's own: the driver-codex rollout (`bedeju`) landed
`tests/test_shell_quality_gate.py` consuming
`livespec_dev_tooling/checks/shell_quality.py::main` WITHOUT the
`cross_repo_public_api` + `supervisor_entry_files` declarations its nine peers
carry. Fleet row `cross-repo-public-api-declared` therefore fails for member
`livespec-dev-tooling`, and because that row evaluates the SELF member at
`canonical_ref` (master, always), pure-trees PR 1248 — which carries the
declaration — cannot clear itself. Verified red: run `30895922985` on `456a793`.
The required ordering was declaration-before-consumer.

Agreed route (a-NARROW), maintainer-routed through the monitor:

1. A normal worktree PR in `livespec-driver-codex` reverting ONLY
   `tests/test_shell_quality_gate.py` — NOT all of `7382f1f7`, because a full
   revert would un-migrate recipes and could turn driver-codex red. driver-codex
   master is green, so no server-side trick is needed. **I released this leg to
   the monitor at 10:12Z** rather than hold a fleet freeze against my own
   wind-down; assume it is done or in flight, and RE-MEASURE.
2. pure-trees merges PR 1248 once the row clears.
3. **RE-LAND THE CONSUMER TEST, WITH ITS DECLARATIONS. THIS LEG IS OURS AND IS
   THE FIRST PRIORITY OF THE NEXT SESSION.** Add `cross_repo_public_api` and
   `supervisor_entry_files` declarations alongside the test, matching the nine
   peers, so declaration lands before or with the consumer.
4. Their `rjyc` P0 — make the row evaluate self from the tree under test — is the
   durable fix. Do NOT rush it as the unblock.

Route (b), an administrative merge, is FORBIDDEN by `.ai/ci-gate-discipline.md`.

### Where the epic actually stands

Measured 2026-08-04T10:05Z. Re-measure before acting.

- **P0 `livespec-dev-tooling-42t4az.1`: CLOSED.** The missing-shellcheck
  `TypeError` is fixed and VERIFIED on master with live controls — corpus 32
  files so the path is reachable, a real shellcheck run returns `Success` so the
  probe discriminates, and the absent-binary probe now returns a typed
  `ShellCheckUnavailable` naming the tool, version `0.11.0`, and a remedy. The
  check is NOT skipped or weakened: its test asserts `rc == 1`.
- **`livespec-dev-tooling-jtrjzk`: CLOSED.**
- **v1.18.7 IS the corrected release**, confirmed by strict commit containment
  (not changelog text): tag `41420425` contains both `25735f0` (the P0) and
  `808802220ed4` (PR 1232), with a reversed-ancestry control proving the test
  discriminates. `.mise.toml` at the tag pins `shellcheck = "0.11.0"`.
- **Rollouts: 4 of 8 CLOSED** — `livespec-driver-claude-gtqrzu`,
  `livespec-driver-codex-bedeju`, `bd-gj-uworva`,
  `livespec-console-beads-fabro-6yii4r`.
- **`bd-ib-35qhta` (beads-fabro): ACTIVE**, run `01KZ6125R9X62VMGXBNYSXGYNV`
  was running at 10:05Z. Its admission followed my `bd-ib-xhcqbc` metadata
  repair.
- **`livespec-runtime-ohlb4f`: ACTIVE with a STALE CLAIM** — see below.
- **`livespec-akg7k5` and `overseer-cdhdlv`: pending-approval.** NOTE:
  `approve:<id>` REFUSES on these ("requires an effective-manual
  pending-approval item") because they are `admission:auto` — their
  pending-approval is transient and the DISPATCHER admits them. Do not waste a
  call on approve; drive `impl:` directly.
- Epic children: `.2` backlog (retire the legacy 65-target mirror, ONLY once
  every pinned consumer reads `check-targets.txt` at the version it pins);
  `.3` open P1 and `.4` open P2, both filed by me from verified root causes;
  closeout `qgw7gb` pending-approval; epic `42t4az` still backlog.

### Runtime is stuck in a genuine deadlock — and I made it worse, then reverted

`livespec-runtime-ohlb4f` reads `active`/`fabro` with NO live run. That is a
STALE CLAIM: release it by hand before any second drive. ACTIVE is never
evidence of a run.

The two PRs are individually unmergeable:

- **PR 466** (release-generated pin, App-authored, workflows-granted) carries
  `.mise.toml`, the `ci.yml` matrix job, the aggregate entry and the recipe —
  but fails `check-shell-quality` because recipes are not migrated yet.
- **PR 467** (factory) migrates recipes AND bumps the pin AND wires locally, but
  the FACTORY DISPATCH CREDENTIAL DELIBERATELY LACKS THE WORKFLOWS GRANT (a
  documented boundary, same as `7caozh`), so it cannot add the `ci.yml` job.

**MY ERROR, CORRECTED — READ THIS BEFORE RETRYING.** I reconciled PR 467 to
migration-only (commit `63076b6`, removing the `check-targets.txt` entry, the
`.github/scripts/check.sh` aggregate entry, and the justfile recipe), reasoning
from git-jsonl where that scope worked. It made things WORSE: 1 failure became
2 (`check-aggregate-completeness` and `check-canonical-recipe-fidelity`). The
structural difference I had missed is that **git-jsonl's migration PR 541 did
NOT bump the pin, while runtime's PR 467 DOES** — so on PR 467
`check-shell-quality` is already canonical, and the aggregate MUST list it. I
reverted at `7dfb0d4` and the branch is back to the factory's own output with
its single original failure. Do not repeat that removal.

The real deadlock: PR 467 cannot be green while it carries the pin without the
`ci.yml` job, and PR 466 cannot be green until recipes are migrated. Plausible
routes, none yet chosen: strip the PIN (not the wiring) from 467 so it is truly
migration-only like git-jsonl's 541; or have the workflows-granted App carry
everything in one PR. **THE DURABLE INVARIANT, which any route must respect:
the aggregate slug and its CI matrix job MUST land in the same commit.**

### The proven rollout sequence, and the step everyone forgets

Worked twice, driver-claude and git-jsonl: migration PR merges FIRST, then the
pin PR is **REBASED onto the migrated master**. That rebase is REQUIRED, not
cosmetic — without it the pin PR sits on STALE pre-migration check results with
ZERO pending, so CI never re-runs and auto-merge never fires. git-jsonl's PR 540
sat exactly like that until I rebased it; it then went green and merged.

### Two source defects I filed, both with verified root causes

- **`42t4az.3` (P1)** — the fanout ships the ShellCheck pin to console-class
  consumers WITHOUT the `check-shell-quality` wiring. Root cause: a SILENT SKIP
  GATED ON A SENTINEL in `.github/actions/bump-pin-rewrite/action.yml`, which
  bails out with only a `::notice::` when the consumer justfile lacks the literal
  `check-aggregate-completeness`. Correlation across seven repos was EXACT:
  console `sentinel=0` and it alone merged its pin ungated; the other six carry
  4–5. CONFIRMED STILL LIVE at 09:20Z: console's repo was repaired by hand, but
  its sentinel is still 0, so console will silently skip EVERY future canonical
  check slug. Adding the sentinel to console as a one-off is NOT the remedy —
  the projection must declare and test which consumer classes it owns.
- **`42t4az.4` (P2)** — `livespec_dev_tooling/worktree_pack/worktree.just` is
  shipped by this repo, lands in consumers as `dev-tooling/worktree.just`, and is
  GITIGNORED, so it exists in every working copy and no CI checkout. The released
  checker reports 6 findings on it locally and none in CI on the same commit.
  Control: the identical local invocation against `livespec-dev-tooling` itself
  reports 0, matching its green CI, because it has no installed fragment.

### Hazards this session actually hit — do not re-learn these

- **`bd update --set-metadata k=v` stores the value as a STRING**, silently
  turning a list into JSON text. The success tick does NOT mean the shape is
  right — check the TYPE. Recover with `bd update --metadata @file.json`.
- **`reject:<id>` alone is not a valid action.** It is `reject:<id>:rework` or
  `:regroom`, and it only operates from `acceptance` state, not
  `pending-approval`. `:regroom` performs a `git revert` of the merge SHA — never
  use it where a revert is forbidden.
- **gh REST `core` and GraphQL are separate budgets.** I exhausted REST (0/5000)
  with `gh run view --log-failed` and `gh run list` while GraphQL still had 4815.
  Prefer `git ls-remote` (no budget at all), then GraphQL `gh pr view/list
  --json`, and reserve REST for job logs. `fabro ps` costs no GitHub budget.
- **A zero-run reading right after a dispatch is LATENCY, not a phantom.** Wait
  before concluding; I nearly misjudged `ohlb4f` that way.
- **zsh does not word-split unquoted `$var`.** A file list passed that way became
  one pathspec and made a diff test vacuously empty — the positive control is the
  only reason it was caught.

### Repo/worktree hygiene

Primary was clean at measurement: equal to `origin/master`, only the user's
untracked `install-livespec-pr-bot.png` (sha256
`a3e2d35997c60459df71fd16d608c71560eeea16d0aee11422db7eecba204fe5`), preserved
byte-for-byte. I restored a stray `uv.lock` version bump that was a local `uv`
artifact, not an intended change.

Worktrees I own and did NOT clean, because their work is unfinished:

- `~/.worktrees/livespec-runtime/ohlb4f-reconcile` on branch
  `feat/livespec-runtime-ohlb4f` — the runtime factory branch, now reverted to
  the factory baseline at `7dfb0d4`. Remove it once runtime's route is decided.
- `~/.worktrees/livespec-dev-tooling/wrapup-fleet-shell-quality-enforcement-supervisor`
  — this handoff's own wrap-up worktree, if its PR has not merged under the
  freeze.

All this thread's earlier dev-tooling worktrees were cleaned. Preserve unrelated
worktrees belonging to other sessions.

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

- **Steering lands MID-TURN with a plain `Enter`.** There is no Tab-queue and no
  turn-boundary starvation, so an instruction no longer sits unread until the
  worker finishes. The Codex-era failure mode where text waited in a
  "Queued follow-up inputs" block — which drove stale state into `handoff.md`
  through PR 1236 — cannot happen the same way. **Verify consumption anyway.**
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
