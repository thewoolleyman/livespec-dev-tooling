#!/usr/bin/env bash
# seed-k3s-agent-join-token-exit-tests.sh — prove ./seed-k3s-agent-join-token.sh
# WITHOUT touching any host and WITHOUT holding a real credential: that its
# --dry-run prints the target the profile names and the mode it will be written
# with while executing nothing and requiring no token, that a run with a
# FIXTURE token writes exactly those bytes at 0600, that a second run reports
# the file unchanged instead of rewriting it, and that every refusal the
# credential discipline calls for fires and names its reason.
#
#   A. --dry-run prints the CLUSTER_TOKEN_FILE path and `0600 root:root`,
#      exits 0 with the variable UNSET, and executes nothing;
#   B. a live run writes the fixture value byte for byte, mode 0600, and the
#      token never reaches an argv;
#   C. an immediate second run REPORTS the file unchanged and runs no `install`
#      at all;
#   D. the refusals: the variable unset, the variable set but EMPTY, a profile
#      whose CLUSTER_ROLE is not `agent`, and a CLUSTER_TOKEN_FILE whose parent
#      directory does not exist — each non-zero, each naming the reason;
#   E. the COMMITTED second node's profile,
#      `../phase0-bare-metal/profiles/gmktec-xubuntu.env`, plans the seed of
#      the path THAT node's provisioning reads
#      (`/etc/rancher/k3s/agent-join-token`).
#
# HOW IT STAYS OFF THE HOST AND OUT OF 1PASSWORD. The token is a fixture string
# this suite invents; nothing here reads the github-ci-runners Environment. The
# target is a file in this suite's own scratch directory, named by a scratch
# copy of a profile. Cases A, D and E run against a PATH of TRIPWIRES for
# `sudo` and `install`, so "executed nothing" is asserted rather than assumed.
# Cases B and C need the write to really happen, so they run against a PATH
# carrying a FAKE `sudo` that logs the command and then runs it AS THE INVOKING
# USER, rewriting `install`'s `-o root -g root` to this user's own names —
# emulating the ONE privilege the real sudo supplies. The suite therefore never
# NEEDS root, and that rewrite is the reason: it passes unchanged as an
# unprivileged user, where the rewrite is what carries the write, and as root,
# where it is a no-op.
#
# Exit 0 iff every test passes. Mutates nothing outside its own scratch dir.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="${HERE}/seed-k3s-agent-join-token.sh"
PROFILES="${HERE}/../phase0-bare-metal/profiles"
AGENT_COMMITTED="${PROFILES}/gmktec-xubuntu.env"
SERVER_COMMITTED="${PROFILES}/poweredge-xubuntu.env"
TOKEN_VAR="K3S_AGENT_JOIN_TOKEN_CI_RUNNER"

# The fixture credential. Shaped like a k3s join token so the assertions read
# like the real thing; it is not one, and this file is the only place it lives.
FIXTURE_TOKEN="K10fixturenotasecret::server:0123456789abcdef"

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

TRIPWIRE="${TMPROOT}/tripwire"
: > "$TRIPWIRE"
export TRIPWIRE

SUDO_LOG="${TMPROOT}/sudo-log"
: > "$SUDO_LOG"
export SUDO_LOG

# The tripwire PATH: every host-mutating tool the script can reach for, and
# `sudo` itself, replaced by a recorder that runs nothing.
TRIPBIN="${TMPROOT}/tripbin"
mkdir -p "$TRIPBIN"
for tool in sudo install; do
  # Single-quoted on purpose: the body is the FAKE's source, expanded when the
  # fake runs, not when this suite writes it.
  printf '#!/usr/bin/env bash\nprintf "%%s %%s\\n" "$(basename "$0")" "$*" >> "$TRIPWIRE"; exit 0\n' \
    > "${TRIPBIN}/${tool}"
  chmod +x "${TRIPBIN}/${tool}"
done

