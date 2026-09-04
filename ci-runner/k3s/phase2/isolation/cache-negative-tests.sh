#!/usr/bin/env bash
# cache-negative-tests.sh — the build-cache tiers' NEGATIVE tests, run FROM
# INSIDE A ROUTED JOB on the pool. SPECIFICATION/non-functional-requirements.md
# §"Runner-pool cache telemetry" (v054), "Negative tests": the pool's
# isolation suite MUST assert, on its existing timer, that a job cannot write
# the warm-cache mount, that a compilation-cache write with a job's
# credentials is refused, and that no writer credential is present in a job
# pod. Plan ci-runner-cache-tiers, child livespec-dev-tooling-tqpszl; the
# trust argument these cases test is in ../crates-proxy/, ../sccache/ and
# ../warm-cache/ and the hook template's header.
#
# WHERE IT RUNS: .github/workflows/ci-cache-negative-tests.yml — a scheduled
# container job on THIS repository's scale set, so the pod is exactly what
# every routed job gets (the hook template's mounts and env), not a
# simulation. The k3s lane has no other isolation timer (the podman lane's
# isolation-exit-tests.sh went with that lane), so the workflow's schedule IS
# the timer, its job conclusion is the green/red report, and the CI
# telemetry export puts that conclusion in Honeycomb's github-ci dataset
# where the `CI cache negative tests failed` trigger reads it.
#
# EVERY CASE MUST BE ABLE TO FAIL. A case is a violation when the forbidden
# thing SUCCEEDS, and ALSO when the precondition that makes the assertion
# meaningful is absent (no warm mount, no redis to refuse): a pod without the
# template's mounts is a misconfigured pool, not a passing test. The
# negative control (a pod given a writable mount and a writer credential on
# purpose) turns cases 1 and 3 red — run it with the Job in
# ./negative-control-job.yaml on the host.
#
# Exit 0 only when every case passes; one `case=<name> result=pass|fail
# <detail>` line per case on stdout either way.
set -uo pipefail

WARM_MOUNT="${CACHE_NEG_WARM_MOUNT:-/var/cache/ci-runner/warm}"
REDIS_HOST="${CACHE_NEG_REDIS_HOST:-sccache-redis.ci-sccache.svc.cluster.local}"
REDIS_PORT="${CACHE_NEG_REDIS_PORT:-6379}"
PROXY_URL="${CACHE_NEG_PROXY_URL:-http://crates-proxy.ci-crates-proxy.svc.cluster.local:3080}"
rc=0
report() { printf 'case=%s result=%s %s\n' "$1" "$2" "$3"; [ "$2" = pass ] || rc=1; }

# ---- 1. the warm-cache mount is read-only from the job ----------------------
if [ ! -d "${WARM_MOUNT}" ]; then
  report warm-mount-unwritable fail "precondition: ${WARM_MOUNT} is not mounted in this pod"
elif ! mountpoint -q "${WARM_MOUNT}" 2>/dev/null; then
  report warm-mount-unwritable fail "precondition: ${WARM_MOUNT} is a plain directory, not the template's mount"
else
  probe="${WARM_MOUNT}/.cache-negative-test-$$"
  if touch "${probe}" 2>/dev/null; then
    rm -f "${probe}" 2>/dev/null || true
    report warm-mount-unwritable fail "VIOLATION: created ${probe} — the warm mount is writable from a job"
  else
    report warm-mount-unwritable pass "touch ${probe} refused"
  fi
fi

# ---- 2. a compilation-cache write with the pod's credentials is refused ----
redis_reply="$(python3 - "${REDIS_HOST}" "${REDIS_PORT}" <<'PY' 2>&1
import socket, sys
host, port = sys.argv[1], int(sys.argv[2])
try:
    s = socket.create_connection((host, port), timeout=5)
except OSError as e:
    print("CONNECT-FAILED " + str(e)); raise SystemExit(0)
s.sendall(b"*3\r\n$3\r\nSET\r\n$29\r\ncache-negative-test:from-a-job\r\n$1\r\n1\r\n")
print(s.recv(256).decode(errors="replace").strip())
PY
)"
case "${redis_reply}" in
  -NOPERM*) report redis-set-refused pass "SET as the pod's (unauthenticated) user -> ${redis_reply}" ;;
  CONNECT-FAILED*) report redis-set-refused fail "precondition: cannot reach ${REDIS_HOST}:${REDIS_PORT} (${redis_reply#CONNECT-FAILED })" ;;
  +OK*) report redis-set-refused fail "VIOLATION: SET succeeded from a job (${redis_reply})" ;;
  *) report redis-set-refused fail "unexpected reply: ${redis_reply}" ;;
esac

# ---- 3. no writer credential in the pod --------------------------------------
leaks="$(env | grep -E '^SCCACHE_REDIS_(WRITER_USERNAME|WRITER_PASSWORD|USERNAME|PASSWORD)=' | cut -d= -f1 | tr '\n' ' ')"
mounted_secret=""
for f in /var/run/secrets/sccache-redis-writer /etc/sccache-redis-writer /etc/ci-runner/sccache-redis-writer.pass; do
  [ -e "$f" ] && mounted_secret="${mounted_secret}${f} "
done
if [ -z "${leaks}" ] && [ -z "${mounted_secret}" ]; then
  report no-writer-credential pass "no SCCACHE_REDIS_* credential variable and no writer secret file in the pod"
else
  report no-writer-credential fail "VIOLATION: writer credential present: env[${leaks}] files[${mounted_secret}]"
fi

# ---- 4. the crates proxy refuses writes ---------------------------------------
code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 10 -X PUT --data x "${PROXY_URL}/crates/serde/0.0.0/download" 2>/dev/null || echo 000)"
case "${code}" in
  403|405) report proxy-write-refused pass "PUT -> ${code}" ;;
  000) report proxy-write-refused fail "precondition: cannot reach ${PROXY_URL}" ;;
  *) report proxy-write-refused fail "VIOLATION or passthrough: PUT -> ${code} (the proxy must refuse non-GET locally)" ;;
esac

exit "${rc}"
