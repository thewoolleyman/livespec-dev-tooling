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
#   exit_code 1..74, 76..127  → FAILED   (a real verdict: a check failed
#                                         or a hook refused; output.log
#                                         carries the reason)
#   exit_code == 75 or >= 128 → DIED_WITHOUT_VERDICT (the delegated
#                                         no-verdict sentinel, or a signal
#                                         death; neither is a check verdict)
#   no exit_code, pid alive   → RUNNING
#   no exit_code, pid dead    → DIED_WITHOUT_VERDICT (vanished)
#
# `status` additionally reports how many check targets were observed to
# START and to COMPLETE in output.log. That is the mechanical answer to
# "did any target actually run", which previously had to be reconstructed
# by hand every time a gate went quiet.
#
# WHERE THE EVIDENCE LIVES (livespec-dev-tooling-trfzkw)
# -----------------------------------------------------
# The run directory used to resolve under the INVOKED worktree
# (`$(git rev-parse --show-toplevel)/tmp/gate-runs`). A linked worktree is
# removed as ROUTINE post-merge cleanup, and `git worktree remove` deleted
# the run directory with it — so on 2026-09-06 two detached runs
# (20260906T025635Z-80255, 20260906T025732Z-87836) refused on
# `core_bare_set` and the question "which aggregate member was running at
# 03:00:09Z" became permanently unanswerable. Evidence whose lifetime is
# shorter than the incident it documents is not evidence.
#
# The store is therefore resolved from the SHARED git directory
# (`git rev-parse --git-common-dir`), which every linked worktree of a
# repository resolves identically and which outlives all of them: runs land
# under the PRIMARY checkout's `tmp/gate-runs/<run-id>/`. `status`, `wait`
# and `list` resolve the same path, so a run started in a worktree is
# readable from the primary — and from any sibling worktree — after that
# worktree is gone. `tmp/` is gitignored exactly as before; nothing about
# what gets committed changes.
#
# THE .git/config WRITE-WATCH (livespec-p32m6d, folded in here)
# ------------------------------------------------------------
# Those same two run ids are the reason the config write-watch lives in
# THIS file: the `core.bare` flip happened INSIDE a detached gate child,
# so the instrument that will name the next writer has to be armed around
# the gate and has to write into the durable run directory above.
#
# Around every gate this runner now:
#
#   core_before        digest of the PRIMARY's shared `[core]` block,
#                      captured before the gate starts
#   config-writes.log  appended by a dependency-free background watcher
#                      (no inotify-tools, no auditd, no root) whenever the
#                      shared config changes or its lockfile is released —
#                      carrying the current core.bare value, the gate
#                      child's descendant process tree, and any
#                      /proc/*/fd holder of the config or its lock
#   watch.armed        touched by the watcher after its first pass; the
#                      gate is launched only once it exists
#   config.lock-seen   touched by the watcher when it first sees the
#                      config's lockfile (an observation, never a record)
#   watch.stop         touched by the child when the gate has exited; the
#                      watcher drains — finishes any in-flight record, runs
#                      one final pass — and exits on its own
#   core_after         the same digest, captured after the gate finishes
#   CORE_BARE_FLIP     written only when before != after; `status` surfaces
#                      it loudly
#
# The watch is STRICTLY an observer. It never changes the verdict: the
# gate's own exit code is passed through unchanged, a flip is NON-FATAL,
# and every watch operation is failure-tolerant so the instrument can
# never be the reason a gate does not report. The existing
# `core_bare_is_true` remedy still heals the primary.
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
# How often `wait` re-reads the run's state. Every poll is bash builtins
# only (see `idle_sleep` and `derive_state_into`), so the cadence costs
# wakeups, never processes; a tenth of a second leaves the scheduler nearly
# the entire five-second return budget after `exit_code` appears.
readonly POLL_INTERVAL_S=0.1
# The config watcher's poll cadence. Fast enough that a writer which is
# still alive one tick after its write is caught in the descendant-tree
# snapshot. A tick forks nothing (see `config_changed`), so the cadence
# costs wakeups only.
readonly WATCH_INTERVAL_S=0.2
# Liveness ceilings for the watcher's two rendezvous with the child
# (livespec-dev-tooling-lndv2l). Neither decides an outcome: the gate waits
# for `watch.armed` and the child waits for the drained watcher to exit, and
# these only bound how long a HUNG watcher can hold either up. Past the arm
# ceiling the gate launches anyway; past the drain ceiling the watcher is
# killed. Whole seconds, because they are checked against `$SECONDS`.
readonly WATCH_ARM_CEILING_S=30
readonly WATCH_DRAIN_CEILING_S=120

# Descriptor that no writer ever feeds, so a timed `read` on it is a sleep
# that spawns nothing. `sleep` is an external program: one fork+exec per
# tick, which at the watcher's cadence was about 15 forks per second per
# live gate (livespec-dev-tooling-ycahud). Empty when the host's bash
# cannot do a fractional `read -t`, in which case `idle_sleep` degrades to
# `sleep` rather than spinning.
#
# A named FIFO opened read-write, then unlinked: the open holds both ends, so
# nothing ever reaches EOF and every read waits its full timeout. It replaced
# `exec {fd}<> <(:)`, which on macOS DUPLICATES the pipe's read end (its
# /dev/fd is a dup, not a reopen), so the descriptor hit EOF as soon as `:`
# exited — a race the open's own probe could win or lose, leaving either a
# silent busy loop or a `sleep` fallback. Two spawns per open, none per tick.
IDLE_FD=""