# The working PATH: a `sudo` that records what it was asked to do and then does
# it as this (unprivileged) user, with `install`'s root ownership flags
# rewritten to this user's own. That rewrite is the whole of the privilege the
# real sudo would have supplied; the mode, the source operand and the target
# are the script's own and are passed through untouched.
WORKBIN="${TMPROOT}/workbin"
mkdir -p "$WORKBIN"
cat > "${WORKBIN}/sudo" <<'FAKE_SUDO'
#!/usr/bin/env bash
printf 'sudo %s\n' "$*" >> "$SUDO_LOG"
args=()
while [ $# -gt 0 ]; do
  case "$1" in
    -o) args+=(-o "$(id -un)"); shift 2 ;;
    -g) args+=(-g "$(id -gn)"); shift 2 ;;
    *) args+=("$1"); shift ;;
  esac
done
exec "${args[@]}"
FAKE_SUDO
chmod +x "${WORKBIN}/sudo"

# run_seed BIN ARGS... -> stdout+stderr in REPLY_OUT, code in REPLY_RC.
# The token variable is NOT exported here; each case decides.
run_seed() {
  local bin="$1"; shift
  REPLY_OUT="$(PATH="${bin}:${PATH}" "$SCRIPT" "$@" 2>&1)"
  REPLY_RC=$?
}

# agent_profile DEST TOKEN_FILE — the committed second node's profile with its
# CLUSTER_TOKEN_FILE redirected at a scratch path. The committed value is a
# path on THAT node holding a cluster credential this suite must not create;
# every other value in the copy is the committed one.
agent_profile() {
  sed "s#^CLUSTER_TOKEN_FILE=.*#CLUSTER_TOKEN_FILE=$2#" "$AGENT_COMMITTED" > "$1"
}

TARGET_DIR="${TMPROOT}/rancher-k3s"
mkdir -p "$TARGET_DIR"
TARGET="${TARGET_DIR}/agent-join-token"
AGENT_PROFILE="${TMPROOT}/agent-scratch-token.env"
agent_profile "$AGENT_PROFILE" "$TARGET"

# ---------------------------------------------------------------------------
# A. --dry-run: the plan, no credential, nothing executed.
# ---------------------------------------------------------------------------
printf '== A. --dry-run prints the target and the mode, and executes nothing ==\n'
unset "$TOKEN_VAR"
run_seed "$TRIPBIN" --dry-run "$AGENT_PROFILE"

if [ "$REPLY_RC" -eq 0 ]; then
  ok "A1  --dry-run exits 0 with ${TOKEN_VAR} unset"
else
  no "A1  --dry-run exits 0 with ${TOKEN_VAR} unset (rc=${REPLY_RC})"
  printf '%s\n' "$REPLY_OUT"
fi

if printf '%s\n' "$REPLY_OUT" | grep -qxF "target:   ${TARGET}"; then
  ok "A2  the plan names the CLUSTER_TOKEN_FILE the profile carries"
else
  no "A2  the plan names the CLUSTER_TOKEN_FILE the profile carries"
fi

if printf '%s\n' "$REPLY_OUT" | grep -qxF 'mode:     0600 root:root'; then
  ok "A3  the plan names the mode 0600 root:root"
else
  no "A3  the plan names the mode 0600 root:root"
fi

if [ -e "$TARGET" ]; then
  no "A4  --dry-run wrote no file"
else
  ok "A4  --dry-run wrote no file"
fi

if [ -s "$TRIPWIRE" ]; then
  no "A5  --dry-run executed no host-mutating command"
  cat "$TRIPWIRE"
else
  ok "A5  --dry-run executed no host-mutating command"
fi

if printf '%s\n' "$REPLY_OUT" | grep -q 'NOTHING was executed'; then
  ok "A6  the dry run says so in its own output"
else
  no "A6  the dry run says so in its own output"
fi

# ---------------------------------------------------------------------------
# B. The write.
# ---------------------------------------------------------------------------
printf '\n== B. a live run writes the injected value, owner-only ==\n'
export "${TOKEN_VAR}=${FIXTURE_TOKEN}"
run_seed "$WORKBIN" "$AGENT_PROFILE"

