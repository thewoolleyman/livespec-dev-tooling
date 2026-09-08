#!/usr/bin/env bash
# ensure-gate-mirror.sh — idempotently create the BARE GIT MIRROR a gate Job
# fetches the tree under test from, on the ci-cache storage tier.
#
# THE PROBLEM IT SOLVES. A gate Job runs this repository's own `just check`
# against the exact tree being pushed, so that tree has to reach a pod on any
# node WITHOUT going through GitHub (the whole point of a pre-push gate is that
# nothing has been pushed to GitHub yet). The driver host pushes HEAD into this
# mirror over Tailscale SSH at `refs/gates/<tree-hash>`; ./gate-mirror.yaml's
# read-only git daemon then serves that mirror in-cluster so a pod on either
# pool node can fetch it. `<tree-hash>` is `git rev-parse HEAD^{tree}` — the
# SAME value the green token is keyed on, so one value names the pushed tree,
# the served ref and the written token. ./README.md carries the whole path.
#
# WHERE IT MUST NOT GO: /var/lib/git. That directory is owned by the `git`
# Debian package (`dpkg -S /var/lib/git` reports git 1:2.53.0-1ubuntu1), which
# is why it is empty and root-owned and why it predates this pool entirely —
# it is the packaged git-daemon's default base path, not a fleet-owned tier.
# Putting the mirror there would put it on the ROOT VOLUME, outside the storage
# tiers (.ai/ci-node-storage-tiers.md), where it competes with the OS for space
# and is lost on a root rebuild. The mirror belongs on the ci-cache tier, live
# at /var/cache/ci-runner, exactly like the sccache snapshot and the PyPI
# proxy's store.
#
# IDEMPOTENT, and required to be: ../reconstruct/converge-ci-stack.sh runs
# ./converge-gate-mirror.sh on EVERY boot, and this mirror — unlike everything
# in the k3s datastore — SURVIVES the boot. A second run must therefore leave
# an already-created mirror byte-identical, refs included; re-creating it would
# throw away the trees of every gate in flight. `git init --bare` on an
# existing repository re-initialises it (a no-op on the object store and the
# refs), and every other step here is a set-to-a-known-value.
#
# --owner USER chowns the tree to the account the SSH receive path lands as
# (./README.md "The receive path"), and is SKIPPED with a reason when this
# script is not root, so the exit tests can drive the whole body unprivileged.
#
# Requires: git. Root only for --owner.
set -euo pipefail

OWNER=""
MIRROR=""

usage() { printf 'usage: %s [--owner USER] MIRROR_DIR\n' "$(basename "$0")"; }

while [ "$#" -gt 0 ]; do
  case "$1" in
    --owner) shift; [ "$#" -gt 0 ] || { echo "FATAL: --owner needs a value" >&2; usage >&2; exit 2; }; OWNER="$1" ;;
    -h|--help) usage; exit 0 ;;
    -*) printf 'FATAL: unknown option: %s\n' "$1" >&2; usage >&2; exit 2 ;;
    *)
      [ -z "$MIRROR" ] || { echo "FATAL: give exactly one MIRROR_DIR" >&2; usage >&2; exit 2; }
      MIRROR="$1"
      ;;
  esac
  shift
done

[ -n "$MIRROR" ] || { echo "FATAL: MIRROR_DIR is required" >&2; usage >&2; exit 2; }
command -v git >/dev/null || { echo "FATAL: git not found on PATH" >&2; exit 1; }

# The one refusal that is not about this script's own arguments: the mirror
# must never be the packaged git-daemon base path (header, "WHERE IT MUST NOT
# GO"). Stated as a run-time refusal as well as a comment, because a caller
# that passes it has misread the design and a silent success would create a
# mirror on the root volume that works right up until the tier is needed.
case "$MIRROR" in
  /var/lib/git|/var/lib/git/*)
    echo "FATAL: ${MIRROR} is under /var/lib/git, which belongs to the git package and sits on the ROOT VOLUME; the mirror goes on the ci-cache tier (see this script's header)" >&2
    exit 1
    ;;
esac

install -d -m 0755 "$MIRROR"
git init --bare --quiet "$MIRROR"

# Configuration, all of it load-bearing for how ./prune-gate-refs.sh and the
# daemon read this repository.
#
#   gc.auto / receive.autogc — OFF. `git gc --auto`, which receive-pack would
#     otherwise run after a push, calls `git pack-refs`, and a PACKED ref has
#     no per-ref file and therefore no per-ref mtime. The sweep ages a gate ref
#     by the mtime of its loose ref file — the moment the driver host pushed it
#     — so packing would cost it the only per-push timestamp there is and force
#     it onto the weaker committer-date fallback. Object pruning is not lost
#     with it: the sweep runs `git prune` itself, which reclaims unreachable
#     objects and touches no ref.
#   core.logAllRefUpdates — ON. A bare repository keeps no reflog by default.
#     One line per push and per client-side delete, for free, is the only
#     forensic record of which trees were gated and when.
#   receive.denyDeletes / receive.denyNonFastForwards — explicitly OFF, because
#     both are what the client contract in ./README.md depends on: a client
#     DELETES its own ref once it has a verdict (the sweep is the backstop, not
#     the mechanism), and a re-gate of a tree can legitimately land a different
#     commit on the same content-addressed ref.
git --git-dir="$MIRROR" config gc.auto 0
git --git-dir="$MIRROR" config receive.autogc false
git --git-dir="$MIRROR" config core.logAllRefUpdates true
git --git-dir="$MIRROR" config receive.denyDeletes false
git --git-dir="$MIRROR" config receive.denyNonFastForwards false

# The daemon serves with `--export-all` OFF (./gate-mirror.yaml), so a
# repository is served ONLY if it carries this marker. That is what keeps the
# daemon's reach to this one mirror even if a second repository ever appears
# beside it on the tier.
: > "${MIRROR}/git-daemon-export-ok"
chmod 0644 "${MIRROR}/git-daemon-export-ok"

# WORLD-READABLE, deliberately. The daemon pod mounts this tree read-only and
# runs as its image's uid, which is not the receive path's account; git objects
# are created 0444 and their directories 0755 already, so the modes below only
# assert what git's own defaults do. Nothing secret is here — every object in
# this mirror is a tree the driver host is about to push to GitHub anyway.
chmod 0755 "$MIRROR"

if [ -n "$OWNER" ]; then
  if [ "$(id -u)" -eq 0 ]; then
    # The SSH receive path runs `git-receive-pack` as this account, so it must
    # own the tree outright; a group-write grant would not be enough for the
    # directories receive-pack creates under objects/.
    chown -R "${OWNER}:" "$MIRROR"
    echo "owner: ${OWNER} (recursive)"
  else
    echo "  SKIPPED [not root]: chown to '${OWNER}' — the receive path needs it, so run this as root on the node"
  fi
fi

echo "gate mirror ready: ${MIRROR} (bare, exportable, gc off)"
git --git-dir="$MIRROR" for-each-ref --format='  %(refname)' refs/gates/ || true
