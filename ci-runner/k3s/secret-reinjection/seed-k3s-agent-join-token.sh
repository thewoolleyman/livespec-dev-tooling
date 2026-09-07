#!/usr/bin/env bash
# seed-k3s-agent-join-token.sh — the ONE attended step that puts an AGENT
# node's k3s join token on that node. Run by the human maintainer (a member of
# the github-ci-runners group, e.g. cwoolley) on the agent, BEFORE
# ../provision-k3s.sh, NOT at boot. It sources the token from the
# github-ci-runners 1Password Environment and writes it to the path the node's
# profile names in CLUSTER_TOKEN_FILE, mode 0600 root:root.
#
# WHY IT EXISTS. ../provision-k3s.sh refuses — in --dry-run too — until
# CLUSTER_TOKEN_FILE exists and is owner-only, because the join token is a
# cluster credential and this tree carries no secret. Until this script the
# only way to satisfy that refusal was a human typing the token into the node
# by hand, which is neither repeatable nor recorded. It is the same shape as
# seed-github-app-creds.sh beside it: attended, one injected variable, the
# value never echoed, never logged and never on argv.
#
# WHY IT HAS NO BOOT HALF. The GitHub App credentials next door need one
# (inject-github-app-secret.service) because they live in the k3s datastore,
# which is volatile by design. The join token does not: it is a file on the
# agent's own durable root filesystem, read at run time by k3s itself out of
# CLUSTER_TOKEN_FILE. Seeding it once is enough, and re-running this is the
# RE-SEED step if the server's token is ever rotated.
#
# WHERE THE VALUE COMES FROM. The cluster's token is
# /var/lib/rancher/k3s/server/node-token on the SERVER (poweredge-xubuntu).
# Storing it in the github-ci-runners 1Password Environment as
# K3S_AGENT_JOIN_TOKEN_CI_RUNNER is the maintainer's own one-time attended
# step, outside this script; this script only reads it back out.
#
# INVOKE (as the human in the github-ci-runners group, ON THE AGENT):
#
#     with-github-ci-runners-env.sh -- \
#       ci-runner/k3s/secret-reinjection/seed-k3s-agent-join-token.sh \
#       ci-runner/k3s/phase0-bare-metal/profiles/gmktec-xubuntu.env
#
#   The wrapper decrypts its service-account token and drops privileges back to
#   the invoking human for `op run --environment`, injecting
#   K3S_AGENT_JOIN_TOKEN_CI_RUNNER into THIS script's environment. The write
#   itself needs root (the file is 0600 root:root under /etc), so it is
#   invoked via `sudo`; sudo will prompt for the human's password, or use a
#   cached credential.
#
# SECRET DISCIPLINE: the value is never echoed, logged, or placed on argv. It
# flows into `install` and into `cmp` over STDIN (the `/dev/stdin` source
# operand and `cmp`'s `-` operand); `printf` is a bash BUILTIN, so the value
# never becomes a command line anything can read out of /proc. Presence is
# probed with `printenv NAME | wc -c` — a byte COUNT, never the value. `set -x`
# is NEVER used.
#
# Usage: seed-k3s-agent-join-token.sh --dry-run PROFILE
#        with-github-ci-runners-env.sh -- seed-k3s-agent-join-token.sh PROFILE
#   PROFILE  path to the node's phase0-bare-metal/profiles/<node>.env
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
K3S_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SCRIPT_NAME="$(basename "$0")"

# The ONE injected variable. Named after the github-ci-runners Environment's
# own key, the way GITHUB_APP_ID_CI_RUNNER and its two siblings are next door.
TOKEN_VAR="K3S_AGENT_JOIN_TOKEN_CI_RUNNER"

# The mode the join token is written with, and the mode ../provision-k3s.sh
# independently REFUSES to provision without: a credential that admits a node
# to the cluster is owner-only.
TARGET_MODE="0600"
TARGET_OWNER="root"
TARGET_GROUP="root"

