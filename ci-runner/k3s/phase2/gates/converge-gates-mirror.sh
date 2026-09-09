#!/usr/bin/env bash
# converge-gates-mirror.sh — the one idempotent converge of the gate SOURCE
# path (R4.S4, livespec-dev-tooling-2hno; plan livespec
# k3s-on-gmktec-for-vps-usage, epic livespec-sab5gn; design in that plan's
# research/003 section E and correction 3). Two halves, in this order:
#
#   HOST   the bare mirrors on the `ci-cache` tier that the driver host pushes
#          `refs/gates/<tree-hash>` into over Tailscale SSH, created with the
#          ownership and mode BOTH that receive path and the daemon need, and
#          swept once of expired refs;
#   CLUSTER ./git-daemon.yaml — the read-only in-cluster daemon that serves
#          those mirrors at git://git-gates.gates.svc.cluster.local:9418, which
#          is where ./render-gate-job.sh points a gate Job's initContainer.
#
# WHY IT RUNS ON EVERY BOOT. The cluster half lives in the k3s datastore, which
# is tmpfs and EMPTY on every boot (../datastore-tmpfs/), so the Deployment and
# Service are simply gone after a reboot and must be re-applied — the same
# reasoning ../warm-cache/converge-warm-cache.sh and
# ../crates-proxy/converge-crates-proxy.sh are called on every boot for. The
# HOST half survives a reboot untouched; re-running it is a cheap assertion
# that the directories, modes and per-repository settings are still what the
# receive path needs, and it is what creates them on a fresh node.
#
# WHERE THE MIRROR LIVES, and where it does NOT. `/var/cache/ci-runner` — the
# `ci-cache` tier (../storage-layout/). NOT `/var/lib/git`: that path belongs
# to the `git` dpkg package, which is why it is empty and root-owned, and
# putting pool data under a package-owned path is how a package upgrade
# silently becomes a data question (research/003 correction 3).
#
# WHICH REPOSITORIES GET A MIRROR. Derived from the ARC values files'
# `githubConfigUrl`, exactly as ../warm-cache/converge-warm-cache.sh derives
# its routed-repository list — that set IS the set of repositories this pool
# runs CI for, and a gate is that repository's own `just check`, so gating
# anything outside it is meaningless. Deriving it means adding a repository to
# the pool needs no edit here. `--repo NAME` (repeatable) overrides the
# derivation for an operator converging one repository by hand.
#
# THE CONVERGE REFUSES when the `ci-cache` tier is not mounted. A mirror
# written to the root disk under an unmounted mountpoint is invisible the
# moment the tier mounts, and every push after that lands somewhere the daemon
# does not read.
#
# --dry-run PRINTS every command this converge would run, in order, and
# executes NOTHING — no host write, no cluster write, no cluster read, not even
# the kubectl and KUBECONFIG preconditions — so it is safe to run from a
# checkout on a machine that is not the node. It DOES still derive the
# repository list, because that reads only the values files and the list is the
# most useful thing a plan can show. Each printed line comes from the same
# `run` wrapper that would execute it, so the plan cannot drift from the body.
#
# Requires: git; kubectl with KUBECONFIG pointed at the k3s cluster; root, or
# an invoking user who already owns the mirror (see step 2).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAMESPACE="gates"
VALUES_DIR="${GATES_VALUES_DIR:-${SCRIPT_DIR}/../arc}"
CACHE_TIER_MOUNT="${CI_CACHE_TIER_MOUNT:-/var/cache/ci-runner}"
MIRROR_ROOT="${GATES_MIRROR_ROOT:-${CACHE_TIER_MOUNT}/gates-mirror}"
# The account Tailscale SSH lands the driver host as (./README.md, "The receive
# path"). An argument rather than a constant so a differently-named receive
# account is a converge argument and not an edit to four files.
MIRROR_OWNER="${GATES_MIRROR_OWNER:-cwoolley}"
ROLLOUT_TIMEOUT="${GATES_DAEMON_ROLLOUT_TIMEOUT:-120s}"
PRUNE="${SCRIPT_DIR}/prune-gate-refs.sh"

DRY_RUN=0
declare -a EXPLICIT_REPOS=()
usage() { printf 'usage: %s [--dry-run] [--repo NAME]...\n' "$(basename "$0")"; }
while [ "$#" -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --repo)    EXPLICIT_REPOS+=("${2:?--repo needs a repository name}"); shift ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'FATAL: unknown argument: %s\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

log() { printf '\n== %s ==\n' "$*"; }
# Print-or-execute: in dry-run the exact argv is shown and NOT run.
run() {
  if [ "${DRY_RUN}" -eq 1 ]; then printf '  would run: %s\n' "$*"; return 0; fi
  "$@"
}
# Same, for the calls whose stdout the converge deliberately discards.
run_quiet() {
  if [ "${DRY_RUN}" -eq 1 ]; then printf '  would run: %s\n' "$*"; return 0; fi
  "$@" >/dev/null
}

