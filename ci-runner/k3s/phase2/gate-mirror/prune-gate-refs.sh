#!/usr/bin/env bash
# prune-gate-refs.sh — delete `refs/gates/*` refs older than the cutoff from
# the bare gate mirror, then reclaim the objects that only they referenced.
#
# WHY IT EXISTS. The driver host pushes ONE ref per gated tree
# (`refs/gates/<tree-hash>`, ./README.md "The receive path"). The client is
# expected to delete its own ref as soon as it has a verdict, and that is the
# normal path — but a client that is killed, loses its network, or dies between
# the verdict and the delete leaves its ref behind. Without a sweep, one ref per
# gated tree accumulates FOREVER: the ref namespace grows without bound, every
# push and every fetch pays to advertise it, and the objects under it are
# reachable so nothing ever reclaims them. This sweep is the backstop for that
# client contract, NOT a replacement for it — the cutoff is a day precisely so
# that it never races a gate in flight.
#
# HOW A REF IS AGED. By the mtime of its LOOSE ref file, which is the instant
# the driver host's push wrote it. ./ensure-gate-mirror.sh turns `gc.auto` and
# `receive.autogc` off exactly so the refs stay loose and that timestamp keeps
# existing. A ref with no loose file (someone ran `git pack-refs` by hand)
# falls back to the ref's COMMITTER DATE, which is a lower bound on the push —
# you cannot push a commit before it exists — so the fallback can only ever
# judge a ref OLDER than it really is. That direction is stated rather than
# hidden: on the fallback path a re-gate of a long-merged commit could be swept
# while its gate is still fetching, which is why the loose path is the design
# and the fallback is a repair, reported on its own line every time it is used.
#
# OBJECT RECLAMATION is `git prune --expire=2.hours.ago`, run only when this
# sweep actually deleted a ref. `git prune` walks from the REMAINING refs, so
# an object still named by a live gate ref is never a candidate; the two-hour
# window then covers the one race `git prune` has of its own — a push that has
# written its objects but not yet updated its ref.
#
# Runs as the ./gate-mirror.yaml CronJob (converged, script mounted from the
# `gate-mirror-prune` ConfigMap), and by hand on the node for a one-off sweep.
#
# Requires: git, and write access to the mirror.
set -euo pipefail

MAX_AGE_SECONDS=86400   # one day; ./README.md "Pruning" derives it
DRY_RUN=0
MIRROR=""

usage() { printf 'usage: %s [--max-age-seconds N] [--dry-run] MIRROR_DIR\n' "$(basename "$0")"; }

while [ "$#" -gt 0 ]; do
  case "$1" in
    --max-age-seconds)
      shift
      [ "$#" -gt 0 ] || { echo "FATAL: --max-age-seconds needs a value" >&2; usage >&2; exit 2; }
      case "$1" in
        ''|*[!0-9]*) echo "FATAL: --max-age-seconds must be a whole number of seconds, got '$1'" >&2; exit 2 ;;
      esac
      MAX_AGE_SECONDS="$1"
      ;;
    --dry-run) DRY_RUN=1 ;;
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
git --git-dir="$MIRROR" rev-parse --is-bare-repository >/dev/null 2>&1 || {
  echo "FATAL: ${MIRROR} is not a git repository (run ./ensure-gate-mirror.sh first)" >&2
  exit 1
}

NOW="$(date +%s)"

# ref_stamp REF -> `<unix time the ref was last written> <loose|packed>` on
# stdout, or NOTHING when neither source can date it (a ref pointing at
# something that is not a commit, which nothing in this design creates).
ref_stamp() {
  local ref="$1" loose="${MIRROR}/$1" stamp
  if [ -f "$loose" ]; then
    printf '%s loose' "$(stat -c %Y "$loose")"
    return 0
  fi
  stamp="$(git --git-dir="$MIRROR" for-each-ref --format='%(committerdate:unix)' "$ref")"
  [ -n "$stamp" ] || return 0
  printf '%s packed' "$stamp"
}

deleted=0
kept=0
undatable=0

while IFS= read -r ref; do
  [ -n "$ref" ] || continue
  dated="$(ref_stamp "$ref")"
  stamp="${dated% *}"
  source="${dated#* }"
  if [ -z "$dated" ]; then
    echo "  UNDATABLE ${ref}: neither a loose ref file nor a committer date; left in place"
    undatable=$((undatable + 1))
    continue
  fi
  age=$((NOW - stamp))
  if [ "$source" = packed ]; then
    echo "  FALLBACK ${ref}: no loose ref file, aged by committer date (${age}s) — someone packed this mirror's refs; see this script's header"
  fi
  if [ "$age" -le "$MAX_AGE_SECONDS" ]; then
    kept=$((kept + 1))
    continue
  fi
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "  would delete ${ref} (${age}s old, cutoff ${MAX_AGE_SECONDS}s)"
  else
    git --git-dir="$MIRROR" update-ref -d "$ref"
    echo "  deleted ${ref} (${age}s old, cutoff ${MAX_AGE_SECONDS}s)"
  fi
  deleted=$((deleted + 1))
done < <(git --git-dir="$MIRROR" for-each-ref --format='%(refname)' refs/gates/)

if [ "$deleted" -gt 0 ] && [ "$DRY_RUN" -eq 0 ]; then
  git --git-dir="$MIRROR" prune --expire=2.hours.ago
fi

printf 'gate refs: %s deleted, %s kept, %s undatable (cutoff %ss%s)\n' \
  "$deleted" "$kept" "$undatable" "$MAX_AGE_SECONDS" \
  "$([ "$DRY_RUN" -eq 1 ] && printf '%s' ', DRY RUN: NOTHING was deleted' || true)"
