#!/usr/bin/env bash
# converge-hook-pod-template.sh — publish the ARC container-hook files as an
# IMMUTABLE, content-addressed ConfigMap revision in arc-runners, render the
# scale-set values that mount it, and prune revisions no pod still mounts
# (livespec-dev-tooling-4oeffe).
#
# WHY REVISIONS, not one mutable ConfigMap: a ConfigMap volume refreshes inside
# RUNNING pods. On 2026-11-04 a converge removed git-seed-hook.js from the one
# mutable `arc-hook-pod-template` ConfigMap, and every runner pod started before
# it still had ACTIONS_RUNNER_CONTAINER_HOOKS naming the vanished file, so its
# teardown failed with "Executing the custom container implementation failed".
# A revision is never edited after it is published, so the files a running pod
# was started with stay at the paths its environment names for its whole life.
#
# A revision is named `arc-hook-pod-template-<hash>`, where <hash> is the first
# 12 hex digits of a sha256 over every key's NAME and CONTENT (HOOK_FILES
# below), so the same files always yield the same name and any change to any
# key yields a new one. It carries `immutable: true` and the label
# `ci-runner.io/hook-template=revision`, which is how the prune finds it.
#
# The values files do NOT spell a revision: each mounts the placeholder
# `arc-hook-pod-template-@HOOK_REVISION@`, and `--render-values` substitutes the
# revision these files hash to. `@` is not legal in a Kubernetes name, so a
# values file applied WITHOUT rendering fails at once instead of mounting a
# stale revision. ../reconstruct/converge-ci-stack.sh publishes (step 7a),
# renders every scale set's values and helm-upgrades them (step 7), and prunes
# (step 8), in that order.
#
# Modes (exactly one; the default is --publish followed by --prune):
#   --name                       print the revision name; touches nothing.
#   --publish                    create the revision if it does not exist.
#   --prune                      delete every OTHER revision that no pod and no
#                                runner-set object in arc-runners references,
#                                naming each revision it KEPT and why.
#   --render-values <src> <dst>  write <src> to <dst> with the placeholder
#                                replaced by the revision name.
#   --dry-run                    print the publish this converge would run and
#                                execute NOTHING (not even the kubectl and
#                                KUBECONFIG preconditions), so it is safe from a
#                                checkout on a machine that is not the node.
#
# Requires (publish/prune): kubectl with KUBECONFIG pointed at the k3s cluster.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Every key of a revision, as `<key>=<source file>`. Adding a hook file is one
# line here; the hash, the publish and the dry-run all read this list.
#  - hook-pod-template.yaml: the workflow-pod template
#    ACTIONS_RUNNER_CONTAINER_HOOK_TEMPLATE names.
#  - action-archive-entry.sh: the runner container's entry point (its
#    `command`), in the same ConfigMap because the runner already mounts it.
HOOK_FILES=(
  "hook-pod-template.yaml=${SCRIPT_DIR}/hook-pod-template.yaml"
  "action-archive-entry.sh=${SCRIPT_DIR}/action-archive-entry.sh"
)
BASE_NAME="arc-hook-pod-template"
PLACEHOLDER="${BASE_NAME}-@HOOK_REVISION@"
REVISION_LABEL_KEY="ci-runner.io/hook-template"
REVISION_LABEL="${REVISION_LABEL_KEY}=revision"
RUNNERS_NAMESPACE="arc-runners"
# The ARC objects whose pod templates name a revision before any pod exists:
# a revision they still reference is the one their NEXT runner pod mounts.
RUNNER_SET_KINDS="autoscalingrunnersets.actions.github.com,ephemeralrunnersets.actions.github.com,ephemeralrunners.actions.github.com"

usage() {
  printf 'usage: %s [--name | --publish | --prune | --render-values <src> <dst> | --dry-run]\n' "$(basename "$0")"
}

MODE="default"
RENDER_SRC=""
RENDER_DST=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --name) MODE="name" ;;
    --publish) MODE="publish" ;;
    --prune) MODE="prune" ;;
    --dry-run) MODE="dry-run" ;;
    --render-values)
      [ "$#" -ge 3 ] || { usage >&2; exit 2; }
      MODE="render"; RENDER_SRC="$2"; RENDER_DST="$3"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'FATAL: unknown argument: %s\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

revision_name() {
  local entry key src
  for entry in "${HOOK_FILES[@]}"; do
    key="${entry%%=*}"
    src="${entry#*=}"
    [ -f "${src}" ] || { echo "FATAL: hook file not found: ${src}" >&2; exit 1; }
    printf '%s\0' "${key}"
    cat "${src}"
    printf '\0'
  done | sha256sum | cut -c1-12 | sed "s/^/${BASE_NAME}-/"
}

from_file_args() {
  local entry
  for entry in "${HOOK_FILES[@]}"; do
    printf -- '--from-file=%s\n' "${entry}"
  done
}

REVISION="$(revision_name)"

