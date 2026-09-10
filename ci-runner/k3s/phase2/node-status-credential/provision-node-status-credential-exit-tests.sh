#!/usr/bin/env bash
# provision-node-status-credential-exit-tests.sh — prove
# ./provision-node-status-credential.sh WITHOUT a cluster, WITHOUT root and
# WITHOUT holding any credential: that its --dry-run prints the whole grant it
# would apply while executing nothing, that the grant is EXACTLY the
# least-privilege rule set and not one verb more, and that every refusal the
# design calls for fires and names its reason.
#
#   A. --dry-run against the COMMITTED gmktec-xubuntu profile prints the node,
#      the API endpoint, the destination path and the grant, exits 0, and
#      executes nothing at all;
#   B. LEAST PRIVILEGE, asserted on the rendered bytes: the ClusterRole's
#      `rules:` block is EXACTLY `get`+`patch` on `nodes/status` with
#      `resourceNames` naming only this node -- byte for byte, so a widened
#      verb, an extra resource or a dropped `resourceNames` fails here rather
#      than reaching a cluster;
#   C. the NEGATIVE half of §B, stated separately because a rule set can be
#      exactly right and the surrounding manifest still wrong: nothing in the
#      whole rendered manifest grants cluster-admin, `delete`, a wildcard, a
#      `list`/`watch` (which `resourceNames` cannot restrict), or the bare
#      `nodes` resource whose `spec` carries the node's own taint;
#   D. the placeholder is fully substituted and the node name is the PROFILE's,
#      so the grant can never be bound to the literal template string;
#   E. the refusals: a `server` profile, an empty CHURN_KUBECONFIG_FILE, an
#      empty CLUSTER_JOIN_ADDRESS, `--render-to` together with `--dry-run`, an
#      unknown option, two profiles, and no profile -- each non-zero, each
#      naming its reason;
#   F. the converge shape: the apply the plan promises is the idempotent
#      `--dry-run=client -o yaml | kubectl apply -f -` form;
#   G. the COMMITTED gmktec-xubuntu profile names a CHURN_KUBECONFIG_FILE that
#      is NOT the k3s server's admin kubeconfig -- the defect this whole
#      artifact exists to close.
#
# HOW IT STAYS OFF THE CLUSTER. Every case runs against a PATH of TRIPWIRES for
# `kubectl`, `install`, `sudo` and `base64`, so "executed nothing" is asserted
# rather than assumed. No case reaches the live path at all: the live path needs
# a cluster, and a suite that needed one could not run in CI or in a sandbox.
# Scratch profiles are copies of the committed one under this suite's own
# scratch directory; nothing here reads or writes any `/etc` on this machine.
#
# Exit 0 iff every test passes. Mutates nothing outside its own scratch dir.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="${HERE}/provision-node-status-credential.sh"
TEMPLATE="${HERE}/node-status-patch-rbac.yaml"
PROFILES="${HERE}/../../phase0-bare-metal/profiles"
AGENT_COMMITTED="${PROFILES}/gmktec-xubuntu.env"
SERVER_COMMITTED="${PROFILES}/poweredge-xubuntu.env"

# The committed agent profile's own values, restated here so an edit to either
# side has to be made deliberately in both.
AGENT_NODE="gmktec-xubuntu"
AGENT_TARGET="/etc/rancher/k3s/node-status-kubeconfig"
SERVER_ADMIN_KUBECONFIG="/etc/rancher/k3s/k3s.yaml"

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

TRIPWIRE="${TMPROOT}/tripwire"
: > "$TRIPWIRE"
export TRIPWIRE

# Every cluster-touching or host-mutating tool the script can reach for,
# replaced by a recorder that runs nothing.
TRIPBIN="${TMPROOT}/tripbin"
mkdir -p "$TRIPBIN"
for tool in kubectl install sudo base64; do
  # Single-quoted on purpose: the body is the FAKE's source, expanded when the
  # fake runs, not when this suite writes it.
  printf '#!/usr/bin/env bash\nprintf "%%s %%s\\n" "$(basename "$0")" "$*" >> "$TRIPWIRE"; exit 0\n' \
    > "${TRIPBIN}/${tool}"
  chmod +x "${TRIPBIN}/${tool}"
done

# run_dry ARGS... — run the script with the tripwire PATH first, capturing
# stdout+stderr into $OUT and the exit code into $RC.
OUT="${TMPROOT}/out"
RC=0
run_dry() {
  : > "$TRIPWIRE"
  PATH="${TRIPBIN}:${PATH}" "$SCRIPT" "$@" > "$OUT" 2>&1
  RC=$?
}