open_idle_fd() {
    local fd="" fifo
    fifo="${TMPDIR:-/tmp}/gate-run-idle.$$.$RANDOM"
    if mkfifo "$fifo" 2>/dev/null && { exec {fd}<>"$fifo"; } 2>/dev/null; then
        rm -f "$fifo"
        # A bash that rejects a fractional timeout returns at once with a
        # status below the 128+ timeout range; using it would busy-loop.
        local status=0
        read -r -t 0.01 -u "$fd" _ 2>/dev/null || status=$?
        if [[ "$status" -gt 128 ]]; then
            IDLE_FD="$fd"
            return 0
        fi
        exec {fd}>&- || true
    fi
    rm -f "$fifo" 2>/dev/null || true
    IDLE_FD=""
}

close_idle_fd() {
    if [[ -n "$IDLE_FD" ]]; then
        exec {IDLE_FD}>&- || true
    fi
    IDLE_FD=""
}

idle_sleep() {
    if [[ -n "$IDLE_FD" ]]; then
        read -r -t "$1" -u "$IDLE_FD" _ || true
    else
        sleep "$1"
    fi
}

# THE STALL BOUND. A gate always ends with a verdict or an explicit
# no-verdict state, and never hangs (SPECIFICATION/non-functional-requirements.md,
# "Developer host platforms": "A gate always ends with a verdict"). A local gate
# runs as its OWN process group, and the child watches its output: when nothing
# new reaches output.log for the stall window, the whole group is ended — a
# pytest session and its pytest-xdist workers alike, such as rerunfailures
# re-runs deadlocked with every worker idle — a line naming the window is
# appended, and the run records STALL_EXIT_CODE, a FAILED verdict, never a pass.
# The window, its default and its override are the commit-time replay leg's
# (LIVESPEC_SUITE_GREEN_STALL_SECONDS, 900 s). TERM first, KILL after
# GATE_STALL_KILL_GRACE_SECONDS. Builtins only per tick (`kill -0`, `-nt`, a
# `: >` redirect, `$SECONDS`, `idle_sleep`), so an idle gate spawns nothing.
# The cluster venue is excluded: its client waits silently through admission
# and bounds that wait itself.
readonly STALL_EXIT_CODE=124

run_gate_with_stall_bound() {
    local dir="$1"
    shift
    local stall="${LIVESPEC_SUITE_GREEN_STALL_SECONDS:-900}"
    local grace="${GATE_STALL_KILL_GRACE_SECONDS:-30}"
    local stamp="$dir/progress.stamp"
    : >"$stamp"
    set -m
    "$@" >>"$dir/output.log" 2>&1 &
    local gate_pid=$!
    set +m
    # Opened after the gate launches, so the gate inherits nothing of ours.
    open_idle_fd || true
    local quiet_since=$SECONDS ended
    while kill -0 "$gate_pid" 2>/dev/null; do
        if [[ "$dir/output.log" -nt "$stamp" ]]; then
            : >"$stamp"
            quiet_since=$SECONDS
        elif (( SECONDS - quiet_since >= stall )); then
            printf '\ngate-run: no output for %ss, the stall window (LIVESPEC_SUITE_GREEN_STALL_SECONDS); ending the gate'"'"'s whole process group, workers included — not a pass\n' \
                "$stall" >>"$dir/output.log"
            kill -TERM -- "-$gate_pid" 2>/dev/null || true
            ended=$SECONDS
            # Wait for the whole GROUP, not just its leader: a worker's TERM
            # handler gets its grace period even after the leader has gone.
            while kill -0 -- "-$gate_pid" 2>/dev/null && (( SECONDS - ended < grace )); do
                idle_sleep 1
            done
            kill -KILL -- "-$gate_pid" 2>/dev/null || true
            wait "$gate_pid" 2>/dev/null || true
            close_idle_fd || true
            return "$STALL_EXIT_CODE"
        fi
        idle_sleep 1
    done
    close_idle_fd || true
    wait "$gate_pid"
}

repo_root() {
    git rev-parse --show-toplevel
}

timestamp() {
    date -u +%Y-%m-%dT%H:%M:%SZ
}

# Absolute path of the SHARED git directory — the primary checkout's
# `.git` for a linked worktree, and the repo's own `.git` otherwise. git
# reports it relative to the cwd, so it is normalized here; every caller
# needs a path that survives the cwd going away.
git_common_dir() {
    local dir
    dir="$(git rev-parse --git-common-dir 2>/dev/null)" || return 1
    [[ -d "$dir" ]] || return 1
    ( cd "$dir" && pwd )
}

# The shared `.git/config` — the file whose `[core]` section the flip
# corrupts. Resolved from the SHARED dir on purpose: a run inside a linked
# worktree must digest and watch the PRIMARY's config, not the worktree's
# per-worktree config.
shared_config_path() {
    local common
    common="$(git_common_dir)" || return 1
    printf '%s/config' "$common"
}

