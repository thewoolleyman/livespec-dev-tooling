#!/usr/bin/env bash
# extract-externals-exit-tests.sh — prove that ./extract-externals.sh WAITS for
# containerd before its first `ctr images pull`, WITHOUT touching any host and
# without a containerd anywhere near this suite.
#
# WHAT IT IS FOR. On gmktec-xubuntu 2026-09-07 the runbook's step 7c reached
# this script five seconds before k3s-agent's containerd was serving and it died
# at the first pull —
#   ctr: connection error: dial unix /run/k3s/containerd/containerd.sock:
#   connect: connection refused
# -> FATAL: ctr pull ... failed. The identical invocation minutes later
# succeeded, so the recipe appeared to need two runs (livespec-dev-tooling-4qp4).
# The three cases below are that failure, its fix, and the fix's own bound:
#
#   A. --dry-run names a BOUNDED containerd-readiness wait, with the socket and
#      the cadence in the line, and prints it BEFORE the pull it protects;
#   B. under a `ctr` whose first two `version` calls fail, the run waits and
#      then pulls — the pull is issued only after a `version` succeeded, which
#      is the whole claim — and the extraction completes;
#   C. under a `ctr` whose `version` never succeeds, the run exits non-zero
#      inside its bound, names the socket, and NEVER issues a pull.
#
# HOW IT STAYS OFF THE HOST. `ctr` is a FAKE on a scratch PATH that logs every
# invocation and serves a two-file image out of a directory this suite made; the
# only real containerd client on this machine is never resolved, because the fake
# shadows it. `--storage-root` points inside this suite's `mktemp -d`, and
# `--image` is a fixture reference so no ../arc/values-*.yaml is read and no
# registry is contacted. The script requires root because on a node it writes
# under /var/lib/rancher/k3s; a fake `id` on the same PATH satisfies that, and
# every path it then writes is inside the scratch root. The suite never runs as
# root and never needs to.
#
# WHY IT TAKES ABOUT TEN SECONDS. The poll cadence is a real 2 s `sleep`, which
# is the property under test: B waits through two of them and C exhausts a
# four-second bound. Nothing here shortens the cadence, because a cadence a test
# can shorten is not the cadence the node runs.
#
# Exit 0 iff every test passes. Mutates nothing outside its own scratch dir.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="${HERE}/extract-externals.sh"

# A fixture image reference: a real-looking tag@digest that no values file pins,
# so this suite asserts against its own version rather than against whatever the
# fleet happens to pin today.
FIXTURE_VERSION="9.9.9"
FIXTURE_IMAGE="ghcr.io/actions/actions-runner:${FIXTURE_VERSION}@sha256:0000000000000000000000000000000000000000000000000000000000000000"
SOCKET="/run/k3s/containerd/containerd.sock"

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

# The image the fake `ctr` mounts: the two files extract-externals.sh reads out
# of a runner image (the externals tree it copies, and the deps.json it
# cross-checks the version against) and nothing else.
IMAGE_TREE="${TMPROOT}/image"
mkdir -p "${IMAGE_TREE}/home/runner/externals/node20/bin" "${IMAGE_TREE}/home/runner/bin"
printf 'fake node\n' > "${IMAGE_TREE}/home/runner/externals/node20/bin/node"
printf '{"targets":{".NETCoreApp,Version=v6.0":{"Runner.Listener/%s":{}}}}\n' "$FIXTURE_VERSION" \
  > "${IMAGE_TREE}/home/runner/bin/Runner.Listener.deps.json"
export IMAGE_TREE

CTR_LOG="${TMPROOT}/ctr.log"
CTR_COUNT="${TMPROOT}/ctr.version-count"
export CTR_LOG CTR_COUNT

# The fake `ctr`. Single-quoted body on purpose: it is the FAKE's source,
# expanded when the fake runs, not when this suite writes it. CTR_FAIL_VERSIONS
# is how many leading `version` calls report a refused connection — the state a
# starting containerd is in — and 999 stands for "never comes up".
FAKEBIN="${TMPROOT}/fakebin"
mkdir -p "$FAKEBIN"
cat > "${FAKEBIN}/ctr" <<'FAKE'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$CTR_LOG"
if [ "$1" = version ]; then
  seen=0
  [ -f "$CTR_COUNT" ] && seen="$(cat "$CTR_COUNT")"
  seen=$((seen + 1))
  printf '%s\n' "$seen" > "$CTR_COUNT"
  if [ "$seen" -le "${CTR_FAIL_VERSIONS:-0}" ]; then
    echo "ctr: connection error: dial unix /run/k3s/containerd/containerd.sock: connect: connection refused" >&2
    exit 1
  fi
  printf 'Client:\n  Version: fake\nServer:\n  Version: fake\n'
  exit 0
