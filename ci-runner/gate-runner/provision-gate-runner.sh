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
SUP_USER=ci-sup                       # supervisor identity; reads the App key, never logged into
SUP_GROUP=github-ci-runners           # membership gates App-key readability
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
[ -x /usr/local/bin/with-github-ci-runners-env.sh ] \
  || { echo "FATAL: missing the github-ci-runners 1Password wrapper (supervisor credential source)"; exit 1; }
getent group "$SUP_GROUP" >/dev/null \
  || { echo "FATAL: group ${SUP_GROUP} does not exist — it gates readability of the App private key and MUST be created deliberately, not by this script"; exit 1; }

# ---------------------------------------------------------------------------
# THIS TIER OWNS ITS OWN SUPERVISOR IDENTITY.
#
# Until `livespec-s43svm.19` this script required `ci-sup` to already exist and
# told the operator to "provision the contained lane first
# (../provision-ci-runner.sh)". Two things were wrong with that, and both were
# load-bearing rather than cosmetic:
#
#   1. The contained lane has since been DELETED. Inheriting an identity from a
#      tree that was going away would have left this tier unprovisionable the
#      moment that landed.
#   2. `provision-ci-runner.sh` never created `ci-sup` in the first place. The
#      only instruction for it was one prose line in `../supervisor/README.md`
#      (since deleted; its credential model was relocated to `../README.md`)
#      ("create the `ci-sup` + confirm `ci-runner` users"), so the identity that
#      a LIVE, currently-running supervisor executes as was recreatable only
#      from a sentence in a README scheduled for deletion.
#
# Creating it here is idempotent and makes this tier self-provisioning. The
# GROUP is deliberately NOT created — group membership is what makes the App
# private key readable, so it stays an explicit operator act with its own
# review, checked above rather than assumed here.
log "0b. Supervisor identity"
if id "$SUP_USER" >/dev/null 2>&1; then
  echo "  ${SUP_USER} exists"
else
  # A system account: no login shell, no home. It runs one unit and reads one
  # credential; it is never logged into.
  useradd --system --no-create-home --shell /usr/sbin/nologin "$SUP_USER"
  echo "  created ${SUP_USER} (system account, nologin)"
fi
if id -nG "$SUP_USER" | tr ' ' '\n' | grep -qx "$SUP_GROUP"; then
  echo "  ${SUP_USER} is in ${SUP_GROUP}"
else
  usermod -aG "$SUP_GROUP" "$SUP_USER"
  echo "  added ${SUP_USER} to ${SUP_GROUP}"
fi
# Verify rather than trust the two writes above: a supervisor that cannot read
# the credential fails at mint time, deep inside a queued gate run, where the
# cause is far less obvious than it is here.
id -nG "$SUP_USER" | tr ' ' '\n' | grep -qx "$SUP_GROUP" \
  || { echo "FATAL: ${SUP_USER} is still not in ${SUP_GROUP} after usermod"; exit 1; }

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
# (The deleted contained lane's sanitize-hook existed precisely because ITS jobs
# must not; the k3s lane gets the same property from its pod securityContext.)

# ---------------------------------------------------------------------------
log "2. Supervisor + runner scripts"
mkdir -p "$LIB"
# `mint-jitconfig.sh` moved here from ../supervisor/ with livespec-s43svm.19:
# `gate-runner-supervisor.sh` EXECUTES it at mint time (its `MINT=` default is
# "${LIB}/mint-jitconfig.sh"), so it is a runtime dependency of this tier, not a
# shared convenience. Leaving it in a deleted tree would have removed a script a
# running service calls.
# `gate-optin-expiry.sh` is the 24h opt-in expiry enforcer (ExecStart of
# gate-optin-expiry.service) and `gate-optin.sh` the ONE sanctioned operator
# opt-in act — see README §"Opt-in expiry" (livespec-s43svm.43).
for f in gate-runner-supervisor.sh run-gate-jit-runner.sh app-installation-token.sh mint-jitconfig.sh gate-optin-expiry.sh gate-optin.sh; do
  install -m 0755 -o root -g root "${HERE}/${f}" "${LIB}/${f}"
