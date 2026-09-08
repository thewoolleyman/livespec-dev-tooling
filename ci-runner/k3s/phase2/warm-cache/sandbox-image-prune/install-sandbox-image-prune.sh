#!/usr/bin/env bash
# install-sandbox-image-prune.sh — install the periodic Fabro sandbox-image
# prune on a k3s runner node: the script into /usr/local/lib/ci-runner-k3s/ and
# the oneshot unit plus its timer into /etc/systemd/system, with the TIMER
# enabled and started. Item `livespec-h96p`.
#
# IT ALSO RENDERS ONE DATA FILE, AND THAT IS THE ONLY REASON THIS INSTALLER
# READS THE REPOSITORY AT ALL. ./prune-sandbox-images.sh gate 4(c) protects
# every sandbox image that a manifest COMMITTED HERE pins, not only the ones a
# live cluster object names — the gap `livespec-ifwnqj.7` recorded, where
# ../../isolation/negative-control-job.yaml pins `:python-v1.40.1` in a
# `kind: Job` applied by hand, so no cluster object holds it between runs and
# the prune listed it for removal. The prune cannot answer that itself: it runs
# on a node out of /usr/local/lib/ci-runner-k3s, where no checkout of this
# repository is guaranteed to exist. So the extraction happens HERE, where the
# repository demonstrably does exist, and the result is installed beside the
# script as `prune-sandbox-images.repo-pins`, one image reference per line.
#
# WHICH MAKES THE FILE A SNAPSHOT. It is as old as the last run of this
# installer, so a manifest whose pin changed afterwards is not protected until
# this runs again — the same "merging is NOT deploying" property the installed
# script itself has, since that is a COPY too. Re-run this after any manifest
# change that pins an OLD tag; a pin to a recent release is already inside the
# prune newest-N window and needs nothing.
#
# THE SCAN IS DELIBERATELY WIDER THAN THE MANIFESTS ANYONE WOULD THINK TO NAME.
# Every YAML file in the repository tree is searched for a reference to the
# prune scope repository, with no list of which files are allowed to carry one
# — the same shape as the prune JSON text-scrape of the cluster dump, and for
# the same reason. A keep-list of protected tags, or an allow-list of manifest
# paths, would drift silently the day someone adds a manifest and forgets, and
# that drift would be invisible in exactly the way the original gap was. Two
# directories are excluded because they are not this repository manifests: the
# `.git` object store, and a `.venv` package install.
#
# WHY THE TIMER IS STARTED HERE AND THE SERVICE IS NOT. The unit itself is a
# bounded pass that removes only what ./prune-sandbox-images.sh's gates leave
# as surplus, and the timer's first tick is 30 minutes after boot — so there is
# no boot-window hazard of the kind that makes ../../storage-sweep/'s installer
# refuse to start its unit. What this installer still does NOT do is run the
# prune itself: the first live pass is an attended step, and it should be run
# once WITHOUT `--apply` first so an operator sees the candidate list for this
# node before anything is removed. The final message says so.
#
# SERVER ONLY, and this is a hard refusal rather than a skip. The prune's
# central gate is a cluster-wide read of every workload's PodSpec — that is how
# it knows a half-hourly CronJob still needs a tag from twelve releases ago —
# and only a server holds the admin kubeconfig that read requires. An agent
# could still prune on node evidence alone; it MUST NOT, because "no container
# is using this image" is exactly the wrong question, so the script refuses
# there and this installer refuses to put it there. The consequence is stated
# rather than hidden: an AGENT node's containerd is NOT pruned by this work,
# and bounding it needs a scoped read-only credential on that node first (the
# shape ../../../observability/ci-kueue-webhook-probe.sh already uses, rendered
# by ../../reconstruct/render-sa-kubeconfig.sh). ../README.md "Sandbox image
# hygiene" records that as the open half.
#
# NOT WIRED INTO ../../install-node.sh. `livespec-h96p` is repository work and
# nothing here has been applied to a live node; adding a step to the node
# runbook would put an unexercised destructive unit into every future rebuild.
# Wiring it in is part of the maintainer-gated apply step.
#
# NODE-LOCAL, like the sibling installers: re-run after any node rebuild, and
# after editing ./prune-sandbox-images.sh (the installed copy is a COPY).
# Requires: root, systemd. `--dry-run` requires neither and installs nothing.
# It DOES perform the manifest scan, into a scratch directory of its own and
# nowhere else, so the pin count it prints is the real one — a dry run that
# reported a made-up number for the one thing this installer derives would be
# worse than not printing it.
#
# Usage: install-sandbox-image-prune.sh [--dry-run] [--role server|agent] [PROFILE]
#   PROFILE  path to ../../../phase0-bare-metal/profiles/<node>.env, read for
#            its CLUSTER_ROLE and for NOTHING else — the form
#            ../../install-node.sh passes to every role-aware installer.
#   --role   the same choice made explicitly, for a hand run with no profile.
#   Neither  defaults to `server`.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_NAME="$(basename "$0")"
LIB_DIR="/usr/local/lib/ci-runner-k3s"
UNIT_DIR="/etc/systemd/system"
SERVICE="prune-sandbox-images.service"
TIMER="prune-sandbox-images.timer"
PRUNE="prune-sandbox-images.sh"
# The prune resolves this name beside its own installed copy, so the two spell
# it the same way by construction rather than by agreement.
PINS="${PRUNE%.sh}.repo-pins"

