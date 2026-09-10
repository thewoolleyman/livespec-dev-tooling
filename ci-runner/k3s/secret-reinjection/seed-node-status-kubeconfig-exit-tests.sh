#!/usr/bin/env bash
# seed-node-status-kubeconfig-exit-tests.sh — prove
# ./seed-node-status-kubeconfig.sh WITHOUT touching any host and WITHOUT holding
# a real credential: that its --dry-run prints the target the profile names and
# the mode it will be written with while executing nothing and requiring no
# credential, that a run with a FIXTURE kubeconfig writes exactly those bytes at
# 0600, that a second run reports the file unchanged instead of rewriting it,
# and that every refusal the credential discipline calls for fires and names its
# reason.
#
#   A. --dry-run prints the CHURN_KUBECONFIG_FILE path and `0600 root:root`,
#      exits 0 with the variable UNSET, and executes nothing;
#   B. a live run writes the fixture value byte for byte, mode 0600, and the
#      value never reaches an argv;
#   C. an immediate second run REPORTS the file unchanged and runs no `install`
#      at all;
#   D. the refusals: the variable unset, the variable set but EMPTY, a profile
#      whose CLUSTER_ROLE is not `agent`, an EMPTY CHURN_KUBECONFIG_FILE, a
#      CHURN_KUBECONFIG_FILE naming the k3s SERVER's admin kubeconfig, and one
#      whose parent directory does not exist AND is not the k3s configuration
#      directory -- each non-zero, each naming the reason;
#   E. the COMMITTED second node's profile,
#      `../phase0-bare-metal/profiles/gmktec-xubuntu.env`, plans the seed of the
#      path THAT node declares (`/etc/rancher/k3s/node-status-kubeconfig`), and
#      that path is NOT `/etc/rancher/k3s/k3s.yaml`;
#   F. the fresh node: a MISSING `.../etc/rancher/k3s` is planned as a `+ ` line
#      and then created `0755 root:root` before the credential is written.
#
# HOW IT STAYS OFF THE HOST AND OUT OF 1PASSWORD. The kubeconfig is a fixture
# string this suite invents; nothing here reads the github-ci-runners
# Environment. The target is a file in this suite's own scratch directory, named
# by a scratch copy of a profile. Cases A, D, E and F's dry run go against a PATH
# of TRIPWIRES for `sudo` and `install`, so "executed nothing" is asserted rather
# than assumed. Cases B, C and F's live runs need the write to really happen, so
# they run against a PATH carrying a FAKE `sudo` that logs the command and then
# runs it AS THE INVOKING USER, rewriting `install`'s `-o root -g root` to this
# user's own names — emulating the ONE privilege the real sudo supplies. The
# suite therefore never NEEDS root, and passes unchanged either way. Every
# directory §F creates is under this suite's own scratch root; no `/etc` on this
# machine is read or written.
#
# It is ./seed-k3s-agent-join-token-exit-tests.sh's structure on purpose: the
# script under test is deliberately that script's shape, so a divergence in
# either one shows up as a divergence between the two suites.
#
# Exit 0 iff every test passes. Mutates nothing outside its own scratch dir.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="${HERE}/seed-node-status-kubeconfig.sh"
PROFILES="${HERE}/../phase0-bare-metal/profiles"
AGENT_COMMITTED="${PROFILES}/gmktec-xubuntu.env"
SERVER_COMMITTED="${PROFILES}/poweredge-xubuntu.env"
KUBECONFIG_VAR="K3S_NODE_STATUS_KUBECONFIG_CI_RUNNER"

AGENT_COMMITTED_TARGET="/etc/rancher/k3s/node-status-kubeconfig"
SERVER_ADMIN_KUBECONFIG="/etc/rancher/k3s/k3s.yaml"

# The fixture credential. Shaped like the kubeconfig the provisioner renders so
# the assertions read like the real thing; it is not one, its token is the word
# `notasecret`, and this file is the only place it lives.
FIXTURE_KUBECONFIG='apiVersion: v1
kind: Config
clusters:
  - name: ci-runner
    cluster:
      server: https://192.168.1.200:6443
      certificate-authority-data: Zml4dHVyZW5vdGFjZXJ0
