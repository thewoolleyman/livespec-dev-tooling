#!/usr/bin/env bash
# gate-runner-supervisor.sh — ON-DEMAND, TRIGGER-VERIFIED privileged runner minter.
#
# The contained CI lane (ci-runner/) cannot run the orchestrator's live
# golden-master gate: that gate needs Docker (root-equivalent here), the host
# Codex credential, the host fabro binary, and the operator's 1Password secrets —
# every one of which the containment deliberately denies. So the gate gets a
# PRIVILEGED runner, and the containment moves from "confine the runner" to
# "control what may reach it".
#
# NO privileged runner idles. Nothing is registered until a QUEUED run passes
# EVERY trust check (see select_trusted_run_id): it must be the gate workflow,
# on a write-access-gated event, on master. Then ONE single-use JIT runner is
# minted; it takes that one job and auto-deregisters. A fork PR's run carries
# event == "pull_request", never matches, and gets no runner — a discrimination
# the runner LABEL alone cannot make, since a label is merely a request any
# workflow may write.
#
# Runs as ci-sup (the only account that reads the App private key), under the
# github-ci-runners 1Password environment. The App key never crosses to the runner.
#
# Modes:
#   (default)          watch loop
#   --select-trusted   read a workflow-runs JSON payload on stdin, print the id of
#                      the first trusted run (or nothing). The testable seam the
#                      trigger-surface exit tests drive.
set -euo pipefail

GATE_REPO="${GATE_RUNNER_REPO:-thewoolleyman/livespec-orchestrator-beads-fabro}"
GATE_WORKFLOW="${GATE_RUNNER_WORKFLOW:-.github/workflows/acceptance-live-golden-master.yml}"
GATE_BRANCH="${GATE_RUNNER_BRANCH:-master}"
GATE_LABELS="${GATE_RUNNER_LABELS:-self-hosted,livespec-orchestrator}"
POLL_SECONDS="${GATE_RUNNER_POLL_SECONDS:-20}"
WORK_FOLDER="${GATE_RUNNER_WORK:-/home/ubuntu/gate-runner/_work}"
MINT="${GATE_RUNNER_MINT:-/usr/local/lib/ci-runner/mint-jitconfig.sh}"
TOKEN_HELPER="${GATE_RUNNER_TOKEN_HELPER:-/usr/local/lib/ci-runner/app-installation-token.sh}"
JIT_DIR="${GATE_RUNNER_JIT_DIR:-/run/gate-runner}"   # RuntimeDirectory, 0700 ci-sup

log() { printf '%s gate-runner-supervisor: %s\n' "$(date -Is)" "$*"; }

# --- THE TRUST BOUNDARY -------------------------------------------------------
# Reads a GitHub `GET /actions/runs` payload on stdin; prints the id of the first
# run that is unambiguously operator-authorized, or nothing. Every condition is
# load-bearing; dropping any one of them would let an untrusted workflow obtain a
# privileged runner.
select_trusted_run_id() {
  jq -r --arg path "$GATE_WORKFLOW" --arg branch "$GATE_BRANCH" '
    [ .workflow_runs[]?
      # 1. The gate workflow ONLY — no other workflow in the repo gets privilege.
      | select(.path == $path)
      # 2. Write-access-gated events ONLY. repository_dispatch needs a token with
      #    write; workflow_dispatch needs an actor with write. A fork PR is
      #    event == "pull_request" and is excluded here.
      | select(.event == "repository_dispatch" or .event == "workflow_dispatch")
      # 3. Reviewed, merged code ONLY (repository_dispatch always uses the default
      #    branch; this pins the workflow_dispatch path to it too).
      | select(.head_branch == $branch)
      | .id
    ] | first // empty'
}

if [ "${1:-}" = "--select-trusted" ]; then
  select_trusted_run_id
  exit 0
fi

: "${GITHUB_APP_ID_CI_RUNNER:?}"; : "${GITHUB_APP_INSTALLATION_ID_CI_RUNNER:?}"
: "${GITHUB_PRIVATE_KEY_CI_RUNNER:?}"

labels_json="$(printf '%s' "$GATE_LABELS" | jq -R 'split(",")')"

# --- poll credential (installation token, refreshed well inside its ~1h life) ---
_tok=""; _tok_at=0
poll_token() {
  local now; now=$(date +%s)
  if [ -z "$_tok" ] || [ $((now - _tok_at)) -gt 2400 ]; then
    _tok="$(APP_ID="$GITHUB_APP_ID_CI_RUNNER" \
            INSTALLATION_ID="$GITHUB_APP_INSTALLATION_ID_CI_RUNNER" \
            APP_KEY_PEM="$GITHUB_PRIVATE_KEY_CI_RUNNER" \
            "$TOKEN_HELPER")"
    _tok_at=$now
  fi
  printf '%s' "$_tok"
}

queued_trusted_run() {
  curl -sS -H "Authorization: token $(poll_token)" -H "Accept: application/vnd.github+json" \
    "https://api.github.com/repos/${GATE_REPO}/actions/runs?status=queued&per_page=50" \
    | select_trusted_run_id
}

# Mint ONE ephemeral privileged runner for exactly this run, wait out its single
# job, then let it auto-deregister. The JIT config is staged in the supervisor's
# own RuntimeDirectory; systemd's LoadCredential (as root) hands it to the runner
# unit, so it is never chowned across users.
mint_and_run() {
  local run_id="$1" name jit jf unit
  name="gate-${run_id}-$$-${RANDOM}"
  jit="$(APP_ID="$GITHUB_APP_ID_CI_RUNNER" \
        INSTALLATION_ID="$GITHUB_APP_INSTALLATION_ID_CI_RUNNER" \
        APP_KEY_PEM="$GITHUB_PRIVATE_KEY_CI_RUNNER" \
        REPO="$GATE_REPO" RUNNER_NAME="$name" LABELS="$labels_json" \
        WORK_FOLDER="$WORK_FOLDER" \
        "$MINT")"
  mkdir -p "$JIT_DIR"
  jf="$JIT_DIR/${name}.jit"
  ( umask 0177; printf '%s' "$jit" > "$jf" )
  unit="gate-runner@${name}.service"
  log "run ${run_id}: starting ${unit}"
  systemctl start "$unit"                 # polkit-granted for gate-runner@*.service only
  while systemctl is-active --quiet "$unit"; do sleep 5; done
  rm -f "$jf"
  log "run ${run_id}: runner ${name} exited (job done; auto-deregistered)"
}

log "watching ${GATE_REPO} for queued ${GATE_WORKFLOW} runs on ${GATE_BRANCH} (trusted events only)"
while :; do
  # A poll failure (network, token) must never kill the watcher.
  if run_id="$(queued_trusted_run 2>/dev/null)" && [ -n "${run_id:-}" ]; then
    log "trusted gate run ${run_id} is queued — minting ONE ephemeral privileged runner"
    mint_and_run "$run_id" || log "run ${run_id}: mint/launch failed; will retry"
  fi
  sleep "$POLL_SECONDS"
done
