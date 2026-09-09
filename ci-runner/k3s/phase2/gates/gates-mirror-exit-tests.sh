#!/usr/bin/env bash
# gates-mirror-exit-tests.sh — prove the R4.S4 gate SOURCE artifacts
# (livespec-dev-tooling-2hno) WITHOUT touching any host, contacting any
# cluster, or holding any credential:
#
#   A. ./converge-gates-mirror.sh CREATES a bare mirror per derived repository
#      on the tier root it is pointed at, with the export marker and the
#      per-repository settings the receive path and the sweep both depend on;
#   B. a SECOND run changes nothing — the idempotence the boot converge relies
#      on, asserted over the whole tree and over the export marker's own mtime,
#      because an unconditional `touch` would pass a weaker test;
#   C. a repository name that is not a plain name is REFUSED, so nothing can
#      escape the mirror root through the derivation;
#   D. ./prune-gate-refs.sh prunes a ref whose PUSH time is older than the
#      cutoff and keeps one that is not — asserted at the boundary, from the
#      reflog, which is the age source a packed ref still has;
#   E. the same cutoff holds when the age comes from the loose ref file's
#      mtime instead, the fallback for a ref written with reflogs off;
#   F. a ref with NEITHER age source is reported and NOT pruned, so a sweep
#      that cannot age a ref says so rather than guessing or going quiet;
#   G. ./git-daemon.yaml is read-only by construction: no --export-all, no
#      per-repository receive-pack override, a readOnly mount, and no hostPort;
#   H. the Service ./git-daemon.yaml declares is exactly the one
#      ./render-gate-job.sh defaults --source-url to, so the two cannot drift
#      into a gate that fetches from an address nothing serves;
#   I. the manifest does NOT declare the gates Namespace, which is owned by
#      ../kueue/cluster-queue-gates.yaml — one live object, one committed
#      source, the same split ./gates-rbac.yaml keeps;
#   J. nothing in this slice references /var/lib/git, the package-owned path
#      research/003 correction 3 moved the mirror off.
#
# HOW IT STAYS OFF THE HOST AND OFF THE CLUSTER. `kubectl` is a FAKE on this
# suite's own PATH that accepts the converge's apply/patch/rollout calls and
# contacts nothing. The mirror root, the ARC values files and every repository
# are inside this suite's scratch directory, and the mirror owner is the user
# running the suite, so no chown is attempted and no privilege is needed. The
# tier-mounted pre-gate is satisfied by pointing CI_CACHE_TIER_MOUNT at `/`,
# which is a real mountpoint on any host — the pre-gate is parameterised, not
# bypassed.
#
# Exit 0 iff every test passes. Mutates nothing outside its own scratch dir.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONVERGE="${SCRIPT_DIR}/converge-gates-mirror.sh"
PRUNE="${SCRIPT_DIR}/prune-gate-refs.sh"
MANIFEST="${SCRIPT_DIR}/git-daemon.yaml"
RENDERER="${SCRIPT_DIR}/render-gate-job.sh"
SCRATCH="$(mktemp -d)"
trap 'rm -rf "${SCRATCH}"' EXIT

failures=0
pass() { echo "  PASS  $1"; }
fail() { echo "  FAIL  $1"; failures=$((failures + 1)); }

for f in "${CONVERGE}" "${PRUNE}"; do
  [ -x "${f}" ] || { echo "FATAL: ${f} not found or not executable" >&2; exit 1; }
done
for f in "${MANIFEST}" "${RENDERER}"; do
  [ -f "${f}" ] || { echo "FATAL: ${f} not found" >&2; exit 1; }
done

# --- the fake kubectl the converge runs against -------------------------------
FAKEBIN="${SCRATCH}/bin"
mkdir -p "${FAKEBIN}"
cat > "${FAKEBIN}/kubectl" <<'FAKE'
#!/usr/bin/env bash
# Accepts apply / patch / rollout status and contacts nothing. Recording the
# argv lets a test assert WHICH manifest the converge applied.
printf '%s\n' "$*" >> "${FAKE_KUBECTL_LOG:-/dev/null}"
exit 0
FAKE
chmod 0755 "${FAKEBIN}/kubectl"