users:
  - name: node-status-patcher-gmktec-xubuntu
    user:
      token: notasecret'

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
# real sudo would have supplied; the mode, the source operand and the target are
# the script's own and are passed through untouched.
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
# The credential variable is NOT exported here; each case decides.
REPLY_OUT=""
REPLY_RC=0
run_seed() {
  local bin="$1"; shift
  REPLY_OUT="$(PATH="${bin}:${PATH}" "$SCRIPT" "$@" 2>&1)"
  REPLY_RC=$?
}

# agent_profile DEST KUBECONFIG_FILE — the committed second node's profile with
# its CHURN_KUBECONFIG_FILE redirected at a scratch path. The committed value is
# a path on THAT node holding a cluster credential this suite must not create;
# every other value in the copy is the committed one.
agent_profile() {
  sed "s#^CHURN_KUBECONFIG_FILE=.*#CHURN_KUBECONFIG_FILE=$2#" "$AGENT_COMMITTED" > "$1"
}

TARGET_DIR="${TMPROOT}/rancher-k3s"
mkdir -p "$TARGET_DIR"
TARGET="${TARGET_DIR}/node-status-kubeconfig"
AGENT_PROFILE="${TMPROOT}/agent-scratch.env"
agent_profile "$AGENT_PROFILE" "$TARGET"

# ---------------------------------------------------------------------------
printf '== A. --dry-run prints the target and the mode, and executes nothing ==\n'
# ---------------------------------------------------------------------------
unset "$KUBECONFIG_VAR"
run_seed "$TRIPBIN" --dry-run "$AGENT_PROFILE"

if [ "$REPLY_RC" -eq 0 ]; then
  ok "A1  --dry-run exits 0 with ${KUBECONFIG_VAR} unset"
else
  no "A1  --dry-run exits 0 with ${KUBECONFIG_VAR} unset (rc=${REPLY_RC})"
  printf '%s\n' "$REPLY_OUT"
fi

if printf '%s\n' "$REPLY_OUT" | grep -qxF "target:   ${TARGET}"; then
  ok "A2  the plan names the CHURN_KUBECONFIG_FILE the profile carries"
else
  no "A2  the plan names the CHURN_KUBECONFIG_FILE the profile carries"
fi

if printf '%s\n' "$REPLY_OUT" | grep -qxF 'mode:     0600 root:root'; then
  ok "A3  the plan names the mode 0600 root:root"
else
  no "A3  the plan names the mode 0600 root:root"
fi

if printf '%s\n' "$REPLY_OUT" | grep -q '^grants:   get,patch on nodes/status for gmktec-xubuntu only'; then
  ok "A4  the plan states what the credential grants, and what it is not"
else
  no "A4  the plan states what the credential grants, and what it is not"
fi

if [ -e "$TARGET" ]; then
  no "A5  --dry-run wrote no file"
else
  ok "A5  --dry-run wrote no file"
fi

if [ -s "$TRIPWIRE" ]; then
  no "A6  --dry-run executed no host-mutating command"
  cat "$TRIPWIRE"
else
  ok "A6  --dry-run executed no host-mutating command"
fi

# ---------------------------------------------------------------------------
printf '\n== B. a live run writes the injected value, owner-only ==\n'
# ---------------------------------------------------------------------------
export "${KUBECONFIG_VAR}=${FIXTURE_KUBECONFIG}"
: > "$SUDO_LOG"
run_seed "$WORKBIN" "$AGENT_PROFILE"

if [ "$REPLY_RC" -eq 0 ]; then
  ok "B1  the seed exits 0"
else
  no "B1  the seed exits 0 (rc=${REPLY_RC})"
  printf '%s\n' "$REPLY_OUT"
fi

if [ -f "$TARGET" ] && [ "$(cat "$TARGET")" = "$FIXTURE_KUBECONFIG" ] \
   && [ "$(wc -c < "$TARGET")" -eq "${#FIXTURE_KUBECONFIG}" ]; then
  ok "B2  the target holds the injected value byte for byte, with no trailing newline"
else
  no "B2  the target holds the injected value byte for byte"
fi

if [ "$(stat -c '%a' "$TARGET")" = 600 ]; then
  ok "B3  the target is mode 0600"
else
  no "B3  the target is mode 0600 (got $(stat -c '%a' "$TARGET"))"
fi

