#!/usr/bin/env bash
# ci-runner-supervisor.sh — ephemeral self-hosted-runner supervisor for the
# thewoolleyman-ci-runners GitHub App. General fleet: maintains a small pool of
# ephemeral runners PER repo in CI_RUNNER_REPOS (personal accounts only support
# repo-level runners, so pools are per-repo).
#
# Runs as its OWN low-priv user (ci-sup), the only account that can read the App
# private key (from the github-ci-runners 1Password environment, injected ONLY
# into this service). Each cycle, per (repo, slot):
#   1. mint a fresh JIT config (no re-registerable token) via the App;
#   2. hand ONLY that JIT config to a freshly-launched ephemeral runner running
#      as ci-runner (via a narrow polkit-granted `systemctl start runner@<id>`);
#   3. wait for that runner unit to finish its single job (auto-deregisters);
#   4. relaunch the slot.
# The App key never crosses to ci-runner or the job container.
#
# Secrets (github-ci-runners 1Password environment, supervisor-only) arrive in the
# env because the WRAPPER injects them:
#   GITHUB_APP_ID_CI_RUNNER, GITHUB_APP_INSTALLATION_ID_CI_RUNNER,
#   GITHUB_PRIVATE_KEY_CI_RUNNER (real-newline PEM).
#
# CONFIG ARRIVES AS ARGUMENTS, NOT ENVIRONMENT — this is load-bearing.
# The credential wrapper this script runs behind scrubs the environment (`env -i`),
# so a systemd `Environment=CI_RUNNER_SLOTS_PER_REPO=18` in the unit NEVER reaches
# this process: the wrapper wipes it and the script silently falls back to its
# default. That is exactly what happened (2026-07-14) — the unit had carried
# Environment= lines since Phase 0 and every one of them was being discarded. It
# went unnoticed only because the repo/label defaults happened to equal the unit's
# values; the slot count did NOT, so the pool stayed stuck at ONE runner while the
# unit claimed 18. Arguments survive the scrub (they are "$@"); environment does not.
#
# Usage: ci-runner-supervisor.sh [--repos "<owner/repo ...>"] [--slots N]
#                                [--labels a,b] [--work DIR] [--mint PATH]
#
# PER-REPO SLOT OVERRIDE: a --repos entry may carry an optional ":N" suffix
# (e.g. "owner/repo-a:9 owner/repo-b:6 owner/repo-c") to run that repo with N
# slots instead of the --slots default. A repo listed without a suffix still
# uses --slots (or its default of 1). This lets one supervisor instance serve
# multiple repos proportioned to their own CI matrix width, instead of every
# repo getting the same flat slot count regardless of size.
set -euo pipefail

# wedge-guard.sh: mid-job liveness backstop (livespec-s43svm.12). A runner
# that passes startup and gets assigned a job can still wedge INSIDE the
# custom container-hook binary (Initialize/Stop containers hanging for
# minutes under host-wide IO contention); without this, the wait loop below
# has no notion of "stuck" and a wedged unit silently holds its slot forever
# since systemd reports it ACTIVE the whole time. Sourced (not exec'd) so its
# CI_RUNNER_WEDGE_* overrides and functions are visible to run_one below.
# shellcheck source=./wedge-guard.sh
. "$(cd "$(dirname "$0")" && pwd)/wedge-guard.sh"

REPOS="thewoolleyman/livespec"
SLOTS_PER_REPO=1
LABELS_CSV="self-hosted,local-ci"
# Parsed for CLI compatibility with deployed units; per-slot runner dirs own actual work paths.
export WORK_FOLDER="/home/ci-runner/_work"
MINT="/usr/local/lib/ci-runner/mint-jitconfig.sh"

while [ $# -gt 0 ]; do
  case "$1" in
    --repos)  REPOS="$2"; shift 2;;
    --slots)  SLOTS_PER_REPO="$2"; shift 2;;
    --labels) LABELS_CSV="$2"; shift 2;;
    --work)   WORK_FOLDER="$2"; shift 2;;
    --mint)   MINT="$2"; shift 2;;
    *) echo "ci-runner-supervisor: unknown argument: $1" >&2; exit 2;;
  esac
