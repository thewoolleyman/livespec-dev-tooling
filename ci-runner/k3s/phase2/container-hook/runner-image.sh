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
