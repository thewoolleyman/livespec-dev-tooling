#!/usr/bin/env bash
# seed-gate-forge-cred.sh — the ONE attended step for the delegated gate's
# forge credential. Run by the human maintainer (a member of the
# github-ci-runners group, e.g. cwoolley), NOT at boot. It sources the
# fine-grained PAT from 1Password and writes it into the host systemd
# credstore (/etc/credstore.encrypted/), host-encrypted, so the boot unit
# (inject-gate-forge-secret.service) can decrypt it locally as root with NO
# `op run`, NO 1Password wrapper, NO network. This is also the RE-SEED step
# when the token expires (the minted PAT has a ~1-year expiry) or rotates.
#
# WHY AN ATTENDED STEP: `op run` refuses to run as root and needs a human's
# dropped-privilege 1Password session; the boot unit runs unattended as root.
# So 1Password is touched exactly once, here, by a human — the boot path
# never touches it. This mirrors the sibling seed-github-app-creds.sh exactly.
#
# WHY THE credstore AT ALL (vs. converge creating the Secret directly): the
# k3s datastore is tmpfs (../phase2/datastore-tmpfs/), wiped every reboot, so
# cluster Secrets do not persist; and the Secret is deliberately NOT applied
# by converge (an empty Secret is worse than an absent one — see
# ../phase2/gates/gate-credentials.yaml). The credstore lives on the
# PERSISTENT rootfs, so it survives reboots, and the boot unit reconstructs
# the cluster Secret from it every boot. That turns "recreate the Secret by
# hand every reboot" into "seed once per host, from 1Password" — which is
# what goal 0 (rebuildable from git, no live host changed by hand) asks for.
#
# INVOKE (as the human in the github-ci-runners group):
#
#     with-github-ci-runners-env.sh -- \
#       ci-runner/k3s/secret-reinjection/seed-gate-forge-cred.sh
#
#   The wrapper decrypts its service-account token and drops privileges back
#   to the invoking human for `op run --environment`, injecting GATE_FORGE_TOKEN
#   into THIS script's environment. The `systemd-creds encrypt` call then needs
#   the host key (root), so it is invoked via `sudo`.
#
# The injected var maps to the credstore credential name (which the boot
# unit's LoadCredentialEncrypted= line and inject-gate-forge-secret.sh
# consume):
#
#   GATE_FORGE_TOKEN  ->  gate-forge-token
#
# The PAT's required scope is Administration:Read + Metadata:Read on the gated
# repositories (branch-protection read is admin-scoped; check-runs are
# readable via Metadata). See ../phase2/gates/gate-credentials.yaml.
#
# SECRET DISCIPLINE: the value is never echoed, logged, or placed on argv. The
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
log "0. Verify the value was injected by the 1Password wrapper"
# Probe PRESENCE only — never the value.
if [ "$(printenv GATE_FORGE_TOKEN 2>/dev/null | wc -c)" -eq 0 ]; then
  cat >&2 <<EOF
FATAL: missing credential variable: GATE_FORGE_TOKEN
Run this script UNDER the github-ci-runners 1Password wrapper:
  with-github-ci-runners-env.sh -- $(basename "$0")
The wrapper must expose GATE_FORGE_TOKEN (the fine-grained PAT for the gated
repositories, Administration:Read + Metadata:Read). Add it to that 1Password
Environment first if it is not present.
EOF
  exit 1
fi

# ---------------------------------------------------------------------------
log "1. Ensure the host credstore directory exists (root-only)"
sudo install -d -m 0700 "$CREDSTORE_DIR"

# ---------------------------------------------------------------------------
log "2. Encrypt the value into the credstore (value -> STDIN, never argv)"
# ${!var} is bash INDIRECT expansion: the value of the variable whose NAME is
# in $var, byte-exact. It is piped straight into systemd-creds; the value
# never becomes a command-line argument. --name=<cred> binds decryption to
# that credential name, which the unit's LoadCredentialEncrypted= line must
# match exactly.
seed_one() {
  local var="$1" name="$2" out="${CREDSTORE_DIR}/$2"
  printf '%s' "${!var}" | sudo systemd-creds encrypt --name="$name" - "$out"
  sudo chmod 0600 "$out"
  printf '   seeded %s -> %s\n' "$var" "$out"
}

seed_one GATE_FORGE_TOKEN gate-forge-token

log "DONE. 1 host-encrypted credential written under ${CREDSTORE_DIR}."
log "The boot unit inject-gate-forge-secret.service now decrypts it locally"
log "as root — no 1Password, no network. Re-run this to rotate the token."
