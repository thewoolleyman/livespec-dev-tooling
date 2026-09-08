#!/usr/bin/env bash
# prune-sandbox-images.sh — bound the set of Fabro sandbox images resident in
# this node's containerd, by keeping the newest N releases OF EACH TAG FAMILY
# and removing older ones that nothing needs. Item `livespec-h96p`.
#
# WHY. Nothing ever removed these. Measured on poweredge-xubuntu 2026-09-07:
# 454 refs of ghcr.io/thewoolleyman/livespec-fabro-sandbox — 227 tag refs and
# their 227 paired digest refs — spanning v1.46.0 to v1.58.6 across three
# families (python 100, python-rust 78, python-rust-fuzz 49), inside 729 total
# image refs and 24 GB under /var/lib/rancher/k3s/agent/containerd. The item
# recorded 60 tags / ~21.8 GB when it was filed on 2026-09-02. 60 to 227 in
# five days is the argument for a policy; the disk number is not, because
# consecutive sandbox releases share nearly every layer (../README.md "Sandbox
# image hygiene"). What is actually unbounded is the RECORD count, and with it
# every listing, GC pass and metadata walk containerd does over it.
#
# ============================================================================
# HOW IT DECIDES WHAT IS SAFE TO REMOVE
# ============================================================================
# A prune that can remove a running workload's image is a worse failure than
# the disk it reclaims. Five gates, each of which alone is enough to save an
# image, and any one of which failing to answer stops the run rather than
# letting it guess:
#
#   1. SCOPE. Only image records inside the single repository named by
#      ${REPOSITORY} below are ever considered. It is a constant, not a flag,
#      because the scope IS the safety property and a scope that can be typed
#      at a call site can be mistyped there. Everything else on the node is
#      invisible to this script — in particular the pinned ARC runner image
#      ghcr.io/actions/actions-runner:2.336.0@sha256:0cfdcc70…, from which both
#      the fleet-patched container hook and the host-side externals seed are
#      derived (`livespec-wm7c`), is not in this repository and is never a
#      candidate.
#
#   2. WHOLE-RECORD SCOPE. A record carrying ANY reference outside the
#      repository is skipped entirely and reported, never removed. This matters
#      because of gate 3's mechanism: removal is per-RECORD, so a record shared
#      with another repository could not be removed without removing that
#      repository's reference too.
#
#   3. REMOVAL IS PER-RECORD, SO KEEPING IS PER-RECORD. containerd's CRI
#      RemoveImage deletes ALL references of the image it resolves, not just
#      the one named. That is not a detail — the sandbox images make it
#      load-bearing. The v1.40.1 tag was BYTE-IDENTICAL to v1.40.0 (10 layers
#      each, 10/10 shared), so two release tags routinely name ONE record, and
#      `crictl rmi …:v1.40.0` would take v1.40.1 with it. Therefore a record is
#      a candidate only when EVERY one of its in-scope tags is prunable; one
#      kept or protected tag saves the whole record. This is also the answer to
#      "each tag has a paired digest-pinned ref": the tag ref and the
#      `…@sha256:` ref are two references to the SAME record, which is why the
#      resident count is exactly twice the tag count, and why they are removed
#      together or not at all.
#
#   4. LIVE REFERENCES, FROM TWO SOURCES, AND NEITHER IS OPTIONAL.
#      (a) The cluster: every image named by any PodSpec of a Pod, Deployment,
#          StatefulSet, DaemonSet, ReplicaSet, Job or CronJob, in every
#          namespace. CronJobs and Jobs are the reason this reads WORKLOADS and
#          not just running containers — the pool has objects that pin OLD tags
#          and hold no pod between runs. Two live examples, both of which a
#          naive "keep the newest N" would have deleted:
#          ../warm-cache-cronjob.yaml pins
#          `livespec-fabro-sandbox:python-rust-fuzz-v1.46.0` and fires on a
#          half-hourly schedule; ../../isolation/negative-control-job.yaml pins
#          `:python-v1.40.1` and runs every six hours. Between runs there is no
#          pod, no container, and nothing in containerd saying either image is
#          needed.
#      (b) The node: every image and imageRef of every container that EXISTS in
#          containerd, running or not.
#      The union is taken as OPPORTUNISTICALLY WIDE as the JSON allows — every
#      `"image"`, `"imageID"` and `"imageRef"` string in either dump, including
#      status fields — because over-protection costs disk and under-protection
#      costs a workload.
#
#   5. FAIL CLOSED, TWICE.
#      (a) If the cluster read fails, or succeeds and yields NO protected
#          references at all, the run STOPS. An empty result from a query that
#          was supposed to enumerate a live cluster is the failure mode
#          `.ai/verifying-against-the-right-source.md` is about: it looks
#          exactly like "nothing is protected", which is the one answer that
#          would authorise deleting everything. A live pool always has the ARC
#          controller and listener pods, so zero is never the truth.
#      (b) The protected set is collected AGAIN immediately before the first
#          removal, and every candidate is re-tested against it. A pod admitted
#          while this script was deciding would otherwise be pruned out from
#          under itself. This is what "safe to run while CI is active" rests
#          on, together with the fact that removing an image reference does not
#          disturb a container already running from it.
#
# ============================================================================
# WHAT IT KEEPS
# ============================================================================
# PER FAMILY, NOT GLOBALLY. A tag is `<family>-v<major>.<minor>.<patch>`, and
# the families are wildly uneven — 100 / 78 / 49 resident on 2026-09-07, and
# the registry has carried six of them (base, python, python-agent,
# python-rust, python-rust-agent, python-rust-fuzz). A global "keep the newest
# N" would spend the whole budget on whichever family releases most often and
# starve the others to nothing. So the newest ${KEEP_PER_FAMILY} of EACH family
# are kept.
#
# THE FAMILY LIST IS DERIVED, NEVER WRITTEN DOWN. Families come from the tags
# actually resident on this node, by stripping the `-v<semver>` suffix. A
# hardcoded list would have said "python, python-rust, python-rust-fuzz" —
# correct for this node on 2026-09-07 and wrong about the registry, which holds
# three more. Deriving also means a new family is bounded the day it appears
# rather than the day someone remembers to add it here.
#
# SEMANTIC ORDER, NOT LEXICAL. v1.46.0 < v1.49.0 < v1.58.6 by version and
# `v1.46.0` > `v1.5.0` > `v1.49.0` by string, so versions are compared
# component-wise as numbers. A lexical sort here would keep an arbitrary set
# and delete recent releases.
#
# A TAG THAT IS NOT `<family>-v<semver>` IS NEVER PRUNED. The repository also
# carries `<family>-sha-<shortsha>` tags. They have no version, so there is no
# defensible "newest N" among them, and one of them may well be what something
# is pinned to. They are kept, their record with them, and counted in the
# report so an operator can see if they ever start to matter.
#
# ============================================================================
# HOW IT IS RUN
# ============================================================================
# REPORT-ONLY BY DEFAULT; `--apply` removes. This inverts the usual `--dry-run`
# convention of this tree, deliberately and for one documented reason: the
# fleet has already been bitten by a destructive verb whose bare form acts and
# whose safe form is the flag (the worktree reaper — "the two forms sitting
# side by side is precisely what makes this easy to get wrong"). For a script
# that deletes container images on a live CI node, the bare invocation is the
# safe one and the destructive one has to be asked for by name. The systemd
# unit beside this file passes `--apply` explicitly, in the open, where an
# operator reading the unit can see it.
#
# IDEMPOTENT: a second run finds the surplus already gone and removes nothing.
#
# Requires: root, `crictl` (or `k3s crictl`), `kubectl` with a kubeconfig that
# can list workloads cluster-wide, and python3 (to read crictl's JSON; it is
# a pre-gate, not an assumption). The cluster read is why the installer beside
# this file is SERVER-ONLY — an agent holds no admin kubeconfig, and gate 4(a)
# cannot be satisfied without one. On an agent this script refuses rather than
# pruning on the node evidence alone.
set -euo pipefail

