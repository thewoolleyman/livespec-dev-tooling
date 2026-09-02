#!/usr/bin/env bash
# seed-github-app-creds.sh — the ONE attended step. Run by the human
# maintainer (a member of the github-ci-runners group, e.g. cwoolley), NOT
# at boot. It sources the three GitHub App values from 1Password and writes
# each into the host systemd credstore (/etc/credstore.encrypted/),
# host-encrypted, so the boot unit (inject-github-app-secret.service) can
# decrypt them locally as root with NO `op run`, NO 1Password wrapper, NO
# network. This is also the RE-SEED step when the App private key rotates.
#
# WHY AN ATTENDED STEP: `op run` refuses to run as root and needs a human's
# dropped-privilege 1Password session; the boot unit runs unattended as
# root. So 1Password is touched exactly once, here, by a human — the boot
# path never touches it.
#
# INVOKE (as the human in the github-ci-runners group):
#
#     with-github-ci-runners-env.sh -- \
#       ci-runner/k3s/secret-reinjection/seed-github-app-creds.sh
#
#   The wrapper decrypts its service-account token and drops privileges back
#   to the invoking human for `op run --environment`, injecting the three
#   vars into THIS script's environment. Each `systemd-creds encrypt` call
#   then needs the host key (root), so it is invoked via `sudo` per value.
#   sudo will prompt for the human's password (or use a cached credential);
#   the wrapper's own `sudo -n` escalation is separate and already done.
#
# The three injected vars map to credstore credential names (which the boot
# unit's LoadCredentialEncrypted= lines and inject-github-app-secret.sh
# consume):
#
#   GITHUB_APP_ID_CI_RUNNER              -> arc-github-app-id
#   GITHUB_APP_INSTALLATION_ID_CI_RUNNER -> arc-github-app-installation-id
#   GITHUB_PRIVATE_KEY_CI_RUNNER (PEM)   -> arc-github-app-private-key
#
# (These var names are the exact ones ../../gate-runner/gate-runner-supervisor.sh
# reads out of that same injected env — reused, not re-derived.)
#
# SECRET DISCIPLINE: no value is ever echoed, logged, or placed on argv. The
# plaintext flows value -> `systemd-creds encrypt` via STDIN (the `-` input
# operand); systemd-creds writes only the ENCRYPTED ciphertext to the output
# file. Presence is probed with `printenv NAME | wc -c` (a count, never the
# value). `set -x` is NEVER used.
set -euo pipefail

log() { printf '\n== %s ==\n' "$*"; }

CREDSTORE_DIR="/etc/credstore.encrypted"

command -v systemd-creds >/dev/null || { echo "FATAL: systemd-creds not found on PATH"; exit 1; }
command -v sudo >/dev/null || { echo "FATAL: sudo not found on PATH (needed for the host encryption key and credstore writes)"; exit 1; }

# ---------------------------------------------------------------------------
log "0. Verify the three values were injected by the 1Password wrapper"
# Probe PRESENCE only — never the value.
_missing=()
for _var in GITHUB_APP_ID_CI_RUNNER GITHUB_APP_INSTALLATION_ID_CI_RUNNER GITHUB_PRIVATE_KEY_CI_RUNNER; do
  if [ "$(printenv "$_var" 2>/dev/null | wc -c)" -eq 0 ]; then
    _missing+=("$_var")
  fi
done
if [ "${#_missing[@]}" -gt 0 ]; then
  cat >&2 <<EOF
FATAL: missing credential variable(s): ${_missing[*]}
Run this script UNDER the github-ci-runners 1Password wrapper:
  with-github-ci-runners-env.sh -- $(basename "$0")
EOF
  exit 1
fi

# ---------------------------------------------------------------------------
log "1. Ensure the host credstore directory exists (root-only)"
sudo install -d -m 0700 "$CREDSTORE_DIR"

# ---------------------------------------------------------------------------
log "2. Encrypt each value into the credstore (value -> STDIN, never argv)"
# ${!var} is bash INDIRECT expansion: the value of the variable whose NAME is
# in $var, byte-exact (no trailing-newline stripping — the PEM keeps its own
# bytes). It is piped straight into systemd-creds; the value never becomes a
# command-line argument. --name=<cred> binds decryption to that credential
# name, which the unit's LoadCredentialEncrypted= line must match exactly.
seed_one() {
  local var="$1" name="$2" out="${CREDSTORE_DIR}/$2"
  printf '%s' "${!var}" | sudo systemd-creds encrypt --name="$name" - "$out"
  sudo chmod 0600 "$out"
  printf '   seeded %s -> %s\n' "$var" "$out"
}

seed_one GITHUB_APP_ID_CI_RUNNER              arc-github-app-id
seed_one GITHUB_APP_INSTALLATION_ID_CI_RUNNER arc-github-app-installation-id
seed_one GITHUB_PRIVATE_KEY_CI_RUNNER         arc-github-app-private-key

log "DONE. 3 host-encrypted credentials written under ${CREDSTORE_DIR}."
log "The boot unit inject-github-app-secret.service now decrypts them locally"
log "as root — no 1Password, no network. Re-run this to rotate the key."
