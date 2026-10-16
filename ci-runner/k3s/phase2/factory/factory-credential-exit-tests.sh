#!/usr/bin/env bash
# factory-credential-exit-tests.sh — prove the `factory` namespace's
# sandbox-launcher credential artifacts (livespec-dev-tooling-sqobqv) WITHOUT
# touching any host, contacting any cluster, or holding a real credential.
#
# THE SIBLING OF ../gates/gates-credential-exit-tests.sh, and deliberately the
# same shape and the same technique — the gates credential is the pattern this
# one follows, and a suite that proved it differently would be proving something
# else. The arms:
#
#   A. ../reconstruct/render-sa-kubeconfig.sh writes a supplied --server
#      VERBATIM for the sandbox-launcher identity. This is the whole difference
#      between this credential and the on-host Kueue-webhook probe: the factory
#      kubeconfig LEAVES the control-plane node, so the loopback the renderer
#      defaults to would name the READER's own machine;
#   B. no loopback remnant survives in an overridden kubeconfig — a credential
#      carrying both addresses is one that looks right and reaches nothing;
#   C. the rendered file names the sandbox-launcher user and context, so the
#      token is presented as the identity ./factory-rbac.yaml grants rather than
#      as whatever the last caller rendered;
#   D. an unknown argument is still refused. `--server` exists only because a
#      kubeconfig that leaves the host needs it, and adding a flag is the moment
#      a parser becomes permissive — a permissive one accepts a MISSPELLED
#      --server silently, leaving the loopback default in a credential nobody
#      can use and no error anywhere;
#   E. the boot converge's render and ./factory-rbac.yaml AGREE on the namespace,
#      the ServiceAccount and the token Secret. A render naming a Secret the
#      manifest does not request waits out the renderer's 60-second token poll
#      and then fails, on a boot path where the failure is a credential that is
#      simply absent.
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
CONVERGE="${SCRIPT_DIR}/../reconstruct/converge-ci-stack.sh"
MANIFEST="${SCRIPT_DIR}/factory-rbac.yaml"
SCRATCH="$(mktemp -d)"
trap 'rm -rf "${SCRATCH}"' EXIT

# The identity ./factory-rbac.yaml declares. Named once here and checked
# against the manifest and the converge in arm E, so a rename of the
# ServiceAccount cannot leave the render pointing at the old name.
NAMESPACE=factory
SERVICE_ACCOUNT=sandbox-launcher
TOKEN_SECRET=sandbox-launcher-token

failures=0
pass() { echo "  PASS  $1"; }
fail() { echo "  FAIL  $1"; failures=$((failures + 1)); }

[ -x "${RENDERER}" ] || { echo "FATAL: ${RENDERER} not found or not executable" >&2; exit 1; }
[ -f "${MANIFEST}" ] || { echo "FATAL: ${MANIFEST} not found" >&2; exit 1; }
[ -f "${CONVERGE}" ] || { echo "FATAL: ${CONVERGE} not found" >&2; exit 1; }

# --- the fake kubectl + chown the renderer runs against -----------------------
FAKEBIN="${SCRATCH}/bin"
mkdir -p "${FAKEBIN}"
# token / ca.crt are fixture strings invented here, base64 of "fixture-token"
# and "fixture-ca". The renderer base64 -d's the token and passes ca.crt through.
cat > "${FAKEBIN}/kubectl" << 'FAKE'
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
cat > "${FAKEBIN}/chown" << 'FAKE'
#!/usr/bin/env bash
exit 0
FAKE
chmod 0755 "${FAKEBIN}/kubectl" "${FAKEBIN}/chown"

render() {
  # Runs the renderer with the fakes ahead of the real PATH, as the factory
  # identity. The destination is the first argument; everything after it is
  # passed through, which is how the arms below vary --server alone.
  PATH="${FAKEBIN}:${PATH}" KUBECONFIG="${SCRATCH}/fake-admin.kubeconfig" \
    "${RENDERER}" --namespace "${NAMESPACE}" --secret "${TOKEN_SECRET}" \
    --user "${SERVICE_ACCOUNT}" --dest "$1" "${@:2}" 2>&1
}