# The scope. A constant on purpose — see gate 1.
REPOSITORY="ghcr.io/thewoolleyman/livespec-fabro-sandbox"

KEEP_PER_FAMILY="${KEEP_PER_FAMILY:-10}"
KUBECONFIG="${KUBECONFIG:-/etc/rancher/k3s/k3s.yaml}"
export KUBECONFIG

APPLY=0
SCRIPT_NAME="$(basename "$0")"
USAGE="usage: ${SCRIPT_NAME} [--apply] [--keep N]   (default: report only, remove nothing)"

die() { printf 'FATAL: %s\n' "$*" >&2; exit 1; }
log() { printf '%s %s: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${SCRIPT_NAME}" "$*"; }

while [ $# -gt 0 ]; do
  case "$1" in
    --apply) APPLY=1 ;;
    --keep)
      [ $# -ge 2 ] || die "--keep needs a value -- ${USAGE}"
      KEEP_PER_FAMILY="$2"; shift ;;
    -h|--help) printf '%s\n' "$USAGE"; exit 0 ;;
    *) die "unknown argument '$1' -- ${USAGE}" ;;
  esac
  shift
done

case "$KEEP_PER_FAMILY" in
  ''|*[!0-9]*) die "--keep must be a non-negative integer, got '${KEEP_PER_FAMILY}'" ;;
