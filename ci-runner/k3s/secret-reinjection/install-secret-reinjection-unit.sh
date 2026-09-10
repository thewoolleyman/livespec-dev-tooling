#!/usr/bin/env bash
# install-secret-reinjection-unit.sh — install the boot-time secret
# reinjection insurance on the k3s host: each injector script into
# /usr/local/lib/ci-runner-k3s, then each oneshot service into
# /etc/systemd/system, ENABLED for next boot (not started now).
#
# TWO SECRETS, ONE INSTALLER. The k3s datastore is on tmpfs
# (../phase2/datastore-tmpfs/), so every reboot wipes all cluster Secrets.
# Two Secrets are reconstructed at boot from the host's systemd credstore,
# each by its own oneshot unit + injector script:
#
#   inject-github-app-secret   -> arc-runners/arc-github-app-installation
#                                  (ARC's GitHub App credential)
#   inject-gate-forge-secret   -> gates/gate-forge-credential
#                                  (the delegated pre-push gate's forge PAT)
#
# This one installer owns the whole reinjection concern (install-node.sh
# step 7 calls it), so a new reinjected Secret is added here rather than in a
# parallel installer.
#
# WHY A SCRIPT rather than hand-run `install` commands: each unit's ExecStart
# references a COPY of its injector script under /usr/local/lib/ci-runner-k3s
# — installing a unit without copying its script yields a oneshot that fails
# at every boot. This installer encodes that dependency (mirrors
# ../phase2/node-extended-resource/install-reapply-unit.sh's rationale).
#
# ENABLE, NOT START: this installer arms each unit for the NEXT boot
# (`systemctl enable`, deliberately NOT `--now`). Running a unit applies its
# Secret live against the cluster — an attended step this installer does not
# take. Enabling makes the recreation automatic on every subsequent boot,
# which is the whole point (disaster recovery of a wiped/tmpfs datastore).
#
# CREDSTORE PREREQUISITE: each boot unit decrypts host-encrypted credentials
# from /etc/credstore.encrypted/ (see the units' LoadCredentialEncrypted=
# lines). Those must be seeded ONCE, attended, by the maintainer via the
# matching seed-*.sh BEFORE the unit can succeed at boot. This installer warns
# (not fatal) per missing credential, so units can be armed before or after
# seeding.
#
# HOST-LOCAL: systemd units are machine state. Re-run after any host rebuild.
#
# Requires: root (writes /usr/local/lib and /etc/systemd/system), systemd.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="/usr/local/lib/ci-runner-k3s"
UNIT_DIR="/etc/systemd/system"
CREDSTORE_DIR="/etc/credstore.encrypted"

# Each reinjected Secret: <service> <injector> <seed-script> <cred>[,<cred>...]
# The creds field is a comma-separated list of the credstore credential names
# the unit decrypts (the LoadCredentialEncrypted= names) — checked for
# seeding below and named in the warning that points at the right seed step.
UNITS=(
  "inject-github-app-secret.service|inject-github-app-secret.sh|seed-github-app-creds.sh|arc-github-app-id,arc-github-app-installation-id,arc-github-app-private-key"
  "inject-gate-forge-secret.service|inject-gate-forge-secret.sh|seed-gate-forge-cred.sh|gate-forge-token"
)

log() { printf '\n== %s ==\n' "$*"; }

[ "$(id -u)" -eq 0 ] || { echo "FATAL: must run as root (writes /usr/local/lib and /etc/systemd/system)"; exit 1; }
command -v systemctl >/dev/null || { echo "FATAL: systemctl not found on PATH"; exit 1; }

install -d -m 0755 "${LIB_DIR}"

for _spec in "${UNITS[@]}"; do
  IFS='|' read -r _service _injector _seed _creds <<<"${_spec}"

  # -------------------------------------------------------------------------
  log "Check the credstore has been seeded for ${_service} (warn-only)"
  # A missing credential means the matching seed-*.sh has not been run yet.
  # Warn loudly rather than fail, so the unit can be armed in either order.
  _missing=()
  IFS=',' read -r -a _cred_list <<<"${_creds}"
  for _c in "${_cred_list[@]}"; do
    [ -r "${CREDSTORE_DIR}/${_c}" ] || _missing+=("$_c")
  done
  if [ "${#_missing[@]}" -gt 0 ]; then
    cat >&2 <<EOF
WARNING: credstore not fully seeded for ${_service} — missing: ${_missing[*]}
The boot unit will FAIL until these exist. Seed them once (attended), as a
member of the github-ci-runners group:
  with-github-ci-runners-env.sh -- ${SCRIPT_DIR}/${_seed}
Continuing to arm the unit anyway.
EOF
  fi

  # -------------------------------------------------------------------------
  log "Install ${_injector} to ${LIB_DIR} (the unit's ExecStart path)"
  install -m 0755 "${SCRIPT_DIR}/${_injector}" "${LIB_DIR}/${_injector}"

  # -------------------------------------------------------------------------
  log "Install ${_service} to ${UNIT_DIR}"
  install -m 0644 "${SCRIPT_DIR}/${_service}" "${UNIT_DIR}/${_service}"
done

# ---------------------------------------------------------------------------
log "Reload systemd and enable the units for next boot (NOT --now)"
systemctl daemon-reload
for _spec in "${UNITS[@]}"; do
  systemctl enable "${_spec%%|*}"
done

# ---------------------------------------------------------------------------
log "Verify the units are enabled"
for _spec in "${UNITS[@]}"; do
  systemctl is-enabled "${_spec%%|*}"
done

log "DONE. Both reinjection units armed for next boot. They do NOT run now —"
log "the live cutover (first application against the cluster) is a separate"
log "attended step per unit."