command -v git >/dev/null || { echo "FATAL: git not found on PATH"; exit 1; }
if [ "${DRY_RUN}" -eq 0 ]; then
  command -v kubectl >/dev/null || { echo "FATAL: kubectl not found on PATH"; exit 1; }
  : "${KUBECONFIG:?set KUBECONFIG to the k3s cluster kubeconfig (see ../../provision-k3s.sh)}"
fi
[ -x "${PRUNE}" ] || { echo "FATAL: ${PRUNE} not found or not executable"; exit 1; }

# ---------------------------------------------------------------------------
log "gates-mirror 1. Decide which repositories get a mirror"
declare -a REPOS=()
if [ "${#EXPLICIT_REPOS[@]}" -gt 0 ]; then
  REPOS=("${EXPLICIT_REPOS[@]}")
  echo "${#REPOS[@]} repositories, given as --repo arguments:"
else
  [ -d "${VALUES_DIR}" ] || { echo "FATAL: ARC values dir not found: ${VALUES_DIR}"; exit 1; }
  # values-EXAMPLE-repo.yaml is the template (its URL carries a <REPO>
  # placeholder); everything else is a live scale set, and several scale sets
  # can name the same repository — hence the sort -u. Identical derivation to
  # ../warm-cache/converge-warm-cache.sh's routed-repository list, one step
  # further: the repository NAME is the URL's last path element, which is also
  # what ./render-gate-job.sh defaults --repo to, so the mirror path and the
  # rendered --source-url agree by construction.
  while IFS= read -r name; do
    [ -n "${name}" ] && REPOS+=("${name}")
  done < <(grep -h '^githubConfigUrl:' "${VALUES_DIR}"/values-*.yaml \
    | sed -E 's/^githubConfigUrl: *"?([^" ]+)"?.*/\1/' \
    | grep -v '<' \
    | sed -E 's#/+$##; s#.*/##' \
    | sort -u)
  [ "${#REPOS[@]}" -gt 0 ] || { echo "FATAL: no githubConfigUrl found under ${VALUES_DIR}"; exit 1; }
  echo "${#REPOS[@]} repositories, derived from ${VALUES_DIR}/values-*.yaml:"
fi
for name in "${REPOS[@]}"; do
  # The name becomes a directory under the mirror root AND a path element of
  # the git:// URL a gate Job fetches from. Refuse anything that is not a
  # plain repository name rather than letting it escape the mirror root.
  case "${name}" in
    *[!A-Za-z0-9._-]* | "" | .* )
      echo "FATAL: refusing repository name that is not a plain [A-Za-z0-9._-] name: ${name}" >&2
      exit 2 ;;
  esac
  echo "  ${name}"
done

# ---------------------------------------------------------------------------
log "gates-mirror 2. Pre-gate: the ci-cache tier is mounted, and we can own what we create"
if [ "${DRY_RUN}" -eq 0 ]; then
  if ! findmnt -no TARGET "${CACHE_TIER_MOUNT}" >/dev/null 2>&1; then
    echo "FATAL: ${CACHE_TIER_MOUNT} is not a mountpoint -- the ci-cache tier is not mounted (../storage-layout/). A mirror written under an unmounted mountpoint disappears the moment the tier mounts, and every push after that lands where the daemon does not read." >&2
    exit 1
  fi
  # Only root can hand a directory to another account. An unprivileged operator
  # converging from a checkout may still create a mirror they own themselves;
  # anything else would create a mirror the receive path cannot write to and
  # report success, so it is refused here rather than discovered at the first
  # push.
  if [ "$(id -u)" -ne 0 ] && [ "$(id -un)" != "${MIRROR_OWNER}" ]; then
    echo "FATAL: not root, and this user ($(id -un)) is not the mirror owner (${MIRROR_OWNER}) -- a mirror created now could not be written by the SSH receive path. Run as root, or pass GATES_MIRROR_OWNER=$(id -un)." >&2
    exit 1
  fi
fi

