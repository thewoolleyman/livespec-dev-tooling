# Supervisor Handoff - pure-trees-role-key-scope

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
status, next action, or date-gated behavior. Live state lives in the ledger, in
`plan/pure-trees-role-key-scope/handoff.md`, and in the supervisor marker.

| Binding | Expression | Resolved value |
|---|---|---|
| `repo_primary` | concrete | `/data/projects/livespec-dev-tooling` |
| `thread_dir` | concrete | `/data/projects/livespec-dev-tooling/plan/pure-trees-role-key-scope/` |
| `topic` | concrete | `pure-trees-role-key-scope` |
| `worker_session` | concrete | `pure-trees-role-key-scope` |
| `supervisor_session` | concrete | `pure-trees-role-key-scope-supervisor` |
| `WORKER_TARGET` | concrete | `'=pure-trees-role-key-scope:'` |
| `SUPERVISOR_TARGET` | concrete | `'=pure-trees-role-key-scope-supervisor:'` |
| `runtime_dir` | `<repo_primary>/tmp/overseer/<topic>/` | `/data/projects/livespec-dev-tooling/tmp/overseer/pure-trees-role-key-scope/` |
| `supervisor_marker` | `<runtime_dir>/.supervisor-state` | `/data/projects/livespec-dev-tooling/tmp/overseer/pure-trees-role-key-scope/.supervisor-state` |
| `wait_channel` | `<runtime_dir>/worker-status.log` | `/data/projects/livespec-dev-tooling/tmp/overseer/pure-trees-role-key-scope/worker-status.log` |
| `ledger_anchor` | concrete | `livespec-dev-tooling-8zv3` |

Complete placeholder declaration for the two-layer charter:

- Concretely bound generation placeholders: `<repo-primary>` and
  `<absolute-target-repo>` are `/data/projects/livespec-dev-tooling`;
  `<topic>` is `pure-trees-role-key-scope`; `<worker-session>` is
  `pure-trees-role-key-scope`; `<supervisor-session>` is
  `pure-trees-role-key-scope-supervisor`; and `<ledger-anchor>` is
  `livespec-dev-tooling-8zv3`.
- Composed bindings, resolved transitively to the fixed values in the table:
  `<runtime-dir>`, `runtime_dir`, `supervisor_marker`, and `wait_channel`.
- Runtime slots deliberately left unsubstituted: `<condition-command>`,
  `<short-slug>`, and `<branch>`.
- Illustrative placeholders occur only in prose or the obligation-schema YAML
  in the shared layer, never as unresolved generation-time values in fenced
  shell commands.

## Generator provenance

The digest is the generator identity. Plugin name, cache ref, and version are
human-readable companions; they do not replace the digest. This charter was
emitted from the installed Claude Code plugin root actually read by the
generator:

```sh
generator_plugin='livespec-overseer'
generator_prose_md5='eaebe06065b3efa0053d6ea5932d52c0'
cache_root="$HOME/.claude/plugins/cache/$generator_plugin/$generator_plugin"
if [ ! -d "$cache_root" ]; then
  printf '%s\n' "UNVERIFIED: no plugin cache at $cache_root, so this is not a host that generates charters and provenance cannot be checked here. Recorded generator: $generator_prose_md5"
else
  # The ref is DETECTED, never pinned. Any installed ref whose prose digests to
  # the recorded value proves this charter's generator is still installed; which
  # directory holds it is not the identity and must not be able to fail the check.
  match=''
  for candidate in "$cache_root"/*/prose/supervise-plan.md; do
    [ -f "$candidate" ] || continue
    installed=$(md5sum "$candidate")
    digest_rc=$?
    [ "$digest_rc" -eq 0 ] \
      || { echo "HALT: cannot digest an installed generator prose at $candidate"; echo "REMEDY: fix read access before trusting anything this charter says about its own currency"; exit 1; }
    installed_md5=${installed%% *}
    if [ "$installed_md5" = "$generator_prose_md5" ]; then match="$candidate"; break; fi
  done
  if [ -z "$match" ]; then
    echo "HALT: no installed ref under $cache_root carries generator prose digesting to $generator_prose_md5, so the generator that emitted this charter is GONE"
    echo "REMEDY: regenerate this charter with supervise-plan, or re-stamp generator_prose_md5 deliberately after reading what changed between the two"
    exit 1
  fi
  printf '%s\n' "PASS: charter provenance matches an installed generator ($generator_prose_md5) at $match"
fi
```

