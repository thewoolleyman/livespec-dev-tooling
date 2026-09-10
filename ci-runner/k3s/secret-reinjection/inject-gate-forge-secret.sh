#!/usr/bin/env bash
# inject-gate-forge-secret.sh — (re)create the k8s Secret
# `gate-forge-credential` in namespace `gates` from the host's systemd-creds
# LOCAL CREDSTORE, so a wiped/tmpfs k3s datastore comes back with the forge
# credential the delegated pre-push gate needs, with ZERO manual steps and NO
# network at boot.
#
# WHY THIS EXISTS: the k3s datastore is on tmpfs (see
# ../phase2/datastore-tmpfs/), so EVERY reboot wipes all cluster state,
# including this Secret. It is deliberately NOT applied by converge — an
# empty Secret is worse than an absent one (see ../phase2/gates/
# gate-credentials.yaml "NOT APPLIED BY CONVERGE"). Until this mechanism the
# Secret lived ONLY in the datastore and was created BY HAND once per cluster
# rebuild; a reboot therefore silently broke the delegated gate — the two
# forge-credential-reading targets (check-branch-protection-alignment and
# check-master-ci-green) fail CLOSED inside a gate pod without it, so every
# delegated gate run went red until an operator hand-recreated the Secret.
# (plan livespec k3s-on-gmktec-for-vps-usage, epic livespec-sab5gn; the
# reboot-durability gap surfaced 2026-09-10 after a poweredge reboot wiped it
# mid-plan.) This script closes that gap the same way its sibling
# inject-github-app-secret.sh closes it for the ARC App credential:
# reconstruct the Secret from a host-encrypted local credential at boot.
#
# CREDENTIAL SOURCE — the host systemd credstore, decrypted locally as ROOT.
# The token is stored host-encrypted at /etc/credstore.encrypted/
# gate-forge-token (seeded once, attended, by the maintainer via
# seed-gate-forge-cred.sh — the ONLY step that touches 1Password). This unit
# runs as ROOT and its `LoadCredentialEncrypted=` line decrypts it into
# $CREDENTIALS_DIRECTORY (root-only, mode 0400) at start — NO `op run`, NO
# 1Password wrapper, NO network. This mirrors inject-github-app-secret.sh
# exactly (see that script's header for why the op-run/wrapper path cannot
# work unattended as root on this host).
#
# The credential arrives in $CREDENTIALS_DIRECTORY under this name, mapping
# onto the Secret's one data key:
#
#   gate-forge-token  ->  secret key GH_TOKEN
#
# SECRET DISCIPLINE: the token value is NEVER echoed, logged, or passed as a
# command-line argument. It already IS a root-only file in
# $CREDENTIALS_DIRECTORY, so it is handed to kubectl via `--from-file`
# straight from that path (never --from-literal / argv, never a copy). The
# dry-run YAML that carries the base64 value is piped in-memory to `apply`
# and never written to disk. `set -x` is NEVER used. Nothing but phase
# banners reaches stdout/stderr.
#
# Deps: kubectl (k3s-provided), a reachable k3s API (KUBECONFIG). This is a
# HOST OPERATIONAL ARTIFACT (not Python product code) — not part of
# `just check`; recreatability is the contract.
set -euo pipefail

log() { printf '\n== %s ==\n' "$*"; }

# k3s cluster kubeconfig — defaulted here and also set in the unit's
# Environment=. This unit runs as root, so it reads the default 0600
# root:root kubeconfig directly.
export KUBECONFIG="${KUBECONFIG:-/etc/rancher/k3s/k3s.yaml}"

GATES_NAMESPACE="gates"
SECRET_NAME="gate-forge-credential"
SECRET_KEY="GH_TOKEN"

# systemd populates $CREDENTIALS_DIRECTORY for a unit that declares
# LoadCredentialEncrypted=/ImportCredential=. Absent it, this script was not
# launched by its unit — fail closed rather than guess a path.
CRED_DIR="${CREDENTIALS_DIRECTORY:?CREDENTIALS_DIRECTORY unset — run this via inject-gate-forge-secret.service (its LoadCredentialEncrypted= line populates it), not by hand}"
TOKEN_CRED="${CRED_DIR}/gate-forge-token"

command -v kubectl >/dev/null || { echo "FATAL: kubectl not found on PATH (k3s provides it at /usr/local/bin/kubectl)"; exit 1; }

# ---------------------------------------------------------------------------
log "0. Verify the decrypted credential file is present"
# Fail closed with an actionable message naming the seed step if the cred is
# missing (never printing a value). A missing file here means the credstore
# was never seeded (or the name drifted).
if [ ! -r "${TOKEN_CRED}" ]; then
  cat >&2 <<EOF
FATAL: missing decrypted credential: gate-forge-token
The host credstore was not seeded (or the credential name drifted). Run the
attended seed step first (maintainer, in the github-ci-runners group):
  with-github-ci-runners-env.sh -- .../secret-reinjection/seed-gate-forge-cred.sh
See ../phase2/gates/gate-credentials.yaml and ../README.md.
EOF
  exit 1
fi

# ---------------------------------------------------------------------------
log "1. Ensure the gates namespace exists (idempotent)"
# May not exist on a genuinely fresh cluster. Create-or-noop without failing
# if a concurrent converge already made it.
kubectl create namespace "${GATES_NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -

# ---------------------------------------------------------------------------
log "2. (Re)create the ${SECRET_NAME} Secret from the local credstore"
# `create ... --dry-run=client -o yaml | apply -f -` is the idempotent
# create-or-replace: it succeeds whether or not the Secret already exists,
# and updates the value in place if it drifted. The token is read via
# --from-file straight from the root-only cred path, so it never appears on
# argv; the rendered YAML (carrying the base64 value) is piped in-memory to
# apply and never touches disk.
kubectl create secret generic "${SECRET_NAME}" \
  --namespace "${GATES_NAMESPACE}" \
  --from-file="${SECRET_KEY}=${TOKEN_CRED}" \
  --dry-run=client -o yaml \
  | kubectl apply -f -

# ---------------------------------------------------------------------------
log "3. Verify the Secret exists with the expected key (presence and size only, never the value)"
# `wc -c` reads the base64 value silently and prints only a byte count — the
# same "presence and size, never the value" idiom the README documents for
# hand verification. A zero count means the key is absent or empty.
_bytes="$(kubectl --namespace "${GATES_NAMESPACE}" get secret "${SECRET_NAME}" \
  -o jsonpath="{.data.${SECRET_KEY}}" | wc -c)"
if [ "${_bytes}" -eq 0 ]; then
  echo "FATAL: ${SECRET_NAME} was created but has no ${SECRET_KEY} data key" >&2
  exit 1
fi
printf '   %s/%s present with %s key (%s base64 bytes)\n' \
  "${GATES_NAMESPACE}" "${SECRET_NAME}" "${SECRET_KEY}" "${_bytes}"

log "DONE. ${GATES_NAMESPACE}/${SECRET_NAME} reconstructed from the local credstore."
