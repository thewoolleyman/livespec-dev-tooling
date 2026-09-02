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
# CREDSTORE PREREQUISITE: the boot unit decrypts three host-encrypted
# credentials from /etc/credstore.encrypted/ (see the unit's
# LoadCredentialEncrypted= lines). Those must be seeded ONCE, attended, by
# the maintainer via seed-github-app-creds.sh BEFORE the unit can succeed at
# boot. This installer warns (not fatal) if they are absent, so the unit can
# be armed either before or after seeding.
#
# HOST-LOCAL: systemd units are machine state. Re-run after any host rebuild.
#
# Requires: root (writes /usr/local/lib and /etc/systemd/system), systemd.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="/usr/local/lib/ci-runner-k3s"
UNIT_DIR="/etc/systemd/system"
SERVICE="inject-github-app-secret.service"
INJECTOR="inject-github-app-secret.sh"
CREDSTORE_DIR="/etc/credstore.encrypted"
CREDS=(arc-github-app-id arc-github-app-installation-id arc-github-app-private-key)

log() { printf '\n== %s ==\n' "$*"; }

[ "$(id -u)" -eq 0 ] || { echo "FATAL: must run as root (writes /usr/local/lib and /etc/systemd/system)"; exit 1; }
command -v systemctl >/dev/null || { echo "FATAL: systemctl not found on PATH"; exit 1; }

# ---------------------------------------------------------------------------
log "0. Check the credstore has been seeded (warn-only — seed is a separate attended step)"
# The boot unit decrypts these three; a missing one means seed-github-app-creds.sh
# has not been run yet. Warn loudly rather than fail, so the unit can be armed
# in either order.
_missing=()
for _c in "${CREDS[@]}"; do
  [ -r "${CREDSTORE_DIR}/${_c}" ] || _missing+=("$_c")
done
if [ "${#_missing[@]}" -gt 0 ]; then
  cat >&2 <<EOF
WARNING: credstore not fully seeded — missing: ${_missing[*]}
The boot unit will FAIL until these exist. Seed them once (attended), as a
member of the github-ci-runners group:
  with-github-ci-runners-env.sh -- ${SCRIPT_DIR}/seed-github-app-creds.sh
Continuing to arm the unit anyway.
EOF
fi

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