esac
[ "$KEEP_PER_FAMILY" -ge 1 ] || die "--keep must be at least 1: a policy that keeps nothing is not a retention policy"

[ "$(id -u)" -eq 0 ] || die "must run as root (talks to containerd)"

command -v python3 >/dev/null 2>&1 || die "python3 not found on PATH; it is how this script reads crictl's JSON"

# crictl, in either of the two forms a k3s node offers. Resolved once so the
# listing and the removals cannot end up aimed at two different runtimes —
# ../../k3s-runtime-ready.sh makes the same argument about `ctr`.
crictl_argv=()
if command -v crictl >/dev/null 2>&1; then
  crictl_argv=(crictl)
elif command -v k3s >/dev/null 2>&1; then
  crictl_argv=(k3s crictl)
else
  die "neither 'crictl' nor 'k3s' found on PATH; this must run on a k3s node"
fi

command -v kubectl >/dev/null 2>&1 || die "kubectl not found on PATH; gate 4(a) needs a cluster read"
[ -r "$KUBECONFIG" ] || die "KUBECONFIG '${KUBECONFIG}' is not readable; an agent node holds no admin kubeconfig, and this prune refuses to run on node evidence alone"

WORKDIR="$(mktemp -d)"
cleanup() { rm -rf "$WORKDIR"; }
trap cleanup EXIT

# ---------------------------------------------------------------------------
# Gate 4: the protected set.
# ---------------------------------------------------------------------------
# Every `"image"`, `"imageID"` and `"imageRef"` string in the cluster's
# workloads and in this node's containers. Deliberately a text scrape of the
# JSON rather than a field-by-field walk: it reaches initContainers,
# ephemeralContainers, a CronJob's jobTemplate and every status field without
# naming any of them, so a Kubernetes shape this script has never heard of
# still protects its image.
collect_protected() {  # collect_protected OUTFILE
  local out="$1" cluster="${WORKDIR}/cluster.json" node="${WORKDIR}/node.json"
  if ! kubectl get pods,deployments,statefulsets,daemonsets,replicasets,jobs,cronjobs \
        --all-namespaces -o json > "$cluster" 2>"${WORKDIR}/cluster.err"; then
    die "the cluster read failed, so nothing can be shown to be unused: $(tr '\n' ' ' < "${WORKDIR}/cluster.err")"
  fi
  # The node half is best-effort: a container listing that fails leaves the
  # cluster half, which is the stronger of the two. The run still stops if the
  # UNION is empty.
  "${crictl_argv[@]}" ps -a -o json > "$node" 2>/dev/null || : > "$node"
  # `|| true` because a dump naming no image at all makes `grep` exit 1, and
  # under `pipefail` that would abort the run HERE — before the emptiness gate
  # below, which is the thing that exists to explain exactly that case. The
  # gate wants an empty file, not a dead script.
  cat "$cluster" "$node" \
    | grep -oE '"(image|imageID|imageRef)"[[:space:]]*:[[:space:]]*"[^"]*"' \
    | sed -E 's/^"[^"]+"[[:space:]]*:[[:space:]]*"(.*)"$/\1/' \
    | sort -u > "$out" || true
}