fi
case "$*" in
  *"images ls"*)   exit 0 ;;                       # nothing present -> pull
  *"images pull"*) exit 0 ;;
  *"images mount"*)
    dest="${*: -1}"
    cp -a "${IMAGE_TREE}/." "${dest}/"
    exit 0 ;;
  *"images unmount"*) exit 0 ;;
esac
exit 1
FAKE
printf '#!/usr/bin/env bash\necho 0\n' > "${FAKEBIN}/id"
chmod +x "${FAKEBIN}/ctr" "${FAKEBIN}/id"

# run_extract FAIL_VERSIONS ARGS... -> stdout+stderr in REPLY_OUT, code in
# REPLY_RC, elapsed whole seconds in REPLY_SECONDS, ctr calls in CTR_LOG.
run_extract() {
  local fail_versions="$1"; shift
  local started=$SECONDS
  : > "$CTR_LOG"
  rm -f "$CTR_COUNT"
  REPLY_OUT="$(PATH="${FAKEBIN}:${PATH}" CTR_FAIL_VERSIONS="$fail_versions" "$SCRIPT" "$@" 2>&1)"
  REPLY_RC=$?
  REPLY_SECONDS=$((SECONDS - started))
}

new_storage_root() {  # new_storage_root NAME -> a fresh scratch storage root
  local root="${TMPROOT}/$1"
  mkdir -p "$root"
  printf '%s' "$root"
}

# line_number_of PATTERN OUTPUT -> the 1-based line number of the first match,
# or 0. The two ordering assertions below are about which line comes FIRST, so
# they compare positions rather than mere presence.
line_number_of() {
  printf '%s\n' "$2" | grep -n -- "$1" | head -1 | cut -d: -f1
}

# ---------------------------------------------------------------------------
# A. The plan names the wait, its bound, its socket — and puts it before the
#    pull. A plan that mentions the wait AFTER the pull would describe the
#    ordering that failed.
# ---------------------------------------------------------------------------
printf '== A. --dry-run prints a bounded containerd wait before the pull ==\n'
run_extract 0 --dry-run --image "$FIXTURE_IMAGE" --storage-root "$(new_storage_root dry)"
if [ "$REPLY_RC" -eq 0 ]; then
  ok "--dry-run exits 0"
else
  no "--dry-run exits 0 (got ${REPLY_RC})"
  printf '%s\n' "$REPLY_OUT"
fi
WAIT_LINE="$(printf '%s\n' "$REPLY_OUT" | grep -F 'wait up to' | head -1)"
case "$WAIT_LINE" in
  *"wait up to 120s"*"every 2s"*"${SOCKET}"*"ctr version"*)
    ok "the plan's wait step states the bound, the cadence, the socket and the probe" ;;
  *)
    no "the plan's wait step states the bound, the cadence, the socket and the probe (got: ${WAIT_LINE})" ;;
esac
WAIT_AT="$(line_number_of 'wait up to' "$REPLY_OUT")"
PULL_AT="$(line_number_of 'images ls -q' "$REPLY_OUT")"
if [ -n "$WAIT_AT" ] && [ -n "$PULL_AT" ] && [ "$WAIT_AT" -lt "$PULL_AT" ]; then
  ok "the wait is printed BEFORE the step that pulls"
else
  no "the wait is printed BEFORE the step that pulls (wait=${WAIT_AT:-none} pull=${PULL_AT:-none})"
fi
if [ -s "$CTR_LOG" ]; then
  no "--dry-run invokes no ctr at all"
  cat "$CTR_LOG"
else
  ok "--dry-run invokes no ctr at all"
fi
# --wait-seconds is data, and the plan reads it rather than restating a literal.
run_extract 0 --dry-run --wait-seconds 7 --image "$FIXTURE_IMAGE" --storage-root "$(new_storage_root dry2)"
case "$REPLY_OUT" in
  *"wait up to 7s"*) ok "--dry-run reports the bound it was given" ;;
  *) no "--dry-run reports the bound it was given" ;;
esac
run_extract 0 --dry-run --wait-seconds two --image "$FIXTURE_IMAGE" --storage-root "$(new_storage_root dry3)"
if [ "$REPLY_RC" -ne 0 ] && printf '%s\n' "$REPLY_OUT" | grep -q 'wait-seconds must be a non-negative integer'; then
  ok "a non-numeric --wait-seconds is refused, naming it"