# The tailnet address the API server holds a SAN for, which is the address this
# credential has to carry. A FIXTURE here, not a lookup: this suite proves the
# renderer writes what it is given, and the converge's own value is checked
# against the gates variable in arm E.
TAILNET_URL='https://poweredge-xubuntu.perch-rudd.ts.net:6443'
LOOPBACK_URL='https://127.0.0.1:6443'

echo "== A. --server is written verbatim for the sandbox-launcher identity =="
dest_a="${SCRATCH}/factory.kubeconfig"
if out="$(render "${dest_a}" --server "${TAILNET_URL}")"; then
  if grep -qF "server: ${TAILNET_URL}" "${dest_a}"; then
    pass "the tailnet API address is written verbatim"
  else
    fail "tailnet address not written; got: $(grep -F 'server:' "${dest_a}" || echo NONE)"
  fi
else
  fail "renderer exited non-zero with --server supplied: ${out}"
fi

echo "== B. no loopback remnant survives in the overridden kubeconfig =="
if [ -f "${dest_a}" ]; then
  if grep -qF '127.0.0.1' "${dest_a}"; then
    fail "loopback default leaked into a credential that leaves this host"
  else
    pass "no loopback remnant in the rendered credential"
  fi
  # The control arm: omitting --server takes the loopback, which is what makes
  # arm A load-bearing rather than incidental. A renderer that ignored --server
  # would pass A only if its default happened to match, and this proves it does
  # not.
  dest_default="${SCRATCH}/default.kubeconfig"
  if render "${dest_default}" > /dev/null; then
    if grep -qF "server: ${LOOPBACK_URL}" "${dest_default}"; then
      pass "the omitted-server default is still the loopback, so arm A proves the override"
    else
      fail "omitted --server no longer defaults to ${LOOPBACK_URL}; arm A proves nothing"
    fi
  else
    fail "renderer exited non-zero with --server omitted"
  fi
fi

echo "== C. the rendered file presents the sandbox-launcher identity =="
if [ -f "${dest_a}" ]; then
  for marker in "name: ${SERVICE_ACCOUNT}" "current-context: ${SERVICE_ACCOUNT}@k3s"; do
    if grep -qF "${marker}" "${dest_a}"; then
      pass "rendered credential carries \`${marker}\`"
    else
      fail "rendered credential is missing \`${marker}\`"
    fi
  done
fi

echo "== D. an unknown argument is still refused =="
if render "${SCRATCH}/never.kubeconfig" --bogus x > /dev/null 2>&1; then
  fail "unknown argument accepted"
else
  pass "unknown argument refused"
fi

echo "== E. the converge's render agrees with this manifest's identity =="
for want in \
  "--namespace ${NAMESPACE}" \
  "--secret ${TOKEN_SECRET}" \
  "--user ${SERVICE_ACCOUNT}" \
  '--dest "${FACTORY_KUBECONFIG}"' \
  '--server "${FACTORY_SERVER}"'; do
  if grep -qF -- "${want}" "${CONVERGE}"; then
    pass "converge renders with \`${want}\`"
  else
    fail "converge does not render with \`${want}\`"
  fi
done
for want in "name: ${SERVICE_ACCOUNT}" "name: ${TOKEN_SECRET}" "namespace: ${NAMESPACE}"; do
  if grep -qF -- "${want}" "${MANIFEST}"; then
    pass "manifest declares \`${want}\`"
  else
    fail "manifest does not declare \`${want}\`"
  fi
done
# ONE literal for this node's tailnet address in the whole converge: the
# factory credential resolves its server FROM the gates one rather than
# respelling it, so the two cannot drift onto different addresses.
if grep -qF 'FACTORY_SERVER="${CI_FACTORY_SERVER:-${GATES_SERVER}}"' "${CONVERGE}"; then
  pass "the factory API address is resolved from the gates one, not respelled"
else
  fail "the factory API address must resolve from GATES_SERVER so the fleet keeps one literal"
fi

echo
if [ "${failures}" -eq 0 ]; then
  echo "ALL TESTS PASSED"
  exit 0
fi
echo "${failures} TEST(S) FAILED"
exit 1