# --- an ARC values tree to derive the repository list from --------------------
VALUES_DIR="${SCRATCH}/arc"
mkdir -p "${VALUES_DIR}"
cat > "${VALUES_DIR}/values-alpha.yaml" <<'YAML'
githubConfigUrl: "https://github.com/thewoolleyman/alpha-repo"
YAML
cat > "${VALUES_DIR}/values-beta.yaml" <<'YAML'
githubConfigUrl: "https://github.com/thewoolleyman/beta-repo"
YAML
# The same repository named by a second scale set: the derivation must yield it
# ONCE, not twice, exactly as ../warm-cache/converge-warm-cache.sh's does.
cat > "${VALUES_DIR}/values-alpha-second-set.yaml" <<'YAML'
githubConfigUrl: "https://github.com/thewoolleyman/alpha-repo"
YAML
# The template is not a live scale set and must not become a mirror.
cat > "${VALUES_DIR}/values-EXAMPLE-repo.yaml" <<'YAML'
githubConfigUrl: "https://github.com/thewoolleyman/<REPO>"
YAML

converge() {
  # Runs the converge with the fake kubectl ahead of the real PATH, the tier
  # pre-gate pointed at a real mountpoint, and everything else in scratch.
  local root="$1"; shift
  PATH="${FAKEBIN}:${PATH}" \
    KUBECONFIG="${SCRATCH}/fake.kubeconfig" \
    GATES_VALUES_DIR="${VALUES_DIR}" \
    CI_CACHE_TIER_MOUNT="/" \
    GATES_MIRROR_ROOT="${root}" \
    GATES_MIRROR_OWNER="$(id -un)" \
    "${CONVERGE}" "$@" 2>&1
}

# A stable fingerprint of a tree: every path with its type and mode, and every
# regular file's content hash. Deliberately NOT mtimes for the whole tree — git
# rewrites nothing on a no-op converge, but comparing content is what proves it.
fingerprint() { find "$1" -printf '%y %m %P\n' | sort; }

echo "== A. a first converge creates one bare mirror per derived repository =="
root_a="${SCRATCH}/mirror-a"
if out="$(converge "${root_a}")"; then
  ok=1
  for name in alpha-repo beta-repo; do
    d="${root_a}/${name}.git"
    [ -f "${d}/HEAD" ] || { fail "A: ${d} is not a bare repository"; ok=0; }
    [ -f "${d}/git-daemon-export-ok" ] || { fail "A: ${d} has no git-daemon-export-ok, so the daemon would refuse to serve it"; ok=0; }
    for kv in "core.sharedRepository 0664" "gc.auto 0" "core.logAllRefUpdates true" "receive.denyDeletes false"; do
      key="${kv%% *}"; want="${kv##* }"
      got="$(git config --file "${d}/config" "${key}" 2>/dev/null)"
      [ "${got}" = "${want}" ] || { fail "A: ${d} has ${key}=${got:-<unset>}, expected ${want}"; ok=0; }
    done
  done
  [ -d "${root_a}/<REPO>.git" ] && { fail "A: the EXAMPLE template became a mirror"; ok=0; }
  count="$(find "${root_a}" -maxdepth 1 -name '*.git' -type d | wc -l)"
  [ "${count}" -eq 2 ] || { fail "A: ${count} mirrors, expected 2 (the duplicate scale set must not create a second)"; ok=0; }
  mode="$(stat -c '%a' "${root_a}")"
  [ "${mode}" = "2775" ] || { fail "A: mirror root mode is ${mode}, expected 2775 (group-writable + setgid for the receive path, world-executable for the daemon)"; ok=0; }
  [ "${ok}" -eq 1 ] && pass "mirrors created with the export marker and the settings the receive path and the sweep need"
else
  fail "A: converge exited non-zero: ${out}"
fi

echo "== B. a second converge changes nothing =="
before="$(fingerprint "${root_a}")"
marker_before="$(stat -c '%Y' "${root_a}/alpha-repo.git/git-daemon-export-ok")"
if out="$(converge "${root_a}")"; then
  after="$(fingerprint "${root_a}")"
  marker_after="$(stat -c '%Y' "${root_a}/alpha-repo.git/git-daemon-export-ok")"
  if [ "${before}" != "${after}" ]; then
    fail "B: the tree changed on a second converge: $(diff <(printf '%s\n' "${before}") <(printf '%s\n' "${after}") | head -5)"
  elif [ "${marker_before}" != "${marker_after}" ]; then
    fail "B: git-daemon-export-ok was restamped on a second converge (${marker_before} -> ${marker_after}); the touch must be guarded"
  elif ! printf '%s' "${out}" | grep -q "already initialised"; then
    fail "B: the second converge did not report the mirrors as already initialised"
  else
    pass "second converge is a no-op over the tree and over the export marker"
  fi
