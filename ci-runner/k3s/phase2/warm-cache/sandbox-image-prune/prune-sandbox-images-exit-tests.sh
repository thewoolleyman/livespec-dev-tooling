#!/usr/bin/env bash
# prune-sandbox-images-exit-tests.sh — prove what ./prune-sandbox-images.sh
# decides, WITHOUT touching any host: no containerd, no cluster, no root, and
# no image removed anywhere. Item `livespec-h96p`.
#
# WHY THESE AND NOT A LIVE RUN. The prune's whole value is in what it REFUSES
# to remove, and a live run only ever demonstrates the case the node happens to
# be in that hour. The interesting cases — an image that only a half-hourly
# CronJob needs, two release tags sharing one record, a family with two
# releases sitting beside one with a hundred, a cluster read that comes back
# empty — are cases the pool is not in on demand. So the node is faked and the
# decisions are read off the report.
#
# WHAT IS PROVED:
#   A. SCOPE. The pinned ARC runner image is never a candidate, and no
#      `crictl rmi` ever names it — the one image whose loss would take the
#      fleet's runners with it (`livespec-wm7c`).
#   B. LIVE WORKLOADS, NOT JUST RUNNING PODS. A tag that only a CronJob's
#      jobTemplate names — no pod, no container, and old enough to be well
#      outside the newest N — is kept, while the still-older release beside it
#      is pruned.
#   C. PER FAMILY, NOT GLOBALLY. A family with a single resident release keeps
#      it, while a busier family loses its oldest. Under a global newest-N the
#      small family would be starved to nothing.
#   D. SEMANTIC ORDER. v1.5.0 is pruned while v1.49.0 is kept. A lexical sort
#      decides this pair the other way round, so it is the case that separates
#      the two orderings.
#   E. ONE RECORD, TWO TAGS. A record carrying a kept tag AND a tag outside the
#      keep set is kept whole — because removal is per-record, this is the
#      byte-identical-layers case the v1.40.0/v1.40.1 finding is about.
#   F. THE PAIRED DIGEST REF GOES WITH THE TAG, and is shown doing so.
#   G. REPORT ONLY BY DEFAULT. A bare invocation runs no `crictl rmi` at all.
#   H. --apply REMOVES EXACTLY THE CANDIDATES, by record, and nothing else.
#   I. FAIL CLOSED on a cluster read that errors.
#   J. FAIL CLOSED on a cluster read that succeeds and names no image — the
#      empty-result trap, which reads exactly like "nothing is protected".
#   K. An unversioned `-sha-` tag is kept.
#   L. A record sharing a reference with another repository is kept.
#   M. LATE PROTECTION. A candidate that becomes referenced between the
#      decision and the removal is skipped, not removed.
#
# HOW IT STAYS OFF THE HOST. Every case prepends a scratch PATH carrying fakes
# for `id` (so the root check passes without root), `crictl` and `kubectl`. The
# fake `crictl` writes every `rmi` it is asked for into a TRIPWIRE file, which
# is what cases A, G and H read. `python3` is deliberately NOT faked — the real
# one parses the fake's JSON, which is the only thing the script uses it for.
# The suite never runs as root and mutates nothing outside its own scratch dir.
#
# THE FAKE IMAGE IDS ARE SHORT (`sha256:aaa1`) where a real containerd would
# give 64 hex characters. Nothing in the script under test parses an id, and
# short ones make the assertions below readable.
#
# Exit 0 iff every test passes.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="${HERE}/prune-sandbox-images.sh"
REPO="ghcr.io/thewoolleyman/livespec-fabro-sandbox"

pass=0; fail=0
ok() { printf '  PASS  %s\n' "$1"; pass=$((pass + 1)); }
no() { printf '  FAIL  %s\n' "$1"; fail=$((fail + 1)); }