# The whole of the credential discipline, asserted: the value must reach
# `install` over STDIN, so it must appear NOWHERE in what sudo was asked to run.
if grep -qF 'notasecret' "$SUDO_LOG"; then
  no "B4  the credential never appears on an argv"
  cat "$SUDO_LOG"
else
  ok "B4  the credential never appears on an argv"
fi

if grep -qF '/dev/stdin' "$SUDO_LOG"; then
  ok "B5  the write goes through /dev/stdin"
else
  no "B5  the write goes through /dev/stdin"
fi

if printf '%s\n' "$REPLY_OUT" | grep -qF 'notasecret'; then
  no "B6  the credential is never echoed into the script's own output"
else
  ok "B6  the credential is never echoed into the script's own output"
fi

# ---------------------------------------------------------------------------
printf '\n== C. an immediate second run reports the file unchanged ==\n'
# ---------------------------------------------------------------------------
: > "$SUDO_LOG"
run_seed "$WORKBIN" "$AGENT_PROFILE"

if [ "$REPLY_RC" -eq 0 ] && printf '%s\n' "$REPLY_OUT" | grep -q 'unchanged:'; then
  ok "C1  the second run reports the target unchanged"
else
  no "C1  the second run reports the target unchanged (rc=${REPLY_RC})"
  printf '%s\n' "$REPLY_OUT"
fi

if grep -q 'install' "$SUDO_LOG"; then
  no "C2  the second run ran no install at all"
  cat "$SUDO_LOG"
else
  ok "C2  the second run ran no install at all"
fi

# ---------------------------------------------------------------------------
printf '\n== D. the refusals ==\n'
# ---------------------------------------------------------------------------
# refuses DESC BIN EXPECTED_SUBSTRING ARGS...
refuses() {
  local desc="$1" bin="$2" want="$3"; shift 3
  : > "$TRIPWIRE"
  run_seed "$bin" "$@"
  if [ "$REPLY_RC" -eq 0 ]; then
    no "${desc} (exited 0)"
  elif ! printf '%s\n' "$REPLY_OUT" | grep -qF "$want"; then
    no "${desc} (exited ${REPLY_RC} but did not say '${want}')"
    printf '%s\n' "$REPLY_OUT" | tail -3
  else
    ok "${desc}"
  fi
}

unset "$KUBECONFIG_VAR"
refuses "D1  the variable unset is refused, naming the wrapper" "$TRIPBIN" \
  "with-github-ci-runners-env.sh" "$AGENT_PROFILE"

export "${KUBECONFIG_VAR}="
refuses "D2  the variable set but EMPTY is refused, and says EMPTY" "$TRIPBIN" \
  "is set but EMPTY" "$AGENT_PROFILE"
unset "$KUBECONFIG_VAR"

refuses "D3  a server profile is refused, naming its own admin file" "$TRIPBIN" \
  "a server patches node status through its own ${SERVER_ADMIN_KUBECONFIG}" \
  --dry-run "$SERVER_COMMITTED"

NO_TARGET_PROFILE="${TMPROOT}/no-target.env"
agent_profile "$NO_TARGET_PROFILE" ""
refuses "D4  an empty CHURN_KUBECONFIG_FILE is refused, naming the key" "$TRIPBIN" \
  "CHURN_KUBECONFIG_FILE is empty" --dry-run "$NO_TARGET_PROFILE"

ADMIN_PROFILE="${TMPROOT}/admin-path.env"
agent_profile "$ADMIN_PROFILE" "$SERVER_ADMIN_KUBECONFIG"
refuses "D5  a CHURN_KUBECONFIG_FILE naming the server's admin kubeconfig is refused" "$TRIPBIN" \
  "would make cluster-admin and this indistinguishable by path" \
  --dry-run "$ADMIN_PROFILE"

STRAY_PROFILE="${TMPROOT}/stray-parent.env"
agent_profile "$STRAY_PROFILE" "${TMPROOT}/no/such/tree/node-status-kubeconfig"
refuses "D6  a parent that is absent and not the k3s config directory is refused" "$TRIPBIN" \
  "is not the k3s configuration directory" --dry-run "$STRAY_PROFILE"

refuses "D7  an unknown option is refused" "$TRIPBIN" \
  "unknown option" --dry-run --nope "$AGENT_PROFILE"