else
  fail "B: second converge exited non-zero: ${out}"
fi

echo "== C. a repository name that is not a plain name is refused =="
root_c="${SCRATCH}/mirror-c"
for bad in "../escape" "a/b" ".hidden"; do
  if out="$(converge "${root_c}" --repo "${bad}")"; then
    fail "C: --repo '${bad}' was accepted"
  elif ! printf '%s' "${out}" | grep -q "refusing repository name"; then
    fail "C: --repo '${bad}' failed for the wrong reason: ${out}"
  else
    pass "--repo '${bad}' refused"
  fi
done

# --- a mirror with real refs, for the pruning tests ---------------------------
# One source repository, three pushed gate refs. Each ref is then AGED by
# writing the push time the sweep reads, which is what lets a cutoff be
# asserted exactly rather than by sleeping.
PRUNE_ROOT="${SCRATCH}/mirror-prune"
mkdir -p "${PRUNE_ROOT}"
SRC="${SCRATCH}/src"
git init --quiet "${SRC}"
git -C "${SRC}" config user.email tester@example.com
git -C "${SRC}" config user.name "Gate Tester"
MIRROR="${PRUNE_ROOT}/gated-repo.git"
git init --quiet --bare --shared=0664 "${MIRROR}"
git config --file "${MIRROR}/config" core.logAllRefUpdates true
touch "${MIRROR}/git-daemon-export-ok"
declare -A TREE=()
for n in old new unaged; do
  echo "${n}" > "${SRC}/file"
  git -C "${SRC}" add file
  git -C "${SRC}" commit --quiet -m "${n}"
  TREE["${n}"]="$(git -C "${SRC}" rev-parse 'HEAD^{tree}')"
  git -C "${SRC}" push --quiet "${MIRROR}" "HEAD:refs/gates/${TREE[${n}]}"
done

NOW="$(date +%s)"
CUTOFF_SECONDS=3600
# Write a reflog entry stamped at a chosen time. The author name deliberately
# carries a SPACE, because the sweep parses the timestamp out of a line whose
# name field can contain one — a parser that split on whitespace from the left
# would read the wrong field and silently never prune.
stamp_reflog() {
  local refname="$2" at="$3" sha zero='0000000000000000000000000000000000000000'
  sha="$(git --git-dir="$1" rev-parse "${refname}")"
  mkdir -p "$(dirname "$1/logs/${refname}")"
  printf '%s %s Gate Tester <tester@example.com> %s +0000\tpush\n' \
    "${zero}" "${sha}" "${at}" > "$1/logs/${refname}"
}
# The third ref gets NO age source at all: no reflog, and its loose file packed
# away exactly as `git pack-refs` would leave it. pack-refs packs all three, so
# the other two are then deleted and re-created to bring their loose files back
# — the packed case under test is the third ref alone.
declare -A SHA=()
for n in old new unaged; do
  SHA["${n}"]="$(git --git-dir="${MIRROR}" rev-parse "refs/gates/${TREE[${n}]}")"
done
rm -f "${MIRROR}/logs/refs/gates/${TREE[unaged]}"
git --git-dir="${MIRROR}" pack-refs --all
for n in old new; do
  git --git-dir="${MIRROR}" update-ref -d "refs/gates/${TREE[${n}]}"
  git --git-dir="${MIRROR}" update-ref "refs/gates/${TREE[${n}]}" "${SHA[${n}]}"
done
# 100 s INSIDE the cutoff and 100 s outside it: the boundary, not a wide margin
# that any cutoff between an hour and a day would satisfy. Stamped AFTER the
# re-creation above, whose update-ref calls write reflog entries of their own.
stamp_reflog "${MIRROR}" "refs/gates/${TREE[old]}" "$((NOW - CUTOFF_SECONDS - 100))"
stamp_reflog "${MIRROR}" "refs/gates/${TREE[new]}" "$((NOW - CUTOFF_SECONDS + 100))"