USAGE="usage: ${SCRIPT_NAME} [--dry-run] PROFILE   (PROFILE = phase0-bare-metal/profiles/<node>.env, which carries CLUSTER_ROLE and CLUSTER_TOKEN_FILE)"

die() { printf 'FATAL: %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------
DRY_RUN=0
PROFILE_PATH=""

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    -h|--help) printf '%s\n' "$USAGE"; exit 0 ;;
    # No `--` end-of-options case on purpose: no option here takes a value, so
    # `--` would only be a way to silently swallow the arguments after it.
    -*) die "unknown option '$1' -- ${USAGE}" ;;
    *)
      if [ -n "$PROFILE_PATH" ]; then
        die "more than one profile given ('${PROFILE_PATH}' and '$1') -- ${USAGE}"
      fi
      PROFILE_PATH="$1" ;;
  esac
  shift
done

[ -n "$PROFILE_PATH" ] || die "no profile given -- ${USAGE}"

# ---------------------------------------------------------------------------
# Profile: parsed, never sourced — through the SAME parser ../provision-k3s.sh
# reads CLUSTER_TOKEN_FILE with, so the file this seeds and the file that
# provisioning reads cannot drift apart. The parser has already refused an
# `agent` naming neither a join address nor a token file by the time it
# returns.
# ---------------------------------------------------------------------------
# shellcheck source=ci-runner/k3s/phase0-bare-metal/profile.sh
source "${K3S_DIR}/phase0-bare-metal/profile.sh"
profile_load "$PROFILE_PATH"

ROLE="${CFG[CLUSTER_ROLE]}"

# A SERVER does not take a join token — it MINTS one, at
# /var/lib/rancher/k3s/server/node-token, which is the very value an agent's
# copy of this seed carries. Refused in --dry-run too: the role is profile
# DATA, so a plan for the wrong role could never have been executed and must
# not be printed as though it could.
[ "$ROLE" = agent ] || die "${PROFILE_PATH}: CLUSTER_ROLE is '${ROLE}', not 'agent'. Only an agent authenticates with a join token; a server MINTS one at /var/lib/rancher/k3s/server/node-token. Nothing was written."

TARGET="${CFG[CLUSTER_TOKEN_FILE]}"
TARGET_DIR="$(dirname "$TARGET")"

print_plan() {
  printf '== %s plan ==\n' "$SCRIPT_NAME"
  printf 'profile:  %s\n' "$PROFILE_PATH"
  printf 'node:     %s\n' "${CFG[NODE_NAME]}"
  printf 'role:     %s\n' "$ROLE"
  printf 'join:     %s\n' "${CFG[CLUSTER_JOIN_ADDRESS]}"
  printf 'variable: %s (injected from the github-ci-runners 1Password Environment by with-github-ci-runners-env.sh)\n' "$TOKEN_VAR"
  printf 'target:   %s\n' "$TARGET"
  printf 'mode:     %s %s:%s\n' "$TARGET_MODE" "$TARGET_OWNER" "$TARGET_GROUP"
  printf 'write:    sudo install -m %s -o %s -g %s /dev/stdin %s   (the token arrives on STDIN, never on argv)\n' \
    "$TARGET_MODE" "$TARGET_OWNER" "$TARGET_GROUP" "$TARGET"
  printf 'skip:     an existing %s whose bytes already equal the injected value is REPORTED, not rewritten\n' "$TARGET"
}

# ---------------------------------------------------------------------------
# --dry-run stops here, having touched nothing at all — and having required no
# credential: an operator reading the plan is deciding WHETHER to seed, so the
# plan must be printable outside the 1Password wrapper.
# ---------------------------------------------------------------------------
if [ "$DRY_RUN" -eq 1 ]; then
  print_plan
  printf '\n-- --dry-run: the plan above was printed and NOTHING was executed --\n'
  exit 0
fi

print_plan