# Where run directories live. Keyed to the SHARED git dir, so every
# worktree of a repository resolves the SAME store and a run outlives the
# worktree that started it (livespec-dev-tooling-trfzkw).
#
# tmp/ is gitignored: run records are host-local evidence, never
# committed, and never a substitute for the gate's own output.
runs_root() {
    local common="" primary
    common="$(git_common_dir)" || common=""
    if [[ -n "$common" && "$(basename "$common")" == ".git" ]]; then
        primary="$(dirname "$common")"
        if [[ -d "$primary" ]]; then
            printf '%s/tmp/gate-runs' "$primary"
            return 0
        fi
    fi
    # No primary checkout to hold the store (a bare or otherwise
    # unconventional shared dir). Per-user state is the fallback, keyed by
    # repository name so unrelated repos never share a store.
    printf '%s/livespec/gate-runs/%s' \
        "${XDG_STATE_HOME:-${HOME:-/tmp}/.local/state}" \
        "$(basename "${common:-unknown-repo}" .git)"
}

# Resolve a run recorded by either store version. New runs always use
# `runs_root`, but a worktree can upgrade its pack between `start` and
# `wait`: the old runner wrote below that worktree while the replacement reads
# the shared primary store. Preserve the old run's real verdict instead of
# reporting it as absent.
run_dir_for_read() {
    local run_id="$1" shared legacy
    shared="$(runs_root)/$run_id"
    if [[ -d "$shared" ]]; then
        printf '%s' "$shared"
        return 0
    fi
    legacy="$(repo_root)/tmp/gate-runs/$run_id"
    if [[ -d "$legacy" ]]; then
        printf '%s' "$legacy"
        return 0
    fi
    return 1
}

unknown_run() {
    local run_id="$1"
    printf 'UNKNOWN_RUN %s — no run directory under shared store %s or invoking worktree store %s\n' \
        "$run_id" "$(runs_root)/$run_id" "$(repo_root)/tmp/gate-runs/$run_id" >&2
}

usage() {
    cat >&2 <<'USAGE'
usage:
  gate-run.sh start [--label LABEL] [--local] -- COMMAND [ARG...]
  gate-run.sh wait  RUN_ID
  gate-run.sh status [RUN_ID]
  gate-run.sh list
USAGE
    exit "$EX_USAGE"
}

# ---------------------------------------------------------------------
# state derivation — the single source of truth for every verdict word
# ---------------------------------------------------------------------

# Set STATE to the terminal-state word for a run directory. Pure function
# of the files on disk plus a liveness probe; no side effects. Builtins
# only (`read`, `kill -0`, `[[ ]]`) — no command substitution — because
# `wait` calls it on every poll and an idle waiter must spawn nothing.
STATE=""
derive_state_into() {
    local dir="$1" code="" pid=""
    if [[ ! -d "$dir" ]]; then
        STATE='UNKNOWN_RUN'
        return
    fi
    if [[ -f "$dir/exit_code" ]]; then
        read -r code <"$dir/exit_code" || code=""
        if [[ "$code" == "0" ]]; then
            STATE='PASSED'
        elif [[ "$code" -eq "$EX_NO_VERDICT" || "$code" -ge "$SIGNAL_EXIT_FLOOR" ]]; then
            STATE='DIED_WITHOUT_VERDICT'
        else
            STATE='FAILED'
        fi
        return
    fi
    if [[ -f "$dir/pid" ]]; then
        read -r pid <"$dir/pid" || pid=""
        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
            STATE='RUNNING'
            return
        fi
    fi
    # A run directory with no exit_code and no live process. Either the
    # child was killed before it could record a verdict, or it never got
    # far enough to publish its pid. Both are the same thing to a caller:
    # there is no verdict and none is coming.
    STATE='DIED_WITHOUT_VERDICT'
}

derive_state() {
    derive_state_into "$1"
    printf '%s' "$STATE"
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
# .git/config write-watch (livespec-p32m6d, folded into trfzkw)
#
# Every function below is an OBSERVER and must behave like one: it may
# report nothing, but it may never fail the gate, block it, or write
# anything outside the run directory. Callers wrap them accordingly.
# ---------------------------------------------------------------------

sha256_of() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum | cut -d' ' -f1
    elif command -v shasum >/dev/null 2>&1; then
        shasum -a 256 | cut -d' ' -f1
    else
        cat >/dev/null
        printf 'unavailable'
    fi
}