done

# ---------------------------------------------------------------------------
log "3. systemd units + the narrow polkit bridge"
install -m 0644 -o root -g root "${HERE}/gate-runner@.service"            /etc/systemd/system/gate-runner@.service
install -m 0644 -o root -g root "${HERE}/gate-runner-supervisor.service" /etc/systemd/system/gate-runner-supervisor.service
install -m 0644 -o root -g root "${HERE}/50-gate-runner-supervisor.rules" /etc/polkit-1/rules.d/50-gate-runner-supervisor.rules
# The hosted-only compensating control (livespec-s43svm.43). `hosted-only.conf`
# carries `ConditionPathExists=/run/livespec-local-ci-enabled`, so the
# supervisor starts ONLY after an explicit operator opt-in
# (`gate-optin.sh`, root — see step 3b for its 24h expiry) and never at boot. Until this
# commit the drop-in existed ONLY on the live host, hand-applied, so re-running
# this script converged a host where the privileged supervisor auto-started
# with no gate and reported success.
install -d -m 0755 /etc/systemd/system/gate-runner-supervisor.service.d
install -m 0644 -o root -g root "${HERE}/hosted-only.conf" /etc/systemd/system/gate-runner-supervisor.service.d/hosted-only.conf
# The opt-in's 24h wall-clock expiry (livespec SPECIFICATION
# §"Fleet CI execution posture", v214): a timer-driven oneshot that REMOVES an
# opt-in older than 24h and stops the supervisor. It never creates one.
install -m 0644 -o root -g root "${HERE}/gate-optin-expiry.service" /etc/systemd/system/gate-optin-expiry.service
install -m 0644 -o root -g root "${HERE}/gate-optin-expiry.timer"   /etc/systemd/system/gate-optin-expiry.timer
systemctl daemon-reload
systemctl restart polkit

# ---------------------------------------------------------------------------
log "3b. Opt-in expiry: enable the timer and enforce once, now"
systemctl enable --now gate-optin-expiry.timer
# One immediate pass, so a host carrying an over-age opt-in (the nine-day one
# measured 2026-08-23) converges to the GATED state in this same run rather than
# up to 15 minutes later. The pass is a no-op when the opt-in is absent or fresh.
systemctl start gate-optin-expiry.service
systemctl is-active --quiet gate-optin-expiry.timer \
  || { echo "FATAL: gate-optin-expiry.timer is not active"; exit 1; }

# ---------------------------------------------------------------------------
log "4. Enable + start the on-demand supervisor"
# `enable --now` is deliberately unconditional and SAFE: with the hosted-only
# drop-in installed in step 3 and the opt-in file absent, `enable` succeeds
# (boot wiring recorded) and the START is skipped because the unit's
# ConditionPathExists is unmet — which IS the hosted-only behaviour. The
# drop-in is why this line does not auto-start a privileged supervisor.
systemctl enable --now gate-runner-supervisor.service
if [ -e /run/livespec-local-ci-enabled ]; then
  # Opt-in present: the condition is met, so the supervisor MUST be running.
  systemctl is-active --quiet gate-runner-supervisor.service \
    || { echo "FATAL: gate-runner-supervisor.service did not come up"; journalctl -u gate-runner-supervisor.service -n 20 --no-pager; exit 1; }
  log "DONE — opt-in present; gate supervisor is watching. NO privileged runner"
  log "exists until a trusted gate run is queued. Prove the trust boundary:"
  log "./trigger-surface-exit-tests.sh"
else
  # Opt-in absent: the supervisor is enabled but NOT started (hosted-only
  # posture). An active unit here would mean the drop-in did not take effect.
  if systemctl is-active --quiet gate-runner-supervisor.service; then
    echo "FATAL: gate-runner-supervisor.service is active with NO opt-in file — the hosted-only drop-in is not in effect"; exit 1
  fi
  log "DONE — hosted-only posture: supervisor enabled but NOT started (no"
  log "/run/livespec-local-ci-enabled). To opt in for the next 24h (the ONLY"
  log "sanctioned act — never hand-touch the file):"
  log "  sudo ${LIB}/gate-optin.sh"
fi