USAGE="usage: ${SCRIPT_NAME} [--dry-run] [--role server|agent] [PROFILE]"

die() { printf 'FATAL: %s\n' "$*" >&2; exit 1; }
log() { printf '\n== %s ==\n' "$*"; }

DRY_RUN=0
ROLE=""
ROLE_GIVEN=0
PROFILE_PATH=""

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --role)
      [ $# -ge 2 ] || die "--role needs a value -- ${USAGE}"
      [ -n "$2" ] || die "--role needs a value -- ${USAGE}"
      [ "$ROLE_GIVEN" -eq 0 ] || die "--role given more than once -- ${USAGE}"
      ROLE_GIVEN=1
      ROLE="$2"; shift ;;
    -h|--help) printf '%s\n' "$USAGE"; exit 0 ;;
    -*) die "unknown option '$1' -- ${USAGE}" ;;
    *)
      [ -z "$PROFILE_PATH" ] || die "unexpected extra argument '$1' -- ${USAGE}"
      PROFILE_PATH="$1" ;;
  esac
  shift
done

if [ "$ROLE_GIVEN" -eq 1 ] && [ -n "$PROFILE_PATH" ]; then
  die "give either --role or a PROFILE, not both -- ${USAGE}"
fi

# The profile is PARSED and never sourced, and exactly ONE key is read out of
# it — the same restraint, and the same reason, as
# ../../storage-sweep/install-storage-sweep.sh's.
profile_role() {  # profile_role PATH -> the profile's CLUSTER_ROLE on stdout
  local path="$1" line seen=0 value=""
  [ -f "$path" ] || die "profile not found: ${path}"
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in CLUSTER_ROLE=*) ;; *) continue ;; esac
    [ "$seen" -eq 0 ] || die "${path}: profile key 'CLUSTER_ROLE' given more than once"
    seen=1
    value="${line#*=}"
  done < "$path"
  [ "$seen" -eq 1 ] || die "${path}: missing required profile key 'CLUSTER_ROLE'"
  [ -n "$value" ] || die "${path}: profile key 'CLUSTER_ROLE' must not be empty"
  printf '%s' "$value"
}

if [ -n "$PROFILE_PATH" ]; then
  # `|| exit 1` on purpose: `die` inside a command substitution exits the
  # SUBSHELL, so without this the assignment's failure would not stop the run.
  ROLE="$(profile_role "$PROFILE_PATH")" || exit 1
fi
ROLE="${ROLE:-server}"
case "$ROLE" in
  server|agent) ;;
  *) die "role must be 'server' or 'agent', got '${ROLE}'" ;;
esac

for artifact in "$PRUNE" "$SERVICE" "$TIMER"; do
  [ -f "${SCRIPT_DIR}/${artifact}" ] || die "missing artifact: ${SCRIPT_DIR}/${artifact}"
done

WORKDIR="$(mktemp -d)"
cleanup() { rm -rf "$WORKDIR"; }
trap cleanup EXIT

# ---------------------------------------------------------------------------
# The repo-pins file (see the header): every reference to the prune scope
# repository that any YAML file of this repository carries.
# ---------------------------------------------------------------------------
# The repository root, reached by walking up out of this tree rather than
# guessed from `pwd`, so the scan reads the checkout this script belongs to
# whatever directory it was invoked from. It is then CONFIRMED, because a
# wrongly-rooted `find` returns nothing and "nothing" is precisely the answer
# this whole change exists to stop anyone from acting on.
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../../../.." && pwd)"
[ -d "${REPO_ROOT}/ci-runner/k3s/phase2" ] || die "expected the repository root five levels above ${SCRIPT_DIR}, but ${REPO_ROOT} has no ci-runner/k3s/phase2. This tree has moved and the walk-up above has not; nothing was installed"