# Print the shared config's `[core]` block verbatim. A section header ends
# the previous section, so tracking "am I inside [core]" across headers is
# the whole parse; `[core "sub"]` counts, `[coreish]` does not.
core_section() {
    local cfg="$1"
    [[ -f "$cfg" ]] || return 0
    awk '
        /^[[:space:]]*\[/ { in_core = ($0 ~ /^[[:space:]]*\[core([[:space:]]|\])/) }
        in_core
    ' "$cfg" 2>/dev/null || true
}

# `core.bare` as git itself resolves it, or the literal `unset` — the
# distinction the incident turns on, since an unset flag and an explicit
# `false` are the same to git but different to a diff.
core_bare_value() {
    local cfg="$1" value=""
    value="$(git config --file "$cfg" --get core.bare 2>/dev/null)" || value=""
    printf '%s' "${value:-unset}"
}

capture_core_state() {
    local cfg="$1" out="$2"
    {
        printf 'captured_at: %s\n' "$(timestamp)"
        printf 'config: %s\n' "$cfg"
        printf 'core.bare: %s\n' "$(core_bare_value "$cfg")"
        printf 'core_sha256: %s\n' "$(core_section "$cfg" | sha256_of)"
    } >"$out"
}

core_field() {
    local file="$1" key="$2" line=""
    line="$(grep -m1 "^$key: " "$file" 2>/dev/null)" || line=""
    [[ -n "$line" ]] || { printf 'unreadable'; return 0; }
    printf '%s' "${line#"$key": }"
}

# Cheap change token. git rewrites the config through a lockfile and a
# rename, so the INODE moves on every real write — which is what makes
# this reliable despite `%Y` having only second resolution.
config_signature() {
    stat -c '%i %s %Y' "$1" 2>/dev/null \
        || stat -f '%i %z %m' "$1" 2>/dev/null \
        || printf 'absent'
}

# Fork-free "has the config been rewritten since the baseline?" The
# baseline is two files in the run directory: a HARD LINK to the config as
# it was (`config.ref`) and a stamp (`config.stamp`) touched at the same
# moment. git rewrites the config through a lockfile and a rename, so a
# real write leaves `$cfg` on a NEW inode while the link still pins the old
# one — `-ef` (same device and inode) catches that regardless of timestamp
# granularity. An in-place write keeps the inode and moves the mtime, which
# `-nt` against the stamp catches. Both tests are `[[ ]]` builtins, so a
# tick that finds nothing spawns nothing. Returns 0 when it changed.
config_changed() {
    local cfg="$1" ref="$2" stamp="$3"
    [[ -e "$cfg" ]] || return 0
    if [[ -e "$ref" ]] && ! [[ "$cfg" -ef "$ref" ]]; then
        return 0
    fi
    [[ "$cfg" -nt "$stamp" ]]
}

# Re-baseline after an event. Forks, but only when something happened.
config_rebaseline() {
    local cfg="$1" ref="$2" stamp="$3"
    rm -f "$ref" 2>/dev/null || true
    ln "$cfg" "$ref" 2>/dev/null || true
    : >"$stamp" 2>/dev/null || true
}

# Parent pid from /proc/<pid>/stat, returned in PROC_PPID (`?` when the
# process is gone). `comm` may itself contain spaces and parentheses, so
# everything through the LAST `) ` is dropped before the state and ppid
# fields are read off the remainder.
#
# Fork-free BY CONSTRUCTION: a builtin `read` and parameter expansion, with
# the answer handed back in a variable. The previous version printed it and
# every caller captured it with `$(...)` — a fork per /proc entry. On a
# 960-process dev host at load 112 that one scan took 50 s
# (livespec-dev-tooling-lndv2l), which is how a record stayed "still being
# composed" long enough for the gate to end around it.
PROC_PPID="?"
read_proc_ppid() {
    local line="" rest
    PROC_PPID="?"
    { read -r line <"/proc/$1/stat"; } 2>/dev/null || true
    [[ -n "$line" ]] || return 0
    rest="${line##*) }"
    rest="${rest#* }"
    PROC_PPID="${rest%% *}"
}

# Every process descended from the gate child, breadth-first. The gate
# runs `just check`, which fans out through a dispatcher, so the writer we
# are hunting is typically several levels below the child. One fork-free
# pass over /proc builds a parent -> children index, so the walk costs one
# lookup per descendant instead of one scan of every pid per descendant.
descendant_pids() {
    local root="$1" d pid cur i=0
    local -A children=() seen=()
    local -a frontier=("$root")
    for d in /proc/[0-9]*; do
        pid="${d##*/}"
        read_proc_ppid "$pid"
        children[$PROC_PPID]+="$pid "
    done
    while [[ "$i" -lt "${#frontier[@]}" ]]; do
        cur="${frontier[$i]}"
        i=$((i + 1))
        # A pid recycled mid-scan can make the index cyclic; visit once.
        [[ -z "${seen[$cur]:-}" ]] || continue
        seen[$cur]=1
        printf '%s\n' "$cur"
        for pid in ${children[$cur]:-}; do
            frontier+=("$pid")
        done
    done
}

# Processes holding the config (or its lock) OPEN right now. This is the
# strongest attribution available without root: it names the writer while
# the write is still in flight. It scans every readable /proc/*/fd, which
# is why it runs only on an event and never on the poll path.
# ONE `find` over /proc/*/fd, not one `readlink` fork per descriptor. The
# per-fd loop this replaces forked 6,223 times on a 1,000-process host and
# took 55 s, so the record was still being composed when the gate ended and
# the watcher was killed, and an empty config-writes.log read as "nothing
# wrote". `find -lname` resolves every link in-process in about 0.1 s on the
# same host. Speed is no longer what keeps the record, though: the watcher
# is now DRAINED on stop rather than killed (livespec-dev-tooling-lndv2l),
# so a slow attribution delays the verdict instead of losing the record —
# which is why the process-tree scan beside this one is fork-free too.
fd_holders() {
    local -a expr=()
    local target hits="" fd
    for target in "$@"; do
        [[ "${#expr[@]}" -eq 0 ]] || expr+=(-o)
        expr+=(-lname "$target")
    done
    hits="$(find /proc/[0-9]*/fd -mindepth 1 -maxdepth 1 \( "${expr[@]}" \) 2>/dev/null)" || hits=""
    if [[ -n "$hits" ]]; then
        while IFS= read -r fd; do
            printf '      %s -> %s\n' "$fd" "$(readlink "$fd" 2>/dev/null)"
        done <<<"$hits"
    else
        printf '      (none held open at sample time)\n'
    fi
}

proc_attribution() {
    local gate_pid="$1" cfg="$2" pid cmd
    local -a argv=()
    if [[ ! -d /proc ]]; then
        printf '    (no /proc on this host — writer attribution unavailable)\n'
        return 0
    fi
    printf '    gate descendant process tree (pid ppid cmdline):\n'
    # Fork-free per descendant, like the scan itself: `mapfile -d ''` splits
    # the NUL-separated cmdline in-process.
    while IFS= read -r pid; do
        argv=()
        { mapfile -d '' -t argv <"/proc/$pid/cmdline"; } 2>/dev/null || argv=()
        cmd="${argv[*]:-}"
        read_proc_ppid "$pid"
        printf '      %-8s %-8s %s\n' "$pid" "$PROC_PPID" "${cmd:-<exited>}"
    done < <(descendant_pids "$gate_pid")
    printf '    /proc/*/fd holders of the shared config or its lock:\n'
    fd_holders "$cfg" "$cfg.lock"
}

# Compose the whole record, THEN append it in one write. A reader of the log
# (the flip test's writer, a human tailing it) must never see a header with
# no writer under it, which reads exactly like a complete record that found
# nothing — and the drain-ceiling kill can still interrupt a hung watcher.
record_config_event() {
    local log="$1" reason="$2" cfg="$3" gate_pid="$4" record=""
    record="$(
        printf '=== %s  %s\n' "$(timestamp)" "$reason"
        printf '    core.bare now: %s\n' "$(core_bare_value "$cfg")"
        proc_attribution "$gate_pid" "$cfg"
    )" || record=""
    [[ -n "$record" ]] || return 0
    printf '%s\n' "$record" >>"$log" 2>/dev/null || true
}