# The rendered manifest, sliced out of the script's own --dry-run output: from
# the banner that introduces it to the closing dry-run notice. Asserting on THIS
# rather than on a copy of the template rendered by the suite is deliberate --
# it is the bytes the script itself would have applied.
manifest_of() {  # manifest_of OUTPUT_FILE
  awk '/^== The rendered RBAC, in full/{f = 1; next} /^-- --dry-run:/{f = 0} f' "$1"
}

# The EFFECTIVE manifest: the same bytes with every comment line and blank line
# dropped. §C and §D's negative assertions read THIS rather than the raw
# manifest, and the distinction is load-bearing rather than cosmetic -- the
# template's header explains the grant in prose, so it necessarily says the
# words `cluster-admin`, `delete` and `gmktec-xubuntu` while granting none of
# them. A negative assertion run over the prose would fail on the very
# rationale that makes the file reviewable, and "delete the explanation to make
# the test pass" is the wrong repair. What the API server acts on is the
# comment-free document, and that is what is judged.
effective_of() {  # effective_of MANIFEST_FILE
  grep -v '^[[:space:]]*#' "$1" | grep -v '^[[:space:]]*$'
}

# The ClusterRole's rule block: `rules:` to the end of that document.
rules_of() {  # rules_of MANIFEST_FILE
  awk '/^rules:$/{r = 1} /^---$/{r = 0} r' "$1"
}

MANIFEST="${TMPROOT}/manifest.yaml"
EFFECTIVE="${TMPROOT}/effective.yaml"
RULES="${TMPROOT}/rules.yaml"

# ===========================================================================
printf '\n== A. --dry-run against the committed agent profile: the whole plan, and nothing executed ==\n'
# ===========================================================================
run_dry --dry-run "$AGENT_COMMITTED"

[ "$RC" -eq 0 ] \
  && ok "--dry-run exits 0" \
  || no "--dry-run exits 0 (got ${RC}); output: $(head -5 "$OUT")"

grep -qF "node:       ${AGENT_NODE}" "$OUT" \
  && ok "the plan names the node the profile names" \
  || no "the plan names the node the profile names"

grep -qF "destination: ${AGENT_TARGET}" "$OUT" \
  && ok "the plan names CHURN_KUBECONFIG_FILE as the destination" \
  || no "the plan names CHURN_KUBECONFIG_FILE as the destination"

grep -qF "grant:      get,patch on nodes/status, resourceNames=[${AGENT_NODE}] -- and nothing else" "$OUT" \
  && ok "the plan states the grant, scoped to this node" \
  || no "the plan states the grant, scoped to this node"

grep -q 'render-to:  (not given' "$OUT" \
  && ok "with no --render-to the plan says no kubeconfig is rendered" \
  || no "with no --render-to the plan says no kubeconfig is rendered"

[ ! -s "$TRIPWIRE" ] \
  && ok "--dry-run executed no kubectl, install, sudo or base64" \
  || no "--dry-run executed something: $(cat "$TRIPWIRE")"

# ===========================================================================
printf '\n== B. LEAST PRIVILEGE: the rule set is EXACTLY get+patch on this node'"'"'s nodes/status ==\n'
# ===========================================================================
manifest_of "$OUT" > "$MANIFEST"
effective_of "$MANIFEST" > "$EFFECTIVE"
rules_of "$EFFECTIVE" > "$RULES"

[ -s "$MANIFEST" ] \
  && ok "the plan prints the rendered manifest in full" \
  || no "the plan prints the rendered manifest in full"

EXPECTED_RULES="${TMPROOT}/expected-rules.yaml"
cat > "$EXPECTED_RULES" <<EXPECTED
rules:
  - apiGroups:
      - ""
    resources:
      - nodes/status
    resourceNames:
      - ${AGENT_NODE}
    verbs:
      - get
      - patch
EXPECTED

if diff -u "$EXPECTED_RULES" "$RULES" > "${TMPROOT}/rules.diff" 2>&1; then
  ok "the ClusterRole's rules are EXACTLY the least-privilege set, byte for byte"
else
  no "the ClusterRole's rules are EXACTLY the least-privilege set; diff:"
  sed 's/^/        /' "${TMPROOT}/rules.diff"
fi

