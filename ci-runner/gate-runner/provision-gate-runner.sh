#!/usr/bin/env bash
# provision-gate-runner.sh — idempotently provision the SECOND, PRIVILEGED runner
# tier: the on-demand golden-master gate runner.
#
# Design: livespec plan/fabro-ci-image-factoring/phase0-runner-containment-design.md
#   §"Second trust tier — the privileged gate runner". Rationale + trust table:
#   ./README.md. Recreatability: re-running this script converges the host.
#
# HARD invariants (never traded away):
#   * NO privileged runner idles. The supervisor mints one ONLY for a queued run of
#     the gate workflow on a write-access-gated event on master; it auto-deregisters
#     after that single job.
#   * The trust boundary is the TRIGGER CHECK, not the uid — a runner LABEL is a
#     request any workflow may write, so the label alone can never be the gate.
#   * The App private key stays readable only by ci-sup; it never reaches the runner.
#   * The CONTAINED CI lane (ci-runner/) is untouched by this script. Two lanes, two
#     trust tiers, no shared units.
#
# Requires: run as a sudo-capable admin. The `thewoolleyman-ci-runners` App must
# already include the gate repo (administration: write) — a maintainer click; a PAT
# cannot modify an App installation.
set -euo pipefail

OPERATOR=ubuntu                       # the gate runner's identity (see README)
GATE_HOME=/home/${OPERATOR}/gate-runner
GATE_DIR=${GATE_HOME}/actions-runner
RUNNER_VERSION=2.335.1                # same pin as the contained lane
LIB=/usr/local/lib/ci-runner
HERE="$(cd "$(dirname "$0")" && pwd)"

log() { printf '\n== %s ==\n' "$*"; }

# ---------------------------------------------------------------------------
log "0. Pre-gate: the operator identity must already carry what the gate needs"
id -nG "$OPERATOR" | tr ' ' '\n' | grep -qx docker \
  || { echo "FATAL: $OPERATOR is not in the docker group (the gate drives DinD)"; exit 1; }
[ -r "/home/${OPERATOR}/.codex/auth.json" ] \
  || { echo "FATAL: missing /home/${OPERATOR}/.codex/auth.json (the Codex credential the gate projects)"; exit 1; }
[ -x "/home/${OPERATOR}/.fabro/bin/fabro" ] \
  || { echo "FATAL: missing the host fabro binary at /home/${OPERATOR}/.fabro/bin/fabro"; exit 1; }
[ -x /data/projects/1password-env-wrapper/with-livespec-env.sh ] \
  || { echo "FATAL: missing the livespec 1Password wrapper the gate step invokes"; exit 1; }
id ci-sup >/dev/null 2>&1 \
  || { echo "FATAL: ci-sup does not exist — provision the contained lane first (../provision-ci-runner.sh)"; exit 1; }
[ -x /usr/local/bin/with-github-ci-runners-env.sh ] \
  || { echo "FATAL: missing the github-ci-runners 1Password wrapper (supervisor credential source)"; exit 1; }
[ -x "${LIB}/mint-jitconfig.sh" ] \
  || { echo "FATAL: missing ${LIB}/mint-jitconfig.sh — provision the contained lane first"; exit 1; }

# ---------------------------------------------------------------------------
log "1. Actions runner ${RUNNER_VERSION} under the operator's own gate-runner dir"
# A dedicated tree (NOT the operator's shell home root, NOT the contained lane's)
# so the runner's _work/_diag stay isolated from both.
mkdir -p "$GATE_DIR"
chown -R "${OPERATOR}:${OPERATOR}" "$GATE_HOME"
if [ ! -f "${GATE_DIR}/config.sh" ]; then
  sudo -u "$OPERATOR" bash -c "
    set -euo pipefail
    cd '${GATE_DIR}'
    curl -fsSL -o r.tgz https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz
    tar xzf r.tgz
    rm r.tgz
  "
fi
# NO container-hooks here, on purpose: the gate's steps run directly on the host.
# (The contained lane's sanitize-hook exists precisely because ITS jobs must not.)

# ---------------------------------------------------------------------------
log "2. Supervisor + runner scripts"
mkdir -p "$LIB"
for f in gate-runner-supervisor.sh run-gate-jit-runner.sh app-installation-token.sh; do
  install -m 0755 -o root -g root "${HERE}/${f}" "${LIB}/${f}"
done

# ---------------------------------------------------------------------------
log "3. systemd units + the narrow polkit bridge"
install -m 0644 -o root -g root "${HERE}/gate-runner@.service"            /etc/systemd/system/gate-runner@.service
install -m 0644 -o root -g root "${HERE}/gate-runner-supervisor.service" /etc/systemd/system/gate-runner-supervisor.service
install -m 0644 -o root -g root "${HERE}/50-gate-runner-supervisor.rules" /etc/polkit-1/rules.d/50-gate-runner-supervisor.rules
systemctl daemon-reload
systemctl restart polkit

# ---------------------------------------------------------------------------
log "4. Enable + start the on-demand supervisor"
systemctl enable --now gate-runner-supervisor.service
systemctl is-active --quiet gate-runner-supervisor.service \
  || { echo "FATAL: gate-runner-supervisor.service did not come up"; journalctl -u gate-runner-supervisor.service -n 20 --no-pager; exit 1; }

log "DONE — gate supervisor is watching. NO privileged runner exists until a"
log "trusted gate run is queued. Prove the trust boundary: ./trigger-surface-exit-tests.sh"