A missing cache root means provenance is UNVERIFIED on a non-generating host
and execution may continue. A cache root that holds NO ref digesting to the
recorded value means the generator was replaced, and that is the HALT.

⛔ **THE REF USED TO BE PINNED HERE, AND THE PIN WAS THE DEFECT.** Adopted from
the `fleet-shell-quality-enforcement` supervisor's verified fix (`96227b5`),
which measured its own pinned ref churning `0.27.1` → `0.27.6` → `0.29.0` in
**ten minutes** while `prose/supervise-plan.md` digested identically at every
step. **The pin failed on the calendar and never on the artifact.** A charter
whose whole purpose is to be readable cold cannot carry a check that HALTs
because a cache directory was garbage-collected.

Measured on this host at 11:50Z: **42 installed refs carry the prose and 31 of
them digest identically** — up from 26 of 37 four hours earlier, five new refs
in one morning, every one byte-identical. The pinned ref survived only by luck.

✅ **The digest is not a constant, which is the positive control the claim above
needs.** Eleven of those refs carry three DIFFERENT digests:
`2283862cf32b60b2e82c02164c9b3b83` (nine refs, `0.12.2`–`0.13.3`),
`30b59fcf0ea5f3cf78402129826b1ffa` (`0.14.0`), and
`9ca18d56772dcf8fcdc2cf78ed8108a8` (`0.15.0`). The identity therefore
DISCRIMINATES — it moved three times when the prose actually changed, and has
held across every ref since. A digest that could only ever report one value
would be the same defect as a check that cannot fail.

⚠️ **DO NOT RE-STAMP THE COUNTS ABOVE AS THEY DRIFT.** They were `26 of 37` at
07:20Z and `31 of 42` at 11:50Z on the same host, same morning. **The counts are
evidence for a claim, not state to maintain** — the durable facts are the RATIO
(one digest across the overwhelming majority) and the DISCRIMINATION (three
other digests exist). A successor who "corrects" these numbers every session has
turned a recorded measurement into a chore, which is how this charter grew a
pinned ref in the first place.

📜 **THE ORIGINAL DEFECT, kept because the reasoning still teaches.** This block
once pinned `generator_ref='070ec63059c0'`, then was re-pointed to
`2a97b88744bd` while the emitting session had actually read `070ec63059c0` — and
the prose was edited to assert it had read `2a97b88744bd`, which was false. See
Corrections C1. **Detecting the ref dissolves that whole class**: there is no
longer a companion field that can disagree with reality, be re-stamped to agree
with itself, or evict out from under a cold reader.

## Live restart state — 2026-08-04T12:45Z

**This section is the authoritative handoff. Re-measure everything below before
acting on it; timestamps and CI states are evidence, not permission to assume
they are still true.** The ledger is authoritative over this file.

### ✅ THE THREAD'S CORE DELIVERABLE IS DONE AND MERGED