# One detection pass over the shared config and its lockfile. It reads and
# updates the CALLING `watch_config_writes`'s locals through bash's dynamic
# scope (cfg, dir, gate_pid, log, lock, ref, stamp, last, lock_seen), so the
# poll loop and the final drain pass share one lock/last state.
config_watch_pass() {
    local cur
    if [[ -e "$lock" ]]; then
        if [[ "$lock_seen" == "0" ]]; then
            lock_seen=1
            # An OBSERVATION, not a record: at appearance `$cfg` is still the
            # old file, so nothing is attributed yet. It lives beside the log,
            # never in it, so a run with no write keeps an empty log.
            : >"$dir/config.lock-seen" 2>/dev/null || true
        fi
    elif [[ "$lock_seen" == "1" ]]; then
        # Git publishes the new config by renaming the lock over it. Read
        # only after that lock disappears: at appearance, `$cfg` is still
        # the old file and would attribute a stale core.bare value.
        record_config_event "$log" "config.lock RELEASED" "$cfg" "$gate_pid"
        lock_seen=0
    fi
    if config_changed "$cfg" "$ref" "$stamp"; then
        cur="$(config_signature "$cfg")"
        record_config_event "$log" "config CHANGED ($last -> $cur)" "$cfg" "$gate_pid"
        last="$cur"
        config_rebaseline "$cfg" "$ref" "$stamp"
    fi
}

# Poll the shared config and its lockfile until the child asks it to stop.
# Runs in a background subshell with errexit relaxed: an observer that
# aborts on its own first hiccup is worse than no observer, because its
# silence reads as "nothing happened".
#
# The baseline signature is passed IN rather than sampled here, and that is
# load-bearing. Sampling it as the watcher's first act loses a race the
# 2026-09-06 aggregate actually lost: under load the gate's writer got
# scheduled before this subshell did, so the "before" sample was already
# the AFTER state and the write was never reported. The caller samples it
# before the gate is launched, where no race exists.
#
# The watch is ORDERED against the gate by two rendezvous, never by
# wall-clock luck (livespec-dev-tooling-lndv2l). It touches `watch.armed`
# after its first pass, and the child launches the gate only once that
# exists — so the watcher is already polling when the gate starts. And it
# is never killed mid-record: the child touches `watch.stop` when the gate
# exits, and the watcher then finishes whatever it is composing, runs ONE
# final pass (a lock released or a config changed since the last pass),
# and exits on its own. The child's own death still ends the loop, so an
# orphaned watcher cannot outlive the run.
watch_config_writes() {
    local cfg="$1" dir="$2" gate_pid="$3" last="$4"
    local log="$dir/config-writes.log" lock="$cfg.lock"
    local ref="$dir/config.ref" stamp="$dir/config.stamp"
    local armed="$dir/watch.armed" stop="$dir/watch.stop"
    local lock_seen=0
    open_idle_fd
    while [[ ! -e "$stop" ]] && kill -0 "$gate_pid" 2>/dev/null; do
        config_watch_pass
        [[ -e "$armed" ]] || : >"$armed" 2>/dev/null || true
        idle_sleep "$WATCH_INTERVAL_S"
    done
    config_watch_pass
}

