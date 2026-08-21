#!/usr/bin/env bash
# set-ci-runner-labels.sh — write a repository's `CI_RUNNER_LABELS` variable,
# refusing to point it at self-hosted capacity unless that repository's
# fork-pull-request approval tier is at its strictest setting.
#
# WHY THE CHECK LIVES ON THE WRITE. The livespec repo's
# `SPECIFICATION/non-functional-requirements.md` §"Self-hosted CI runner host
# requirements" makes the containment-floor reduction CONDITIONAL: self-hosted
# capacity may carry a repository's merge gate ONLY while no fork-originating
# workflow can execute on it, and that exclusion "MUST be enforced by the
# repository's fork-pull-request workflow-approval setting ... at its strictest
# tier -- requiring approval for all outside collaborators, not merely for
# first-time contributors, because under the weaker tiers a returning outside
# contributor's fork pull request runs its fork-controlled workflow definition
# with no approval event."
#
# The condition that engages that precondition is exactly this variable. A
# repository begins gating merges on self-hosted capacity at the instant
# `CI_RUNNER_LABELS` names a self-hosted label -- not when its scale set is
# installed, not when its ClusterQueue is committed, not when its values file
# lands. Every other step of a cutover is a cluster change; this one is the
# security boundary, and until now it was a bare one-line variable write with
# nothing attached to it.
#
# THE GAP THIS CLOSES (livespec-s43svm.39). Nine repositories were cut over
# during livespec-s43svm.16/.18 and nothing in the procedure set or verified the
# tier -- the precondition was assumed to already hold. Two of them,
# `livespec-overseer` and `livespec-driver-pi`, were found on 2026-08-21 gating
# merges on self-hosted capacity at `first_time_contributors`: live, and
# unnoticed since their cutovers. `livespec-driver-pi` shows the mechanism
# plainly -- cut over as the ninth repository on 2026-08-20 with a tier that had
# never been strict, so the cutover engaged a precondition the repository did
# not meet and shipped anyway. A checklist row would not have caught it; that
# cutover otherwise completed correctly.
#
# THIS IS NOT THE CI GATE that livespec-s43svm.39 scope item 3 rejected. The
# tier endpoint requires fine-grained `Administration: read`, which the workflow
# `permissions:` key does not expose and `GITHUB_TOKEN` can therefore never
# hold; a CI-resident detector would mean escalating the shared fleet GitHub App
# across every repository it is installed in. This script runs in the
# MAINTAINER's shell at cutover time under the MAINTAINER's own credential, so
# it needs no escalation at all.
#
# FAIL-CLOSED, in every direction. Every way of NOT KNOWING the tier -- an
# endpoint error, a credential without the scope, an unexpected payload --
# refuses the write. A write that proceeded on an unreadable tier would
# reproduce the exact failure this exists to prevent. `--set-tier` does not
# trust its own write either: it re-reads and requires the strict value back
# before the variable is touched.
#
# ROUTING BACK TO HOSTED CAPACITY IS UNGATED, and deliberately. The precondition
# is conditional on self-hosted routing, so a write of `["ubuntu-latest"]` reads
# no tier and makes no second call. Failover away from a sick pool must never be
# blocked by a permissions endpoint.
#
# Requires: `gh`, authenticated with a credential carrying `Administration:
# read` on the target repository (`Administration: write` as well for
# `--set-tier`), plus the usual Actions variables scope.
set -euo pipefail