`8zv3.1`, `8zv3.2`, `8zv3.3` are all **CLOSED**. The decoupling shipped as
`46c5dab` (PR #1248) and is on master. **Do not re-open, re-derive, or re-litigate
it.** The mandatory positive control was discharged in both directions on one
stated basis (shipped semantics, `_`-file skip RETAINED): it CONVICTS on
`livespec-runtime` `@9b4c518` — exit 1, 26 of universe 31 scanned, **11
offenders**, up from exit 0 / ZERO files — and still PASSES on
`livespec-dev-tooling` (exit 0, 93 of universe 177 scanned, up from 0).

⚠️ **Verify the check by AST, never by grep.** The shipped module has **ZERO**
code references to `pure_trees`; a raw grep reports **8**, all prose in
docstrings explaining the history. A grep here says the decoupling failed.

### ▶️ WHAT IS ACTUALLY OPEN, in priority order

1. **`livespec-dev-tooling-niyl` — P0, and it blocks the whole fan-out.**
   `docker/fabro-sandbox/base/Dockerfile:69` pins `gh=2.96.0`, which upstream
   dropped, so `fabro-sandbox-image.yml` fails. That workflow is the **only**
   producer of the `python-v<X.Y.Z>` tags and triggers on `release`; its run for
   tag **v1.18.8 FAILED** (`30900774835`). **`python-v1.18.8` was never
   published**, so every consumer bumping to it dies at `Docker pull failed` —
   measured on `livespec-orchestrator-beads-fabro` PR #1291, **39 of 41 checks**,
   identical on two unrelated jobs, zero check output in either.
   Fix needs `Dockerfile:69` **and** `checks/fabro_image_pin_lockstep.py:86`
   (`_SUPPORTED_GH_VERSION`), the latter product `.py` needing its own Red-Green
   pair. **Not started. Not claimed by any lane. Raise it with the maintainer
   before taking it — it is infra, outside this thread's charter.**
2. **`livespec-dev-tooling-rjyc` — P0**, the durable fix for the merge deadlock.
   The row evaluates the repo under test from its REMOTE default branch, so a PR
   can never clear it. Reviewed and de-risked: the objection ("a PR asserts its
   own conformance") does NOT bite, because the verdict is a JOIN — consumption
   EDGES come from SIBLING trees and are unfakeable; only the declaration and own
   sources come from self. ⛔ **GUARDRAIL, not optional: ONLY the self member may
   read locally.** Blast radius is one call site
   (`_rows_public_api_conformance.py:133`). **Land it deliberately; it was
   explicitly NOT rushed in as the unblock.**
3. **`8zv3.5` — P1, still gates `8zv3.4`.** The `_`-prefixed FILE skip is worth
   **286 of 446** fleet offenders (64%). Budget and blast radius move ~2.8x on
   this one decision. Nothing has been decided.
4. **`8zv3.4` — P1, blocked by both `8zv3.5` and `niyl`.** ⚠️ **Any per-repo
   offender count taken against v1.18.8 right now is measuring NOTHING** — the
   checks never execute, they fail at image pull.
5. `livespec-dev-tooling-tkzf` (P2) — `check-fleet-conformance-admin` runs in
   PRE-COMMIT, so an external adopter repo's state can block every commit here.
   It fired for ~40 min and cleared itself with no action.
6. `livespec-dev-tooling-9s2j` (P2) — the row reports NOTHING when a consumed
   function is DELETED; the edge vanishes rather than convicting. Orthogonal to
   `rjyc`; do not fold them together.

### 🔄 IN FLIGHT AT RESTART — worker session, verify first

The worker holds worktree `~/.worktrees/livespec-dev-tooling/docs-unshadow-stale-gate-prose`
with **two commits complete and clean but UNPUBLISHED** at 12:45Z: `6f89f84`
(corrects the now-false `public_api_result_typed` docstring claiming the check
still runs behind the `pure_trees` gate) and `80a20e8` (a
`SPECIFICATION/proposed_changes/` entry for the `contracts.md` drift at lines
227 and 354, whose "four such entries" is now **three**, measured). It was told
to rebase onto `8f14af3`, push, PR, merge, and clean up. **Re-measure whether
that landed; do not assume either way.**

### 🤝 CROSS-LANE — fully discharged, do not re-open

The repo was merge-frozen this morning. `livespec-driver-codex` `7382f1f7`
landed a consumer of `shell_quality.py::main` 24 minutes after this repo's last
green run, without the `cross_repo_public_api` / `supervisor_entry_files`
declarations its nine peers carry. Resolved through the ratified
`livespec/.ai/ci-gate-discipline.md` path — **"NEVER add escape gates; revert
and re-land"** — as driver-codex #390 (narrow revert, one file) → dev-tooling
#1248 (declarations) → driver-codex #392 (re-land byte-identical, blob
`391c822e`) → `livespec-driver-codex-4uc` closed. **No gate weakened, none
bypassed.** The `fleet-shell-quality-enforcement` monitor owns that lane and
executed its legs; it has withdrawn its "latent ROP debt fleet-wide" hypothesis
after verifying the Docker-pull refutation end-to-end.

⛔ **An administrative merge is FORBIDDEN by that doctrine.** A prior supervisor
offered it to the maintainer as one of three routes without having found the
file — it lives in `livespec`, not here. Do not re-offer it.

### 📜 WHAT THIS THREAD KEEPS RE-LEARNING, in one place

Every defect this session found — and every one it committed — was the same
shape: **a measurement reported over the wrong population, or a check that
verifies something other than what it governs.** Seven consumers from a grep vs
five from an AST. Twenty `resolve_check_universe()` callers vs nineteen. Four
plugin refs from a sample vs 31 of 42 from a census. A demonstration repo chosen
without checking which BASIS its offender count was on. A severity rated by one
repo's merge gate for a fleet-wide artifact producer. A red check read as a
finding when it was a failed image pull.

**Corollaries that earned their place:** exit status is not evidence — and
neither is a FAILURE status, until you have read why. An empty result is not a
finding until the query is proven able to produce a positive. A right conclusion
does not launder a wrong premise.

## Thread-specific Valves

- **The `_`-prefixed FILE skip must not ride along inside the decoupling.**
  `livespec-dev-tooling-8zv3.5` owns that decision and BLOCKS the fleet fan-out
  `8zv3.4`. `8zv3.3` proceeds under the **stated assumption that the skip is
  retained**. If the worker's diff touches the `_`-file skip, stop it: that is a
  separate, independently-argued change worth 286 of 446 fleet offenders.
- **Say which basis you mean, every time.** Every per-repo number in this thread
  has TWO bases — shipped semantics (with the `_`-file skip) and the epic's
  measurement basis (without it). `livespec-dev-tooling` is **0** on one and
  **1** on the other. `8o8e.17` exists because a part and a total from different
  bases were added.
- **Do not "helpfully" add a replacement role gate.** A new declared key to
  express the zero-first-party-Python exemption reintroduces the exact hazard
  this epic closes: a declaration whose emptiness means "skip me", indistinguishable
  from "genuinely no code". `resolve_check_universe()` already fails closed.
- **The decoupling is FIDELITY, not softening**, and it is the one shape that
  must be argued explicitly before it lands. It makes the check strictly
  stricter — four structurally-unconvictable repos become scanned — so it does
  not hit the shared layer's "never remove, weaken or skip a check" boundary.
  Requiring that argument on the record is what keeps that boundary meaningful.
- **This thread does NOT drive `livespec-mutreal.1` or `bd-ib-6qb2mc`.** Those
  remain valid for `check_mutation` and `pbt_coverage_pure_modules`, which
  genuinely need a pure-layer carve. Do not re-prioritise either on this
  thread's account; that manufactures urgency from a coupling about to be
  deleted.
- **`livespec-dev-tooling` runs this check on ITSELF** (`justfile:206`, `:730`).
  Arming it while the repo is dirty turns its own `just check` red and
  `lefthook` then blocks the very commit that fixes it. Measured 2026-08-04:
  the trap does not fire under shipped semantics — but re-measure before
  relying on that, because it is conditional on the bullet above.
- **Runner minutes are a first-class constraint.** The parent epic `8o8e` is ON
  HOLD for token and runner-minute cost. `check-fleet-conformance` fails
  intermittently on HTTP 403 from the GitHub App installation's hourly pool.
  Never re-run a 403 while another fleet-conformance job is in flight — it
  cannot succeed and only adds a competitor.
- **Two repos cannot accept PRs today**: `livespec` (`check-doctor-static`,
  `8o8e.26`) and `livespec-orchestrator-beads-fabro` (`check-shell-quality`,
  the `fleet-shell-quality-enforcement` peer lane). Verify landability per repo
  before spending runner minutes on the `8zv3.4` fan-out.
- **The plan thread is knowingly stale on one point and the ledger says so.**
  `handoff.md` still frames the scope-mismatch premise as *"INFERRED — attack
  this first"*. The ledger records it as CONFIRMED from ratified text
  (`livespec` `SPECIFICATION/non-functional-requirements.md:114`). A discharged
  "attack this first" reads exactly like a live one; fold the correction into
  the next edit of that file rather than re-investigating it.
- **`plan/rop-railway-enforcement` is ON HOLD and `8zv3` BLOCKS `8o8e`.** Do not
  resume the ROP track from this thread. The peer lane
  `plan/fleet-shell-quality-enforcement` owns the shell-quality freeze; stand
  down on that action only, never on this thread.

## HALT-first preconditions

Verify the exact worker session `pure-trees-role-key-scope`, exact supervisor
session `pure-trees-role-key-scope-supervisor`, and exact target repository
`/data/projects/livespec-dev-tooling` before doing anything else. Stop on the
first failure, report the exact expected name, and act on the literal labelled
`REMEDY:`. The process-tree checks pass only when a live `claude` or `codex`
driver appears; a session NAME proves nothing.

1. Supervised session exists:

```bash
WORKER_TARGET='=pure-trees-role-key-scope:'
tmux has-session -t "$WORKER_TARGET" \
  || { echo "HALT: expected worker session 'pure-trees-role-key-scope'"; echo "REMEDY: ask the maintainer whether to start that worker session"; exit 1; }
```

2. The supervised session is a live agent session:

```bash
WORKER_TARGET='=pure-trees-role-key-scope:'
pane_pid=$(tmux display-message -p -t "$WORKER_TARGET" '#{pane_pid}')
[ -n "$pane_pid" ] \
  || { echo "HALT: empty pane_pid for 'pure-trees-role-key-scope'"; echo "REMEDY: re-check the exact worker target and stop if it still resolves empty"; exit 1; }
ps -o pid=,comm=,args= --ppid "$pane_pid" --pid "$pane_pid" -H
# PASS only if a live `claude` or `codex` process appears in that tree.
# A lone shell (zsh/bash) with no agent child is a HALT.
# REMEDY: if no live agent appears, ask the maintainer whether to restart the worker.
```

3. The supervisor session exists, is distinct, and is a live agent session:

```bash
WORKER_TARGET='=pure-trees-role-key-scope:'
SUPERVISOR_TARGET='=pure-trees-role-key-scope-supervisor:'
tmux has-session -t "$SUPERVISOR_TARGET" \
  || { echo "HALT: expected supervisor session 'pure-trees-role-key-scope-supervisor'"; echo "REMEDY: switch to the correct supervisor session or ask the maintainer to bootstrap it"; exit 1; }
pane_pid=$(tmux display-message -p -t "$WORKER_TARGET" '#{pane_pid}')
supervisor_pane_pid=$(tmux display-message -p -t "$SUPERVISOR_TARGET" '#{pane_pid}')
[ -n "$supervisor_pane_pid" ] \
  || { echo "HALT: empty pane_pid for 'pure-trees-role-key-scope-supervisor'"; echo "REMEDY: re-check the exact supervisor target and stop if it still resolves empty"; exit 1; }
[ "$supervisor_pane_pid" != "$pane_pid" ] \
  || { echo "HALT: supervisor and worker resolve to the SAME pane"; echo "REMEDY: re-check both exact targets — a prefix match puts both names on one pane, and the worker's agent then reads as the supervisor's"; exit 1; }
ps -o pid=,comm=,args= --ppid "$supervisor_pane_pid" --pid "$supervisor_pane_pid" -H
# PASS only if a live `claude` or `codex` process appears in that tree.
# A lone shell (zsh/bash) with no agent child is a HALT.
# REMEDY: if no live agent appears, ask the maintainer to start the agent in that session.
```

⚠️ **On this host both panes' agents were launched under DIFFERENT `-n` labels
than their tmux session names** (`rop-railway-enforcement` /
`rop-railway-enforcement-supervisor`, from the thread this topic was split out
of). That is not a failure: the check proves a LIVE agent in the resolved pane,
and a launch-time label is as weak an identity as a session name. Do not
"correct" the label and do not treat the mismatch as a HALT.

4. The plan thread exists inside the target repository:

```bash
test -d "/data/projects/livespec-dev-tooling/plan/pure-trees-role-key-scope" \
  || { echo "HALT: missing plan thread /data/projects/livespec-dev-tooling/plan/pure-trees-role-key-scope"; echo "REMEDY: create or choose the correct plan topic before supervising"; exit 1; }
```

5. The worker pane cwd resolves inside the target repository:

```bash
WORKER_TARGET='=pure-trees-role-key-scope:'
pane_cwd=$(tmux display-message -p -t "$WORKER_TARGET" '#{pane_current_path}')
[ -n "$pane_cwd" ] \
  || { echo "HALT: empty pane_current_path for 'pure-trees-role-key-scope'"; echo "REMEDY: re-check the exact worker target and stop if it still resolves empty"; exit 1; }
case "$(readlink -f -- "$pane_cwd")" in
  /data/projects/livespec-dev-tooling|/data/projects/livespec-dev-tooling/*) echo "PASS: $pane_cwd" ;;
  *) echo "HALT: pane cwd $pane_cwd is outside the target repo"; echo "REMEDY: move the worker into the target repo or start the correct worker session"; exit 1 ;;
esac
```

## How to inspect and drive

The shared protocol owns the role-level rules. These commands substitute this
thread's ledger and tmux bindings so they run as written.

```sh
ledger_anchor='livespec-dev-tooling-8zv3'
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
# EXIT STATUS IS NOT EVIDENCE. A tool that exits 0 while printing nothing would
# let the MEASURED_AT stamp below certify a re-measurement that never happened.
[ -n "$ledger_json" ] \
  || { echo "HALT: ledger re-measure for '$ledger_anchor' exited 0 but returned NOTHING"; echo "REMEDY: do not record this as a measurement — an empty success is not a reading; confirm the anchor exists and that the ledger tool is actually reporting"; exit 1; }
printf '%s\n' "$ledger_json"
date -u '+MEASURED_AT: %Y-%m-%dT%H:%M:%SZ'
```

The five children hang off that anchor as `livespec-dev-tooling-8zv3.1`
through `8zv3.5`. Re-measure the child too before quoting its state; the epic's
own notes say **do not close any child on the supervisor's analysis alone.**

```sh
WORKER_TARGET='=pure-trees-role-key-scope:'
pane_pid=$(tmux display-message -p -t "$WORKER_TARGET" '#{pane_pid}')
tmux_rc=$?
[ "$tmux_rc" -eq 0 ] \
  || { echo "HALT: tmux pane lookup failed for 'pure-trees-role-key-scope'"; echo "REMEDY: re-check the exact target before filtering its output"; exit 1; }
printf '%s\n' "$pane_pid" | head -1
```

The thread's own positive control, which is not optional: after the decoupling
lands, show `public_api_result_typed` **CONVICTING** on a repo where it
previously scanned zero files, with the scanned-file count, and show that it
still passes on a clean tree. **Exit status 0 is not evidence** — that is the
parent epic's founding lesson and this thread inherits it.

## Corrections

Thread-specific corrections belong here. Regeneration MUST preserve this
section byte-for-byte, from the heading through the end of the section,
including spelling, punctuation, code formatting, blank lines, and ordering.

**C1 — 2026-08-04. The generating supervisor shipped a provenance stamp whose
`generator_ref` is not the root it read, and it very nearly shipped the
supporting prose as a false first-person claim.** The emitting Claude Code
session resolved its skill base directory to `070ec63059c0` (`0.25.0`) and read
`prose/supervise-plan.md` from there. The committed stamp records
`2a97b88744bd` (`0.27.0`). The accompanying paragraph asserted that *"the
session that emitted this stamp read `2a97b88744bd`"* — a first-person claim
about this session's own behavior that was simply not true, sitting inside the
one section whose entire purpose is to record honestly which generator produced
the charter. It was rewritten to state the discrepancy instead of asserting the
convenient version.

The stamp still VERIFIES: both roots hold byte-identical prose, the digest is
the contract's stated identity, and the ref and version are explicitly
"human-readable companions." So this is a companion that is imprecise, not a
check that can no longer fail — the negative control was run at generation time
and a wrong digest does HALT. **But the failure mode being logged is not the
imprecision. It is that a provenance record can be adjusted to agree with
itself, and the adjustment reads exactly like the truth.** That is the same
shape as this thread's founding defect — a check reporting on files it never
inspected, and a grep reported as an AST count.

Supporting numbers in that paragraph were also wrong and were re-measured
rather than trusted: it claimed FOUR installed refs digest identically; the
measured figure is **26 of 37**, spanning 23 plugin versions. The corrected
text also adds the positive control the original lacked — three OTHER digests
exist across `0.12.2`–`0.15.0`, so the identity demonstrably discriminates.

**Standing instruction for this thread's supervisor: never let a record of your
own behavior be edited into agreement with the artifact it describes.** Correct
the record, or correct the artifact, and say which one you did.

**C2 — 2026-08-04. The supervisor was wrong five times in one session, and the
worker or a peer lane caught every one. That ratio is the finding.**

1. **Nineteen, not twenty.** Carried a filed `resolve_check_universe()` caller
   count forward without re-deriving it. The worker measured 19. Re-ran it: 19.
2. **`livespec-driver-codex` was an invalid positive control.** Named it as a
   demonstration repo off its ledger-recorded 1 offender WITHOUT CHECKING WHICH
   BASIS that 1 was on. On the retained-skip basis it convicts **zero** — a
   control that cannot succeed, offered while enforcing the very two-bases valve
   that exists to prevent it.
3. **Accused the worker of a sample-as-census error and was itself measuring the
   wrong population.** Tested "all 9 siblings carry both keys" against all 58
   entry-point-shaped check modules instead of the 9 that are actually consumed
   cross-repo, where the pairing is exceptionless. Nearly reversed a correct
   ruling.
4. **Rated `niyl` P2 on a repo-local blast radius.** Justified it as "does not
   gate `ci-green`" — true for this repo's merge, and the wrong question for an
   artifact producer the whole fleet pulls. It is the v1.18.8 fan-out blocker.
   Re-prioritised P0.
5. **Offered the maintainer an administrative merge** as one of three legitimate
   routes, when `livespec/.ai/ci-gate-discipline.md` had already forbidden it.

⛔ **AND THREE PROCESS FAILURES WORTH MORE THAN THE ANALYTICAL ONES**, because
they are what a successor will repeat:

- **A re-entry that only looked armed.** Launched a watcher with a bare `&` in a
  foreground call, writing to `/dev/null` — unable to ever notify. Then
  `pkill -f "watcher.sh"` matched its own command line and killed the shell.
- **An obligation record that asserted the edit, not the outcome.** A marker
  rewrite dropped two open obligations without writing them to `closed`; a later
  one wrote unparseable YAML while the script printed `PASS`, because it asserted
  the substitution applied rather than that the artifact still parses. **Validate
  the artifact, not the action.**
- **A `git status`-clean primary is not a refreshed one.** A `uv.lock`
  modification this supervisor had told the worker to PRESERVE later blocked the
  fast-forward. Preserving it was right while it was inert; it stopped being
  inert, and the instruction was reversed explicitly rather than quietly.

**The standing instruction:** this thread's supervisor is wrong often enough
that the worker contradicting it is the SYSTEM WORKING, not friction. When that
happens, re-run the exact command with a positive control before defending
anything.