# Block until the watcher has armed (or exited, or the ceiling passed).
# Builtins only — `[[ ]]`, `kill -0`, `$SECONDS`, a timed `read` — so the
# wait costs wakeups, not processes.
await_watch_armed() {
    local dir="$1" watch_pid="$2"
    local deadline=$((SECONDS + WATCH_ARM_CEILING_S))
    while [[ ! -e "$dir/watch.armed" ]] && kill -0 "$watch_pid" 2>/dev/null; do
        [[ "$SECONDS" -lt "$deadline" ]] || return 0
        idle_sleep "$POLL_INTERVAL_S"
    done
}

# Ask the watcher to stop, let it drain, and reap it. Only a watcher still
# alive past the drain ceiling — a hung observer — is killed.
drain_watcher() {
    local dir="$1" watch_pid="$2"
    local deadline=$((SECONDS + WATCH_DRAIN_CEILING_S))
    : >"$dir/watch.stop" 2>/dev/null || true
    while kill -0 "$watch_pid" 2>/dev/null; do
        if [[ "$SECONDS" -ge "$deadline" ]]; then
            kill "$watch_pid" 2>/dev/null || true
            break
        fi
        idle_sleep "$POLL_INTERVAL_S"
    done
    wait "$watch_pid" 2>/dev/null || true
}

# Write the marker iff the shared `[core]` block is not what it was. The
# marker is a REPORT, never a verdict — `cmd_child` writes it after the
# gate's exit code is already decided and never lets it change that code.
maybe_write_flip_marker() {
    local dir="$1"
    local before_bare after_bare before_sha after_sha
    before_bare="$(core_field "$dir/core_before" 'core.bare')"
    after_bare="$(core_field "$dir/core_after" 'core.bare')"
    before_sha="$(core_field "$dir/core_before" 'core_sha256')"
    after_sha="$(core_field "$dir/core_after" 'core_sha256')"
    if [[ "$before_bare" == "$after_bare" && "$before_sha" == "$after_sha" ]]; then
        return 0
    fi
    {
        printf '⛔ CORE_BARE_FLIP — the SHARED .git/config [core] section CHANGED while\n'
        printf '   this gate ran. Something wrote the primary checkout out from under it.\n'
        printf '   core.bare: %s -> %s\n' "$before_bare" "$after_bare"
        printf '   [core] sha256: %s -> %s\n' "$before_sha" "$after_sha"
        printf '   This is NOT a verdict: the gate exit code is passed through unchanged.\n'
        if [[ "$after_bare" == "true" ]]; then
            # The remedy is NOT restated here. It is the `core_bare_set`
            # hint that `check-primary-checkout-commit-refuse-hook-installed`
            # already prints, and spelling its destructive-default steps
            # into a run record would leave a copy-pasteable working-tree
            # reset lying around in host-local evidence.
            printf '   Heal the primary with the `core_bare_set` remedy printed by\n'
            printf '   `just check-primary-checkout-commit-refuse-hook-installed`.\n'
        fi
        printf '   --- core_before ---\n'
        sed 's/^/   /' "$dir/core_before" 2>/dev/null || true
        printf '   --- core_after ---\n'
        sed 's/^/   /' "$dir/core_after" 2>/dev/null || true
        printf '   --- config-writes.log (writer attribution window) ---\n'
        if [[ -s "$dir/config-writes.log" ]]; then
            sed 's/^/   /' "$dir/config-writes.log" 2>/dev/null || true
        else
            # Say so rather than showing an empty block: an empty window is
            # itself a finding — the change was seen only by the before/after
            # digest, so nothing named the writer.
            printf '   (empty — no in-flight write was sampled, so this run carries NO\n'
            printf '   writer attribution; the change is known only from the digests above)\n'
        fi
    } >"$dir/CORE_BARE_FLIP"
}

# ---------------------------------------------------------------------
# worktree-pack preflight (livespec-dev-tooling-ebkrhz.1)
# ---------------------------------------------------------------------

# A fresh `git worktree add` never runs `just bootstrap`, so the
# gitignored `dev-tooling/` worktree-discipline pack is absent until
# someone remembers the manual first-touch step. That absence fails
# exactly one target,
# `check-primary-checkout-commit-refuse-hook-installed`, deep inside the
# full aggregate — so a forgotten `just bootstrap` used to burn a whole
# ~25-30 minute `just check` run to fail on one cheap, fast-to-fix
# target. Materializing the pack costs a few seconds; checking for it
# first keeps that cost off every run where the pack is already present.
ensure_worktree_pack() {
    local root="$1"
    local pack_dir="$root/dev-tooling"
    local f
    for f in worktree-lib.sh branch-protection.sh worktree.just branch-protection.just; do
        [[ -f "$pack_dir/$f" ]] && return 0
    done
    printf ':: dev-tooling/ worktree pack absent — running `just install-worktree-pack`\n' >&2
    ( cd "$root" && just install-worktree-pack ) >&2 || true
}

# ---------------------------------------------------------------------
# start
# ---------------------------------------------------------------------