case "${MODE}" in
  name)
    printf '%s\n' "${REVISION}"
    exit 0
    ;;
  render)
    [ -f "${RENDER_SRC}" ] || { echo "FATAL: values file not found: ${RENDER_SRC}" >&2; exit 1; }
    count="$(grep -cF -- "${PLACEHOLDER}" "${RENDER_SRC}" || true)"
    [ "${count}" -ge 1 ] || {
      echo "FATAL: ${RENDER_SRC} does not mount ${PLACEHOLDER}; every scale set's values must mount the published hook-template revision" >&2
      exit 1
    }
    sed "s/${BASE_NAME}-@HOOK_REVISION@/${REVISION}/g" "${RENDER_SRC}" > "${RENDER_DST}"
    exit 0
    ;;
  dry-run)
    mapfile -t args < <(from_file_args)
    printf '  would run: kubectl create configmap %s --namespace %s %s --dry-run=client -o yaml | (immutable: true, label %s) | kubectl create -f -\n' \
      "${REVISION}" "${RUNNERS_NAMESPACE}" "${args[*]}" "${REVISION_LABEL}"
    printf '  would prune: every %s ConfigMap other than %s that no pod or runner set in %s references\n' \
      "${REVISION_LABEL}" "${REVISION}" "${RUNNERS_NAMESPACE}"
    echo "DRY RUN: nothing was applied."
    exit 0
    ;;
esac

command -v kubectl >/dev/null || { echo "FATAL: kubectl not found on PATH"; exit 1; }
: "${KUBECONFIG:?set KUBECONFIG to the k3s cluster kubeconfig (see ../../provision-k3s.sh)}"

publish() {
  if kubectl -n "${RUNNERS_NAMESPACE}" get configmap "${REVISION}" -o name >/dev/null 2>&1; then
    echo "hook-template revision ${REVISION}: already published (immutable; unchanged)"
    return 0
  fi
  mapfile -t args < <(from_file_args)
  # `create`, not `apply`: a revision is written once. kubectl's own
  # --dry-run=client renders the object; the awk adds `immutable: true` at the
  # top level and the revision label under metadata, which
  # `kubectl create configmap` has no flags for.
  kubectl create configmap "${REVISION}" \
    --namespace "${RUNNERS_NAMESPACE}" \
    "${args[@]}" \
    --dry-run=client -o yaml \
    | awk -v k="${REVISION_LABEL_KEY}" '
        {print}
        /^kind: ConfigMap$/ {print "immutable: true"}
        /^metadata:$/ {print "  labels:"; print "    " k ": revision"}' \
    | kubectl create -f -
  echo "hook-template revision ${REVISION}: published"
}

prune() {
  local revisions pod_mounts set_refs rev pods
  # A listing that FAILS must never read as "nothing mounts it": each read is
  # checked, and any failure skips the prune with the revisions intact.
  if ! revisions="$(kubectl -n "${RUNNERS_NAMESPACE}" get configmap -l "${REVISION_LABEL}" \
      -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}')"; then
    echo "WARN: could not list hook-template revisions; pruning nothing"
    return 0
  fi
  # One line per (pod, configMap volume): `<pod> <configmap>`. The go-template
  # `$p` is kubectl's, not the shell's, hence the single quotes.
  # shellcheck disable=SC2016
  if ! pod_mounts="$(kubectl -n "${RUNNERS_NAMESPACE}" get pods \
      -o go-template='{{range .items}}{{$p := .metadata.name}}{{range .spec.volumes}}{{if .configMap}}{{$p}} {{.configMap.name}}{{"\n"}}{{end}}{{end}}{{end}}')"; then
    echo "WARN: could not list the pods in ${RUNNERS_NAMESPACE}; pruning nothing"
    return 0
  fi
  if ! set_refs="$(kubectl -n "${RUNNERS_NAMESPACE}" get "${RUNNER_SET_KINDS}" -o json)"; then
    echo "WARN: could not read the runner sets in ${RUNNERS_NAMESPACE}; pruning nothing"
    return 0
  fi
  while IFS= read -r rev; do
    [ -n "${rev}" ] || continue
    if [ "${rev}" = "${REVISION}" ]; then
      echo "kept ${rev}: the revision this converge published"
      continue
    fi
    pods="$(printf '%s\n' "${pod_mounts}" | awk -v r="${rev}" '$2 == r {print $1}' | sort -u | paste -sd, -)"
    if [ -n "${pods}" ]; then
      echo "kept ${rev}: still mounted by live pod(s) ${pods}"
    elif [[ "${set_refs}" == *"\"${rev}\""* ]]; then
      echo "kept ${rev}: still named by a runner set's pod template in ${RUNNERS_NAMESPACE}"
    else
      kubectl -n "${RUNNERS_NAMESPACE}" delete configmap "${rev}"
      echo "deleted ${rev}: no pod in ${RUNNERS_NAMESPACE} mounts it"
    fi
  done <<< "${revisions}"
}

case "${MODE}" in
  publish) publish ;;
  prune) prune ;;
  default) publish; prune ;;
esac