# One rule and one only: a second rule could be perfectly narrow on its own and
# still widen the grant.
rule_count="$(grep -c '^  - apiGroups:$' "$RULES")"
[ "$rule_count" -eq 1 ] \
  && ok "the ClusterRole carries exactly ONE rule" \
  || no "the ClusterRole carries ${rule_count} rules, want 1"

# resourceNames is what makes a cluster-scoped ClusterRole per-node-bound. Its
# absence is the single highest-consequence drift this file guards.
grep -qxF "      - ${AGENT_NODE}" "$RULES" \
  && ok "resourceNames binds the rule to this node by name" \
  || no "resourceNames binds the rule to this node by name"

# ===========================================================================
printf '\n== C. the negative half: nothing in the manifest grants more than that ==\n'
# ===========================================================================
for forbidden in cluster-admin '"*"' "- '*'"; do
  grep -qF -e "$forbidden" "$EFFECTIVE" \
    && no "the effective manifest is free of '${forbidden}'" \
    || ok "the effective manifest is free of '${forbidden}'"
done

# The verbs `resourceNames` CANNOT restrict -- Kubernetes applies it only to
# requests naming a single object -- plus the mutating verbs no reconciler of a
# status field needs. Any of them would silently widen this to every node.
for verb in delete deletecollection list watch create update patch; do
  count="$(grep -cxF "      - ${verb}" "$EFFECTIVE")"
  case "$verb" in
    patch)
      [ "$count" -eq 1 ] \
        && ok "verb '${verb}' appears exactly once (it is half the intended grant)" \
        || no "verb '${verb}' appears ${count} times, want 1" ;;
    *)
      [ "$count" -eq 0 ] \
        && ok "verb '${verb}' is granted nowhere" \
        || no "verb '${verb}' is granted ${count} times, want 0" ;;
  esac
done

# The PARENT resource, whose `spec` carries `node-role/ci=pending:NoSchedule` --
# the one thing keeping CI work off this node today. The status subresource
# cannot reach it; a grant on bare `nodes` could.
grep -qxF '      - nodes' "$EFFECTIVE" \
  && no "the bare 'nodes' resource is granted nowhere (only nodes/status)" \
  || ok "the bare 'nodes' resource is granted nowhere (only nodes/status)"

# The binding points at the per-node ClusterRole this file renders, not at some
# other role that happens to exist on the cluster.
grep -qF "name: ci-runner-node-status-patcher-${AGENT_NODE}" "$EFFECTIVE" \
  && ok "the ClusterRoleBinding names the per-node ClusterRole" \
  || no "the ClusterRoleBinding names the per-node ClusterRole"

# The token Secret carries no `data:` -- this tree holds no credential, ever.
grep -qx 'data:' "$EFFECTIVE" \
  && no "the manifest carries no secret material of its own" \
  || ok "the manifest carries no secret material of its own"

# ===========================================================================
printf '\n== D. the placeholder is substituted, and with the PROFILE'"'"'s node name ==\n'
# ===========================================================================
grep -qF 'NODE_NAME_PLACEHOLDER' "$EFFECTIVE" \
  && no "no NODE_NAME_PLACEHOLDER survives into the rendered manifest" \
  || ok "no NODE_NAME_PLACEHOLDER survives into the rendered manifest"

grep -qF 'NODE_NAME_PLACEHOLDER' "$TEMPLATE" \
  && ok "the committed template still carries the placeholder (it is never applied as it stands)" \
  || no "the committed template still carries the placeholder"

grep -qF "name: node-status-patcher-${AGENT_NODE}" "$EFFECTIVE" \
  && ok "the ServiceAccount is named for this node" \
  || no "the ServiceAccount is named for this node"

# A DIFFERENT profile must render a DIFFERENT grant, or the substitution is not
# reading the profile at all.
OTHER_PROFILE="${TMPROOT}/other-node.env"
sed 's#^NODE_NAME=.*#NODE_NAME=some-other-node#' "$AGENT_COMMITTED" > "$OTHER_PROFILE"
run_dry --dry-run "$OTHER_PROFILE"
manifest_of "$OUT" | effective_of /dev/stdin > "${TMPROOT}/other-effective.yaml"
grep -qxF '      - some-other-node' "${TMPROOT}/other-effective.yaml" \
  && ok "a different profile binds the grant to that profile's node" \
  || no "a different profile binds the grant to that profile's node"
