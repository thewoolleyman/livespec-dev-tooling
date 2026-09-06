#!/usr/bin/env bash
# cache-negative-tests.sh — the build-cache tiers' NEGATIVE tests, run FROM
# INSIDE A ROUTED JOB on the pool. SPECIFICATION/non-functional-requirements.md
# §"Runner-pool cache telemetry" (v054), "Negative tests": the pool's
# isolation suite MUST assert, on its existing timer, that a job cannot write
# the warm cache (nothing a job can reach is a shared inode, since the
# reflink seed of livespec-dev-tooling-hmv2bo; before that the hardlink seed
# of livespec-lvtu, and before that the read-only mount), that a compilation-
# cache write with a job's credentials is refused, and that no writer
# credential is present in a job pod. Plan ci-runner-cache-tiers, children
# livespec-dev-tooling-tqpszl and -hmv2bo; the trust argument these cases
# test is in ../crates-proxy/, ../sccache/, ../warm-cache/README.md and the
# hook template's header.
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

# The warm uv cache as a job sees it: not a mount but the seed the local-path
# provisioner made in this job's own work volume while the volume was
# provisioned (../warm-cache/README.md "Where it lives"). Since 2026-09-06
# it is a REFLINK COPY of the generation on the XFS `ci-workvols` tier: every
# file is this volume's own inode, sharing the generation's data blocks
# copy-on-write until either side writes, so a job's write lands in the
# volume and never in the generation. From 2026-09-04 to 2026-09-06 it was a
# HARDLINK seed whose inodes WERE the generation's, and case 1 reported that
# violation on every run on purpose (the maintainer's decision between the
# closures is livespec plan ci-runner-pod-lifecycle-reliability research/006;
# option (a), reflink on XFS, was taken).
WARM_SEED="${CACHE_NEG_WARM_SEED:-${UV_CACHE_DIR:-/__w/_warm/uv}}"
REDIS_HOST="${CACHE_NEG_REDIS_HOST:-sccache-redis.ci-sccache.svc.cluster.local}"
REDIS_PORT="${CACHE_NEG_REDIS_PORT:-6379}"
PROXY_URL="${CACHE_NEG_PROXY_URL:-http://crates-proxy.ci-crates-proxy.svc.cluster.local:3080}"
rc=0
report() { printf 'case=%s result=%s %s\n' "$1" "$2" "$3"; [ "$2" = pass ] || rc=1; }

# ---- 1. nothing under the warm seed is shared with anything outside it -----
# Three things must hold. (i) No inode under the seed has a link outside it:
# uv hardlinks some entries to each other WITHIN a cache (archive <-> wheels),
# and `cp -a` preserves those as hardlinks within the copy, so a link count
# above 1 is fine exactly when every one of the inode's links is under the
# seed — one `find -printf '%i %n'` pass, grouped by inode, finds any inode
# with fewer links here than it has in total. A link elsewhere is the
# generation's (the populator hardlinks consecutive generations to each
# other, so the negative control's mount of the warm root shows exactly
# this), and if such an inode also opens for writing that is the violation
# the hardlink seed had. (ii) The copy is a reflink, not a byte copy: where
# `filefrag` is present (the fleet's job image carries e2fsprogs), a seeded
# file's extents carry the `shared` flag. A byte copy is not a trust
# violation but a misconfigured pool (../warm-cache/README.md "Lesson": a
# per-start byte copy must never ship on the start path), so it fails too.
# Caveat: the flag clears once the generation the seed was cloned from is
# pruned — the populator keeps two generations and publishes twice an hour,
# so a volume would have to outlive an hour. (iii) The job can still CREATE
# an entry beside the seed, or the cache would be protected and useless.
# `find -H`: in a job WARM_SEED is a real directory, but the negative control
# points it at the warm root's `uv` SYMLINK, and plain `find` does not follow
# a symlink named on its command line — it saw zero files there on
# 2026-09-06 and this case passed vacuously in the control. -H follows only
# that top-level argument.
if [ ! -d "${WARM_SEED}" ]; then
  report warm-seed-private fail "precondition: ${WARM_SEED} is absent — this volume was not seeded (provisioner setup script, no published generation, or a tier without reflink)"
else
  outside="$(find -H "${WARM_SEED}" -type f -links +1 -printf '%i\t%n\t%p\n' 2>/dev/null \
    | awk -F'\t' '{c[$1]++; n[$1]=$2; p[$1]=$3} END {for (i in c) if (c[i] < n[i]) {print p[i]; exit}}')"
  if [ -n "${outside}" ]; then
    if ( : >> "${outside}" ) 2>/dev/null; then
      report warm-seed-private fail "VIOLATION: ${outside} is an inode with a link outside this tree (link count $(stat -c %h "${outside}"), owner uid $(stat -c %u "${outside}")) and it opened for writing from a job — a shared cache is writable"
    else
      report warm-seed-private fail "precondition: ${outside} has a link outside this tree (link count $(stat -c %h "${outside}")) — a hardlink seed, not the private reflink copy; the write was refused, but nothing a job sees may be a shared inode"
    fi
  else
    sample="$(find -H "${WARM_SEED}" -type f -size +64k -print -quit 2>/dev/null)"
    reflink="reflink unverified (no filefrag in this image)"
    if command -v filefrag >/dev/null 2>&1 && [ -n "${sample}" ]; then
      if filefrag -v "${sample}" 2>/dev/null | grep -q 'shared'; then
        reflink="extents of ${sample} shared with the generation (reflink copy)"
      else
        reflink=""
      fi
    fi
    if [ -z "${sample}" ]; then
      report warm-seed-private fail "precondition: no file above 64k under ${WARM_SEED} — an empty or unreadable seed, not the generation's copy"
    elif [ -z "${reflink}" ]; then
      report warm-seed-private fail "precondition: no seeded inode is shared, but ${sample} has no shared extents either — a byte copy, not the reflink seed (README \"Lesson\")"
    else
      probe="${WARM_SEED}/.cache-negative-test-$$"
      if touch "${probe}" 2>/dev/null; then
        rm -f "${probe}" 2>/dev/null || true
        report warm-seed-private pass "every seeded inode is this volume's own (no link outside the tree); ${reflink}; new entry beside it creatable"
      else
        report warm-seed-private fail "every seeded inode is private, but ${WARM_SEED} is not writable for new entries — uv cannot use this cache"
      fi
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