# ---------------------------------------------------------------------------
log "gates-mirror 3. Create the bare mirrors on ${MIRROR_ROOT} (idempotent)"
# 2775: group-writable so the receive account's group can push, setgid so every
# object a push creates inherits that group rather than the pusher's primary
# one, and world-EXECUTABLE so the daemon's unprivileged uid can traverse it.
run install -d -m 2775 "${MIRROR_ROOT}"
for name in "${REPOS[@]}"; do
  repo_dir="${MIRROR_ROOT}/${name}.git"
  if [ "${DRY_RUN}" -eq 1 ] || [ ! -e "${repo_dir}/HEAD" ]; then
    # --shared=0664 fixes the mode of everything a push writes: files 0664,
    # directories 2775. Deterministic, unlike --shared=group, whose result
    # depends on the umask the pushing process happens to carry — and the
    # world-READ bit is what lets the daemon's uid read objects it does not own.
    run git init --quiet --bare --shared=0664 "${repo_dir}"
  else
    echo "  ${repo_dir} already initialised"
  fi
  # Asserted on every converge, not only at creation, so a hand-edited config
  # is corrected rather than carried. `git config --file` edits the file
  # directly and performs NO repository setup, which is what lets root assert
  # these against a mirror owned by another account without tripping git's
  # dubious-ownership refusal.
  run git config --file "${repo_dir}/config" core.sharedRepository 0664
  # gc.auto=0 stops receive-pack forking `git gc --auto` after a push. Two
  # reasons, and the first is load-bearing: gc packs refs, and
  # ./prune-gate-refs.sh ages a ref by the mtime of its LOOSE file, which
  # packing destroys. The second is that a gc racing a gate fetch is latency
  # nobody asked for; ./prune-gate-refs.sh does the housekeeping instead.
  run git config --file "${repo_dir}/config" gc.auto 0
  # Reflogs ON, in a BARE repository, where git's own default is off. This is
  # what gives ./prune-gate-refs.sh an exact PUSH time per ref — the one age
  # source that survives `git pack-refs`, and the reason the sweep does not
  # have to trust a loose ref file still being there.
  run git config --file "${repo_dir}/config" core.logAllRefUpdates true
  # The client deletes its own ref after a verdict (./README.md, "Pruning"),
  # which is a delete-push; denyDeletes would refuse it and leave the sweep as
  # the only collector.
  run git config --file "${repo_dir}/config" receive.denyDeletes false
  # THE export-all SWITCH. ./git-daemon.yaml runs `git daemon` WITHOUT
  # --export-all, so this marker is the ONLY thing that makes a repository
  # servable. Written here and nowhere else: whatever else ends up under the
  # mirror root stays unreachable over git://.
  if [ "${DRY_RUN}" -eq 1 ]; then
    printf '  would run: touch %s\n' "${repo_dir}/git-daemon-export-ok"
  elif [ ! -f "${repo_dir}/git-daemon-export-ok" ]; then
    # Guarded rather than an unconditional touch: an unconditional one would
    # restamp the file on every converge, which is exactly the kind of
    # meaningless change that makes a converge's output impossible to read.
    touch "${repo_dir}/git-daemon-export-ok"
  fi
  if [ "${DRY_RUN}" -eq 1 ]; then
    printf '  would run: chown -R %s %s (when root)\n' "${MIRROR_OWNER}" "${repo_dir}"
  elif [ "$(id -u)" -eq 0 ]; then
    chown -R "${MIRROR_OWNER}" "${MIRROR_ROOT}"
  fi
done

# ---------------------------------------------------------------------------
log "gates-mirror 4. Sweep expired refs/gates/* once, now"
# The timer (./gate-ref-prune.timer) is what keeps the namespace bounded
# between boots; this call is the boot-time catch-up for a host that was off
# while refs aged, and it is also the cheapest proof at converge time that the
# sweep can read every mirror it was just handed.
run "${PRUNE}" --mirror-root "${MIRROR_ROOT}"

# ---------------------------------------------------------------------------
log "gates-mirror 5. Apply the read-only in-cluster git daemon"
run kubectl apply -f "${SCRIPT_DIR}/git-daemon.yaml"
# A changed ConfigMap does not restart the Deployment by itself; stamp the
# manifest's hash onto the pod template so an edit rolls the pod
# (../crates-proxy/converge-crates-proxy.sh does the same).
if [ "${DRY_RUN}" -eq 1 ]; then
  printf '  would run: kubectl -n %s patch deployment git-gates --type=merge -p {annotations with the manifest hash}\n' "${NAMESPACE}"
else
  conf_hash="$(sha256sum "${SCRIPT_DIR}/git-daemon.yaml" | cut -c1-16)"
  run_quiet kubectl -n "${NAMESPACE}" patch deployment git-gates --type=merge \
    -p "{\"spec\":{\"template\":{\"metadata\":{\"annotations\":{\"ci-runner.io/config-hash\":\"${conf_hash}\"}}}}}"
fi

# ---------------------------------------------------------------------------
log "gates-mirror 6. Wait (bounded, ${ROLLOUT_TIMEOUT}) for the rollout"
# Bounded so a boot converge is never held hostage by an image pull. A daemon
# that is not yet Ready does not corrupt anything: a gate Job submitted in the
# meantime fails CLOSED at its initContainer's fetch and refuses the push,
# which is the direction this whole plane errs in.
if [ "${DRY_RUN}" -eq 1 ]; then
  run kubectl -n "${NAMESPACE}" rollout status deployment/git-gates --timeout="${ROLLOUT_TIMEOUT}"
  echo
  echo "DRY RUN: nothing was created, written or applied."
  exit 0
fi
if kubectl -n "${NAMESPACE}" rollout status deployment/git-gates --timeout="${ROLLOUT_TIMEOUT}"; then
  echo "git-gates ready: git://git-gates.${NAMESPACE}.svc.cluster.local:9418/<repo>.git"
else
  echo "WARN: git-gates rollout not complete after ${ROLLOUT_TIMEOUT}; gate Jobs fail closed at their fetch until it is Ready (kubectl -n ${NAMESPACE} get pods -l app.kubernetes.io/name=git-gates)"
fi
