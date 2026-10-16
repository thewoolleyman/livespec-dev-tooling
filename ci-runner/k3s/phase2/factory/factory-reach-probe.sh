#!/usr/bin/env bash
# factory-reach-probe.sh — the program a factory reach-check pod RUNS: open a
# TCP connection to each named endpoint in order and refuse at the first one
# that will not answer (livespec-dev-tooling-sszvvw, livespec plan
# factory-worker-nodes-gitops, epic livespec-sqvj7p, plan assertion 7).
#
# ./verify-factory-reach.sh embeds this file VERBATIM in the Job it renders, so
# this is the only copy of the verdict and it is a program a test can run on
# real sockets rather than a string nobody can execute. Its arguments are
# `NAME=HOST:PORT`, in the order they are to be probed; `NAME` is what the
# check reports, so it is the operator-facing identity of the endpoint rather
# than a slot number.
#
# WHY BASH'S /dev/tcp AND NOT nc / curl / a python one-liner. The pod runs the
# fleet sandbox image, and this probe must assert reachability rather than
# assert which tools that image happens to bake today: `exec 3<>/dev/tcp/...`
# is a bash builtin, so the only dependency is the shell already interpreting
# this file. A TCP connect is also the whole question — the beads Dolt tenant
# speaks the MySQL wire protocol and the telemetry receiver speaks OTLP/HTTP,
# and a probe that spoke either would be proving a protocol, not a path.
#
# WHY IT STOPS AT THE FIRST FAILURE. An operator fixes one path at a time, and
# the first unreachable endpoint is the one to fix; probing on would report a
# second failure that may simply be the same cause. Exit 1 naming it.
#
# `timeout` bounds the connect so an endpoint that BLACKHOLES (a dropped packet
# rather than a refusal) fails as a failure instead of hanging the Job until
# its deadline — the two shapes are indistinguishable to a reader, so both must
# end the same way.
#
# Exit 0 iff every endpoint answered, and only after printing the verdict line
# ALL ENDPOINTS REACHED. Exit 1 at the first unreachable endpoint. Exit 2 on a
# malformed argument or on NO arguments at all: a probe that probed nothing has
# not reached anything, and reporting success for it is the one green this
# check must never print.
set -uo pipefail

CONNECT_TIMEOUT_SECONDS="${FACTORY_REACH_CONNECT_TIMEOUT_SECONDS:-5}"

if [ "$#" -eq 0 ]; then
  echo "FATAL: no endpoints to probe; refusing to report a reach of nothing" >&2
  exit 2
fi

connect() {
  # The function's status is the connect's status. `timeout` is coreutils and
  # the sandbox image carries it, but an image that did not would otherwise
  # fail every probe for the wrong reason, so its absence degrades to an
  # unbounded connect rather than to a false negative.
  if command -v timeout > /dev/null 2>&1; then
    timeout "${CONNECT_TIMEOUT_SECONDS}" bash -c "exec 3<>/dev/tcp/$1/$2" 2> /dev/null
  else
    bash -c "exec 3<>/dev/tcp/$1/$2" 2> /dev/null
  fi
}

for endpoint in "$@"; do
  name="${endpoint%%=*}"
  target="${endpoint#*=}"
  host="${target%:*}"
  port="${target##*:}"
  if [ "${name}" = "${endpoint}" ] || [ -z "${name}" ] || [ -z "${host}" ] \
    || [ "${port}" = "${target}" ] || [ -z "${port}" ]; then
    echo "FATAL: endpoint must be NAME=HOST:PORT; got '${endpoint}'" >&2
    exit 2
  fi
  if connect "${host}" "${port}"; then
    echo "reached ${name} at ${host}:${port}"
  else
    echo "UNREACHABLE ${name} at ${host}:${port}"
    echo "FATAL: ${name} at ${host}:${port} refused a TCP connection within ${CONNECT_TIMEOUT_SECONDS}s" >&2
    exit 1
  fi
done

echo "ALL ENDPOINTS REACHED"