refuses "D8  two profiles are refused rather than one silently winning" "$TRIPBIN" \
  "more than one profile given" --dry-run "$AGENT_PROFILE" "$AGENT_PROFILE"

refuses "D9  no profile at all is refused" "$TRIPBIN" "no profile given" --dry-run

# ---------------------------------------------------------------------------
printf '\n== E. the COMMITTED profile plans the path that node declares ==\n'
# ---------------------------------------------------------------------------
unset "$KUBECONFIG_VAR"
run_seed "$TRIPBIN" --dry-run "$AGENT_COMMITTED"

# On a machine that has no /etc/rancher/k3s the plan reports the parent as one
# it would CREATE; on one that has it, as existing. Either is correct, and
# neither is what this case is about -- the TARGET is.
if printf '%s\n' "$REPLY_OUT" | grep -qxF "target:   ${AGENT_COMMITTED_TARGET}"; then
  ok "E1  the committed profile plans the seed of ${AGENT_COMMITTED_TARGET}"
else
  no "E1  the committed profile plans the seed of ${AGENT_COMMITTED_TARGET}"
  printf '%s\n' "$REPLY_OUT"
fi

if [ "$AGENT_COMMITTED_TARGET" != "$SERVER_ADMIN_KUBECONFIG" ]; then
  ok "E2  that path is NOT the k3s server's admin kubeconfig"
else
  no "E2  that path is NOT the k3s server's admin kubeconfig"
fi

if [ -s "$TRIPWIRE" ]; then
  no "E3  planning against the committed profile executed nothing"
  cat "$TRIPWIRE"
else
  ok "E3  planning against the committed profile executed nothing"
fi

# ---------------------------------------------------------------------------
printf '\n== F. a fresh node: the k3s configuration directory is planned, then made ==\n'
# ---------------------------------------------------------------------------
FRESH_ROOT="${TMPROOT}/fresh"
FRESH_DIR="${FRESH_ROOT}/etc/rancher/k3s"
mkdir -p "${FRESH_ROOT}/etc/rancher"
FRESH_TARGET="${FRESH_DIR}/node-status-kubeconfig"
FRESH_PROFILE="${TMPROOT}/fresh.env"
agent_profile "$FRESH_PROFILE" "$FRESH_TARGET"

: > "$TRIPWIRE"
unset "$KUBECONFIG_VAR"
run_seed "$TRIPBIN" --dry-run "$FRESH_PROFILE"

if printf '%s\n' "$REPLY_OUT" | grep -q "^parent:   ${FRESH_DIR} (absent, and it is the k3s configuration directory"; then
  ok "F1  the plan reports the absent k3s config directory as one it will create"
else
  no "F1  the plan reports the absent k3s config directory as one it will create"
  printf '%s\n' "$REPLY_OUT"
fi

if printf '%s\n' "$REPLY_OUT" | grep -q "^+ sudo install -d -m 0755 -o root -g root ${FRESH_DIR}$"; then
  ok "F2  the creation is printed as a '+ ' line"
else
  no "F2  the creation is printed as a '+ ' line"
fi

if [ -d "$FRESH_DIR" ]; then
  no "F3  the dry run did not actually create it"
else
  ok "F3  the dry run did not actually create it"
fi

export "${KUBECONFIG_VAR}=${FIXTURE_KUBECONFIG}"
run_seed "$WORKBIN" "$FRESH_PROFILE"

if [ "$REPLY_RC" -eq 0 ] && [ -d "$FRESH_DIR" ] && [ -f "$FRESH_TARGET" ]; then
  ok "F4  the live run created the directory and wrote the credential into it"
else
  no "F4  the live run created the directory and wrote the credential into it (rc=${REPLY_RC})"
  printf '%s\n' "$REPLY_OUT"
fi

if [ -d "$FRESH_DIR" ] && [ "$(stat -c '%a' "$FRESH_DIR")" = 755 ]; then
  ok "F5  the created directory is mode 0755"
else
  no "F5  the created directory is mode 0755"
fi

if [ -f "$FRESH_TARGET" ] && [ "$(stat -c '%a' "$FRESH_TARGET")" = 600 ]; then
  ok "F6  the credential inside it is mode 0600"
else
  no "F6  the credential inside it is mode 0600"
fi

unset "$KUBECONFIG_VAR"

# ---------------------------------------------------------------------------
printf '\n== %d passed, %d failed ==\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