PROTECTED="${WORKDIR}/protected.txt"
collect_protected "$PROTECTED"
protected_count="$(wc -l < "$PROTECTED" | tr -d ' ')"
[ "$protected_count" -gt 0 ] || die "the cluster and node reads produced ZERO image references. A live pool always runs the ARC controller and listener pods, so this is a broken read, not an idle cluster — and 'nothing is protected' is the one answer that would authorise deleting everything"
log "protected references in scope-independent form: ${protected_count}"

declare -A PROTECTED_REF=()
while IFS= read -r ref; do
  [ -n "$ref" ] || continue
  PROTECTED_REF["$ref"]=1
done < "$PROTECTED"

# ---------------------------------------------------------------------------
# The resident image records.
# ---------------------------------------------------------------------------
# One line per record: id, size in bytes, pinned flag, and a comma-separated
# list of every reference containerd holds for it (tags first, then digests).
# python3 does the JSON and NOTHING else — every policy decision below is in
# this file, in the open.
list_records() {  # list_records -> TSV on stdout
  "${crictl_argv[@]}" images -o json | python3 -c '
import json, sys

data = json.load(sys.stdin)
for image in data.get("images") or []:
    refs = list(image.get("repoTags") or []) + list(image.get("repoDigests") or [])
    if not refs:
        continue
    print("\t".join([
        image.get("id", ""),
        str(image.get("size", "0")),
        "1" if image.get("pinned") else "0",
        ",".join(refs),
    ]))
'
}

RECORDS="${WORKDIR}/records.tsv"
list_records > "$RECORDS"

declare -A ID_SIZE=() ID_REFS=() ID_TAGS=() ID_KEEP_REASON=()
declare -A VERSION_ID=() VERSION_TAG=()
declare -A FAMILY_SEEN=()
TAG_PREFIX="${REPOSITORY}:"
in_scope_ids=()
unversioned_records=0
foreign_mixed=0

while IFS=$'\t' read -r image_id size pinned refs; do
  [ -n "$image_id" ] || continue
  in_scope=0
  out_of_scope=0
  tags=""
  IFS=',' read -r -a ref_list <<< "$refs"
  for ref in "${ref_list[@]}"; do
    case "$ref" in
      "${REPOSITORY}:"*) in_scope=1; tags="${tags}${tags:+,}${ref}" ;;
      "${REPOSITORY}@"*) in_scope=1 ;;
      *) out_of_scope=1 ;;
    esac
  done
  [ "$in_scope" -eq 1 ] || continue          # gate 1: another repository entirely
  # A size containerd did not report as a plain byte count is recorded as 0
  # rather than left to fail an arithmetic expansion later: the report's MiB
  # column is information, and no decision is taken from it.
  case "$size" in ''|*[!0-9]*) size=0 ;; esac
  ID_SIZE["$image_id"]="$size"
  ID_REFS["$image_id"]="$refs"
  ID_TAGS["$image_id"]="$tags"
  in_scope_ids+=("$image_id")
  if [ "$out_of_scope" -eq 1 ]; then
    # gate 2: shared with a repository outside the scope. Removal is
    # per-record, so this record cannot be touched without touching that.
    ID_KEEP_REASON["$image_id"]="shares its record with a reference outside ${REPOSITORY}"
    foreign_mixed=$((foreign_mixed + 1))
    continue
  fi
  if [ "$pinned" = "1" ]; then
    ID_KEEP_REASON["$image_id"]="containerd has pinned this record"
    continue
  fi
  if [ -z "$tags" ]; then
    # Digest references only. Nothing names a version, so there is no place
    # for it in a newest-N order; keep it.
    ID_KEEP_REASON["$image_id"]="carries no tag, only digest references"
    continue
  fi
done < "$RECORDS"

