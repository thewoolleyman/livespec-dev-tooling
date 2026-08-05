#!/usr/bin/env bash
#
# gate-run.sh — run a gate command DETACHED and report a durable verdict.
#
# WHY THIS EXISTS
# ---------------
# The committed `.claude/settings.json` caps a Bash tool call at
# BASH_MAX_TIMEOUT_MS=1200000 (20 minutes). The commit aggregate
# (`just check` via scripts/just/check-pre-commit.sh) measures 593s and
# 1043s on an unloaded host and exceeds 1200s under sustained fleet
# load. When it does, the harness kills the tool call and the agent sees
# NOTHING: no exit code, no hook output, no verdict. That kill is
# indistinguishable from a hook REFUSAL unless you go and check by hand
# whether any check target actually ran. Under load the repo therefore
# becomes uncommittable for product `.py`, and it fails silently.
#
# This runner decouples gate RUNTIME from harness PATIENCE. It does NOT
# weaken any gate:
#
#   - the SAME command runs, with the SAME hooks, over the SAME targets
#   - every verdict is still honored — the gate's own exit code is the
#     verdict and this runner only transports it
#   - a run that does not finish can NEVER read as a pass; it reports
#     the dedicated terminal state DIED_WITHOUT_VERDICT
#
# The only thing that changes is where the waiting happens: the gate
# runs in its own detached session that outlives the tool call, and a
# separate, cheap, restartable waiter reports the verdict when it lands.
#
# THE SILENT-KILL FIX
# -------------------
# The run directory IS the evidence, and it is written by the gate's own
# process rather than by the agent:
#
#   started_at   written before the gate starts  → "a run was launched"
#   pid          written by the child itself     → "the gate has a live process"
#   output.log   streamed as the gate runs       → "these targets ran"
#   exit_code    written ONLY on real completion → "there is a verdict"
#
# `exit_code` present is the ONE marker of a verdict. From those four
# files every terminal state is derivable, with no ambiguity left:
#
#   exit_code == 0            → PASSED
#   exit_code 1..127          → FAILED   (a real verdict: a check failed
#                                         or a hook refused; output.log
#                                         carries the reason)
#   exit_code >= 128          → DIED_WITHOUT_VERDICT (killed by signal
#                                         N=code-128; a signal death is
#                                         NOT a check verdict)
#   no exit_code, pid alive   → RUNNING
#   no exit_code, pid dead    → DIED_WITHOUT_VERDICT (vanished)
#
# `status` additionally reports how many check targets were observed to
# START and to COMPLETE in output.log. That is the mechanical answer to
# "did any target actually run", which previously had to be reconstructed
# by hand every time a gate went quiet.
#
# USAGE
# -----
#   just gate-start -- mise exec -- git commit --amend --no-edit
#   just gate-start -- just check
#       Mints a run id, launches the gate detached, prints the id, and
#       returns in well under a second. Safe to run FOREGROUND.
#
#   just gate-wait <run-id>
#       Blocks until the run reaches a terminal state, prints the
#       verdict, and exits with the gate's own exit code (or 75 for
#       DIED_WITHOUT_VERDICT). This is the command to hand to
#       `run_in_background: true` — killing the waiter does not touch
#       the gate, and `gate-wait` can simply be re-issued.
#
#   just gate-status [<run-id>]    one-shot verdict, never blocks
#   just gate-list                 recent runs, newest last
#
# EXIT CODES
#   0        PASSED
#   1..127   FAILED — the gate's own exit code, passed through unchanged
#   75       DIED_WITHOUT_VERDICT (EX_TEMPFAIL) — the gate did not finish;
#            this is NOT a failing verdict and NOT a pass
#   64       usage error (EX_USAGE)
#   70       the runner itself could not launch the gate (EX_SOFTWARE)
#
# `set -euo pipefail` (errexit): a runner whose own bookkeeping fails
# part-way MUST NOT go on to write a verdict file, because a
# half-written run directory is exactly the ambiguity this script
# exists to remove. The one place errexit is deliberately suspended is
# around the gate invocation itself in `_child`, where a non-zero exit
# IS the payload rather than an error.
set -euo pipefail

readonly EX_USAGE=64
readonly EX_SOFTWARE=70
readonly EX_NO_VERDICT=75
readonly SIGNAL_EXIT_FLOOR=128
readonly POLL_INTERVAL_S=5

repo_root() {
    git rev-parse --show-toplevel
}

runs_root() {
    # tmp/ is gitignored: run records are host-local evidence, never
    # committed, and never a substitute for the gate's own output.
    printf '%s/tmp/gate-runs' "$(repo_root)"
}

usage() {
    cat >&2 <<'USAGE'
usage:
  gate-run.sh start [--label LABEL] -- COMMAND [ARG...]
  gate-run.sh wait  RUN_ID
  gate-run.sh status [RUN_ID]
  gate-run.sh list
USAGE
    exit "$EX_USAGE"
}

# ---------------------------------------------------------------------
# state derivation — the single source of truth for every verdict word
# ---------------------------------------------------------------------