if [ "$REPLY_RC" -eq 0 ]; then
  ok "B1  the seed exits 0"
else
  no "B1  the seed exits 0 (rc=${REPLY_RC})"
  printf '%s\n' "$REPLY_OUT"
fi

if [ -f "$TARGET" ] && [ "$(cat "$TARGET")" = "$FIXTURE_TOKEN" ] \
   && [ "$(wc -c < "$TARGET")" -eq "${#FIXTURE_TOKEN}" ]; then
  ok "B2  the target holds the injected value, byte for byte"
else
  no "B2  the target holds the injected value, byte for byte"
fi

TARGET_MODE_SEEN="$(stat -c '%a' "$TARGET" 2>/dev/null)"
if [ "$TARGET_MODE_SEEN" = 600 ]; then
  ok "B3  the target is mode 0600"
else
  no "B3  the target is mode 0600 (got '${TARGET_MODE_SEEN}')"
fi

if grep -qF -- "-o root -g root" "$SUDO_LOG" && grep -qF -- "/dev/stdin ${TARGET}" "$SUDO_LOG"; then
  ok "B4  the write went through sudo install -o root -g root, reading /dev/stdin"
else
  no "B4  the write went through sudo install -o root -g root, reading /dev/stdin"
  cat "$SUDO_LOG"
fi

if grep -qF "$FIXTURE_TOKEN" "$SUDO_LOG"; then
  no "B5  the token never appears on a command line"
  printf 'the sudo log carried the token itself\n'
else
  ok "B5  the token never appears on a command line"
fi

if printf '%s\n' "$REPLY_OUT" | grep -qF "$FIXTURE_TOKEN"; then
  no "B6  the token is never echoed to the operator"
else
  ok "B6  the token is never echoed to the operator"
fi

# ---------------------------------------------------------------------------
# C. The second run is a report, not a rewrite.
# ---------------------------------------------------------------------------
printf '\n== C. an identical second run reports the file unchanged ==\n'
: > "$SUDO_LOG"
run_seed "$WORKBIN" "$AGENT_PROFILE"

if [ "$REPLY_RC" -eq 0 ] && printf '%s\n' "$REPLY_OUT" | grep -qF 'unchanged:'; then
  ok "C1  the second run exits 0 and reports the file unchanged"
else
  no "C1  the second run exits 0 and reports the file unchanged (rc=${REPLY_RC})"
  printf '%s\n' "$REPLY_OUT"
fi

if grep -q '^sudo install ' "$SUDO_LOG"; then
  no "C2  the second run ran no install at all"
  cat "$SUDO_LOG"
else
  ok "C2  the second run ran no install at all"
fi

if [ "$(cat "$TARGET")" = "$FIXTURE_TOKEN" ]; then
  ok "C3  the target still holds the value"
else
  no "C3  the target still holds the value"
fi

# A CHANGED value is written: the skip is byte-identity, not mere existence.
export "${TOKEN_VAR}=${FIXTURE_TOKEN}-rotated"
run_seed "$WORKBIN" "$AGENT_PROFILE"
if [ "$REPLY_RC" -eq 0 ] && [ "$(cat "$TARGET")" = "${FIXTURE_TOKEN}-rotated" ]; then
  ok "C4  a rotated value IS written — the skip is byte-identity, not existence"
else
  no "C4  a rotated value IS written — the skip is byte-identity, not existence (rc=${REPLY_RC})"
fi
export "${TOKEN_VAR}=${FIXTURE_TOKEN}"

# ---------------------------------------------------------------------------
# D. The refusals.
# ---------------------------------------------------------------------------
printf '\n== D. refusals: no credential, empty credential, wrong role, no parent ==\n'
: > "$TRIPWIRE"

refuses() {  # refuses DESCRIPTION EXPECTED-FRAGMENT ARGS...
  local description="$1" fragment="$2"; shift 2
  run_seed "$TRIPBIN" "$@"
  if [ "$REPLY_RC" -eq 0 ]; then
    no "${description} (exited 0)"
    return
  fi
  case "$REPLY_OUT" in
    *"$fragment"*) ok "$description" ;;
    *) no "${description} (message did not name it: ${REPLY_OUT})" ;;
  esac
}