# Gate 4, applied: any reference of a record, or the record's own id, appearing
# in the protected set saves the whole record.
protect_referenced_records() {
  local image_id ref
  for image_id in "${in_scope_ids[@]}"; do
    [ -z "${ID_KEEP_REASON[$image_id]:-}" ] || continue
    if [ -n "${PROTECTED_REF[$image_id]:-}" ]; then
      ID_KEEP_REASON["$image_id"]="its image id is referenced by a live workload or an existing container"
      continue
    fi
    IFS=',' read -r -a ref_list <<< "${ID_REFS[$image_id]}"
    for ref in "${ref_list[@]}"; do
      if [ -n "${PROTECTED_REF[$ref]:-}" ]; then
        ID_KEEP_REASON["$image_id"]="${ref} is referenced by a live workload or an existing container"
        break
      fi
    done
  done
}
protect_referenced_records

# Parse the tags of every still-unprotected record into (family, version).
# A tag that does not parse protects its record — see "A TAG THAT IS NOT
# <family>-v<semver> IS NEVER PRUNED".
for image_id in "${in_scope_ids[@]}"; do
  [ -z "${ID_KEEP_REASON[$image_id]:-}" ] || continue
  IFS=',' read -r -a ref_list <<< "${ID_TAGS[$image_id]}"
  for ref in "${ref_list[@]}"; do
    tag="${ref#"$TAG_PREFIX"}"
    if [[ "$tag" =~ ^(.+)-v([0-9]+)\.([0-9]+)\.([0-9]+)$ ]]; then
      family="${BASH_REMATCH[1]}"
      version="${BASH_REMATCH[2]}.${BASH_REMATCH[3]}.${BASH_REMATCH[4]}"
      FAMILY_SEEN["$family"]=1
      VERSION_ID["${family}|${version}"]="$image_id"
      VERSION_TAG["${family}|${version}"]="$ref"
    else
      ID_KEEP_REASON["$image_id"]="carries the unversioned tag ${ref}"
      unversioned_records=$((unversioned_records + 1))
      break
    fi
  done
done

# Per family: order the versions newest-first by NUMBER, keep the head, and
# protect every record any kept version names.
kept_by_policy=0
keep_summary=""
for family in $(printf '%s\n' "${!FAMILY_SEEN[@]}" | sort); do
  versions=()
  for key in "${!VERSION_ID[@]}"; do
    case "$key" in "${family}|"*) versions+=("${key#*|}") ;; esac
  done
  ordered="$(printf '%s\n' "${versions[@]}" | sort -t. -k1,1nr -k2,2nr -k3,3nr)"
  total="${#versions[@]}"
  kept="$(printf '%s\n' "$ordered" | head -n "$KEEP_PER_FAMILY")"
  newest="$(printf '%s\n' "$ordered" | head -n 1)"
  oldest_kept="$(printf '%s\n' "$kept" | tail -n 1)"
  # What is actually kept, which is fewer than the budget when the family has
  # fewer versions than that — a summary line claiming to keep ten of six
  # would be a small lie in the one place an operator checks the policy.
  effective_keep="$KEEP_PER_FAMILY"
  [ "$effective_keep" -le "$total" ] || effective_keep="$total"
  keep_summary="${keep_summary}  ${family}: ${total} resident version(s), keeping the newest ${effective_keep} (v${newest} down to v${oldest_kept})"$'\n'
  while IFS= read -r version; do
    [ -n "$version" ] || continue
    image_id="${VERSION_ID["${family}|${version}"]}"
    if [ -z "${ID_KEEP_REASON[$image_id]:-}" ]; then
      ID_KEEP_REASON["$image_id"]="holds ${VERSION_TAG["${family}|${version}"]}, one of the newest ${KEEP_PER_FAMILY} of ${family}"
      kept_by_policy=$((kept_by_policy + 1))
    fi
  done <<< "$kept"
done

# Whatever is left is a candidate: in scope, wholly in scope, unpinned, tagged,
# every tag versioned, no tag among the newest N of its family, and nothing
# alive referring to it.
candidates=()
candidate_bytes=0
for image_id in "${in_scope_ids[@]}"; do
  [ -z "${ID_KEEP_REASON[$image_id]:-}" ] || continue
  candidates+=("$image_id")
  candidate_bytes=$((candidate_bytes + ${ID_SIZE[$image_id]:-0}))
done