echo "== D. the sweep prunes past the cutoff and keeps inside it, aged from the reflog =="
if out="$("${PRUNE}" --mirror-root "${PRUNE_ROOT}" --max-age-seconds "${CUTOFF_SECONDS}" 2>&1)"; then
  remaining="$(git --git-dir="${MIRROR}" for-each-ref --format='%(refname)' 'refs/gates/')"
  if printf '%s\n' "${remaining}" | grep -qF "refs/gates/${TREE[old]}"; then
    fail "D: the ref pushed $((CUTOFF_SECONDS + 100))s ago survived a ${CUTOFF_SECONDS}s cutoff"
  elif ! printf '%s\n' "${remaining}" | grep -qF "refs/gates/${TREE[new]}"; then
    fail "D: the ref pushed $((CUTOFF_SECONDS - 100))s ago was pruned by a ${CUTOFF_SECONDS}s cutoff"
  else
    pass "cutoff holds at the boundary in both directions (reflog age)"
  fi
else
  fail "D: the sweep exited non-zero: ${out}"
fi

echo "== F. a ref with no age source is reported and left alone =="
if printf '%s' "${out}" | grep -q "age unknown, NOT pruned"; then
  if git --git-dir="${MIRROR}" for-each-ref --format='%(refname)' 'refs/gates/' | grep -qF "refs/gates/${TREE[unaged]}"; then
    pass "the unageable ref was named on stderr and kept"
  else
    fail "F: the unageable ref was pruned despite having no age source"
  fi
else
  fail "F: the sweep did not report the unageable ref: ${out}"
fi

echo "== E. the same cutoff holds when the age comes from the loose ref's mtime =="
MIRROR_M="${SCRATCH}/mirror-mtime/mtime-repo.git"
mkdir -p "$(dirname "${MIRROR_M}")"
git init --quiet --bare --shared=0664 "${MIRROR_M}"
touch "${MIRROR_M}/git-daemon-export-ok"
for n in old new; do
  git -C "${SRC}" push --quiet "${MIRROR_M}" "$(git -C "${SRC}" rev-list --all | tail -1):refs/gates/mtime-${n}"
done
# Reflogs were never enabled on this mirror, so the loose file's mtime is the
# only source — the fallback path, at the same boundary.
[ -d "${MIRROR_M}/logs" ] && rm -rf "${MIRROR_M}/logs"
touch -d "@$((NOW - CUTOFF_SECONDS - 100))" "${MIRROR_M}/refs/gates/mtime-old"
touch -d "@$((NOW - CUTOFF_SECONDS + 100))" "${MIRROR_M}/refs/gates/mtime-new"
if out="$("${PRUNE}" --mirror-root "$(dirname "${MIRROR_M}")" --max-age-seconds "${CUTOFF_SECONDS}" 2>&1)"; then
  remaining="$(git --git-dir="${MIRROR_M}" for-each-ref --format='%(refname)' 'refs/gates/')"
  if printf '%s\n' "${remaining}" | grep -qF "refs/gates/mtime-old"; then
    fail "E: the ref last written $((CUTOFF_SECONDS + 100))s ago survived a ${CUTOFF_SECONDS}s cutoff"
  elif ! printf '%s\n' "${remaining}" | grep -qF "refs/gates/mtime-new"; then
    fail "E: the ref last written $((CUTOFF_SECONDS - 100))s ago was pruned by a ${CUTOFF_SECONDS}s cutoff"
  else
    pass "cutoff holds at the boundary in both directions (mtime fallback)"
  fi
else
  fail "E: the sweep exited non-zero on the mtime mirror: ${out}"
fi

echo "== G. the daemon manifest is read-only by construction =="
# EFFECTIVE lines only. These artifacts explain at length WHY --export-all and
# a hostPort are absent, so a grep over the raw file would find the words in
# the very comments that justify their absence and report the opposite of the
# truth. Stripping whole-line comments is what makes the assertion about the
# manifest rather than about its prose.
effective() { grep -v '^[[:space:]]*#' "$1"; }
EFFECTIVE_MANIFEST="${SCRATCH}/git-daemon.effective.yaml"
effective "${MANIFEST}" > "${EFFECTIVE_MANIFEST}"
if grep -q -- '--export-all' "${EFFECTIVE_MANIFEST}"; then
  fail "G: --export-all appears in the manifest; the daemon would serve every directory under the base path, not only the mirrors"