else
  no "a non-numeric --wait-seconds is refused, naming it (rc=${REPLY_RC}: ${REPLY_OUT})"
fi

# ---------------------------------------------------------------------------
# B. A containerd that is still coming up: the run waits through it and pulls
#    afterwards. This is the case that used to be a FATAL and a second manual
#    invocation.
# ---------------------------------------------------------------------------
printf '\n== B. containerd up on the third probe: the run waits, then pulls ==\n'
BROOT="$(new_storage_root late)"
run_extract 2 --image "$FIXTURE_IMAGE" --storage-root "$BROOT"
if [ "$REPLY_RC" -eq 0 ]; then
  ok "the run exits 0 once containerd answers"
else
  no "the run exits 0 once containerd answers (got ${REPLY_RC})"
  printf '%s\n' "$REPLY_OUT"
fi
version_calls="$(grep -c '^version$' "$CTR_LOG")"
if [ "$version_calls" -eq 3 ]; then
  ok "the run probed \`ctr version\` until it succeeded (3 calls: 2 refused, 1 served)"
else
  no "the run probed \`ctr version\` until it succeeded (expected 3, got ${version_calls})"
  cat "$CTR_LOG"
fi
FIRST_PULL="$(grep -n 'images pull' "$CTR_LOG" | head -1 | cut -d: -f1)"
LAST_VERSION="$(grep -n '^version$' "$CTR_LOG" | tail -1 | cut -d: -f1)"
if [ -n "$FIRST_PULL" ] && [ -n "$LAST_VERSION" ] && [ "$LAST_VERSION" -lt "$FIRST_PULL" ]; then
  ok "the pull was issued only AFTER a probe succeeded"
else
  no "the pull was issued only AFTER a probe succeeded (last version=${LAST_VERSION:-none} first pull=${FIRST_PULL:-none})"
  cat "$CTR_LOG"
fi
case "$REPLY_OUT" in
  *"answered \`ctr version\` after 4s"*)
    ok "the run reports how long it waited" ;;
  *)
    no "the run reports how long it waited"
    printf '%s\n' "$REPLY_OUT" ;;
esac
if [ -f "${BROOT}/.externals/${FIXTURE_VERSION}/.externals-seeded-${FIXTURE_VERSION}" ]; then
  ok "the extraction completed: the marked externals tree is in place"
else
  no "the extraction completed: the marked externals tree is in place"
fi
if [ "$(readlink "${BROOT}/.externals/current")" = "$FIXTURE_VERSION" ]; then
  ok "the seed pointer was published"
else
  no "the seed pointer was published"
fi

# ---------------------------------------------------------------------------
# C. A containerd that never comes up: bounded, loud, and no pull attempted.
# ---------------------------------------------------------------------------
printf '\n== C. containerd never answers: the run dies inside its bound ==\n'
CROOT="$(new_storage_root never)"
run_extract 999 --wait-seconds 4 --image "$FIXTURE_IMAGE" --storage-root "$CROOT"
if [ "$REPLY_RC" -ne 0 ]; then
  ok "the run exits non-zero"
else
  no "the run exits non-zero"
  printf '%s\n' "$REPLY_OUT"
fi
case "$REPLY_OUT" in
  *"FATAL: containerd at ${SOCKET} did not answer"*"within 4s"*)
    ok "the failure names the socket and the bound it waited out" ;;
  *)
    no "the failure names the socket and the bound it waited out"
    printf '%s\n' "$REPLY_OUT" ;;
esac
# "Within the bound" is the point of a bound: a wait that overruns it is the
# same hang by another name. The slack is generous because this is wall clock.
if [ "$REPLY_SECONDS" -le 20 ]; then
  ok "the run gave up inside its bound (${REPLY_SECONDS}s wall clock for a 4s bound)"
else
  no "the run gave up inside its bound (took ${REPLY_SECONDS}s for a 4s bound)"
fi
if grep -q 'images pull' "$CTR_LOG"; then
  no "no pull is attempted against a runtime that never answered"
  cat "$CTR_LOG"
else
  ok "no pull is attempted against a runtime that never answered"
fi
if [ -e "${CROOT}/.externals" ]; then
  no "the failed run wrote nothing under the storage root"
else
  ok "the failed run wrote nothing under the storage root"
fi

# ---------------------------------------------------------------------------
printf '\n%s passed, %s failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
