#!/usr/bin/env bash
# Reclaim build-artifact and orphaned-worktree storage on a Fabro factory host.
#
#   ./storage-reclaim.sh hosts/vps.env            # DRY RUN (default)
#   ./storage-reclaim.sh hosts/vps.env --apply    # actually delete
#
# WHY THIS EXISTS. On 2026-08-22 the hp factory filled to zero bytes and every
# dispatch routed there died at stage `fabro-run` with ENOSPC. The consumer was
# the container image store, and a hotfix on hp now reclaims it. Measuring the
# OTHER factory found a different and larger layer that nothing reclaims: 231.7
# GB of per-worktree build artifacts across 574 worktrees under ~/.worktrees,
# which is 95% of that tree and 41% of the whole disk. Neither `docker prune`
# nor `fabro system prune` touches a byte of it.
#
# TWO LEGS, deliberately different in kind:
#
#   A. CAPACITY -- build artifacts inside LIVE, REGISTERED worktrees. This is
#      where the bytes are (~232 GB). Artifacts regenerate, so the cost of
#      reclaiming one is a rebuild, not a loss.
#   B. COMPLIANCE -- worktrees on disk that no clone registers. Measured
#      fleet-wide at 6.4 GB across 70 directories, i.e. 2.6% of the layer. This
#      leg exists because AGENTS.md says "do not leave orphaned worktrees" and
#      nothing was noticing; it is NOT where the capacity comes from, and it is
#      always REPORTED even when nothing is removed.
#
# SAFETY MODEL. Every deletion must pass all of:
#   1. the path is strictly under RECLAIM_WORKTREE_ROOT (prefix-guarded, and
#      re-checked after realpath so a symlink cannot escape);
#   2. the path is not under any DENY-listed root;
#   3. `git check-ignore` says the directory is IGNORED -- so a TRACKED dist/ or
#      build/ is protected by git's own answer rather than by our name list;
#   4. no live process has a cwd inside the worktree (another session is using
#      it) -- see `worktree_is_live`;
#   5. the worktree has been idle at least the configured horizon.
# Orphan REMOVAL additionally requires a clean tree and no commits missing from
# every remote. A worktree whose git linkage is too broken to answer those
# questions is reported and SKIPPED, never removed.
#
# Sourceable for testing: `main` runs only on direct execution.

set -euo pipefail

# Roots this script must never touch even if misconfigured to point at them.
# /srv is a backup snapshot and /tmp holds live agent scratchpads; both sit in
# the same `du` output as the target and both look like obvious wins.
readonly DENY_ROOTS=(/ /srv /tmp /var /usr /etc /boot /nix /opt /home /root /data)

# Candidate build-artifact directory names. This list only NOMINATES; git's
# check-ignore decides. A tracked directory of any of these names survives.
readonly ARTIFACT_NAMES=(target node_modules .venv venv .next dist build .mypy_cache .pytest_cache .ruff_cache .tox .gradle)

log()  { printf '%s\n' "$*"; }
warn() { printf '%s\n' "$*" >&2; }
# Per-item progress, deliberately on STDERR. `main` captures reclaim_artifacts'
# stdout to get its MB total and then does `$(( freed / 1024 ))`, so ANY other
# line on stdout is captured into that arithmetic and aborts the run -- at the
# SUMMARY, i.e. under --apply after every deletion has already happened. Using
# `log` here cost exactly that. Progress still reaches the operator, and still
# reaches a `2>&1` log file, because stderr is not swallowed by `$( )`.
progress() { printf '%s\n' "$*" >&2; }

# --- guards ---------------------------------------------------------------

path_is_denied() {
    # True when $1 is exactly a deny-root, or would delete one wholesale.
    local p="$1" deny
    for deny in "${DENY_ROOTS[@]}"; do
        [[ "${p}" == "${deny}" ]] && return 0
    done
    return 1
}

