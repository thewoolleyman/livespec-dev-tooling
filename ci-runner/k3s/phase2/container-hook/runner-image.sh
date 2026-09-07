#!/usr/bin/env bash
# runner-image.sh — SOURCED by the three scripts in this directory (never run):
# the one place that says which runner image the fleet pins and how the runner
# version and containerd's digest name are read off its reference, so the build,
# the extraction and the install cannot disagree about any of the three.
#
# The pin itself lives in the scale-set values (every ../arc/values-*.yaml
# carries the same `image:` line; ../../README.md "Pinned versions"); this
# reads the reference example, ../arc/values-livespec.yaml, rather than keeping
# a second copy that could drift. Callers may pass an explicit reference.
# assert_values_pins_agree() below is what makes reading ONE file safe.
#
# Expects the caller to have set CONTAINER_HOOK_DIR to this directory.

# Print the pinned runner image reference: the argument if non-empty, else the
# `image:` line of ../arc/values-livespec.yaml.
resolve_runner_image() {
  if [ -n "${1:-}" ]; then
    printf '%s\n' "$1"
    return 0
  fi
  local values="${CONTAINER_HOOK_DIR}/../arc/values-livespec.yaml"
  local ref
  ref="$(grep -m1 -E '^[[:space:]]*image:[[:space:]]*ghcr\.io/actions/actions-runner:' "${values}" \
        | sed -E 's/^[[:space:]]*image:[[:space:]]*//; s/[[:space:]]*(#.*)?$//')"
  if [ -z "${ref}" ]; then
    echo "FATAL: no ghcr.io/actions/actions-runner image pin found in ${values}" >&2
    return 1
  fi
  printf '%s\n' "${ref}"
}

# ghcr.io/actions/actions-runner:2.336.0@sha256:... -> 2.336.0
runner_version_from_ref() {
  local ref="$1" name tag
  name="${ref%%@*}"
  tag="${name##*:}"
  if ! [[ "${tag}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "FATAL: cannot read a runner version from '${ref}' (expected <repo>:<x.y.z>@sha256:<digest>)" >&2
    return 1
  fi
  printf '%s\n' "${tag}"
}

# Every ../arc/values-*.yaml states the runner version THREE times: the
# `image:` pin, the hostPath of the fleet-patched container hook, and the
# ACTIONS_RUNNER_PRESEEDED_EXTERNALS_VERSION the hook reads. It cannot be
# stated once anywhere: ../reconstruct/converge-ci-stack.sh applies each file
# on its own with `helm upgrade -f <file>` and merges no shared base, so there
# is nothing for a file to inherit it from. Nothing else in this tree would
# notice one file left behind at a bump — resolve_runner_image reads the
# reference file alone. This is that notice: every file must agree with the
# reference, and each disagreement is named. It compares files against EACH
# OTHER, never against a caller's --image, so the documented bump order (build
# the bundle first, then rewrite the values files) still passes.
assert_values_pins_agree() {
  local arc_dir ref_image ref_version file bad=0
  arc_dir="${CONTAINER_HOOK_DIR}/../arc"
  ref_image="$(resolve_runner_image "")" || return 1
  ref_version="$(runner_version_from_ref "${ref_image}")" || return 1
  for file in "${arc_dir}"/values-*.yaml; do
    local pinned hook_version env_version
    pinned="$(sed -nE 's#^[[:space:]]*image:[[:space:]]*(ghcr\.io/actions/actions-runner:[^[:space:]]+)[[:space:]]*$#\1#p' "${file}" | head -1)"
    hook_version="$(sed -nE 's#^[[:space:]]*path:[[:space:]]*/usr/local/lib/ci-runner-k3s/hooks/([^/]+)/index\.js[[:space:]]*$#\1#p' "${file}" | head -1)"
    env_version="$(grep -A1 -F 'name: ACTIONS_RUNNER_PRESEEDED_EXTERNALS_VERSION' "${file}" \
                   | sed -nE 's/^[[:space:]]*value:[[:space:]]*"?([^"[:space:]]+)"?[[:space:]]*$/\1/p' | head -1)"
    if [ "${pinned}" != "${ref_image}" ]; then
      echo "FATAL: ${file##*/} pins runner image '${pinned:-<none>}', not the reference '${ref_image}'" >&2
      bad=1
    fi
    if [ "${hook_version}" != "${ref_version}" ]; then
      echo "FATAL: ${file##*/} mounts the fleet container hook for runner '${hook_version:-<none>}', not ${ref_version}" >&2
      bad=1
    fi
    if [ "${env_version}" != "${ref_version}" ]; then
      echo "FATAL: ${file##*/} declares ACTIONS_RUNNER_PRESEEDED_EXTERNALS_VERSION='${env_version:-<none>}', not ${ref_version}" >&2
      bad=1
    fi
  done
  if [ "${bad}" -ne 0 ]; then
    echo "FATAL: the arc/ values files disagree about the runner version — a bump rewrites EVERY one of them in the same change (README.md \"Runner-image bump procedure\")" >&2
    return 1
  fi
  printf 'all arc/values-*.yaml pin %s and select the fleet hook for %s\n' "${ref_image}" "${ref_version}"
}

# ghcr.io/actions/actions-runner:2.336.0@sha256:... -> ghcr.io/actions/actions-runner@sha256:...
# — the name containerd stores a digest-pinned pull under.
digest_ref_from_ref() {
  local ref="$1" name digest
  if [[ "${ref}" != *@sha256:* ]]; then
    echo "FATAL: '${ref}' carries no digest; the fleet pins tag AND digest" >&2
    return 1
  fi
  name="${ref%%@*}"
  digest="${ref#*@}"
  printf '%s@%s\n' "${name%:*}" "${digest}"
}