else
  pass "no --export-all: only a repository carrying git-daemon-export-ok is served"
fi
if grep -q -- '--forbid-override=receive-pack' "${EFFECTIVE_MANIFEST}"; then
  pass "a per-repository daemon.receivepack cannot re-enable pushes over git://"
else
  fail "G: --forbid-override=receive-pack is absent"
fi
if grep -A3 'name: mirror' "${EFFECTIVE_MANIFEST}" | grep -q 'readOnly: true'; then
  pass "the mirror is mounted readOnly"
else
  fail "G: the mirror volumeMount is not readOnly: true"
fi
if grep -q 'hostPort' "${EFFECTIVE_MANIFEST}"; then
  fail "G: the daemon declares a hostPort; it serves whatever a push put in the mirror and must stay on the pod network"
else
  pass "no hostPort: reachable from pods only"
fi
if grep -A1 'path: /var/cache/ci-runner/gates-mirror' "${EFFECTIVE_MANIFEST}" | grep -q 'type: Directory$'; then
  pass "hostPath type is Directory, so kubelet cannot create a root-owned mirror the receive path could not write to"
else
  fail "G: the mirror hostPath is not 'type: Directory'"
fi

echo "== H. the Service is exactly what render-gate-job.sh defaults --source-url to =="
default_url="$(grep -oE 'git://[^"$]+' "${RENDERER}" | head -1)"
host_part="${default_url#git://}"
host_part="${host_part%%/*}"
if [ "${host_part}" = "git-gates.gates.svc.cluster.local" ]; then
  svc_ok=1
  grep -q '^  name: git-gates$' "${EFFECTIVE_MANIFEST}" || svc_ok=0
  grep -q '^  namespace: gates$' "${EFFECTIVE_MANIFEST}" || svc_ok=0
  grep -q '      port: 9418$' "${EFFECTIVE_MANIFEST}" || svc_ok=0
  if [ "${svc_ok}" -eq 1 ]; then
    pass "renderer default ${default_url} resolves to this manifest's Service on 9418"
  else
    fail "H: the manifest's Service does not match the renderer default ${default_url}"
  fi
else
  fail "H: the renderer's default source URL host is '${host_part}', not git-gates.gates.svc.cluster.local"
fi
# The daemon resolves /<repo>.git against its --base-path, so the base path and
# the hostPath must name the same directory or every fetch 404s.
base_path="$(grep -oE '\-\-base-path=[^"]+' "${EFFECTIVE_MANIFEST}" | head -1)"
base_path="${base_path#--base-path=}"
if grep -q "path: /var/cache/ci-runner/$(basename "${base_path}")$" "${EFFECTIVE_MANIFEST}"; then
  pass "--base-path ${base_path} is the directory the hostPath mounts"
else
  fail "H: --base-path ${base_path} does not match the mounted hostPath"
fi

echo "== I. the manifest does not declare the gates Namespace =="
if grep -q '^kind: Namespace' "${EFFECTIVE_MANIFEST}"; then
  fail "I: the manifest declares a Namespace; ../kueue/cluster-queue-gates.yaml owns it"
else
  pass "the gates Namespace is left to its one committed source"
fi

echo "== J. nothing in this slice references /var/lib/git =="
# Effective lines again, and for a sharper reason than G's: correction 3 is
# explained IN these files, so the path appears in prose saying not to use it.
# The criterion is that no artifact USES it.
offenders=""
for f in "${MANIFEST}" "${CONVERGE}" "${PRUNE}" "${SCRIPT_DIR}/gate-ref-prune.service" "${SCRIPT_DIR}/gate-ref-prune.timer"; do
  [ -f "${f}" ] || continue
  effective "${f}" | grep -q '/var/lib/git' && offenders="${offenders} $(basename "${f}")"
done
if [ -n "${offenders}" ]; then
  fail "J: /var/lib/git referenced in:${offenders} (research/003 correction 3 moved the mirror to the ci-cache tier)"
else
  pass "the mirror lives on the ci-cache tier and nothing points at the package-owned path"
fi

echo
if [ "${failures}" -eq 0 ]; then
  echo "ALL TESTS PASSED"
  exit 0
fi
echo "${failures} TEST(S) FAILED"
exit 1
