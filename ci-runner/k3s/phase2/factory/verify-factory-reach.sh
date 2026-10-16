#!/usr/bin/env bash
# verify-factory-reach.sh — prove that a `factory`-namespace pod ON A NAMED NODE
# reaches the beads Dolt tenant and the telemetry receiver, and that the node can
# pull the fleet sandbox image (livespec-dev-tooling-sszvvw, livespec plan
# factory-worker-nodes-gitops, epic livespec-sqvj7p, plan assertion 7).
#
# WHY A SHORT-LIVED JOB AND NOT A PROBE FROM THE HOST. Every bound that could
# make the answer "no" belongs to the POD and not to the host: ./factory-rbac.yaml's
# `sandbox-launcher` identity, ./factory-namespace.yaml's default-deny
# `factory-egress` NetworkPolicy and its ResourceQuota, the node's taint, and the
# node's own image pull path. A host-side `nc` from poweredge answers a different
# question entirely, which is why ./DERIVATION.md "The tailnet" — where the hp
# Docker-sandbox measurements of 2026-10-13 are recorded — defers the per-node
# reach question to this check by name.
#
# WHY THE PROBE IS EMBEDDED FROM A SEPARATE FILE. ./factory-reach-probe.sh is
# the verdict, and it is committed on its own so a test can run the same bytes
# the pod runs. It is embedded VERBATIM here rather than mounted, because a
# ConfigMap is one more object to converge on a node whose datastore is a tmpfs.
#
# WHY THE ENDPOINTS AND THE IMAGE ARE NEVER SPELLED IN THIS FILE. The endpoints
# come from ./factory-reach-endpoints.env (or `--endpoint` / `--endpoints`), and
# the image is READ from this repository's own `.github/workflows/ci.yml`
# `container:` block — the fleet sandbox image pin, which the release fan-out
# rewrites there and which moves with every release. A constant for either would
# make this check prove a reach to an endpoint nobody uses, with a toolchain
# nobody runs, while still printing green. ../gates/render-gate-job.sh reads the
# image the same way and for the same reason.
#
# Usage:
#   verify-factory-reach.sh --node NAME [--dry-run]
#                           [--endpoints FILE] [--endpoint NAME=HOST:PORT]...
#                           [--image REF] [--workflow FILE]
#                           [--job-name NAME] [--timeout-seconds N]
#
# `--dry-run` prints the manifest to stdout and contacts NOTHING — no cluster,
# no endpoint, no registry. Without it the Job is submitted with `kubectl`, its
# logs are printed, and the exit code is the verdict:
#
#   0  every endpoint answered and the pod ran, so the image pulled too
#   1  the first unreachable endpoint, named; or a pull that failed, naming the
#      image and the pod's waiting reason; or a Job that produced NO verdict
#   2  a usage or configuration error (an unknown argument, a malformed
#      endpoint, an unresolvable image) — nothing was submitted
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROBE="${SCRIPT_DIR}/factory-reach-probe.sh"
endpoints_file="${SCRIPT_DIR}/factory-reach-endpoints.env"
workflow="${SCRIPT_DIR}/../../../../.github/workflows/ci.yml"

# The namespace, the identity and the taint key are ./factory-namespace.yaml's,
# ./factory-rbac.yaml's and the committed hp profile's respectively. They are
# named here because this script must land INSIDE those bounds; a rename in one
# of those files is meant to break this check rather than silently escape it.
NAMESPACE=factory
SERVICE_ACCOUNT=sandbox-launcher
# Quoted because an unquoted `a/b` reads as arithmetic to shellcheck (SC2100),
# and a taint key that silently became a division is a Job that tolerates
# nothing.
TOLERATION_KEY="node-role/ci"
# A well-known Kubernetes label and not this tree's to choose; a variable only
# so the heredoc below reads as one line per field.
HOSTNAME_LABEL="kubernetes.io/hostname"
# The column the probe's block scalar starts at, which the manifest's own
# nesting fixes. Named once because the indenting `sed` and the reader that
# dedents it have to agree.
PROBE_INDENT="              "

node=""
dry_run=0
image=""
job_name=""
timeout_seconds=300
overrides=()