# Echo the terminal-state word for a run directory. Pure function of the
# files on disk plus a liveness probe; no side effects.
derive_state() {
    local dir="$1"
    if [[ ! -d "$dir" ]]; then
        printf 'UNKNOWN_RUN'
        return
    fi
    if [[ -f "$dir/exit_code" ]]; then
        local code
        code=$(cat "$dir/exit_code")
        if [[ "$code" == "0" ]]; then
            printf 'PASSED'
        elif [[ "$code" -ge "$SIGNAL_EXIT_FLOOR" ]]; then
            printf 'DIED_WITHOUT_VERDICT'
        else
            printf 'FAILED'
        fi
        return
    fi
    if [[ -f "$dir/pid" ]] && kill -0 "$(cat "$dir/pid")" 2>/dev/null; then
        printf 'RUNNING'
        return
    fi
    # A run directory with no exit_code and no live process. Either the
    # child was killed before it could record a verdict, or it never got
    # far enough to publish its pid. Both are the same thing to a caller:
    # there is no verdict and none is coming.
    printf 'DIED_WITHOUT_VERDICT'
}

state_exit_code() {
    local dir="$1" state="$2"
    case "$state" in
        PASSED) printf '0' ;;
        FAILED) cat "$dir/exit_code" ;;
        *) printf '%s' "$EX_NO_VERDICT" ;;
    esac
}

# ---------------------------------------------------------------------
# start
# ---------------------------------------------------------------------

