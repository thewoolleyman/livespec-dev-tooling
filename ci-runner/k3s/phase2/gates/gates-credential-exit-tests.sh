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
#      jobs and pods, get on pods/log, and CREATE ALONE on secrets: no `delete`,
#      no read verb on secrets, no wildcard, and nothing cluster-scoped anywhere
#      in the manifest;
#   E. the manifest does NOT declare the gates Namespace, which is owned by
#      ../kueue/cluster-queue-gates.yaml — one live object, one committed source;
#   F. the manifest declares exactly ONE Secret — the ServiceAccount token it has
#      always carried — so the private-sibling installation token the gate client
#      creates per run exists in no committed source and nothing standing holds it.
#
# WHY D NOW ALLOWS ONE SECRETS VERB (work-item livespec-dev-tooling-7kvh2d). It
# used to assert NO verb on secrets at all. A delegated push whose consumer names
# a PRIVATE cross-repo sibling needs a read-only GitHub App installation token
# inside its gate Job, and the token must not be in the rendered manifest — the
# API server stores that text and hands it back to any reader. The client
# therefore creates a per-run Secret owner-referenced to the Job, and `create` is
# the whole grant: garbage collection removes it, so no `delete`; the client only
# ever writes, so no `get`/`list`/`watch` — and a read verb here would let any
# gate run read every other run's token. The arms below assert that narrowing
# POSITIVELY, by enumerating the exact verb set per resource, rather than by the
# blanket "no secrets anywhere" grep they replace: a blanket refusal cannot tell
# `create` from `*`, so it would have had to be deleted rather than tightened.
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
  # The verb lines and the resource lines are compared as ORDERED sequences
  # against the whole expected set, so a rule that drifts, is reordered, or is
  # ADDED fails here. `secrets` is last because it was added last, and its one
  # verb is the narrowest line in the file.
  got_verbs="$(printf '%s\n' "${role_doc}" | grep -E '^\s+verbs:' | sed 's/^[[:space:]]*//' | tr -d ' ')"
  want_verbs=$'verbs:["create","get","list","watch"]\nverbs:["create","get","list","watch"]\nverbs:["get"]\nverbs:["create"]'
  if [ "${got_verbs}" = "${want_verbs}" ]; then
    pass "Role verb set is exactly create/get/list/watch, create/get/list/watch, get, create"
  else
    fail "Role verb set drifted; got:"$'\n'"${got_verbs}"
  fi
  got_res="$(printf '%s\n' "${role_doc}" | grep -E '^\s+resources:' | sed 's/^[[:space:]]*//' | tr -d ' ')"
  want_res=$'resources:["jobs"]\nresources:["pods"]\nresources:["pods/log"]\nresources:["secrets"]'
  if [ "${got_res}" = "${want_res}" ]; then
    pass "Role resources are exactly jobs, pods, pods/log, secrets"
  else
    fail "Role resources drifted; got:"$'\n'"${got_res}"
  fi
  # The two sequences above agree only if the SECRETS rule is the one carrying
  # the bare `create`. Pairing them explicitly closes the gap: two orderings
  # could each match their own expectation while naming the wrong pairs.
  secrets_rule="$(printf '%s\n' "${role_doc}" \
    | grep -A2 -F 'resources: ["secrets"]' | grep -E '^\s+verbs:' \
    | sed 's/^[[:space:]]*//' | tr -d ' ')"
  if [ "${secrets_rule}" = 'verbs:["create"]' ]; then
    pass "the secrets rule grants create and nothing else — no read verb, no delete"
  else
    fail "the secrets rule is not create-only; got: ${secrets_rule:-NONE}"
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
# The CONTROL for the three arms above: the one secrets grant lives in the Role
# and nowhere else in the file. A second rule, or one smuggled into a document
# this suite's Role extraction does not read, is caught here.
if [ "$(grep -cF 'resources: ["secrets"]' "${MANIFEST}")" = "1" ]; then
  pass "the manifest carries exactly one secrets grant, in the Role"
else
  fail "the manifest carries $(grep -cF 'resources: ["secrets"]' "${MANIFEST}") secrets grants"
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

echo "== F. the manifest declares no Secret beyond the ServiceAccount token =="
# The `create` grant above exists so a per-run token Secret can be made AT
# SUBMIT TIME and garbage-collected with its Job. A Secret for it declared HERE
# would be the standing credential the contract forbids: converge re-applies
# this file on every boot, so anything in it persists for as long as the node
# does. The ServiceAccount token is the one Secret this manifest has always
# carried, and it holds no GitHub credential.
#
# The credential grep runs on the DECLARED YAML only, with comment lines
# stripped: this file's own header explains the App token at length, and a
# prose mention is the opposite of a credential in source.
declared_yaml="$(grep -vE '^[[:space:]]*#' "${MANIFEST}")"
secret_kinds="$(printf '%s\n' "${declared_yaml}" | grep -cE '^kind: Secret$')"
sa_token_type="$(printf '%s\n' "${declared_yaml}" \
  | grep -cF 'type: kubernetes.io/service-account-token')"
if [ "${secret_kinds}" != "1" ]; then
  fail "the manifest declares ${secret_kinds} Secret documents; exactly one is expected"
elif [ "${sa_token_type}" != "1" ]; then
  fail "the one declared Secret is not a ServiceAccount token — a standing credential?"
elif printf '%s\n' "${declared_yaml}" \
     | grep -qiE 'github|ghs_|github_pat_|^[[:space:]]*(data|stringData):'; then
  fail "the declared YAML carries credential material: $(printf '%s\n' "${declared_yaml}" | grep -niE 'github|ghs_|^[[:space:]]*(data|stringData):')"
else
  pass "the only Secret is the ServiceAccount token; no GitHub credential is in source"
fi

echo
if [ "${failures}" -eq 0 ]; then
  echo "ALL TESTS PASSED"
  exit 0
fi
echo "${failures} TEST(S) FAILED"
exit 1