fatal() {
  echo "FATAL: $1" >&2
  exit "${2:-2}"
}

while [ $# -gt 0 ]; do
  case "$1" in
    --node) node="$2"; shift 2 ;;
    --dry-run) dry_run=1; shift ;;
    --endpoints) endpoints_file="$2"; shift 2 ;;
    --endpoint) overrides+=("$2"); shift 2 ;;
    --image) image="$2"; shift 2 ;;
    --workflow) workflow="$2"; shift 2 ;;
    --job-name) job_name="$2"; shift 2 ;;
    --timeout-seconds) timeout_seconds="$2"; shift 2 ;;
    *) fatal "unknown argument $1" ;;
  esac
done

[ -n "${node}" ] || fatal "--node is required: this check proves ONE node's reach"
[ -f "${PROBE}" ] || fatal "probe not found: ${PROBE}"
[ -f "${endpoints_file}" ] || fatal "endpoint configuration not found: ${endpoints_file}"

# --- the endpoints ------------------------------------------------------------
# Validated BEFORE anything is submitted: a typo in a target renders a Job that
# probes an address nobody meant, and a Job that cannot answer the question is
# worse than one that never ran, because it answers it wrongly.
endpoint_names=()
endpoint_specs=()

add_endpoint() {
  local spec="$1" name target host port index
  name="${spec%%=*}"
  target="${spec#*=}"
  [ "${name}" != "${spec}" ] || fatal "endpoint must be NAME=HOST:PORT; got '${spec}'"
  case "${name}" in
    "" | *[!a-z0-9-]*) fatal "endpoint name must be lowercase [a-z0-9-]; got '${name}'" ;;
  esac
  host="${target%:*}"
  port="${target##*:}"
  [ "${port}" != "${target}" ] && [ -n "${host}" ] \
    || fatal "endpoint ${name} must name HOST:PORT; got '${target}'"
  case "${port}" in
    "" | *[!0-9]*) fatal "endpoint ${name} must name a numeric port; got '${port}'" ;;
  esac
  for index in "${!endpoint_names[@]}"; do
    if [ "${endpoint_names[index]}" = "${name}" ]; then
      endpoint_specs[index]="${name}=${target}"
      return 0
    fi
  done
  endpoint_names+=("${name}")
  endpoint_specs+=("${name}=${target}")
}

# Surrounding whitespace is stripped before anything is parsed: a trailing space
# in the committed configuration would otherwise reach the port check and be
# reported as a non-numeric port, which sends the reader hunting for a typo that
# is not there.
trim() {
  local value="$1"
  value="${value#"${value%%[![:space:]]*}"}"
  printf '%s' "${value%"${value##*[![:space:]]}"}"
}

while IFS= read -r line || [ -n "${line}" ]; do
  line="$(trim "${line}")"
  case "${line}" in "" | "#"*) continue ;; esac
  add_endpoint "${line}"
done < "${endpoints_file}"

if [ "${#overrides[@]}" -gt 0 ]; then
  for override in "${overrides[@]}"; do
    add_endpoint "${override}"
  done
fi

[ "${#endpoint_specs[@]}" -gt 0 ] \
  || fatal "no endpoints to probe: ${endpoints_file} names none and no --endpoint was given"

# --- the image ----------------------------------------------------------------
# Every `image:` that is the first field of a `container:` block, exactly as
# ../gates/render-gate-job.sh resolves it. SEVERAL distinct images is a REFUSAL
# rather than a pick: which toolchain the probe should run is then a real
# question, and guessing it wrong proves a pull nobody performs.
if [ -z "${image}" ]; then
  [ -f "${workflow}" ] || fatal "cannot resolve the sandbox image: ${workflow} not found"
  mapfile -t images < <(grep -A1 -E '^[[:space:]]*container:[[:space:]]*$' "${workflow}" \
    | grep -oE 'image:[[:space:]]*[^[:space:]]+' \
    | sed -E 's/^image:[[:space:]]*//' | sort -u)
  [ "${#images[@]}" -eq 1 ] \
    || fatal "${workflow} declares ${#images[@]} distinct container images; refusing to guess"
  image="${images[0]}"
fi

