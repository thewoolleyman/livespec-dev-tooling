#!/usr/bin/env bash
# gates-credential-exit-tests.sh — prove the R4.S2 delegated-gate credential
# artifacts (livespec-dev-tooling-y8em) WITHOUT touching any host, contacting any
# cluster, or holding a real credential:
#
#   A. ../reconstruct/render-sa-kubeconfig.sh DEFAULTS the API-server URL to
#      https://127.0.0.1:6443 when --server is omitted, so the existing
#      Kueue-webhook-probe caller is unchanged by this slice;
#   B. --server OVERRIDES it, writing exactly the given URL — the case that makes
#      a kubeconfig usable off the control-plane node;
#   C. an unknown argument is still refused, so adding --server did not turn the
#      parser permissive;
#   D. gates-rbac.yaml's Role grants NOTHING outside create/get/list/watch on
#      jobs and pods plus get on pods/log: no `delete`, no `secrets`, no
#      wildcard, and nothing cluster-scoped anywhere in the manifest;
#   E. the manifest does NOT declare the gates Namespace, which is owned by
#      ../kueue/cluster-queue-gates.yaml — one live object, one committed source.
#
# HOW IT STAYS OFF THE HOST AND OFF THE CLUSTER. `kubectl` is a FAKE on this
# suite's own PATH that answers the two jsonpath reads the renderer makes with
# fixture bytes this suite invents; no kubeconfig is read and no API server is
# contacted. `chown` is faked too, because the renderer chowns the file to
# root:<group> and this suite must pass as an unprivileged user. Every path
# written is inside this suite's scratch directory.
#
# Exit 0 iff every test passes. Mutates nothing outside its own scratch dir.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RENDERER="${SCRIPT_DIR}/../reconstruct/render-sa-kubeconfig.sh"
MANIFEST="${SCRIPT_DIR}/gates-rbac.yaml"
SCRATCH="$(mktemp -d)"
trap 'rm -rf "${SCRATCH}"' EXIT

failures=0
pass() { echo "  PASS  $1"; }
fail() { echo "  FAIL  $1"; failures=$((failures + 1)); }

[ -x "${RENDERER}" ] || { echo "FATAL: ${RENDERER} not found or not executable" >&2; exit 1; }
[ -f "${MANIFEST}" ] || { echo "FATAL: ${MANIFEST} not found" >&2; exit 1; }

# --- the fake kubectl + chown the renderer runs against -----------------------
FAKEBIN="${SCRATCH}/bin"
mkdir -p "${FAKEBIN}"
# token / ca.crt are fixture strings invented here, base64 of "fixture-token"
# and "fixture-ca". The renderer base64 -d's the token and passes ca.crt through.
cat > "${FAKEBIN}/kubectl" <<'FAKE'
#!/usr/bin/env bash
# The renderer passes the jsonpath as ONE argv element, `jsonpath={...}`,
# because `-o jsonpath='{.data.token}'` is two words, not three.
for a in "$@"; do
  case "$a" in
    jsonpath=*ca*)    printf 'Zml4dHVyZS1jYQ=='; exit 0 ;;
    jsonpath=*token*) printf 'Zml4dHVyZS10b2tlbg=='; exit 0 ;;
  esac
done
exit 0
FAKE
cat > "${FAKEBIN}/chown" <<'FAKE'
#!/usr/bin/env bash
exit 0
FAKE
chmod 0755 "${FAKEBIN}/kubectl" "${FAKEBIN}/chown"

render() {
  # Runs the renderer with the fakes ahead of the real PATH.
  PATH="${FAKEBIN}:${PATH}" KUBECONFIG="${SCRATCH}/fake-admin.kubeconfig" \
    "${RENDERER}" --namespace gates --secret gate-submitter-token \
      --user gate-submitter --dest "$1" "${@:2}" 2>&1
}

echo "== A. --server omitted defaults to the loopback URL =="
dest_a="${SCRATCH}/default.kubeconfig"
if out="$(render "${dest_a}")"; then
  if grep -qF 'server: https://127.0.0.1:6443' "${dest_a}"; then
    pass "default server is https://127.0.0.1:6443"
  else
    fail "default server line absent; got: $(grep -F 'server:' "${dest_a}" || echo NONE)"
  fi