USAGE="usage: set-ci-runner-labels.sh OWNER/REPO LABEL [LABEL...] [--set-tier] [--dry-run]

  OWNER/REPO   the target repository, e.g. thewoolleyman/livespec-overseer
  LABEL        one or more runner labels, written as a JSON array in the order
               given, e.g. livespec-overseer-k3s   (hosted labels are those
               beginning ubuntu, windows, or macos; anything else is treated as
               self-hosted and engages the fork-exclusion precondition)

  --set-tier   when the tier is not already strict, WRITE it to
               all_external_contributors, verify the write by re-reading, and
               only then set the variable. Without this flag a non-strict tier
               is refused and nothing is written.
  --dry-run    report what would happen -- including the tier verdict -- and
               write nothing. Reads only.

  Examples:
    set-ci-runner-labels.sh thewoolleyman/livespec-overseer livespec-overseer-k3s --dry-run
    set-ci-runner-labels.sh thewoolleyman/livespec-overseer livespec-overseer-k3s --set-tier
    set-ci-runner-labels.sh thewoolleyman/livespec-overseer ubuntu-latest"

STRICT_TIER="all_external_contributors"
SET_TIER=0
DRY_RUN=0
SLUG=""
LABELS=()

while [ $# -gt 0 ]; do
  case "$1" in
    --set-tier) SET_TIER=1; shift ;;
    --dry-run)  DRY_RUN=1; shift ;;
    -h|--help)  echo "$USAGE"; exit 0 ;;
    -*)         echo "FATAL: unknown option '$1'"$'\n'"$USAGE" >&2; exit 2 ;;
    *)
      if [ -z "$SLUG" ]; then
        SLUG="$1"
      else
        LABELS+=("$1")
      fi
      shift
      ;;
  esac
done

[ -n "$SLUG" ] || { echo "FATAL: OWNER/REPO is required"$'\n'"$USAGE" >&2; exit 2; }
case "$SLUG" in
  */*/*) echo "FATAL: '$SLUG' is not OWNER/REPO"$'\n'"$USAGE" >&2; exit 2 ;;
  */*)   : ;;
  *)     echo "FATAL: '$SLUG' is not OWNER/REPO"$'\n'"$USAGE" >&2; exit 2 ;;
esac
[ "${#LABELS[@]}" -gt 0 ] || { echo "FATAL: at least one LABEL is required"$'\n'"$USAGE" >&2; exit 2; }

command -v gh >/dev/null || { echo "FATAL: gh not found on PATH" >&2; exit 2; }

log() { printf '\n== %s ==\n' "$*"; }

# ---------------------------------------------------------------------------
# A label is HOSTED when it names GitHub-hosted capacity, which is exactly the
# `ubuntu`/`windows`/`macos` prefix set the fleet's own detector keys on (see
# livespec's `needs-attention-internal` Signal 6). Anything else is self-hosted:
# an unrecognised label must fall on the GATED side, never the ungated one.
is_self_hosted_label() {
  case "$1" in
    ubuntu*|windows*|macos*) return 1 ;;
    *)                       return 0 ;;
  esac
}

