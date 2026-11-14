# shellcheck shell=bash
# forge-retry.sh — ONE bounded retry for a gate Job's anonymous github.com git
# reads: the livespec core fetch (fetch-livespec-core) and every cross-repo
# sibling clone. render-gate-job.sh inlines this file's function into both
# scripts, so there is one definition. It is not executed on its own.
#
# WHY. Every pool node, ARC runner and factory sandbox leaves through the
# homelab's one NAT egress. On 2026-11-12, roughly 13:20Z-13:35Z, GitHub
# answered a large share of anonymous shallow fetches from that address with
# 401. In a pod with no askPass, git reports that as "could not read Username
# for 'https://github.com'". 7 of 11 gates failed fetch-livespec-core,
# interleaved with passes, across two nodes and two repositories, and each
# failure was a whole red gate. A throttle window lasts seconds to minutes, so
# one immediate attempt turns it into a verdict. livespec-dev-tooling-reuqym
# removes these anonymous reads (the in-cluster git-gates mirror); this is the
# conformance fallback ruled by legacy-coordinator-agent the same day.
#
# WHAT IS RETRIED. Only an answer that can change on its own: a 401 (git's
# username prompt, or "terminal prompts disabled"), a 403, a 429, a 5xx, or a
# transport fault (resolve, connect, timeout, early EOF, a broken
# smart-protocol exchange). A ref or repository the forge positively reports
# missing ("couldn't find remote ref", "Repository not found") is NEVER retried:
# the pin is wrong, and waiting does not fix a pin. Anything unclassified is
# retried too, because the budget bounds it.
#
# THE BUDGET. FORGE_RETRY_ATTEMPTS attempts (default 5), waiting
# FORGE_RETRY_BASE_WAIT seconds (default 5) and doubling: 5, 10, 20, 40, so
# 75 s of waiting inside the 3-minute budget. Every attempt is logged with its
# classified status on stderr, so a throttle is measurable from the Job's log.
# After the budget, the function returns the last attempt's exit status; the
# CALLER reports the red verdict naming the repository, exactly as it did
# before this retry existed.
#
# THE TRANSIENT LAYER ONLY. The fleet's ONE answer to a 401 where a container
# ALREADY holds a token is the git credential helper of spec topic
# self-hosted-ci-git-fetches (ci-runtime-and-cost, livespec-dev-tooling#4329).
# It is rendered here once that topic ratifies. No token is ever mounted into a
# context that holds none (coordinator ruling, 2026-11-12). The tokenless reads
# above move to the in-cluster mirror under livespec-dev-tooling-reuqym, and
# this retry stays as their fallback.
forge_retry() {
  local label="$1"
  shift
  local attempts="${FORGE_RETRY_ATTEMPTS:-5}"
  local wait_s="${FORGE_RETRY_BASE_WAIT:-5}"
  local attempt=1 rc=0 output status
  while :; do
    # A clone that failed part-way leaves its target directory behind, and
    # `git clone` refuses a non-empty target, so a caller that clones names
    # that directory here and every attempt starts from nothing.
    if [ -n "${FORGE_RETRY_RESET_DIR:-}" ]; then
      rm -rf "${FORGE_RETRY_RESET_DIR}"
    fi
    if output="$(GIT_TERMINAL_PROMPT=0 "$@" 2>&1)"; then
      [ -n "${output}" ] && printf '%s\n' "${output}" >&2
      echo ":: gate: forge read ${label} attempt ${attempt}/${attempts}: ok" >&2
      return 0
    else
      rc=$?
    fi
    case "${output}" in
      *"couldn't find remote ref"*|*"Repository not found"*|*"repository"*"not found"*)
        status="not-found" ;;
      *"could not read Username"*|*"terminal prompts disabled"*|*"returned error: 401"*)
        status="401" ;;
      *"returned error: 403"*) status="403" ;;
      *"returned error: 429"*) status="429" ;;
      *"returned error: 5"[0-9][0-9]*) status="5xx" ;;
      *"Could not resolve host"*|*"Failed to connect"*|*"timed out"*|*"early EOF"*|*"expected flush"*|*"RPC failed"*|*"Connection reset"*)
        status="transport" ;;
      *) status="unclassified" ;;
    esac
    echo ":: gate: forge read ${label} attempt ${attempt}/${attempts}: ${status} (git exit ${rc})" >&2
    if [ "${status}" = "not-found" ] || [ "${attempt}" -ge "${attempts}" ]; then
      printf '%s\n' "${output}" >&2
      return "${rc}"
    fi
    sleep "${wait_s}"
    wait_s=$((wait_s * 2))
    attempt=$((attempt + 1))
  done
}
