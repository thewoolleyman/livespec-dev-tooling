#!/usr/bin/env bash
# patch-node-churn-capacity-exit-tests.sh — prove that ./patch-node-churn-capacity.sh
# reads and patches THIS node BY NAME through the STATUS SUBRESOURCE only, never
# the bare `nodes` resource, WITHOUT touching any host.
#
# WHY THIS MATTERS. The scoped agent credential
# (../node-status-credential/node-status-patch-rbac.yaml) grants get/patch on
# `nodes/status` ONLY — deliberately, so it cannot reach `spec` to untaint the
# node. A bare `kubectl get node` is a read of the parent `nodes` resource and
# would 403 on an agent, timing out the readiness wait and never reaching the
# patch. So EVERY kubectl the patch script issues must carry
# `--subresource=status`; a bare `get node` is a regression that makes the agent
# reapply timer inoperable and leaves that node at whatever the server stamped.
#
#   A. against an AGENT profile the script exits 0, and every kubectl it issues
#      — the readiness GET, the verify GET and the patch — carries
#      `--subresource=status`; not one is a bare `get node` / `patch node`
#      without it;
#   B. the same holds for a SERVER profile.
#
# HOW IT STAYS OFF THE HOST. `kubectl` is a fake that records its argv and exits
# 0; `KUBECONFIG` points at a scratch file so the script needs no real cluster
# and no credential derivation reaches a real path. The suite never runs as root.
#
# Exit 0 iff every test passes. Mutates nothing outside its own scratch dir.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="${HERE}/patch-node-churn-capacity.sh"
PROFILES="${HERE}/../../phase0-bare-metal/profiles"

pass=0; fail=0
ok() { printf '  PASS  %s\n' "$1"; pass=$((pass + 1)); }
no() { printf '  FAIL  %s\n' "$1"; fail=$((fail + 1)); }

TMPROOT="$(mktemp -d)"
case "$TMPROOT" in
  /tmp/*|/var/tmp/*) ;;
  *) echo "FATAL: mktemp -d returned an unexpected path '${TMPROOT}'" >&2; exit 1 ;;
esac
cleanup() { rm -rf "$TMPROOT"; }
trap cleanup EXIT

KCALLS="${TMPROOT}/kubectl-calls"
: > "$KCALLS"
export KCALLS

FAKEBIN="${TMPROOT}/fakebin"
mkdir -p "$FAKEBIN"
# Records the full argv, one call per line, and exits 0 so the readiness wait
# breaks on the first iteration. Single-quoted: expanded when the fake runs.
printf '#!/usr/bin/env bash\nprintf "%%s\\n" "$*" >> "$KCALLS"; exit 0\n' > "${FAKEBIN}/kubectl"
chmod +x "${FAKEBIN}/kubectl"

# A scratch KUBECONFIG that EXISTS, so the script's `-f KUBECONFIG` guard passes
# and no derivation reaches a real path; its contents are never read (kubectl is
# a fake).
FAKE_KUBECONFIG="${TMPROOT}/kubeconfig"
printf 'apiVersion: v1\nkind: Config\n' > "$FAKE_KUBECONFIG"

run_patch() {  # run_patch PROFILE -> REPLY_OUT, REPLY_RC, and fresh KCALLS
  : > "$KCALLS"
  REPLY_OUT="$(KUBECONFIG="$FAKE_KUBECONFIG" NODE_WAIT_TIMEOUT=5 \
    PATH="${FAKEBIN}:${PATH}" "$SCRIPT" "$1" 2>&1)"
  REPLY_RC=$?
}

# assert_all_status DESCRIPTION — every recorded kubectl call that addresses a
# node carries --subresource=status. `--subresource=status` may sit before the
# node (the GET: `get --subresource=status node NAME`) or after it (the PATCH:
# `patch node NAME --subresource=status`), so the test is per-LINE: any line
# naming a node that lacks the flag anywhere is the regression.
assert_all_status() {
  local description="$1" bad
  bad="$(grep -F ' node ' "$KCALLS" | grep -v -- '--subresource=status' || true)"
  if [ -n "$bad" ]; then
    no "${description} (a node verb reached kubectl without --subresource=status)"
    printf '    %s\n' "$bad"
  else
    ok "$description"
  fi
}

for role_profile in "gmktec-xubuntu.env:agent" "poweredge-xubuntu.env:server"; do
  profile="${PROFILES}/${role_profile%%:*}"
  role="${role_profile##*:}"
  printf '== %s profile (%s): status-subresource reads only ==\n' "${role_profile%%:*}" "$role"
  run_patch "$profile"
  if [ "$REPLY_RC" -eq 0 ]; then
    ok "the ${role} patch run exits 0"
  else
    no "the ${role} patch run exits 0 (got ${REPLY_RC})"
    printf '%s\n' "$REPLY_OUT"
  fi
  # It actually issued node verbs (otherwise the assertion is vacuous).
  if grep -Eq '(get|patch) .*node ' "$KCALLS"; then
    ok "the ${role} run issued kubectl node verbs to assert over"
  else
    no "the ${role} run issued kubectl node verbs to assert over"
    cat "$KCALLS"
  fi
  assert_all_status "every ${role} kubectl node verb carries --subresource=status"
  # And specifically the patch and both gets are present with the flag.
  if grep -Eq 'get --subresource=status node ' "$KCALLS" \
     && grep -Eq 'patch node .* --subresource=status' "$KCALLS"; then
    ok "the ${role} run issued a status-subresource GET and a status-subresource PATCH"
  else
    no "the ${role} run issued a status-subresource GET and a status-subresource PATCH"
    cat "$KCALLS"
  fi
done

printf '\n%s passed, %s failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
