#!/usr/bin/env bash
# install-secret-reinjection-unit.sh — install the boot-time GitHub App
# secret reinjection insurance on the k3s host: the injector script into
# /usr/local/lib/ci-runner-k3s, then the oneshot service into
# /etc/systemd/system, ENABLED for next boot (not started now).
#
# WHY A SCRIPT rather than two hand-run `install` commands: the unit file's
# ExecStart references /usr/local/lib/ci-runner-k3s/inject-github-app-secret.sh,
# a COPY of the script living in this repository — installing the unit
# without copying the script yields a oneshot that fails at every boot. This
# installer encodes that dependency (mirrors ../phase2/node-extended-resource/
# install-reapply-unit.sh's rationale).
#
# ENABLE, NOT START: this installer arms the unit for the NEXT boot
# (`systemctl enable`, deliberately NOT `--now`). Running it applies the
# secret live against the cluster — an attended step this installer does not
# take. Enabling makes the recreation automatic on every subsequent boot,
# which is the whole point (disaster recovery of a wiped/tmpfs datastore).
#
# HOST-LOCAL: systemd units are machine state. Re-run after any host rebuild.
#
# Requires: root (writes /usr/local/lib and /etc/systemd/system), systemd,
# and the github-ci-runners 1Password wrapper the unit's ExecStart invokes.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="/usr/local/lib/ci-runner-k3s"
UNIT_DIR="/etc/systemd/system"
SERVICE="inject-github-app-secret.service"
INJECTOR="inject-github-app-secret.sh"
WRAPPER="/usr/local/bin/with-github-ci-runners-env.sh"

log() { printf '\n== %s ==\n' "$*"; }

[ "$(id -u)" -eq 0 ] || { echo "FATAL: must run as root (writes /usr/local/lib and /etc/systemd/system)"; exit 1; }
command -v systemctl >/dev/null || { echo "FATAL: systemctl not found on PATH"; exit 1; }

# ---------------------------------------------------------------------------
log "0. Pre-gate: the github-ci-runners 1Password wrapper must already exist"
# It is the unit's credential source (the same wrapper the gate supervisor
# uses). A missing wrapper means the unit would fail at every boot — fail
# loudly here rather than installing a unit that can never succeed.
[ -x "$WRAPPER" ] \
  || { echo "FATAL: missing ${WRAPPER} (the github-ci-runners 1Password wrapper the unit invokes) — provision it before installing this unit"; exit 1; }

# ---------------------------------------------------------------------------
log "1. Install the injector script to ${LIB_DIR} (the unit's ExecStart path)"
install -d -m 0755 "${LIB_DIR}"
install -m 0755 "${SCRIPT_DIR}/${INJECTOR}" "${LIB_DIR}/${INJECTOR}"

# ---------------------------------------------------------------------------
log "2. Install the unit file to ${UNIT_DIR}"
install -m 0644 "${SCRIPT_DIR}/${SERVICE}" "${UNIT_DIR}/${SERVICE}"

# ---------------------------------------------------------------------------
log "3. Reload systemd and enable the unit for next boot (NOT --now)"
systemctl daemon-reload
systemctl enable "${SERVICE}"

# ---------------------------------------------------------------------------
log "4. Verify the unit is enabled"
systemctl is-enabled "${SERVICE}"

log "DONE. ${SERVICE} armed for next boot. It does NOT run now — the live"
log "cutover (first application against the cluster) is a separate attended step."
