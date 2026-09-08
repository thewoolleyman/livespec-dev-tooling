#!/usr/bin/env bash
# verify-installed-tree.sh — compare a host's INSTALLED ci-runner artifacts against
# the COMMITTED sources they were copied from, and fail on any drift.
#
#   ./verify-installed-tree.sh                       # this host
#   ./verify-installed-tree.sh --host poweredge-xubuntu
#   ./verify-installed-tree.sh --host X --quiet      # report only problems
#
# THE DEFECT THIS CLOSES (livespec-dev-tooling-fdse). Files under
# /usr/local/lib/ci-runner-k3s/ are installed COPIES of committed sources. Nothing
# compared them, so when a commit landed and the host was not re-provisioned, the
# host silently kept running the old code — no error, no warning. Worse, the stale
# code REPORTS SUCCESS for the work it does know about.
#
# Measured instance, 2026-09-08: poweredge ran a converge-ci-stack.sh from before the
# `gates` queue existed. It ran four minutes AFTER the gates manifest landed, exited
# Result=success, and logged "DONE ... all queues". That message was not a lie — the
# script converged everything IT knew about. The operator-visible signal was green
# and the actual state was an unapplied manifest. Three instances are on record.
#
# WHY IT RUNS FROM THE CHECKOUT, NOT FROM INSIDE CONVERGE. A check living inside the
# installed tree cannot detect that the installed tree is stale: a stale script does
# not contain the check. This one is invoked from the repository, so it works even
# when the installed copy is arbitrarily old — the case that actually occurred.
#
# HOW THE EXPECTED SET IS DERIVED, and why it is not a list. It runs
# `install-converge-unit.sh --stage-to <tmpdir>` — the REAL installer, rootless,
# stopping before its systemd steps — and treats what lands there as canonical. A
# hand-maintained list of installed files would be a second source of truth that can
# fall behind the installer, which is the very defect this script exists to catch,
# one level up. Add a file to the installer and this check covers it with no edit
# here.
#
# SCOPE. It judges only files the installer actually ships. Other installers put
# their own artifacts under the same root (host tools, hooks); those are counted and
# named as out of scope rather than reported as findings — a check that cries wolf
# about files it does not own would not survive being run routinely.
#
# Exit 0 when every shipped file matches. Exit 1 on any STALE or MISSING file.
# Read-only with respect to the target: it installs and changes nothing.
set -uo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
INSTALLER="${SCRIPT_DIR}/install-converge-unit.sh"

LIB_DIR="${LIB_DIR:-/usr/local/lib/ci-runner-k3s}"
HOST=""
QUIET=0
while [ $# -gt 0 ]; do
  case "$1" in
    --host)    HOST="$2"; shift 2 ;;
    --lib-dir) LIB_DIR="$2"; shift 2 ;;
    --quiet)   QUIET=1; shift ;;
    *) echo "FATAL: unknown argument $1" >&2; exit 2 ;;
  esac
done
[ -x "${INSTALLER}" ] || { echo "FATAL: ${INSTALLER} not found or not executable" >&2; exit 1; }

STAGE="$(mktemp -d)"
trap 'rm -rf "${STAGE}"' EXIT

say() { [ "${QUIET}" -eq 1 ] || printf '%s\n' "$*"; }
target_label="${HOST:-$(hostname)}"

if ! "${INSTALLER}" --stage-to "${STAGE}" > "${STAGE}/.stage.log" 2>&1; then
  echo "FATAL: staging the canonical tree failed; see below" >&2
  tail -20 "${STAGE}/.stage.log" >&2
  exit 1
fi
rm -f "${STAGE}/.stage.log"

canonical_count="$(find "${STAGE}" -type f | wc -l)"
[ "${canonical_count}" -gt 0 ] || { echo "FATAL: the installer staged no files" >&2; exit 1; }
say "verifying ${target_label}:${LIB_DIR} against ${canonical_count} committed artifacts"

# One remote round trip for all digests. A per-file ssh would take minutes, and a
# check too slow to run routinely detects nothing.
installed="$(ssh_or_local() { if [ -n "${HOST}" ]; then ssh -o BatchMode=yes -o ConnectTimeout=15 "${HOST}" "$1"; else bash -c "$1"; fi; }
  ssh_or_local "sudo find '${LIB_DIR}' -type f -print0 2>/dev/null | xargs -0 -r sudo sha256sum")" || {
  echo "FATAL: could not read ${LIB_DIR} on ${target_label} — check the path exists and sudo works there" >&2
  exit 1
}
[ -n "${installed}" ] || { echo "FATAL: ${LIB_DIR} on ${target_label} is empty or absent" >&2; exit 1; }

ok=0; stale=0; missing=0
while IFS= read -r staged; do
  rel="${staged#"${STAGE}"/}"
  want="$(sha256sum "${staged}" | cut -d' ' -f1)"
  got="$(awk -v p="${LIB_DIR}/${rel}" '$2 == p {print $1; exit}' <<< "${installed}")"
  if [ -z "${got}" ]; then
    echo "MISSING  ${rel}"
    echo "         shipped by the installer but absent on ${target_label}"
    missing=$((missing + 1))
  elif [ "${got}" = "${want}" ]; then
    say "OK       ${rel}"
    ok=$((ok + 1))
  else
    echo "STALE    ${rel}"
    echo "         installed ${got}"
    echo "         committed ${want}"
    stale=$((stale + 1))
  fi
done < <(find "${STAGE}" -type f | sort)

# Files present on the host that this installer does not ship. Counted for
# transparency, never a finding: other installers legitimately share this root.
foreign=0
while read -r _ path; do
  [ -n "${path}" ] || continue
  [ -f "${STAGE}/${path#"${LIB_DIR}"/}" ] || foreign=$((foreign + 1))
done <<< "${installed}"

echo
echo "${target_label}: ${ok} current, ${stale} stale, ${missing} missing (+${foreign} files under ${LIB_DIR} shipped by other installers, not judged here)"
if [ "${stale}" -eq 0 ] && [ "${missing}" -eq 0 ]; then
  echo "RESULT: every artifact this installer ships matches its committed source."
  exit 0
fi
echo "RESULT: DRIFT. Re-provision, then apply what it installs:"
echo "  sudo ${INSTALLER}"
echo "  sudo systemctl start converge-ci-stack.service"
exit 1