cmd_start() {
    local label="gate"
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --label)
                [[ $# -ge 2 ]] || usage
                label="$2"
                shift 2
                ;;
            --) shift; break ;;
            *) usage ;;
        esac
    done
    [[ $# -ge 1 ]] || usage

    local root run_id dir
    root="$(runs_root)"
    # Second resolution plus the pid keeps ids unique without needing a
    # lock, and keeps them sortable so `list` is chronological.
    run_id="$(date -u +%Y%m%dT%H%M%SZ)-$$"
    dir="$root/$run_id"
    mkdir -p "$dir"

    printf '%s\n' "$label" >"$dir/label"
    printf '%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >"$dir/started_at"
    printf '%s\n' "$(pwd)" >"$dir/cwd"
    printf '%s\n' "$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo '?')" >"$dir/branch"
    printf '%s\n' "$(git rev-parse HEAD 2>/dev/null || echo '?')" >"$dir/head"
    # One argument per line: the record shows exactly what ran, with no
    # re-quoting guesswork when someone reads it back later.
    printf '%s\n' "$@" >"$dir/command"
    : >"$dir/output.log"

    local self
    self="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"

    # setsid detaches the gate into its own session, so the harness
    # killing the tool call's process group cannot reach it. Without
    # setsid the whole point is lost: the gate would die with the tool
    # call exactly as it does today.
    if command -v setsid >/dev/null 2>&1; then
        setsid "$self" __child "$dir" "$@" </dev/null >/dev/null 2>&1 &
    else
        nohup "$self" __child "$dir" "$@" </dev/null >/dev/null 2>&1 &
    fi
    disown 2>/dev/null || true

    # The child publishes its own pid as its first act. Waiting briefly
    # for that file means `start` never returns claiming success for a
    # gate that failed to launch.
    local waited=0
    while [[ ! -f "$dir/pid" ]] && [[ ! -f "$dir/exit_code" ]] && [[ "$waited" -lt 100 ]]; do
        sleep 0.1
        waited=$((waited + 1))
    done
    if [[ ! -f "$dir/pid" ]] && [[ ! -f "$dir/exit_code" ]]; then
        printf 'ERROR: gate child never published a pid; run dir: %s\n' "$dir" >&2
        return "$EX_SOFTWARE"
    fi

    cat >&2 <<EOF
:: gate launched detached — run id: $run_id
::   verdict : just gate-wait $run_id     (background this; killing it is harmless)
::   peek    : just gate-status $run_id
::   output  : $dir/output.log
:: the gate now outlives this tool call. A run that does not finish reports
:: DIED_WITHOUT_VERDICT — it can never read as a pass.
EOF
    printf '%s\n' "$run_id"
}

# ---------------------------------------------------------------------
# __child — internal; runs inside the detached session
# ---------------------------------------------------------------------

cmd_child() {
    local dir="$1"
    shift
    printf '%s\n' "$$" >"$dir/pid"

    # errexit off for the gate itself: a non-zero exit is the verdict we
    # are here to capture, not an error in the runner.
    set +e
    "$@" >>"$dir/output.log" 2>&1
    local code=$?
    set -e

    printf '%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >"$dir/finished_at"
    # exit_code is written LAST and atomically. Its presence is the sole
    # marker that a verdict exists, so it must never appear early or
    # half-written.
    printf '%s\n' "$code" >"$dir/exit_code.partial"
    mv "$dir/exit_code.partial" "$dir/exit_code"
}

# ---------------------------------------------------------------------
# status / wait / list
# ---------------------------------------------------------------------

latest_run_id() {
    local root
    root="$(runs_root)"
    [[ -d "$root" ]] || return 1
    ls -1 "$root" 2>/dev/null | sort | tail -1
}

# Count check targets observed in the captured output. The dispatcher
# writes one `::: just <target> [ok|FAILED, wall: Ns]` line per completed
# target, so these counts are direct evidence of work actually done —
# the thing that previously had to be reconstructed by hand to tell a
# kill from a refusal.
report_target_evidence() {
    local dir="$1"
    local completed failed
    completed=$(grep -c '^::: just .*\[' "$dir/output.log" 2>/dev/null || true)
    failed=$(grep -c '^::: just .*\[FAILED' "$dir/output.log" 2>/dev/null || true)
    printf '  targets completed : %s (failed: %s)\n' "${completed:-0}" "${failed:-0}"
    if [[ "${completed:-0}" == "0" ]]; then
        printf '  NOTE: zero check targets completed — the gate produced no per-target evidence.\n'
    fi
}

cmd_status() {
    local run_id="${1:-}"
    if [[ -z "$run_id" ]]; then
        run_id="$(latest_run_id)" || {
            printf 'no gate runs recorded\n' >&2
            return "$EX_USAGE"
        }
    fi
    local dir state
    dir="$(runs_root)/$run_id"
    state="$(derive_state "$dir")"

    if [[ "$state" == "UNKNOWN_RUN" ]]; then
        printf 'UNKNOWN_RUN %s — no such run directory\n' "$run_id" >&2
        return "$EX_USAGE"
    fi

    printf '=== gate run %s ===\n' "$run_id"
    printf '  state             : %s\n' "$state"
    printf '  label             : %s\n' "$(cat "$dir/label" 2>/dev/null || echo '?')"
    printf '  command           : %s\n' "$(tr '\n' ' ' <"$dir/command" 2>/dev/null || echo '?')"
    printf '  branch @ head     : %s @ %s\n' \
        "$(cat "$dir/branch" 2>/dev/null || echo '?')" \
        "$(cut -c1-8 "$dir/head" 2>/dev/null || echo '?')"
    printf '  started_at        : %s\n' "$(cat "$dir/started_at" 2>/dev/null || echo '?')"
    [[ -f "$dir/finished_at" ]] && printf '  finished_at       : %s\n' "$(cat "$dir/finished_at")"
    [[ -f "$dir/exit_code" ]] && printf '  exit_code         : %s\n' "$(cat "$dir/exit_code")"
    report_target_evidence "$dir"
    printf '  output.log        : %s\n' "$dir/output.log"

    case "$state" in
        PASSED)
            printf '  VERDICT: the gate RAN TO COMPLETION and PASSED.\n'
            ;;
        FAILED)
            printf '  VERDICT: the gate RAN TO COMPLETION and REFUSED (exit %s).\n' \
                "$(cat "$dir/exit_code")"
            printf '  This IS a verdict and it must be honored — read output.log for the reason.\n'
            printf '  --- last 40 lines ---\n'
            tail -40 "$dir/output.log" 2>/dev/null || true
            ;;
        RUNNING)
            printf '  VERDICT: NONE YET — still running (pid %s).\n' "$(cat "$dir/pid")"
            ;;
        DIED_WITHOUT_VERDICT)
            printf '  ⛔ NO VERDICT: the gate DID NOT FINISH.\n'
            printf '  This is NOT a pass and NOT a refusal. Nothing was decided, so nothing\n'
            printf '  may be concluded from it. Re-run the gate; do not treat this as green.\n'
            ;;
    esac
    return "$(state_exit_code "$dir" "$state")"
}

cmd_wait() {
    [[ $# -ge 1 ]] || usage
    local run_id="$1" dir state
    dir="$(runs_root)/$run_id"
    if [[ ! -d "$dir" ]]; then
        printf 'UNKNOWN_RUN %s — no such run directory\n' "$run_id" >&2
        return "$EX_USAGE"
    fi
    while true; do
        state="$(derive_state "$dir")"
        [[ "$state" == "RUNNING" ]] || break
        sleep "$POLL_INTERVAL_S"
    done
    cmd_status "$run_id"
}

cmd_list() {
    local root
    root="$(runs_root)"
    if [[ ! -d "$root" ]]; then
        printf 'no gate runs recorded\n'
        return 0
    fi
    local run_id dir
    for run_id in $(ls -1 "$root" 2>/dev/null | sort); do
        dir="$root/$run_id"
        printf '%-24s  %-20s  %s\n' \
            "$run_id" "$(derive_state "$dir")" \
            "$(tr '\n' ' ' <"$dir/command" 2>/dev/null || echo '?')"
    done
}

main() {
    [[ $# -ge 1 ]] || usage
    local sub="$1"
    shift
    case "$sub" in
        start) cmd_start "$@" ;;
        wait) cmd_wait "$@" ;;
        status) cmd_status "$@" ;;
        list) cmd_list "$@" ;;
        __child) cmd_child "$@" ;;
        *) usage ;;
    esac
}

main "$@"