cmd_start() {
    local label="gate"
    local force_local="false"
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --label)
                [[ $# -ge 2 ]] || usage
                label="$2"
                shift 2
                ;;
            --local)
                force_local="true"
                shift
                ;;
            --) shift; break ;;
            *) usage ;;
        esac
    done
    [[ $# -ge 1 ]] || usage

    ensure_worktree_pack "$(repo_root)"

    local venue_fields=()
    if [[ "$force_local" == "true" ]]; then
        mapfile -t venue_fields < <(
            uv run --no-sync python -m livespec_dev_tooling.gate_runner_delegate --local -- "$@" 2>/dev/null
        )
    else
        mapfile -t venue_fields < <(
            uv run --no-sync python -m livespec_dev_tooling.gate_runner_delegate -- "$@" 2>/dev/null
        )
    fi
    # Consumer worktrees normally have their pinned environment ready, but a
    # source checkout with an importable package and no initialized project
    # environment can still select locally through the interpreter that made
    # the package importable.
    if [[ "${#venue_fields[@]}" != "2" ]]; then
        if [[ "$force_local" == "true" ]]; then
            mapfile -t venue_fields < <(
                python3 -m livespec_dev_tooling.gate_runner_delegate --local -- "$@"
            )
        else
            mapfile -t venue_fields < <(
                python3 -m livespec_dev_tooling.gate_runner_delegate -- "$@"
            )
        fi
    fi
    [[ "${#venue_fields[@]}" == "2" ]] || {
        printf 'ERROR: gate venue selection did not return a venue and reason\n' >&2
        return "$EX_SOFTWARE"
    }
    local venue="${venue_fields[0]}"
    local venue_reason="${venue_fields[1]}"

    local root run_id dir
    root="$(runs_root)"
    # Second resolution plus the pid keeps ids unique without needing a
    # lock, and keeps them sortable so `list` is chronological.
    run_id="$(date -u +%Y%m%dT%H%M%SZ)-$$"
    dir="$root/$run_id"
    mkdir -p "$dir"

    printf '%s\n' "$label" >"$dir/label"
    printf '%s\n' "$venue" >"$dir/venue"
    printf '%s\n' "$venue_reason" >"$dir/venue_reason"
    printf '%s\n' "$(timestamp)" >"$dir/started_at"
    printf '%s\n' "$(pwd)" >"$dir/cwd"
    # The store is shared across every worktree of the repository, so the
    # record has to say which one the gate actually ran in — otherwise the
    # durable directory answers "what ran" but not "where".
    printf '%s\n' "$(repo_root 2>/dev/null || pwd)" >"$dir/worktree"
    local shared=""
    shared="$(shared_config_path)" || shared=""
    printf '%s\n' "$shared" >"$dir/shared_config"
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

    # Arm the write-watch. Every step is `|| true`: the observer may report
    # nothing, but it may never be the reason a gate does not report.
    local cfg="" watch_pid="" baseline=""
    cfg="$(cat "$dir/shared_config" 2>/dev/null || true)"
    if [[ -n "$cfg" ]]; then
        capture_core_state "$cfg" "$dir/core_before" || true
        : >"$dir/config-writes.log"
        # Sampled HERE, before the gate exists, so no writer can beat the
        # watcher to the baseline.
        config_rebaseline "$cfg" "$dir/config.ref" "$dir/config.stamp"
        baseline="$(config_signature "$cfg")"
        # errexit/nounset relaxed inside the watcher for the same reason.
        ( set +e +u +o pipefail; watch_config_writes "$cfg" "$dir" "$$" "$baseline" ) &
        watch_pid=$!
        # Launch the gate only once the watcher is polling. Opened after
        # the fork so the watcher keeps its own descriptor, and closed
        # again before the gate so the gate inherits nothing of ours.
        open_idle_fd || true
        await_watch_armed "$dir" "$watch_pid" || true
        close_idle_fd || true
    fi

    # errexit off for the gate itself: a non-zero exit is the verdict we
    # are here to capture, not an error in the runner.
    set +e
    if [[ "$(cat "$dir/venue")" == "cluster_job" ]]; then
        uv run --no-sync python -m livespec_dev_tooling.gate_runner_delegate run --run-dir "$dir" -- "$@" \
            >>"$dir/output.log" 2>&1
    else
        run_gate_with_stall_bound "$dir" "$@"
    fi
    local code=$?
    set -e

    # core_after is captured BEFORE the watcher is stopped, so a write
    # landing in the teardown gap is still attributed rather than merely
    # detected. The watcher is then DRAINED, not killed: it completes any
    # record it is composing and runs one final pass before it exits, so an
    # attribution still in flight when the gate ended is kept rather than
    # discarded (livespec-dev-tooling-lndv2l).
    if [[ -n "$cfg" ]]; then
        capture_core_state "$cfg" "$dir/core_after" || true
    fi
    if [[ -n "$watch_pid" ]]; then
        open_idle_fd || true
        drain_watcher "$dir" "$watch_pid" || true
        close_idle_fd || true
    fi
    rm -f "$dir/config.ref" "$dir/config.stamp" 2>/dev/null || true
    if [[ -n "$cfg" ]]; then
        maybe_write_flip_marker "$dir" || true
    fi

    printf '%s\n' "$(timestamp)" >"$dir/finished_at"
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

# Count check targets observed in the captured output — direct evidence
# of work actually done, the thing that previously had to be
# reconstructed by hand to tell a kill from a refusal.
#
# The zero-target NOTE below is the operator's signal that a green
# verdict is NOT backed by evidence, and it only works while it stays
# rare. Print it on runs that DID produce full evidence and the reader
# learns to dismiss it — so the next genuinely vacuous pass, the case it
# exists for, reads as the same false alarm. Everything the probe widens
# to here is about keeping that warning honest, not about a nicer count.
#
# TWO emitters are in play across the fleet and BOTH must be read:
#
#   parallel dispatcher   ::: just <target> [ok|FAILED, wall: Ns]
#                         one line per COMPLETED target
#   serial check loop     ::: just <target>
#                         one line per STARTED target, no bracket suffix
#
# The probe used to require the bracket, so every green SERIAL aggregate
# reported zero targets and printed the NOTE directly beneath its own
# `All 79 targets passed.` (measured 2026-08-21 in livespec core).
# Matching `( \[|$)` after the target name reads both emitters while
# still excluding the `(skipped)` suffix both of them use.
#
# Both aggregates close with the same authoritative summary, and it is
# the only line reporting COMPLETION OF THE AGGREGATE rather than
# observation of one target, so it wins when present:
#
#   All <N> targets passed.   → N completed, 0 failed
#   Failed targets (<N>):     → N failed — the serial emitter's
#                               per-target lines carry no status, so
#                               this is its ONLY failure evidence
#
# Without a summary the count falls back to the per-target lines. On the
# serial emitter those mark STARTS, so a run killed mid-target counts
# one target that began and did not finish. That overstatement is
# bounded at one and cannot manufacture a pass: a run with no summary
# has no verdict, and `derive_state` reports it DIED_WITHOUT_VERDICT
# regardless of this count. It also cannot mask a vacuous run, which
# emits no `::: just` line at all.
#
# Every match runs against a CR-stripped copy. On the push path the gate
# runs under lefthook, which relays each hook command's output through a
# pty and replays it BUFFERED and CRLF-terminated; an end-anchored match
# against the raw bytes never fires there.

# Count CR-stripped capture lines matching an extended regex. `grep`
# exits 1 on no match — which errexit would read as a runner failure —
# so the non-match is absorbed and reported as the 0 that `grep -c`
# already printed.
count_log_lines() {
    local log="$1" pattern="$2" count
    count=$(tr -d '\r' <"$log" 2>/dev/null | grep -c -E "$pattern" || true)
    printf '%s' "${count:-0}"
}

# Echo the LAST aggregate-summary count matching `pattern` (an extended
# regex with one capturing group), or nothing when the capture carries
# no such summary.
summary_count() {
    local log="$1" pattern="$2"
    tr -d '\r' <"$log" 2>/dev/null | sed -n -E "s/$pattern/\\1/p" | tail -1
}

report_target_evidence() {
    local dir="$1"
    local log="$dir/output.log"
    local completed failed passed_summary failed_summary
    completed=$(count_log_lines "$log" '^::: just [^ ]+( \[|$)')
    failed=$(count_log_lines "$log" '^::: just .*\[FAILED')
    passed_summary=$(summary_count "$log" '^All ([0-9]+) targets passed\.$')
    failed_summary=$(summary_count "$log" '^Failed targets \(([0-9]+)\):$')
    if [[ -n "$passed_summary" ]]; then
        completed="$passed_summary"
        failed=0
    elif [[ -n "$failed_summary" ]]; then
        failed="$failed_summary"
    fi
    printf '  targets completed : %s (failed: %s)\n' "$completed" "$failed"
    if [[ "$completed" == "0" ]]; then
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
    dir="$(run_dir_for_read "$run_id")" || {
        unknown_run "$run_id"
        return "$EX_USAGE"
    }
    state="$(derive_state "$dir")"

    if [[ "$state" == "UNKNOWN_RUN" ]]; then
        unknown_run "$run_id"
        return "$EX_USAGE"
    fi

    printf '=== gate run %s ===\n' "$run_id"
    printf '  state             : %s\n' "$state"
    printf '  label             : %s\n' "$(cat "$dir/label" 2>/dev/null || echo '?')"
    printf '  venue             : %s (%s)\n' \
        "$(cat "$dir/venue" 2>/dev/null || echo '?')" \
        "$(cat "$dir/venue_reason" 2>/dev/null || echo '?')"
    [[ -f "$dir/job_name" ]] && printf '  Job name          : %s\n' "$(cat "$dir/job_name")"
    [[ -f "$dir/tree_hash" ]] && printf '  tree hash         : %s\n' "$(cat "$dir/tree_hash")"
    printf '  command           : %s\n' "$(tr '\n' ' ' <"$dir/command" 2>/dev/null || echo '?')"
    printf '  worktree          : %s\n' "$(cat "$dir/worktree" 2>/dev/null || echo '?')"
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
    # Last, so it is the last thing read — and unconditional on state,
    # because a flip is orthogonal to the verdict and must be seen even
    # under a PASSED run.
    if [[ -f "$dir/CORE_BARE_FLIP" ]]; then
        printf '\n'
        printf '  ############################################################\n'
        cat "$dir/CORE_BARE_FLIP"
        printf '  ############################################################\n'
    fi
    return "$(state_exit_code "$dir" "$state")"
}

cmd_wait() {
    [[ $# -ge 1 ]] || usage
    local run_id="$1" dir
    dir="$(run_dir_for_read "$run_id")" || {
        unknown_run "$run_id"
        return "$EX_USAGE"
    }
    open_idle_fd
    while true; do
        derive_state_into "$dir"
        [[ "$STATE" == "RUNNING" ]] || break
        idle_sleep "$POLL_INTERVAL_S"
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