[ -n "${job_name}" ] || job_name="factory-reach-${node}"

# --- the manifest -------------------------------------------------------------
# The requests and limits are deliberate and small: ./factory-namespace.yaml's
# ResourceQuota declares BOTH `requests.*` and `limits.*`, so a pod that omits
# either is rejected at admission — and this pod opens two sockets, so it needs
# a slot rather than a share.
render() {
  cat << MANIFEST
apiVersion: batch/v1
kind: Job
metadata:
  name: ${job_name}
  namespace: ${NAMESPACE}
  labels:
    app.kubernetes.io/managed-by: livespec-ci-runner-factory
    livespec.workitem: sszvvw
spec:
  backoffLimit: 0
  ttlSecondsAfterFinished: 600
  template:
    metadata:
      labels:
        app.kubernetes.io/managed-by: livespec-ci-runner-factory
        livespec.workitem: sszvvw
    spec:
      restartPolicy: Never
      serviceAccountName: ${SERVICE_ACCOUNT}
      nodeSelector:
        ${HOSTNAME_LABEL}: ${node}
      tolerations:
        - key: ${TOLERATION_KEY}
          operator: Exists
          effect: NoSchedule
      containers:
        - name: reach
          image: ${image}
          command:
            - /bin/bash
            - -c
          args:
            - |
$(sed "s/^./${PROBE_INDENT}&/" "${PROBE}")
            - factory-reach-probe
$(printf '            - %s\n' "${endpoint_specs[@]}")
          resources:
            requests:
              cpu: 100m
              memory: 128Mi
            limits:
              cpu: 500m
              memory: 256Mi
MANIFEST
}

manifest="$(render)"

if [ "${dry_run}" -eq 1 ]; then
  printf '%s\n' "${manifest}"
  exit 0
fi

# --- the live run -------------------------------------------------------------
command -v kubectl > /dev/null 2>&1 || fatal "kubectl not found: a live run needs it"

cleanup() {
  kubectl delete job "${job_name}" -n "${NAMESPACE}" --ignore-not-found > /dev/null 2>&1 || true
}
trap cleanup EXIT

printf '%s\n' "${manifest}" | kubectl apply -f - > /dev/null \
  || fatal "kubectl apply failed for job ${job_name} in namespace ${NAMESPACE}" 1

wait_rc=0
kubectl wait --for=condition=complete "job/${job_name}" -n "${NAMESPACE}" \
  --timeout="${timeout_seconds}s" > /dev/null 2>&1 || wait_rc=$?

# A pod that never ran has no logs to classify, and the only evidence of a pull
# that failed is its waiting reason — the kubelet pulls before the container
# exists, so no probe inside the pod can ever observe this. Without this arm an
# unpullable image would surface as "no verdict", which reads as a broken check
# rather than as an image this node cannot fetch.
if [ "${wait_rc}" -ne 0 ]; then
  reason="$(kubectl get pod -n "${NAMESPACE}" --selector "job-name=${job_name}" \
    -o 'jsonpath={.items[*].status.containerStatuses[*].state.waiting.reason}' 2> /dev/null)"
  case "${reason}" in
    *ImagePull* | *ErrImage*)
      fatal "node ${node} could not pull ${image}: pod waiting reason ${reason}" 1
      ;;
  esac
fi

logs="$(kubectl logs "job/${job_name}" -n "${NAMESPACE}" 2>&1)"
printf '%s\n' "${logs}"

unreachable="$(printf '%s\n' "${logs}" | grep -m1 '^UNREACHABLE ' || true)"
if [ -n "${unreachable}" ]; then
  fatal "${unreachable#UNREACHABLE }: unreachable from a factory pod on ${node}" 1
fi

# The verdict LINE, not the Job's exit status: a container that exited 0 without
# probing — a changed command, a shell that died after its last `reached` line —
# would otherwise be read as a reach nobody observed. Silence is not a pass.
printf '%s\n' "${logs}" | grep -q '^ALL ENDPOINTS REACHED$' \
  || fatal "job ${job_name} produced no all-reached verdict (wait exit ${wait_rc})" 1

echo "OK: every endpoint was reached from a factory pod on ${node}, running ${image}"
