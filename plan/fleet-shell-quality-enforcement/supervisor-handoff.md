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

## Generator provenance

The digest is the generator identity. Plugin name, cache ref, and version are
human-readable companions; they do not replace the digest. This charter was
emitted from the installed Codex plugin root actually read by the generator:

```sh
generator_plugin='livespec-overseer'
generator_ref='0.15.0'
generator_version='0.15.0'
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