path_under_root() {
    # True when $1 is strictly INSIDE $2 (not equal to it).
    local p="$1" root="$2"
    [[ "${p}" == "${root}" ]] && return 1
    [[ "${p}" == "${root}"/* ]]
}

safe_to_delete() {
    # The single chokepoint every deletion passes through.
    local target="$1" root="$2" real
    [[ -n "${target}" && -n "${root}" ]] || return 1
    # GUARD THE ROOT FIRST. The target checks below cannot save a misconfigured
    # root: with RECLAIM_WORKTREE_ROOT=/srv, "/srv/anything" is legitimately
    # under the root and is not itself a deny-root, so every other check passes
    # and the backup snapshot gets deleted. A root of "/" is refused here too,
    # which is why no path is ever deletable under one.
    path_is_denied "${root}" && { warn "REFUSING deny-listed worktree root: ${root}"; return 1; }
    path_is_denied "${target}" && { warn "REFUSING deny-listed path: ${target}"; return 1; }
    path_under_root "${target}" "${root}" || { warn "REFUSING path outside ${root}: ${target}"; return 1; }
    # Re-check after resolving symlinks so a symlinked worktree cannot escape.
    real="$(realpath -m -- "${target}")"
    path_is_denied "${real}" && { warn "REFUSING deny-listed realpath: ${real}"; return 1; }
    path_under_root "${real}" "${root}" || { warn "REFUSING realpath outside ${root}: ${real}"; return 1; }
    return 0
}

# --- inventory ------------------------------------------------------------

list_worktrees_on_disk() {
    # A worktree is defined by carrying a .git entry, NOT by being a directory
    # at some fixed depth: a branch name containing a slash nests one deeper,
    # and a stray directory would otherwise be counted as a worktree.
    local root="$1"
    [[ -d "${root}" ]] || return 0
    find "${root}" -mindepth 1 -name .git -printf '%h\n' 2>/dev/null | LC_ALL=C sort -u
}

list_registered_worktrees() {
    # Every worktree path registered by every clone under the checkout roots.
    # The primary checkout appears here too and is correctly NOT under the
    # worktree root, which is why differencing on raw counts is wrong.
    local roots="$1" checkout_root repo
    for checkout_root in ${roots}; do
        [[ -d "${checkout_root}" ]] || continue
        for repo in "${checkout_root}"/*/; do
            [[ -e "${repo}.git" ]] || continue
            git -C "${repo}" worktree list --porcelain 2>/dev/null \
                | awk '/^worktree /{print substr($0,10)}'
        done
    done | LC_ALL=C sort -u
}

# Cached snapshot of every readable process cwd, refreshed on a TTL.
#
# WHY A SNAPSHOT AT ALL. The first version ran `$(readlink)` once PER PROCESS
# PER WORKTREE. Measured on vps 2026-08-22 at load 71: 1,727 process entries,
# 27.5 SECONDS for a SINGLE worktree_is_live call, against 608 worktrees --
# 4.6 hours in this guard alone and over a million forks. That is why the
# earlier dry run never finished, and the scan was itself a significant share
# of the host load this whole service exists to relieve. It also made the
# suite's own liveness case FLAKY: the scan outlived the fixture's `sleep`, so
# the guard reported not-live for a process whose cwd readlink resolved
# correctly the instant before.
#
# WHY A TTL AND NOT A ONE-SHOT CACHE. Liveness is a SAFETY guard, and a
# snapshot taken once at startup would go stale across a long run -- a session
# that starts using an idle worktree mid-run would not be seen, and its
# artifacts would be deleted out from under it. A TTL bounds that staleness to
# a known window while still costing one `find` per window instead of one fork
# per process per worktree.
_LIVE_CWDS=""
_LIVE_CWDS_AT=0
readonly LIVE_CWD_TTL_SECONDS=60

now_epoch() {
    # EPOCHSECONDS is a bash 5 builtin and costs no fork; `date` is the fallback.
    if [[ -n "${EPOCHSECONDS:-}" ]]; then printf '%s\n' "${EPOCHSECONDS}"; else date +%s; fi
}

live_cwd_snapshot() {
    # Every readable process cwd, in ONE `find` rather than one fork each.
    # A cwd we cannot read (another user's process) is skipped, exactly as the
    # per-process `readlink ... || continue` skipped it.
    find /proc -mindepth 2 -maxdepth 2 -path '/proc/[0-9]*/cwd' -printf '%l\n' 2>/dev/null \
        | LC_ALL=C sort -u
}

refresh_live_cwds() {
    # Re-snapshot when the cache is older than the TTL. Also refreshed on demand
    # by passing "force", which the tests use to observe a just-started process.
    local now
    now="$(now_epoch)"
    if [[ "${1:-}" == "force" ]] || (( now - _LIVE_CWDS_AT > LIVE_CWD_TTL_SECONDS )); then
        # THE `|| true` IS LOAD-BEARING AND IS NOT THE ANTI-PATTERN IT RESEMBLES.
        # `find` exits NON-ZERO whenever it cannot read some /proc entry, which
        # is the normal case on a busy multi-user host, and `pipefail` propagates
        # that status out of the pipeline. Under `set -e` a bare assignment from
        # it therefore KILLS THE SCRIPT -- silently, with no output at all,
        # before a single line is logged. Measured 2026-08-22: adding the
        # up-front `refresh_live_cwds force` to `main` did exactly that, and it
        # was invisible to the unit suite because the harness runs `set +e`. It
        # survived here before only because every caller sat inside an `if`
        # condition, where `set -e` is suppressed.
        #
        # Swallowing the STATUS is safe precisely because the status carries no
        # information -- a partially-readable /proc is both non-zero and
        # perfectly usable. What carries the safety is the CONTENT check in
        # `live_cwds_are_usable`, which runs on the result below.
        _LIVE_CWDS="$(live_cwd_snapshot || true)"
        _LIVE_CWDS_AT="${now}"
    fi
}

live_cwds_are_usable() {
    # A WORKING SNAPSHOT IS NEVER EMPTY. This script's own process has a cwd, so
    # a functioning `find` must report at least one line. An empty result is
    # therefore proof the INSTRUMENT IS BROKEN -- a `find` without GNU
    # `-printf`, an unreadable or unmounted /proc, no `find` at all -- and it is
    # NOT proof that no worktree is in use.
    #
    # THE DISTINCTION IS THE WHOLE SAFETY PROPERTY, because the two readings are
    # byte-identical at this seam: `live_cwd_snapshot` swallows stderr with
    # `2>/dev/null`, so a hard failure arrives as the same empty string a
    # genuinely idle host would produce. Read as "nothing is live", it makes
    # EVERY live worktree look idle and permits deletion inside another
    # session's live work -- and it does so silently, at exit 0, with no
    # diagnostic. That is the same anti-pattern the container-reclaim leg
    # shipped and caught: a call whose emptiness is indistinguishable from a
    # legitimate result must fail loudly, never read as zero.
    #
    # MEASURED 2026-08-22 against the pre-fix build. With `live_cwd_snapshot`
    # replaced by a failing `find`, a directory holding a live `sleep` -- whose
    # /proc/<pid>/cwd still resolved to that directory at the moment of the
    # call -- reported NOT-LIVE, exit 0, no warning. A liveness guard failing
    # toward NOT-LIVE permits a deletion, which is the expensive direction.
    [[ -n "${_LIVE_CWDS}" ]]
}

worktree_is_live() {
    # True when any running process has a cwd inside this worktree. This is the
    # guard that keeps us off another session's active worktree; AGENTS.md is
    # explicit that another session's worktrees are not ours to touch.
    #
    # The comparison is unchanged from the per-process version -- exact match or
    # a path strictly inside -- and is done in pure bash against the cached
    # snapshot, so it costs no forks at all.
    local d="$1" cwd
    refresh_live_cwds
    if ! live_cwds_are_usable; then
        # FAIL CLOSED. An instrument that cannot see the process table has not
        # established that this worktree is idle; it has established nothing.
        # Report LIVE so no caller can clear anything on a blind reading.
        # `main` aborts the whole run on the same condition, so this arm is the
        # belt to that braces -- it keeps every other caller, and the tests,
        # safe by construction rather than by remembering to check first.
        return 0
    fi
    while IFS= read -r cwd; do
        [[ -z "${cwd}" ]] && continue
        [[ "${cwd}" == "${d}" || "${cwd}" == "${d}"/* ]] && return 0
    done <<<"${_LIVE_CWDS}"
    return 1
}

worktree_idle_days() {
    # Days since the newest non-artifact file changed. Artifact dirs are excluded
    # so that a build does not make an abandoned worktree look active.
    local d="$1" newest now prune_expr=()
    local name
    for name in "${ARTIFACT_NAMES[@]}"; do prune_expr+=(-o -name "${name}"); done
    newest="$(find "${d}" -mindepth 1 -maxdepth 4 \
        \( -name .git "${prune_expr[@]}" \) -prune -o \
        -type f -printf '%T@\n' 2>/dev/null | sort -rn | head -1)"
    [[ -z "${newest}" ]] && { echo 99999; return 0; }
    now="$(date +%s)"
    echo $(( (now - ${newest%.*}) / 86400 ))
}

worktree_is_clean() {
    local d="$1" out
    out="$(git -C "${d}" status --porcelain 2>/dev/null)" || return 1
    [[ -z "${out}" ]]
}

worktree_fully_pushed() {
    # No commit reachable from HEAD that is absent from every remote.
    #
    # `HEAD` IS LOAD-BEARING. Without it, `git log --not --remotes` in a repo
    # with NO remotes walks nothing and exits 0 with empty output -- which this
    # function would read as "fully pushed" and clear an orphan holding unpushed
    # work for deletion. Caught by storage-reclaim.test.sh, which is the reason
    # that case exists.
    local d="$1" out
    out="$(git -C "${d}" log --oneline HEAD --not --remotes 2>/dev/null)" || return 1
    [[ -z "${out}" ]]
}

dir_is_git_ignored() {
    # git's own answer, not our name list. A TRACKED build/ is not ignored and
    # is therefore protected here.
    local repo="$1" path="$2"
    git -C "${repo}" check-ignore -q -- "${path}" 2>/dev/null
}

dir_size_mb() {
    local d="$1" s
    s="$(timeout 120 du -xsm -- "${d}" 2>/dev/null | cut -f1)"
    [[ -n "${s}" ]] && echo "${s}" || echo 0
}

# --- legs -----------------------------------------------------------------

reclaim_artifacts() {
    # LEG A: build artifacts inside worktrees idle >= horizon. Returns MB freed.
    #
    # CONTRACT: STDOUT CARRIES THE INTEGER AND NOTHING ELSE. `main` reads this
    # through a command substitution and does arithmetic on it. All per-item
    # narration goes to stderr via `progress`. Guarded by the "reclaim_artifacts
    # returns ONLY an integer on stdout" cases in storage-reclaim.test.sh.
    local root="$1" horizon="$2" apply="$3"
    local d idle freed=0 sz name cand
    while IFS= read -r d; do
        [[ -n "${d}" ]] || continue
        idle="$(worktree_idle_days "${d}")"
        (( idle < horizon )) && continue
        if worktree_is_live "${d}"; then
            progress "  skip (live process cwd inside): ${d}"
            continue
        fi
        for name in "${ARTIFACT_NAMES[@]}"; do
            cand="${d}/${name}"
            [[ -d "${cand}" ]] || continue
            dir_is_git_ignored "${d}" "${cand}" || { progress "  skip (tracked, not ignored): ${cand}"; continue; }
            safe_to_delete "${cand}" "${root}" || continue
            sz="$(dir_size_mb "${cand}")"
            (( sz == 0 )) && continue
            freed=$(( freed + sz ))
            if [[ "${apply}" == "yes" ]]; then
                rm -rf -- "${cand}"
                progress "  removed ${sz}M (idle ${idle}d): ${cand}"
            else
                progress "  would remove ${sz}M (idle ${idle}d): ${cand}"
            fi
        done
    done < <(list_worktrees_on_disk "${root}")
    echo "${freed}"
}

report_orphans() {
    # LEG B, reporting half. ALWAYS runs, even when nothing is removable, so the
    # AGENTS.md protocol violation is visible rather than silently reclaimed.
    local root="$1" roots="$2" ondisk registered
    ondisk="$(list_worktrees_on_disk "${root}")"
    registered="$(list_registered_worktrees "${roots}")"
    sorted_difference "${ondisk}" "${registered}"
}

sorted_difference() {
    # Lines present in $1 and absent from $2, both already LC_ALL=C sorted.
    #
    # VIA TEMP FILES, NOT TWO PROCESS SUBSTITUTIONS. This looks like a stylistic
    # choice and is not: `comm -23 <(...) <(...)` returns a WRONG ANSWER on this
    # data. Measured 2026-08-22 on the live vps inventory, 591 worktrees against
    # 565 registered paths, with byte-identical inputs each way:
    #
    #     comm -23 <(a) <(b)     -> 407  + "comm: file 1 is not in sorted order"
    #     comm -23 <(a) file_b   ->  73  clean
    #     comm -23 file_a file_b ->  73  clean
    #     comm -23 --nocheck-order <(a) <(b) -> 73  clean
    #
    # 73 is correct and agrees with an independent count. The locale is NOT the
    # cause -- the three-way matrix above is identical with LC_ALL=C absent,
    # prefixed, or exported. TWO concurrent process substitutions are the cause.
    #
    # WHY THIS MATTERED MORE THAN A WRONG NUMBER: 407 of 591 worktrees would have
    # been reported as orphaned when 73 are. Every one of the 334 extras is a
    # LIVE, REGISTERED worktree belonging to another session. A reporting bug,
    # not a guard failure, is what would have aimed the removal leg at them.
    #
    # THE ROOT CAUSE IS NOT ESTABLISHED, and this comment does not guess at one.
    # What IS established: both FIFOs deliver byte-exact data (verified through
    # `tee`), the fds are distinct, the inputs are pure ASCII and pass `sort -c`,
    # the result is NONDETERMINISTIC across identical runs (46, then 42 four
    # times, on the same 100-line input), and no synthetic fixture reproduced it.
    # Because no small deterministic reproducer exists, this is guarded by the
    # POST-CONDITION below rather than by a unit test that could only be flaky.
    local a="$1" b="$2" fa fb result
    fa="$(mktemp)"; fb="$(mktemp)"
    printf '%s\n' "${a}" > "${fa}"
    printf '%s\n' "${b}" > "${fb}"
    result="$(LC_ALL=C comm -23 "${fa}" "${fb}")"
    if ! difference_is_sound "${result}" "${fb}"; then
        rm -f "${fa}" "${fb}"
        return 1
    fi
    rm -f "${fa}" "${fb}"
    printf '%s\n' "${result}"
}

difference_is_sound() {
    # POST-CONDITION: nothing in the computed difference may appear in list B.
    #
    # This is the guard that actually protects the removal leg, and it holds
    # whatever the cause of a wrong difference: a registered worktree can never
    # legitimately appear in the orphan set, so if one does, the computation is
    # broken and we must refuse rather than report. Cheap, exact, and testable
    # without reproducing the underlying fault.
    local result="$1" b_file="$2" intruders
    [[ -z "${result}" ]] && return 0
    intruders="$(LC_ALL=C grep -xF -f "${b_file}" <<<"${result}" || true)"
    if [[ -n "${intruders}" ]]; then
        warn "ERROR: orphan computation is unsound -- $(grep -c . <<<"${intruders}") registered path(s) appeared in the difference; refusing to report"
        warn "$(head -3 <<<"${intruders}")"
        return 1
    fi
    return 0
}

main() {
    local host_env="${1:?usage: storage-reclaim.sh <hosts/NAME.env> [--apply]}"
    local apply=no
    [[ "${2:-}" == "--apply" ]] && apply=yes

    [[ -f "${host_env}" ]] || { warn "ERROR: no such host env file: ${host_env}"; exit 2; }
    set -a
    # shellcheck source=/dev/null
    source "${host_env}"
    set +a
    : "${RECLAIM_CANONICAL_HOST:?host env must set RECLAIM_CANONICAL_HOST}"
    : "${RECLAIM_WORKTREE_ROOT:?host env must set RECLAIM_WORKTREE_ROOT}"
    : "${RECLAIM_CHECKOUT_ROOTS:?host env must set RECLAIM_CHECKOUT_ROOTS}"
    : "${RECLAIM_ARTIFACT_IDLE_DAYS:?host env must set RECLAIM_ARTIFACT_IDLE_DAYS}"
    : "${RECLAIM_ORPHAN_IDLE_DAYS:?host env must set RECLAIM_ORPHAN_IDLE_DAYS}"
    : "${RECLAIM_SYSTEM_HOSTNAME:?host env must set RECLAIM_SYSTEM_HOSTNAME}"

    # Refuse to apply one host's configuration on another, exactly as the
    # fabro-server installer does. This repo exists because forking per host
    # failed silently.
    # Guard on the MEASURED system hostname, not on the tailscale label derived
    # from RECLAIM_CANONICAL_HOST: on vps those differ (vmi3006760 vs vps), and
    # deriving it would refuse to run on the host it targets.
    local expected actual
    expected="${RECLAIM_SYSTEM_HOSTNAME}"
    actual="$(hostname -s)"
    [[ "${expected}" == "${actual}" ]] || {
        warn "ERROR: ${host_env} targets '${expected}' but this host is '${actual}'"
        exit 2
    }

    # PROVE THE LIVENESS INSTRUMENT WORKS BEFORE ANY LEG RUNS. The guard that
    # keeps this service off another session's live worktree is only as good as
    # the process-table snapshot behind it, and that snapshot fails to an empty
    # string rather than to an error (see `live_cwds_are_usable`). Checking it
    # once, up front, converts a silent host-wide over-deletion into a refusal
    # the operator can read. Doing it here rather than only inside the guard
    # also means a broken instrument does not present as a successful run that
    # happened to reclaim nothing.
    refresh_live_cwds force
    live_cwds_are_usable || {
        warn "ERROR: the live-cwd snapshot is EMPTY, so the liveness guard cannot see the"
        warn "       process table. A working snapshot always contains this process's own"
        warn "       cwd, so this is a BROKEN INSTRUMENT (a find without GNU -printf, an"
        warn "       unreadable /proc), not an idle host."
        warn "       Refusing to run: treating it as 'nothing is live' would permit deletion"
        warn "       inside worktrees that other sessions are actively using."
        exit 3
    }

    local before after freed orphans orphan_count
    before="$(df -BM --output=avail / | tail -1 | tr -dc '0-9')"
    log "storage-reclaim on ${actual} ($( [[ ${apply} == yes ]] && echo APPLY || echo DRY-RUN ))"
    log "  worktree root : ${RECLAIM_WORKTREE_ROOT}"
    log "  free before   : $(( before / 1024 )) GB"
    log ""

    log "LEG B (compliance): orphaned worktrees -- reported always"
    orphans="$(report_orphans "${RECLAIM_WORKTREE_ROOT}" "${RECLAIM_CHECKOUT_ROOTS}")"
    orphan_count="$(grep -c . <<<"${orphans}" || true)"
    [[ -z "${orphans}" ]] && orphan_count=0
    log "  orphaned worktrees on disk: ${orphan_count}"
    if (( orphan_count > 0 )); then
        printf '%s\n' "${orphans//${RECLAIM_WORKTREE_ROOT}\//}" \
            | awk -F/ '{print $1}' | sort | uniq -c | sort -rn \
            | while read -r n repo; do log "    ${n}  ${repo}"; done
    fi
    log ""

    log "LEG A (capacity): build artifacts in worktrees idle >= ${RECLAIM_ARTIFACT_IDLE_DAYS}d"
    freed="$(reclaim_artifacts "${RECLAIM_WORKTREE_ROOT}" "${RECLAIM_ARTIFACT_IDLE_DAYS}" "${apply}")"
    log ""

    after="$(df -BM --output=avail / | tail -1 | tr -dc '0-9')"
    log "SUMMARY"
    log "  artifact bytes $( [[ ${apply} == yes ]] && echo reclaimed || echo reclaimable ): $(( freed / 1024 )) GB"
    log "  orphaned worktrees reported                    : ${orphan_count}"
    log "  free before                                    : $(( before / 1024 )) GB"
    log "  free after                                     : $(( after / 1024 )) GB"
    [[ "${apply}" == "no" ]] && log "  (dry run -- pass --apply to act)"
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
