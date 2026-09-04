#!/usr/bin/env bash
# cache-negative-tests.sh — the build-cache tiers' NEGATIVE tests, run FROM
# INSIDE A ROUTED JOB on the pool. SPECIFICATION/non-functional-requirements.md
# §"Runner-pool cache telemetry" (v054), "Negative tests": the pool's
# isolation suite MUST assert, on its existing timer, that a job cannot write
# the warm cache (the shared inodes it is seeded with, since livespec-lvtu;
# before that, the read-only mount), that a compilation-cache write with a job's
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
# meaningful is absent (no warm seed in the volume, no redis to refuse): a
# pod without the seed or the template's env is a misconfigured pool, not a
# passing test. The negative control (a pod given the warm root itself,
# writable, and a writer credential on purpose) turns cases 1 and 3 red —
# run it with the Job in ./negative-control-job.yaml on the host.
#
# Exit 0 only when every case passes; one `case=<name> result=pass|fail
# <detail>` line per case on stdout either way.
set -uo pipefail

# The warm uv cache as a job sees it since livespec-lvtu: not a mount but the
# hardlink seed the local-path provisioner made in this job's own work
# volume (../warm-cache/README.md "Where it lives"). Its files are the
# fleet-wide generation's inodes and must be unwritable from here while the
# directory itself stays usable. KNOWN RED as of 2026-09-04: the generation
# is root-owned and this pod's root is uid 0 on its idmapped volume, so case
# 1 reports a VIOLATION on every run until the mechanical closure lands
# (an owner no pod maps was tried and broke uv's cache init; the decision
# between the remaining options is the maintainer's -- livespec plan
# ci-runner-pod-lifecycle-reliability research/006, README.md "The hazard").
# It stays red rather than relaxed: the clause it asserts is ratified, and a
# red that names the violation is the report.
WARM_SEED="${CACHE_NEG_WARM_SEED:-${UV_CACHE_DIR:-/__w/_warm/uv}}"
REDIS_HOST="${CACHE_NEG_REDIS_HOST:-sccache-redis.ci-sccache.svc.cluster.local}"
REDIS_PORT="${CACHE_NEG_REDIS_PORT:-6379}"
PROXY_URL="${CACHE_NEG_PROXY_URL:-http://crates-proxy.ci-crates-proxy.svc.cluster.local:3080}"
rc=0
report() { printf 'case=%s result=%s %s\n' "$1" "$2" "$3"; [ "$2" = pass ] || rc=1; }

# ---- 1. the warm cache's shared inodes are unwritable from the job ----------
# A seeded file is one with a link count above 1 (its inode is the
# generation's) that is not one of uv's world-writable lock files (those are
# re-created per volume by the seed). Opening it for writing must fail; the
# job must still be able to CREATE an entry beside it, or the cache would be
# useless rather than protected.
if [ ! -d "${WARM_SEED}" ]; then
  report warm-seed-unwritable fail "precondition: ${WARM_SEED} is absent — this volume was not seeded (provisioner setup script, or no published generation)"
else
  shared="$(find "${WARM_SEED}" -type f -links +1 ! -perm -0002 -print -quit 2>/dev/null)"
  if [ -z "${shared}" ]; then
    report warm-seed-unwritable fail "precondition: no shared (link count > 1) file under ${WARM_SEED} — a byte copy, not the hardlink seed"
  elif ( : >> "${shared}" ) 2>/dev/null; then
    report warm-seed-unwritable fail "VIOLATION: opened ${shared} for writing from a job (owner uid $(stat -c %u "${shared}"), mode $(stat -c %a "${shared}"))"
  else
    probe="${WARM_SEED}/.cache-negative-test-$$"
    if touch "${probe}" 2>/dev/null; then
      rm -f "${probe}" 2>/dev/null || true
      report warm-seed-unwritable pass "write to shared ${shared} refused (owner uid $(stat -c %u "${shared}")); new entry beside it creatable"
    else
      report warm-seed-unwritable fail "shared inode refused as required, but ${WARM_SEED} is not writable for new entries either — uv cannot use this cache"
    fi
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
key = b"cache-negative-test:from-a-job"
s.sendall(b"*3\r\n$3\r\nSET\r\n$%d\r\n%s\r\n$1\r\n1\r\n" % (len(key), key))
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