done
# Resolve each --repos entry's ACTUAL slot count (its own ":N" suffix, or the
# --slots default) up front, once, so the startup log line — the sole source
# of truth per this script's own trap-5 discipline (never the unit file) —
# shows what will really run rather than the raw, possibly-ambiguous input.
resolved_repos=""
for repo_spec in $REPOS; do
  repo="${repo_spec%%:*}"
  if [ "$repo_spec" = "$repo" ]; then
    resolved_slots="$SLOTS_PER_REPO"
  else
    resolved_slots="${repo_spec##*:}"
  fi
  resolved_repos="${resolved_repos}${repo}:${resolved_slots} "
done
printf 'ci-runner-supervisor: repos=[%s] labels=%s\n' "${resolved_repos% }" "$LABELS_CSV"
JIT_DIR=/run/ci-runner                 # tmpfs, ci-runner-readable one-shot handoff

: "${GITHUB_APP_ID_CI_RUNNER:?}"; : "${GITHUB_APP_INSTALLATION_ID_CI_RUNNER:?}"
: "${GITHUB_PRIVATE_KEY_CI_RUNNER:?}"

# JSON array form of the labels for the JIT mint API.
labels_json="$(printf '%s' "$LABELS_CSV" | jq -R 'split(",")')"

run_one() {
  local repo="$1" slot="$2" name jit unit jf reposlug inst work
  reposlug="${repo//\//-}"
  # TWO DISTINCT IDENTIFIERS, deliberately:
  #   inst — STABLE per (repo, slot). It names the systemd unit instance AND the
  #          runner's own directory, which must be per-runner: the Actions runner
  #          materializes its JIT config to .runner/.credentials in its root dir,
  #          so N runners sharing one dir overwrite each other's session and loop
  #          on "√ Connected to GitHub" forever while jobs stall queued.
  #   name — UNIQUE per mint. It is the GitHub-side runner name inside the JIT
  #          config; each ephemeral runner is a fresh registration.
  inst="${reposlug}-${slot}"
  # GitHub rejects a runner name >64 chars ("A valid runner name is 64 characters
  # or less"). The org/owner prefix is REDUNDANT in the name — the runner is already
  # registered to a specific repo — so drop it here and use the repo name without
  # owner. This keeps the longest fleet repo
  # (thewoolleyman/livespec-orchestrator-beads-fabro) comfortably under the cap;
  # inst above stays org-qualified because it names the systemd unit + runner dir.
  name="ci-${repo##*/}-${slot}-$$-${RANDOM}"
  work="/home/ci-runner/runners/${inst}/_work"
  jit="$(APP_ID="$GITHUB_APP_ID_CI_RUNNER" \
        INSTALLATION_ID="$GITHUB_APP_INSTALLATION_ID_CI_RUNNER" \
        APP_KEY_PEM="$GITHUB_PRIVATE_KEY_CI_RUNNER" \
        REPO="$repo" RUNNER_NAME="$name" LABELS="$labels_json" WORK_FOLDER="$work" \
        "$MINT")"
  # JIT_DIR is the supervisor unit's RuntimeDirectory (0700 ci-sup). The runner
  # unit's LoadCredential= reads the file as root and stages it into the runner's
  # $CREDENTIALS_DIRECTORY (ci-runner-only) — so no cross-user chown is needed and
  # ci-runner never has raw access to the JIT file here.
  mkdir -p "$JIT_DIR"
  jf="$JIT_DIR/${inst}.jit"
  ( umask 0177; printf '%s' "$jit" > "$jf" )
  unit="runner@${inst}.service"
  systemctl start "$unit"                 # polkit-granted for runner@*.service only
  # wedge-guard: on every poll, also check whether this unit is wedged inside
  # the dockershim binary past the bounded threshold; if so, force-stop it
  # here. `is-active` then goes false on the NEXT iteration (systemctl stop
  # already completed synchronously) and the loop exits normally, so run_one
  # returns as it always did -- the caller's existing `while :; do run_one
  # ... || sleep 10; done` re-mints and restarts the slot at the normal paced
  # rate. This function never starts a replacement itself.
  while systemctl is-active --quiet "$unit"; do
    wedge_guard_check_and_recycle "$unit" || true
    sleep 5
  done
  rm -f "$jf"
}

for repo_spec in $REPOS; do
  repo="${repo_spec%%:*}"
  if [ "$repo_spec" = "$repo" ]; then
    repo_slots="$SLOTS_PER_REPO"
  else
    repo_slots="${repo_spec##*:}"
  fi
  for slot in $(seq 1 "$repo_slots"); do
    ( while :; do run_one "$repo" "$slot" || sleep 10; done ) &
  done
done
wait