# The write and the comparison both need root — the target is owner-only root
# under /etc. Checked here rather than at the top so `--dry-run` stays a pure
# read of the profile, executable anywhere.
command -v sudo >/dev/null || die "sudo not found on PATH, and both the comparison and the write need root (the target is ${TARGET_MODE} ${TARGET_OWNER}:${TARGET_GROUP})"

# ---------------------------------------------------------------------------
# 1. The value was injected, and is not empty
#
# `${!TOKEN_VAR+set}` is bash INDIRECT expansion asking only whether the
# variable EXISTS — it expands to the word `set` or to nothing, never to the
# token. The length probe below is a byte COUNT from `printenv` (which appends
# a newline, so a set-but-empty variable counts 1). Neither surface can print
# the value.
# ---------------------------------------------------------------------------
if [ -z "${!TOKEN_VAR+set}" ]; then
  die "${TOKEN_VAR} is not set. Run this UNDER the github-ci-runners 1Password wrapper: with-github-ci-runners-env.sh -- $(basename "$0") ${PROFILE_PATH}"
fi
if [ "$(printenv "$TOKEN_VAR" 2>/dev/null | wc -c)" -le 1 ]; then
  die "${TOKEN_VAR} is set but EMPTY. The join token is the value at /var/lib/rancher/k3s/server/node-token on the server; store it in the github-ci-runners 1Password Environment under that name before seeding."
fi

# ---------------------------------------------------------------------------
# 2. The target's parent directory exists
#
# NOT created here, on purpose. /etc/rancher/k3s is made by the k3s installer,
# which on an agent runs AFTER this seed — so an operator seeding a node that
# has never had k3s creates it themselves, in one visible command. A script
# that made the parent instead would silently manufacture a whole directory
# tree for a mistyped CLUSTER_TOKEN_FILE and report success.
# ---------------------------------------------------------------------------
[ -d "$TARGET_DIR" ] || die "${PROFILE_PATH}: CLUSTER_TOKEN_FILE '${TARGET}' names parent directory '${TARGET_DIR}', which does not exist on this node. Create it deliberately first (sudo install -d -m 0755 -o root -g root '${TARGET_DIR}'); this script does not create it, so a mistyped path is refused rather than made."

# ---------------------------------------------------------------------------
# 3. Idempotence: byte-identical content is REPORTED, not rewritten
#
# `cmp` reads the injected value from STDIN and the target through sudo (the
# file is owner-only root, so an unprivileged read would fail as "absent" and
# rewrite a file that was already correct). A file whose bytes match but whose
# MODE has been widened by hand is not repaired here — ../provision-k3s.sh
# refuses that file by name and by mode, which is the check that must not be
# quietly satisfied behind the operator's back.
# ---------------------------------------------------------------------------
if sudo test -e "$TARGET" && printf '%s' "${!TOKEN_VAR}" | sudo cmp -s - "$TARGET"; then
  printf '\nunchanged: %s already holds the value of %s, byte for byte — not rewritten.\n' "$TARGET" "$TOKEN_VAR"
  exit 0
fi

# ---------------------------------------------------------------------------
# 4. The write. ${!TOKEN_VAR} is bash INDIRECT expansion into the `printf`
# BUILTIN, so the token reaches `install` only over the pipe `/dev/stdin`
# names; `install -m/-o/-g` sets the mode and ownership as it creates the file,
# so the token is never momentarily readable beyond its owner.
# ---------------------------------------------------------------------------
printf '%s' "${!TOKEN_VAR}" | sudo install -m "$TARGET_MODE" -o "$TARGET_OWNER" -g "$TARGET_GROUP" /dev/stdin "$TARGET"

printf '\nseeded: %s -> %s (%s %s:%s)\n' "$TOKEN_VAR" "$TARGET" "$TARGET_MODE" "$TARGET_OWNER" "$TARGET_GROUP"
printf 'Next: sudo %s/provision-k3s.sh %s (see ../README.md).\n' "$K3S_DIR" "$PROFILE_PATH"