# JSON array, in the order given. Labels are GitHub runner labels -- a
# restricted character set -- so any label carrying a quote, a backslash, or
# whitespace is a typo or an injection attempt rather than a label, and is
# rejected rather than escaped.
json_array() {
  local out="[" first=1 label
  for label in "$@"; do
    case "$label" in
      ""|*[\"\\]*|*[[:space:]]*)
        echo "FATAL: '$label' is not a usable runner label (quote, backslash, whitespace, or empty)" >&2
        exit 2
        ;;
    esac
    if [ "$first" -eq 1 ]; then first=0; else out="${out},"; fi
    out="${out}\"${label}\""
  done
  printf '%s]' "$out"
}

VALUE="$(json_array "${LABELS[@]}")"

SELF_HOSTED=0
for label in "${LABELS[@]}"; do
  if is_self_hosted_label "$label"; then SELF_HOSTED=1; fi
done

log "Target ${SLUG}: CI_RUNNER_LABELS -> ${VALUE}"
if [ "$SELF_HOSTED" -eq 1 ]; then
  echo "  self-hosted capacity: the fork-exclusion precondition APPLIES to this write"
else
  echo "  hosted-only capacity: the fork-exclusion precondition does not apply; no tier read"
fi

# ---------------------------------------------------------------------------
# Read the tier. Branch on gh's EXIT CODE, never on whether its output is empty:
# on an error `gh api --jq` writes the error object to STDOUT and exits
# non-zero, so an emptiness test does not fire and the error JSON flows onward
# as if it were a value.
read_tier() {
  gh api "repos/${SLUG}/actions/permissions/fork-pr-contributor-approval" \
    --jq '.approval_policy' 2>/dev/null
}

if [ "$SELF_HOSTED" -eq 1 ]; then
  log "1. Read the fork-pull-request approval tier"
  if ! TIER="$(read_tier)"; then
    {
      echo "FATAL: could not read repos/${SLUG}/actions/permissions/fork-pr-contributor-approval."
      echo "       REFUSING the write. That endpoint needs fine-grained 'Administration: read';"
      echo "       an unreadable tier is not a strict tier, and routing this repository to"
      echo "       self-hosted capacity without knowing it is the failure this script exists"
      echo "       to prevent."
    } >&2
    exit 1
  fi
  echo "  approval_policy: ${TIER}"

  if [ "$TIER" != "$STRICT_TIER" ]; then
    if [ "$SET_TIER" -ne 1 ]; then
      {
        echo "FATAL: ${SLUG} is at '${TIER}', not '${STRICT_TIER}'. REFUSING the write."
        echo "       Under the weaker tiers a RETURNING outside contributor's fork pull"
        echo "       request runs its fork-controlled workflow definition with no approval"
        echo "       event -- so routing this repository's merge gate to self-hosted"
        echo "       capacity would put fork-controlled code on the runner host."
        echo "       Re-run with --set-tier to correct it in the same operation, or set it"
        echo "       yourself and re-run."
      } >&2
      exit 1
    fi

    if [ "$DRY_RUN" -eq 1 ]; then
      echo "  DRY RUN: would raise the tier from '${TIER}' to '${STRICT_TIER}' before writing"
    else
      log "2. Raise the tier to ${STRICT_TIER}"
      gh api --method PUT "repos/${SLUG}/actions/permissions/fork-pr-contributor-approval" \
        -f "approval_policy=${STRICT_TIER}" >/dev/null

      # Do NOT trust the write. A tier that reports success and reads back weak
      # leaves the repository in exactly the state this refuses to create.
      if ! TIER="$(read_tier)"; then
        echo "FATAL: tier write reported success but the verification read failed. REFUSING the variable write." >&2
        exit 1
      fi
      if [ "$TIER" != "$STRICT_TIER" ]; then
        echo "FATAL: tier write reported success but the repository still reads '${TIER}'. REFUSING the variable write." >&2
        exit 1
      fi
      echo "  verified: ${TIER}"
    fi
  fi
fi

# ---------------------------------------------------------------------------
if [ "$DRY_RUN" -eq 1 ]; then
  log "DRY RUN: nothing written. CI_RUNNER_LABELS would be set to ${VALUE}."
  exit 0
fi

log "3. Write CI_RUNNER_LABELS"
gh variable set CI_RUNNER_LABELS --repo "$SLUG" --body "$VALUE"

log "4. Read back and verify"
if ! READBACK="$(gh api "repos/${SLUG}/actions/variables/CI_RUNNER_LABELS" --jq '.value' 2>/dev/null)"; then
  echo "FATAL: wrote CI_RUNNER_LABELS but could not read it back. Verify by hand before dispatching any job." >&2
  exit 1
fi
if [ "$READBACK" != "$VALUE" ]; then
  echo "FATAL: wrote '${VALUE}' but ${SLUG} reads back '${READBACK}'." >&2
  exit 1
fi
echo "  ${READBACK}"

if [ "$SELF_HOSTED" -eq 1 ]; then
  log "DONE. ${SLUG} routes to ${VALUE} at tier ${STRICT_TIER}."
else
  log "DONE. ${SLUG} routes to ${VALUE} (hosted capacity)."
fi