grep -qF "${AGENT_NODE}" "${TMPROOT}/other-effective.yaml" \
  && no "the other profile's manifest does not mention ${AGENT_NODE}" \
  || ok "the other profile's manifest does not mention ${AGENT_NODE}"

# ===========================================================================
printf '\n== E. the refusals ==\n'
# ===========================================================================
# refuses DESC EXPECTED_SUBSTRING ARGS...
refuses() {
  local desc="$1" want="$2"; shift 2
  run_dry "$@"
  if [ "$RC" -eq 0 ]; then
    no "${desc} (exited 0)"
  elif ! grep -qF "$want" "$OUT"; then
    no "${desc} (exited ${RC} but did not say '${want}'); output: $(tail -3 "$OUT")"
  elif [ -s "$TRIPWIRE" ]; then
    no "${desc} (refused, but executed: $(cat "$TRIPWIRE"))"
  else
    ok "${desc}"
  fi
}

refuses "a server profile is refused, naming the admin file it already has" \
  "a server patches node status through its own ${SERVER_ADMIN_KUBECONFIG}" \
  --dry-run "$SERVER_COMMITTED"

NO_TARGET="${TMPROOT}/no-target.env"
sed 's#^CHURN_KUBECONFIG_FILE=.*#CHURN_KUBECONFIG_FILE=#' "$AGENT_COMMITTED" > "$NO_TARGET"
refuses "an empty CHURN_KUBECONFIG_FILE is refused, naming the key" \
  "CHURN_KUBECONFIG_FILE is empty" \
  --dry-run "$NO_TARGET"

NO_API="${TMPROOT}/no-api.env"
sed 's#^CLUSTER_JOIN_ADDRESS=.*#CLUSTER_JOIN_ADDRESS=#' "$AGENT_COMMITTED" > "$NO_API"
# The shared parser refuses an agent naming no join address before this script
# reaches its own check, which is the correct layering -- assert the refusal,
# not which layer produced it.
refuses "an agent profile with no CLUSTER_JOIN_ADDRESS is refused" \
  "CLUSTER_JOIN_ADDRESS" \
  --dry-run "$NO_API"

refuses "--render-to together with --dry-run is refused as mutually exclusive" \
  "mutually exclusive" \
  --dry-run --render-to "${TMPROOT}/would-be-credential" "$AGENT_COMMITTED"

[ ! -e "${TMPROOT}/would-be-credential" ] \
  && ok "the refused --render-to path was not created" \
  || no "the refused --render-to path was created"

refuses "an unknown option is refused" \
  "unknown option" \
  --dry-run --nope "$AGENT_COMMITTED"

refuses "two profiles are refused rather than one silently winning" \
  "more than one profile given" \
  --dry-run "$AGENT_COMMITTED" "$AGENT_COMMITTED"

refuses "no profile at all is refused" \
  "no profile given" \
  --dry-run

# ===========================================================================
printf '\n== F. the converge shape is the idempotent dry-run=client | apply form ==\n'
# ===========================================================================
run_dry --dry-run "$AGENT_COMMITTED"
grep -qF 'kubectl apply --dry-run=client -o yaml -f - | kubectl apply -f -' "$OUT" \
  && ok "the plan promises the --dry-run=client -o yaml | kubectl apply -f - converge" \
  || no "the plan promises the --dry-run=client -o yaml | kubectl apply -f - converge"

grep -qF 'idempotent; re-running changes nothing' "$OUT" \
  && ok "the plan states the converge is idempotent" \
  || no "the plan states the converge is idempotent"

# ===========================================================================
printf '\n== G. the committed profile does not point at the server'"'"'s admin file ==\n'
# ===========================================================================
if grep -qxF "CHURN_KUBECONFIG_FILE=${AGENT_TARGET}" "$AGENT_COMMITTED"; then
  ok "${AGENT_NODE} names ${AGENT_TARGET}"
else
  no "${AGENT_NODE} names ${AGENT_TARGET} (found: $(grep '^CHURN_KUBECONFIG_FILE=' "$AGENT_COMMITTED"))"
fi

grep -qxF "CHURN_KUBECONFIG_FILE=${SERVER_ADMIN_KUBECONFIG}" "$AGENT_COMMITTED" \
  && no "${AGENT_NODE} does NOT point at the server's admin kubeconfig" \
  || ok "${AGENT_NODE} does NOT point at the server's admin kubeconfig"

# ---------------------------------------------------------------------------
printf '\n== %d passed, %d failed ==\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