UNSEEDED_DIR="${TMPROOT}/unseeded"
mkdir -p "$UNSEEDED_DIR"
UNSEEDED_PROFILE="${TMPROOT}/agent-unseeded.env"
agent_profile "$UNSEEDED_PROFILE" "${UNSEEDED_DIR}/agent-join-token"

unset "$TOKEN_VAR"
refuses "D1  an unset ${TOKEN_VAR} is refused, naming the wrapper to run under" \
  "${TOKEN_VAR} is not set" "$UNSEEDED_PROFILE"

export "${TOKEN_VAR}="
refuses "D2  an EMPTY ${TOKEN_VAR} is refused, and not written as a zero-byte token" \
  "${TOKEN_VAR} is set but EMPTY" "$UNSEEDED_PROFILE"
if [ -e "${UNSEEDED_DIR}/agent-join-token" ]; then
  no "D3  neither refusal created the target"
else
  ok "D3  neither refusal created the target"
fi

export "${TOKEN_VAR}=${FIXTURE_TOKEN}"
refuses "D4  a CLUSTER_ROLE that is not 'agent' is refused, naming the role it read" \
  "CLUSTER_ROLE is 'server', not 'agent'" "$SERVER_COMMITTED"
refuses "D5  the wrong role is refused under --dry-run too" \
  "CLUSTER_ROLE is 'server', not 'agent'" --dry-run "$SERVER_COMMITTED"

NO_PARENT_PROFILE="${TMPROOT}/agent-no-parent.env"
agent_profile "$NO_PARENT_PROFILE" "${TMPROOT}/no-such-dir/agent-join-token"
refuses "D6  a CLUSTER_TOKEN_FILE whose parent directory is absent is refused, naming it" \
  "which does not exist on this node" "$NO_PARENT_PROFILE"

refuses "D7  a missing profile is refused, naming the path" \
  "profile not found" "${TMPROOT}/does-not-exist.env"

refuses "D8  no profile at all is refused with the usage line" \
  "no profile given" --dry-run

if [ -s "$TRIPWIRE" ]; then
  no "D9  not one refusal executed a host-mutating command"
  cat "$TRIPWIRE"
else
  ok "D9  not one refusal executed a host-mutating command"
fi

# ---------------------------------------------------------------------------
# E. The committed second node's profile, not a fixture derived from it.
#
# Sections A-D redirect CLUSTER_TOKEN_FILE at a scratch path, because the
# committed value is a path on THAT node. This case runs the committed file
# itself, through --dry-run, and asserts the plan names the path
# ../provision-k3s.sh will later refuse to provision without.
# ---------------------------------------------------------------------------
printf '\n== E. the committed gmktec-xubuntu profile plans the node'"'"'s own path ==\n'
run_seed "$TRIPBIN" --dry-run "$AGENT_COMMITTED"

if [ "$REPLY_RC" -eq 0 ] \
   && printf '%s\n' "$REPLY_OUT" | grep -qxF 'target:   /etc/rancher/k3s/agent-join-token' \
   && printf '%s\n' "$REPLY_OUT" | grep -qxF 'node:     gmktec-xubuntu'; then
  ok "E1  the committed profile plans the seed of /etc/rancher/k3s/agent-join-token on gmktec-xubuntu"
else
  no "E1  the committed profile plans the seed of /etc/rancher/k3s/agent-join-token on gmktec-xubuntu (rc=${REPLY_RC})"
  printf '%s\n' "$REPLY_OUT"
fi

if grep -qxF 'CLUSTER_TOKEN_FILE=/etc/rancher/k3s/agent-join-token' "$AGENT_COMMITTED"; then
  ok "E2  that path is the committed profile's own value, not this suite's"
else
  no "E2  that path is the committed profile's own value, not this suite's"
fi

# ---------------------------------------------------------------------------
printf '\n%s passed, %s failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