TMPROOT="$(mktemp -d)"
case "$TMPROOT" in
  /tmp/*|/var/tmp/*) ;;
  *) echo "FATAL: mktemp -d returned an unexpected path '${TMPROOT}'" >&2; exit 1 ;;
esac
cleanup() { rm -rf "$TMPROOT"; }
trap cleanup EXIT

FAKEBIN="${TMPROOT}/fakebin"
mkdir -p "$FAKEBIN"

# --------------------------------------------------------------------------
# The fakes. Single-quoted heredocs on purpose: each body is the FAKE's source,
# expanded when the fake runs and not when this suite writes it.
# --------------------------------------------------------------------------
cat > "${FAKEBIN}/id" <<'FAKE'
#!/usr/bin/env bash
# The script under test only ever asks `id -u`, to refuse a non-root run.
echo 0
FAKE

cat > "${FAKEBIN}/crictl" <<'FAKE'
#!/usr/bin/env bash
case "$1" in
  images) cat "${FAKE_IMAGES_JSON}" ;;
  ps)     [ -f "${FAKE_PS_JSON:-}" ] && cat "${FAKE_PS_JSON}" || echo '{"containers":[]}' ;;
  rmi)    shift; printf '%s\n' "$1" >> "${TRIPWIRE_RMI}"; exit "${FAKE_RMI_EXIT:-0}" ;;
  *)      echo "unexpected crictl call: $*" >&2; exit 99 ;;
esac
FAKE

cat > "${FAKEBIN}/kubectl" <<'FAKE'
#!/usr/bin/env bash
# Counts its own calls, so a case can make the SECOND read (the pre-removal
# re-check) differ from the first.
n=0
[ -f "${KUBECTL_CALLS}" ] && n="$(cat "${KUBECTL_CALLS}")"
n=$((n + 1))
printf '%s' "$n" > "${KUBECTL_CALLS}"
if [ "${FAKE_KUBECTL_EXIT:-0}" -ne 0 ]; then
  echo "the server could not find the requested resource" >&2
  exit "${FAKE_KUBECTL_EXIT}"
fi
if [ "$n" -ge 2 ] && [ -f "${FAKE_CLUSTER_JSON_2:-}" ]; then
  cat "${FAKE_CLUSTER_JSON_2}"
else
  cat "${FAKE_CLUSTER_JSON}"
fi
FAKE

chmod +x "${FAKEBIN}/id" "${FAKEBIN}/crictl" "${FAKEBIN}/kubectl"

# A readable kubeconfig is a precondition of the script; its contents are never
# read by anything here, because `kubectl` is a fake.
KUBECONFIG_FILE="${TMPROOT}/kubeconfig"
echo "fake" > "$KUBECONFIG_FILE"

# --------------------------------------------------------------------------
# The fixture node: one containerd image listing exercising every gate.
# --------------------------------------------------------------------------
IMAGES_JSON="${TMPROOT}/images.json"
cat > "$IMAGES_JSON" <<JSON
{"images":[
 {"id":"sha256:aaa1","size":"268435456","pinned":false,
  "repoTags":["${REPO}:python-v1.58.6"],"repoDigests":["${REPO}@sha256:aaa1"]},
 {"id":"sha256:bbb1","size":"268435456","pinned":false,
  "repoTags":["${REPO}:python-v1.49.0"],"repoDigests":["${REPO}@sha256:bbb1"]},
 {"id":"sha256:ccc1","size":"268435456","pinned":false,
  "repoTags":["${REPO}:python-v1.5.0"],"repoDigests":["${REPO}@sha256:ccc1"]},
 {"id":"sha256:ddd1","size":"268435456","pinned":false,
  "repoTags":["${REPO}:python-v1.46.0"],"repoDigests":["${REPO}@sha256:ddd1"]},
 {"id":"sha256:eee1","size":"268435456","pinned":false,
  "repoTags":["${REPO}:python-rust-fuzz-v1.46.0"],"repoDigests":["${REPO}@sha256:eee1"]},
 {"id":"sha256:fff1","size":"268435456","pinned":false,
  "repoTags":["${REPO}:python-rust-fuzz-v1.47.0"],"repoDigests":["${REPO}@sha256:fff1"]},
 {"id":"sha256:ggg1","size":"268435456","pinned":false,
  "repoTags":["${REPO}:python-rust-fuzz-v1.48.0"],"repoDigests":["${REPO}@sha256:ggg1"]},
 {"id":"sha256:hhh1","size":"268435456","pinned":false,
  "repoTags":["${REPO}:python-rust-fuzz-v1.45.0"],"repoDigests":["${REPO}@sha256:hhh1"]},
 {"id":"sha256:iii1","size":"268435456","pinned":false,
  "repoTags":["${REPO}:python-rust-v1.58.6","${REPO}:python-rust-v1.20.0"],
  "repoDigests":["${REPO}@sha256:iii1"]},
 {"id":"sha256:jjj1","size":"268435456","pinned":false,
  "repoTags":["${REPO}:python-rust-v1.58.5"],"repoDigests":["${REPO}@sha256:jjj1"]},
 {"id":"sha256:kkk1","size":"268435456","pinned":false,
  "repoTags":["${REPO}:python-rust-v1.10.0"],"repoDigests":["${REPO}@sha256:kkk1"]},
 {"id":"sha256:lll1","size":"268435456","pinned":false,
  "repoTags":["${REPO}:base-v1.10.0"],"repoDigests":["${REPO}@sha256:lll1"]},
 {"id":"sha256:mmm1","size":"268435456","pinned":false,
  "repoTags":["${REPO}:python-sha-abc1234"],"repoDigests":["${REPO}@sha256:mmm1"]},
 {"id":"sha256:nnn1","size":"268435456","pinned":false,
  "repoTags":["${REPO}:python-v1.1.0","ghcr.io/thewoolleyman/something-else:v1.1.0"],
  "repoDigests":["${REPO}@sha256:nnn1"]},
 {"id":"sha256:run1","size":"1073741824","pinned":true,
  "repoTags":["ghcr.io/actions/actions-runner:2.336.0"],
  "repoDigests":["ghcr.io/actions/actions-runner@sha256:0cfdcc70"]}
]}
JSON

# The cluster as this fixture's pool has it: the ARC runner image in a live
# pod, and ONE sandbox tag that exists only inside a CronJob's jobTemplate.
CLUSTER_JSON="${TMPROOT}/cluster.json"
cat > "$CLUSTER_JSON" <<JSON
{"items":[
 {"kind":"Pod","spec":{"containers":[
   {"name":"runner","image":"ghcr.io/actions/actions-runner:2.336.0"}]}},
 {"kind":"CronJob","spec":{"jobTemplate":{"spec":{"template":{"spec":{"containers":[
   {"name":"populate","image":"${REPO}:python-rust-fuzz-v1.46.0"}]}}}}}}
]}
JSON

# The same cluster, a moment later, with a pod that has just been admitted for
# a release the decision had already classified as surplus.
CLUSTER_JSON_LATE="${TMPROOT}/cluster-late.json"
cat > "$CLUSTER_JSON_LATE" <<JSON
{"items":[
 {"kind":"Pod","spec":{"containers":[
   {"name":"runner","image":"ghcr.io/actions/actions-runner:2.336.0"}]}},
 {"kind":"CronJob","spec":{"jobTemplate":{"spec":{"template":{"spec":{"containers":[
   {"name":"populate","image":"${REPO}:python-rust-fuzz-v1.46.0"}]}}}}}},
 {"kind":"Pod","spec":{"containers":[
   {"name":"job","image":"${REPO}:python-v1.5.0"}]}}
]}
JSON

EMPTY_CLUSTER_JSON="${TMPROOT}/cluster-empty.json"
echo '{"items":[]}' > "$EMPTY_CLUSTER_JSON"

# --------------------------------------------------------------------------
# run_prune OUTFILE [ARG...] -> the script's exit status, output in OUTFILE.
# Every invocation gets a fresh tripwire and a fresh kubectl call counter.
# --------------------------------------------------------------------------
TRIPWIRE_RMI="${TMPROOT}/rmi.log"
KUBECTL_CALLS="${TMPROOT}/kubectl.calls"
export TRIPWIRE_RMI KUBECTL_CALLS

run_prune() {
  local out="$1"; shift
  : > "$TRIPWIRE_RMI"
  : > "$KUBECTL_CALLS"
  env -i \
    PATH="${FAKEBIN}:/usr/bin:/bin" \
    HOME="$TMPROOT" \
    KUBECONFIG="$KUBECONFIG_FILE" \
    TRIPWIRE_RMI="$TRIPWIRE_RMI" \
    KUBECTL_CALLS="$KUBECTL_CALLS" \
    FAKE_IMAGES_JSON="${FAKE_IMAGES_JSON:-$IMAGES_JSON}" \
    FAKE_CLUSTER_JSON="${FAKE_CLUSTER_JSON:-$CLUSTER_JSON}" \
    FAKE_CLUSTER_JSON_2="${FAKE_CLUSTER_JSON_2:-}" \
    FAKE_KUBECTL_EXIT="${FAKE_KUBECTL_EXIT:-0}" \
    FAKE_RMI_EXIT="${FAKE_RMI_EXIT:-0}" \
    KEEP_PER_FAMILY="${KEEP:-2}" \
    bash "$SCRIPT" "$@" > "$out" 2>&1
  return $?
}

# would_remove OUTFILE -> the record ids the report lists as removable.
would_remove() {
  sed -n '/records that would be removed/,$p' "$1" \
    | grep -oE 'sha256:[a-z0-9]+' | sort -u
}

# --------------------------------------------------------------------------
printf '\n-- report-only run over the fixture node --\n'
OUT="${TMPROOT}/report.out"
run_prune "$OUT"; status=$?

if [ "$status" -eq 0 ]; then ok "a report-only run exits 0"; else no "a report-only run exits 0 (got ${status})"; cat "$OUT"; fi

removable="$(would_remove "$OUT")"

# A. Scope: the ARC runner image is not a candidate and is never named.
if ! printf '%s\n' "$removable" | grep -q 'sha256:run1' && ! grep -q 'actions-runner' "$OUT"; then
  ok "A. the pinned ARC runner image is neither a candidate nor mentioned"
else
  no "A. the ARC runner image reached the report"
fi

# B. A CronJob-only tag, older than the newest N, survives; the still-older
#    release beside it does not.
if ! printf '%s\n' "$removable" | grep -q 'sha256:eee1'; then
  ok "B. python-rust-fuzz-v1.46.0 is kept — only a CronJob jobTemplate names it"
else
  no "B. python-rust-fuzz-v1.46.0 was classified as removable"
fi
if printf '%s\n' "$removable" | grep -q 'sha256:hhh1'; then
  ok "B. python-rust-fuzz-v1.45.0, which nothing names, is removable"
else
  no "B. python-rust-fuzz-v1.45.0 was not classified as removable"
fi

# C. Per-family: the single-release `base` family keeps its release.
if ! printf '%s\n' "$removable" | grep -q 'sha256:lll1'; then
  ok "C. base-v1.10.0 is kept — a global newest-N would have starved its family"
else
  no "C. the only release of the base family was classified as removable"
fi
if grep -q 'base: 1 resident version(s), keeping the newest 1' "$OUT"; then
  ok "C. the per-family summary reports what is actually kept, not the budget"
else
  no "C. the per-family summary does not report base's single kept release"
fi

# D. Semantic order: v1.5.0 goes, v1.49.0 stays.
if printf '%s\n' "$removable" | grep -q 'sha256:ccc1' \
   && ! printf '%s\n' "$removable" | grep -q 'sha256:bbb1'; then
  ok "D. python-v1.5.0 is removable and python-v1.49.0 is kept (semantic, not lexical)"
else
  no "D. the v1.5.0 / v1.49.0 pair was ordered lexically"
fi

# E. One record, two tags: a kept tag saves the whole record.
if ! printf '%s\n' "$removable" | grep -q 'sha256:iii1'; then
  ok "E. the record carrying both python-rust-v1.58.6 and v1.20.0 is kept whole"
else
  no "E. a record holding a kept tag was classified as removable"
fi

# F. The paired digest ref is shown going with the tag.
if grep -q "${REPO}:python-v1.5.0,${REPO}@sha256:ccc1" "$OUT"; then
  ok "F. the report shows the tag and its paired digest ref removed together"
else
  no "F. the report does not show the paired digest ref"
fi

# G. Report only: nothing was removed.
if [ ! -s "$TRIPWIRE_RMI" ]; then
  ok "G. a bare invocation ran no 'crictl rmi' at all"
else
  no "G. a bare invocation removed something: $(tr '\n' ' ' < "$TRIPWIRE_RMI")"
fi
if grep -q 'REPORT ONLY' "$OUT"; then
  ok "G. the report says so in its own first line"
else
  no "G. the report does not announce report-only mode"
fi

# K. An unversioned tag keeps its record.
if ! printf '%s\n' "$removable" | grep -q 'sha256:mmm1'; then
  ok "K. the python-sha-abc1234 record is kept — no version, no defensible order"
else
  no "K. an unversioned-tag record was classified as removable"
fi

# L. A record shared with another repository keeps it.
if ! printf '%s\n' "$removable" | grep -q 'sha256:nnn1'; then
  ok "L. a record also tagged in another repository is kept"
else
  no "L. a record shared outside the repository was classified as removable"
fi

# The whole expected candidate set, so a future change that adds a candidate
# has to say so here rather than slipping past the per-case assertions.
expected="$(printf '%s\n' sha256:ccc1 sha256:ddd1 sha256:hhh1 sha256:kkk1 | sort)"
if [ "$removable" = "$expected" ]; then
  ok "the candidate set is exactly {ccc1, ddd1, hhh1, kkk1}"
else
  no "the candidate set drifted: got [$(echo "$removable" | tr '\n' ' ')] want [$(echo "$expected" | tr '\n' ' ')]"
fi

# --------------------------------------------------------------------------
printf '\n-- --apply over the same fixture --\n'
OUT="${TMPROOT}/apply.out"
run_prune "$OUT" --apply; status=$?
if [ "$status" -eq 0 ]; then ok "H. an --apply run exits 0"; else no "H. an --apply run exits 0 (got ${status})"; cat "$OUT"; fi
applied="$(sort -u < "$TRIPWIRE_RMI")"
if [ "$applied" = "$expected" ]; then
  ok "H. --apply removed exactly the candidate records, by record id"
else
  no "H. --apply removed [$(echo "$applied" | tr '\n' ' ')] want [$(echo "$expected" | tr '\n' ' ')]"
fi
if ! grep -q 'run1\|actions-runner' "$TRIPWIRE_RMI"; then
  ok "A. --apply never named the ARC runner image"
else
  no "A. --apply named the ARC runner image"
fi

# --------------------------------------------------------------------------
printf '\n-- fail-closed cases --\n'
OUT="${TMPROOT}/kubefail.out"
FAKE_KUBECTL_EXIT=1 run_prune "$OUT" --apply; status=$?
FAKE_KUBECTL_EXIT=0
if [ "$status" -ne 0 ] && [ ! -s "$TRIPWIRE_RMI" ] && grep -q 'cluster read failed' "$OUT"; then
  ok "I. a failing cluster read stops the run and removes nothing"
else
  no "I. a failing cluster read did not stop the run (status ${status})"
fi

OUT="${TMPROOT}/kubeempty.out"
FAKE_CLUSTER_JSON="$EMPTY_CLUSTER_JSON" run_prune "$OUT" --apply; status=$?
if [ "$status" -ne 0 ] && [ ! -s "$TRIPWIRE_RMI" ] && grep -q 'ZERO image references' "$OUT"; then
  ok "J. a cluster read naming no image stops the run and removes nothing"
else
  no "J. an empty cluster read did not stop the run (status ${status})"
fi

# --------------------------------------------------------------------------
printf '\n-- late protection --\n'
OUT="${TMPROOT}/late.out"
FAKE_CLUSTER_JSON_2="$CLUSTER_JSON_LATE" run_prune "$OUT" --apply; status=$?
applied="$(sort -u < "$TRIPWIRE_RMI")"
if [ "$status" -eq 0 ] && ! printf '%s\n' "$applied" | grep -q 'sha256:ccc1' \
   && grep -q 'became referenced while this run was deciding' "$OUT"; then
  ok "M. a candidate referenced by a pod admitted mid-run is skipped, not removed"
else
  no "M. late protection did not skip the newly-referenced record (status ${status})"
fi
if printf '%s\n' "$applied" | grep -q 'sha256:ddd1'; then
  ok "M. the other candidates were still removed"
else
  no "M. one late protection stopped the rest of the run"
fi

# --------------------------------------------------------------------------
printf '\n-- argument handling --\n'
OUT="${TMPROOT}/keep0.out"
run_prune "$OUT" --keep 0; status=$?
if [ "$status" -ne 0 ] && grep -q 'not a retention policy' "$OUT"; then
  ok "--keep 0 is refused: a policy that keeps nothing is not one"
else
  no "--keep 0 was accepted (status ${status})"
fi
OUT="${TMPROOT}/keepbad.out"
run_prune "$OUT" --keep twelve; status=$?
if [ "$status" -ne 0 ] && grep -q 'non-negative integer' "$OUT"; then
  ok "--keep with a non-integer is refused by name"
else
  no "--keep twelve was accepted (status ${status})"
fi
OUT="${TMPROOT}/unknown.out"
run_prune "$OUT" --force; status=$?
if [ "$status" -ne 0 ] && grep -q "unknown argument '--force'" "$OUT"; then
  ok "an unknown argument is refused by name"
else
  no "an unknown argument was accepted (status ${status})"
fi
OUT="${TMPROOT}/keepbig.out"
KEEP=99 run_prune "$OUT"; status=$?
if [ "$status" -eq 0 ] && grep -q 'nothing to remove' "$OUT" && [ ! -s "$TRIPWIRE_RMI" ]; then
  ok "a keep budget larger than the resident set leaves everything alone"
else
  no "a large keep budget still found candidates (status ${status})"
fi

# --------------------------------------------------------------------------
printf '\n%s passed, %s failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