else
  fail "renderer exited non-zero with --server omitted: ${out}"
fi

echo "== B. --server overrides it verbatim =="
dest_b="${SCRATCH}/override.kubeconfig"
url='https://poweredge-xubuntu.perch-rudd.ts.net:6443'
if out="$(render "${dest_b}" --server "${url}")"; then
  if grep -qF "server: ${url}" "${dest_b}"; then
    pass "overridden server is written verbatim"
  else
    fail "override not written; got: $(grep -F 'server:' "${dest_b}" || echo NONE)"
  fi
  if grep -qF '127.0.0.1' "${dest_b}"; then
    fail "loopback default leaked into an overridden kubeconfig"
  else
    pass "no loopback remnant in the overridden kubeconfig"
  fi
else
  fail "renderer exited non-zero with --server supplied: ${out}"
fi

echo "== C. an unknown argument is still refused =="
if render "${SCRATCH}/never.kubeconfig" --bogus x >/dev/null 2>&1; then
  fail "unknown argument accepted"
else
  pass "unknown argument refused"
fi

echo "== D. the Role's grant is exactly the least-privilege set =="
# Extract the Role document only: from its `kind: Role` line to the next `---`.
role_doc="$(awk '/^kind: Role$/{f=1} f{print} f&&/^---$/{exit}' "${MANIFEST}")"
if [ -z "${role_doc}" ]; then
  fail "no Role document found in ${MANIFEST}"
else
  got_verbs="$(printf '%s\n' "${role_doc}" | grep -E '^\s+verbs:' | sed 's/^[[:space:]]*//' | tr -d ' ')"
  want_verbs=$'verbs:["create","get","list","watch"]\nverbs:["create","get","list","watch"]\nverbs:["get"]'
  if [ "${got_verbs}" = "${want_verbs}" ]; then
    pass "Role verb set is exactly create/get/list/watch, create/get/list/watch, get"
  else
    fail "Role verb set drifted; got:"$'\n'"${got_verbs}"
  fi
  got_res="$(printf '%s\n' "${role_doc}" | grep -E '^\s+resources:' | sed 's/^[[:space:]]*//' | tr -d ' ')"
  want_res=$'resources:["jobs"]\nresources:["pods"]\nresources:["pods/log"]'
  if [ "${got_res}" = "${want_res}" ]; then
    pass "Role resources are exactly jobs, pods, pods/log"
  else
    fail "Role resources drifted; got:"$'\n'"${got_res}"
  fi
  forbidden_found=0
  for forbidden in delete deletecollection patch update escalate bind impersonate; do
    if printf '%s\n' "${role_doc}" | grep -qE "\"${forbidden}\""; then
      fail "Role grants the forbidden verb ${forbidden}"
      forbidden_found=1
    fi
  done
  [ "${forbidden_found}" -eq 0 ] &&
    pass "Role grants no delete/deletecollection/patch/update/escalate/bind/impersonate"
  if printf '%s\n' "${role_doc}" | grep -qE '"\*"'; then
    fail "Role carries a wildcard"
  else
    pass "Role carries no wildcard"
  fi
fi
if grep -qE '"secrets"|resources:.*secrets' "${MANIFEST}"; then
  fail "manifest grants access to secrets"
else
  pass "manifest grants nothing on secrets"
fi
if grep -qE '^kind: Cluster(Role|RoleBinding)$' "${MANIFEST}"; then
  fail "manifest declares a cluster-scoped RBAC object"
else
  pass "manifest declares nothing cluster-scoped"
fi

echo "== E. the manifest does not re-declare the gates Namespace =="
if grep -qE '^kind: Namespace$' "${MANIFEST}"; then
  fail "manifest re-declares the gates Namespace (owned by ../kueue/cluster-queue-gates.yaml)"
else
  pass "Namespace is left to its single owning manifest"
fi

echo
if [ "${failures}" -eq 0 ]; then
  echo "ALL TESTS PASSED"
  exit 0
fi
echo "${failures} TEST(S) FAILED"
exit 1