# The scope repository is READ OUT OF the prune script, never repeated here. It
# is the value gate 1 calls the safety property, and two copies of it is one
# copy too many: a divergence would leave the prune protecting one repository
# while this installer extracted pins for another, with nothing anywhere to
# notice. `die` cannot be used inside the command substitution (it would exit
# only the subshell), hence the `|| die` on the assignment.
prune_repository() {  # prune_repository -> the prune scope constant on stdout
  local matches
  matches="$(sed -n 's/^REPOSITORY="\([^"]*\)"$/\1/p' "${SCRIPT_DIR}/${PRUNE}")"
  [ "$(printf '%s\n' "$matches" | grep -c .)" -eq 1 ] || return 1
  printf '%s' "$matches"
}
REPOSITORY="$(prune_repository)" || die "could not read exactly one REPOSITORY=\"...\" line out of ${SCRIPT_DIR}/${PRUNE}. This installer extracts pins for exactly the repository the prune protects and refuses to guess which one that is"

# ERE-escaped in full rather than just the dots the current value happens to
# contain, so a future scope constant carrying a `+` or a `?` cannot turn this
# grep into a pattern that matches something else.
ere_escape() {  # ere_escape STRING -> the same string, safe inside an ERE
  printf '%s' "$1" | sed -e 's/[\\^$.[|()*+?{]/\\&/g' -e 's/]/\\]/g'
}

PINS_FILE="${WORKDIR}/${PINS}"
find "$REPO_ROOT" \( -name .git -o -name .venv \) -prune -o -type f \( -name '*.yaml' -o -name '*.yml' \) -print0 \
  | xargs -0 -r grep -ohE "$(ere_escape "$REPOSITORY")(:[A-Za-z0-9_][A-Za-z0-9_.-]*|@sha256:[0-9a-f]+)" \
  | sort -u > "$PINS_FILE" || true
PIN_COUNT="$(grep -c . "$PINS_FILE" || true)"

# Zero is refused, and it is the same refusal the prune makes when the file is
# missing. This repository pins at least the warm cache own CronJob image, so a
# scan finding nothing has looked in the wrong place — a partial checkout, a
# tree without its manifests — and installing an empty file would disarm gate
# 4(c) silently, at the exact place it matters. The prune refuses to run with
# one anyway, so writing it would only move the failure to the next timer tick.
[ "$PIN_COUNT" -gt 0 ] || die "found no reference to ${REPOSITORY} in any YAML file under ${REPO_ROOT}. This repository pins at least the warm-cache CronJob image, so zero means the scan looked at the wrong tree rather than a repository that pins nothing. Nothing was installed"

printf '== %s plan ==\n' "$SCRIPT_NAME"
printf 'role:    %s\n' "$ROLE"
printf 'script:  %s -> %s/%s\n' "$PRUNE" "$LIB_DIR" "$PRUNE"
printf 'pins:    %s reference(s) to %s found in the YAML of %s -> %s/%s\n' "$PIN_COUNT" "$REPOSITORY" "$REPO_ROOT" "$LIB_DIR" "$PINS"
while IFS= read -r pin; do printf '           %s\n' "$pin"; done < "$PINS_FILE"
printf 'units:   %s (enabled + started), %s (installed, never started here)\n' "$TIMER" "$SERVICE"

if [ "$ROLE" = agent ]; then
  die "this prune is SERVER-only. Its central gate is a cluster-wide PodSpec read, and an agent holds no admin kubeconfig; pruning on node evidence alone would delete images that only a between-runs CronJob or Job needs. Nothing was installed. See this script's header for what bounding an agent's containerd would take."
fi

# ---------------------------------------------------------------------------
# ONE call site per command, printed under --dry-run and executed otherwise, so
# the plan a dry run prints cannot describe a different run from the one that
# happens.
# ---------------------------------------------------------------------------
run() {  # run CMD ARG...
  if [ "$DRY_RUN" -eq 1 ]; then
    printf '  %s\n' "$*"
  else
    "$@"
  fi
}

if [ "$DRY_RUN" -eq 0 ]; then
  [ "$(id -u)" -eq 0 ] || die "must run as root (writes ${LIB_DIR} and ${UNIT_DIR})"
  command -v systemctl >/dev/null || die "systemctl not found on PATH"
fi

log "1. Install the prune script and its repo-pins file to ${LIB_DIR}"
run install -d -m 0755 "${LIB_DIR}"
run install -m 0755 "${SCRIPT_DIR}/${PRUNE}" "${LIB_DIR}/${PRUNE}"
run install -m 0644 "$PINS_FILE" "${LIB_DIR}/${PINS}"

log "2. Install the unit and its timer"
run install -m 0644 "${SCRIPT_DIR}/${SERVICE}" "${UNIT_DIR}/${SERVICE}"
run install -m 0644 "${SCRIPT_DIR}/${TIMER}" "${UNIT_DIR}/${TIMER}"
run systemctl daemon-reload

log "3. Enable and start the TIMER (never the service — see the header)"
run systemctl enable --now "${TIMER}"

log "4. Verify the timer is enabled"
if [ "$DRY_RUN" -eq 1 ]; then
  run systemctl is-enabled "${TIMER}"
else
  state="$(systemctl is-enabled "${TIMER}" 2>/dev/null || true)"
  [ "$state" = "enabled" ] || die "${TIMER} is '${state}', expected 'enabled'"
fi

if [ "$DRY_RUN" -eq 1 ]; then
  printf '\n-- --dry-run: the plan above was printed and NOTHING was executed --\n'
  exit 0
fi

log "DONE. ${TIMER} enabled; the first tick is 30 minutes after boot, then every 6 h."
log "BEFORE trusting it, run one REPORT pass by hand and read the candidate list:"
log "  sudo ${LIB_DIR}/${PRUNE}"
log "It removes nothing without --apply, which only the unit passes."