# ---------------------------------------------------------------------------
# Report. Always printed, in both modes, before anything is removed.
# ---------------------------------------------------------------------------
printf '\n== %s: %s ==\n' "${SCRIPT_NAME}" "$([ "$APPLY" -eq 1 ] && echo 'APPLY — records below will be removed' || echo 'REPORT ONLY — nothing will be removed (pass --apply to remove)')"
printf 'repository:        %s\n' "$REPOSITORY"
printf 'keep per family:   %s\n' "$KEEP_PER_FAMILY"
printf 'resident records:  %s in this repository\n' "${#in_scope_ids[@]}"
printf 'kept by policy:    %s\n' "$kept_by_policy"
printf 'kept, other:       %s unversioned-tag record(s), %s record(s) shared outside the repository\n' "$unversioned_records" "$foreign_mixed"
printf 'candidates:        %s record(s), %s MiB of record size\n' "${#candidates[@]}" "$((candidate_bytes / 1048576))"
printf '\nper family:\n%s' "$keep_summary"

if [ "${#candidates[@]}" -eq 0 ]; then
  printf '\nnothing to remove.\n'
  exit 0
fi

printf '\nrecords that would be removed (every reference of each goes with it):\n'
for image_id in "${candidates[@]}"; do
  printf '  %s  %6s MiB  %s\n' "${image_id:0:19}" "$(( ${ID_SIZE[$image_id]:-0} / 1048576 ))" "${ID_REFS[$image_id]}"
done

if [ "$APPLY" -eq 0 ]; then
  printf '\n-- report only: nothing was removed. Re-run with --apply to remove the %s record(s) above. --\n' "${#candidates[@]}"
  exit 0
fi

# ---------------------------------------------------------------------------
# Gate 5(b): re-read the protected set immediately before removing anything, so
# a pod admitted while the above was being decided is not pruned out from under
# itself.
# ---------------------------------------------------------------------------
collect_protected "$PROTECTED"
[ -s "$PROTECTED" ] || die "the re-read of the protected set came back empty; removing nothing"
declare -A PROTECTED_NOW=()
while IFS= read -r ref; do
  [ -n "$ref" ] || continue
  PROTECTED_NOW["$ref"]=1
done < "$PROTECTED"

removed=0
skipped_late=0
removed_bytes=0
for image_id in "${candidates[@]}"; do
  # Re-test against the fresh set.
  late=""
  [ -z "${PROTECTED_NOW[$image_id]:-}" ] || late="$image_id"
  IFS=',' read -r -a ref_list <<< "${ID_REFS[$image_id]}"
  for ref in "${ref_list[@]}"; do
    [ -z "${PROTECTED_NOW[$ref]:-}" ] || { late="$ref"; break; }
  done
  if [ -n "$late" ]; then
    log "SKIPPED ${image_id:0:19}: ${late} became referenced while this run was deciding"
    skipped_late=$((skipped_late + 1))
    continue
  fi
  # Gates 1 and 2 again, as an assertion rather than a decision: nothing
  # reaches a removal without every one of its references being inside the
  # repository. If this ever fires, the classification above is wrong and the
  # run must stop rather than continue past it.
  for ref in "${ref_list[@]}"; do
    case "$ref" in
      "${REPOSITORY}:"*|"${REPOSITORY}@"*) ;;
      *) die "refusing to remove ${image_id}: reference '${ref}' is outside ${REPOSITORY} (classification bug — nothing further was removed)" ;;
    esac
  done
  if "${crictl_argv[@]}" rmi "$image_id" >/dev/null 2>"${WORKDIR}/rmi.err"; then
    removed=$((removed + 1))
    removed_bytes=$((removed_bytes + ${ID_SIZE[$image_id]:-0}))
    log "removed ${image_id:0:19} (${ID_TAGS[$image_id]})"
  else
    # A single failed removal is not a reason to abandon the rest: the usual
    # cause is a record that became in-use between the re-read and now, which
    # containerd refuses, which is the outcome this script wants anyway.
    log "WARN could not remove ${image_id:0:19}: $(tr '\n' ' ' < "${WORKDIR}/rmi.err")"
  fi
done

log "removed ${removed} record(s), ${skipped_late} skipped as newly referenced, ${removed_bytes} bytes of record size"
