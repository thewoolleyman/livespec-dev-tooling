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
generator_ref='2a97b88744bd'
generator_version='0.27.0'
generator_prose_md5='eaebe06065b3efa0053d6ea5932d52c0'
cache_root="$HOME/.claude/plugins/cache/$generator_plugin/$generator_plugin"
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

⚠️ **Recorded at generation time: the ref is NOT the identity, and this host
proves why — at a scale that is worth stating exactly.** Measured 2026-08-04
against `~/.claude/plugins/cache/livespec-overseer/livespec-overseer/`:
**37 installed refs carry a `prose/supervise-plan.md`, and 26 of them —
spanning 23 distinct plugin versions from `0.16.0` through `0.27.5` — digest
identically to `eaebe06065b3efa0053d6ea5932d52c0`.** Twenty-six refs and
twenty-three versions report twenty-six generators where the prose says there
is **one**.

✅ **And the digest is not a constant, which is the positive control this claim
needs.** The other eleven refs carry three DIFFERENT digests:
`2283862cf32b60b2e82c02164c9b3b83` (nine refs, `0.12.2`–`0.13.3`),
`30b59fcf0ea5f3cf78402129826b1ffa` (`0.14.0`), and
`9ca18d56772dcf8fcdc2cf78ed8108a8` (`0.15.0`). The identity therefore
DISCRIMINATES — it moved three times when the prose actually changed, and held
across twenty-six refs when it did not. A digest that could only ever report
one value would be the same defect as a check that cannot fail.

⛔ **`generator_ref` here is a companion that does NOT name the root this
session read, and that discrepancy is recorded rather than hidden.** The Claude
Code session that emitted this charter resolved its skill base directory to
`070ec63059c0` (`0.25.0`) and read the prose from there; the stamp was
afterwards re-pointed at `2a97b88744bd` (`0.27.0`). Both roots hold
byte-identical prose, so the digest — the actual identity — is unaffected and
the block still verifies what it claims to verify. See Corrections C1. If a
future cold open HALTs because `2a97b88744bd` has been evicted, the documented
re-stamp path applies: re-point `generator_ref` at an installed ref, and
re-stamp `generator_prose_md5` from it only after reading what changed.

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
