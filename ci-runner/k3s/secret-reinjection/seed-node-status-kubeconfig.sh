#!/usr/bin/env bash
# seed-node-status-kubeconfig.sh — the ONE attended step that puts an AGENT
# node's node-status-patch KUBECONFIG on that node. Run by the human maintainer
# (a member of the github-ci-runners group, e.g. cwoolley) ON THE AGENT. It
# sources the rendered kubeconfig from the github-ci-runners 1Password
# Environment and writes it to the path the node's profile names in
# CHURN_KUBECONFIG_FILE, mode 0600 root:root.
#
# WHY IT EXISTS. ../phase2/node-extended-resource/reapply-node-extended-resource.service
# patches node status through the API; on a server its patch script authenticates
# as the k3s SERVER's admin file `/etc/rancher/k3s/k3s.yaml`, which does not exist
# on an agent — so a node-local churn-slot reapply timer on an agent has no
# credential at all (livespec-dev-tooling-xa6o, found by the 2026-09-06 rebuild
# dry-run on gmktec-xubuntu). Since R5 the agent's reapply timer reads the
# kubeconfig this seed places at CHURN_KUBECONFIG_FILE. The credential
# itself is minted cluster-side by
# ../phase2/node-status-credential/provision-node-status-credential.sh; this is
# the half that gets it onto the node, and it is DELIBERATELY the same path the
# join token takes rather than a second one.
#
# IT IS ./seed-k3s-agent-join-token.sh's SHAPE ON PURPOSE, AND THAT IS THE
# POINT. Same wrapper, same 1Password Environment, same attended-once posture,
# same "the value is never echoed, logged or on argv" discipline, same
# byte-identical-is-not-rewritten idempotence, same
# only-the-k3s-configuration-directory creation rule. A credential delivered by
# a second, differently-shaped mechanism is a second mechanism to audit and a
# second one to get wrong; the item that asked for this asked for it by name.
#
# WHAT IT DELIVERS IS NOT CLUSTER-ADMIN. The bytes this places grant `get` and
# `patch` on ONE node's `nodes/status` and nothing else — not the node's `spec`
# (so it cannot lift the node's own NoSchedule taint), not `delete`, not any
# other node. Read ../phase2/node-status-credential/node-status-patch-rbac.yaml
# for the whole grant. Copying the server's admin file here instead would put
# unrestricted control of the cluster on the machine that runs other people's
# CI jobs, and it is the specific mistake this script exists so that nobody
# takes.
#
# WHY IT HAS NO BOOT HALF, like the join token beside it: the file lives on the
# agent's own durable root filesystem and is read at run time by a systemd unit,
# not out of the k3s datastore (which is volatile by design and is why
# ./inject-github-app-secret.service exists). Seeding it once is enough, and
# re-running this is the RE-SEED step after a rotation.
#
# ROTATION. Deleting the ServiceAccount token Secret and re-running the
# provisioner mints a new token; the maintainer replaces the 1Password value and
# re-runs this script. Nothing here rotates anything on its own — a credential
# that rotated itself on an unattended timer would need a second credential to
# do it with, which is the regress this design refuses.
#
# INVOKE (as the human in the github-ci-runners group, ON THE AGENT):
#
#     with-github-ci-runners-env.sh -- \
#       ci-runner/k3s/secret-reinjection/seed-node-status-kubeconfig.sh \
#       ci-runner/k3s/phase0-bare-metal/profiles/gmktec-xubuntu.env
#
#   The wrapper decrypts its service-account token and drops privileges back to
#   the invoking human for `op run --environment`, injecting
#   K3S_NODE_STATUS_KUBECONFIG_CI_RUNNER into THIS script's environment. The
#   write itself needs root (the file is 0600 root:root under /etc), so it is
#   invoked via `sudo`.
#
# SECRET DISCIPLINE: the value is never echoed, logged, or placed on argv. It
# flows into `install` and into `cmp` over STDIN; `printf` is a bash BUILTIN, so
# it never becomes a command line anything can read out of /proc. Presence is
# probed with `printenv NAME | wc -c` — a byte COUNT, never the value. `set -x`
# is NEVER used.
#
# Usage: seed-node-status-kubeconfig.sh --dry-run PROFILE
#        with-github-ci-runners-env.sh -- seed-node-status-kubeconfig.sh PROFILE
#   PROFILE  path to the node's phase0-bare-metal/profiles/<node>.env
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
K3S_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SCRIPT_NAME="$(basename "$0")"

# The ONE injected variable, named after the github-ci-runners Environment's own
# key, the way K3S_AGENT_JOIN_TOKEN_CI_RUNNER is next door.
KUBECONFIG_VAR="K3S_NODE_STATUS_KUBECONFIG_CI_RUNNER"

# A bearer token is owner-only or it is not a secret — the same mode, owner and
# group the join token beside it is written with.
TARGET_MODE="0600"
TARGET_OWNER="root"
TARGET_GROUP="root"

# The k3s CONFIGURATION DIRECTORY — the ONE tree this script creates when it is
# missing, for the reason ./seed-k3s-agent-join-token.sh's header gives in full
# ("WHY IT MAKES /etc/rancher/k3s"): on a node that has never run k3s it does
# not exist, and a recipe step an operator cannot reproduce without an
# uncommitted `mkdir` is a defect in the procedure.
K3S_CONFIG_DIR="/etc/rancher/k3s"
PARENT_MODE="0755"

# The SERVER's admin kubeconfig. Naming it here is not a path this script uses —
# it is the one value CHURN_KUBECONFIG_FILE must never be, and the refusal below
# is what makes that a rule rather than a comment.
SERVER_ADMIN_KUBECONFIG="/etc/rancher/k3s/k3s.yaml"

USAGE="usage: ${SCRIPT_NAME} [--dry-run] PROFILE   (PROFILE = phase0-bare-metal/profiles/<node>.env, which carries CLUSTER_ROLE and CHURN_KUBECONFIG_FILE)"

die() { printf 'FATAL: %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------
DRY_RUN=0
PROFILE_PATH_ARG=""

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    -h|--help) printf '%s\n' "$USAGE"; exit 0 ;;
    # No `--` end-of-options case on purpose: no option here takes a value, so
    # `--` would only be a way to silently swallow the arguments after it.
    -*) die "unknown option '$1' -- ${USAGE}" ;;
    *)
      if [ -n "$PROFILE_PATH_ARG" ]; then
        die "more than one profile given ('${PROFILE_PATH_ARG}' and '$1') -- ${USAGE}"
      fi
      PROFILE_PATH_ARG="$1" ;;
  esac
  shift
done

[ -n "$PROFILE_PATH_ARG" ] || die "no profile given -- ${USAGE}"

# ---------------------------------------------------------------------------
# Profile: parsed, never sourced — through the SAME parser the provisioner and
# the node's own k3s stage read these keys with, so the path this seeds and the
# path everything else names cannot drift apart.
# ---------------------------------------------------------------------------
# shellcheck source=ci-runner/k3s/phase0-bare-metal/profile.sh
source "${K3S_DIR}/phase0-bare-metal/profile.sh"
profile_load "$PROFILE_PATH_ARG"

ROLE="${CFG[CLUSTER_ROLE]}"

# A SERVER already patches node status through its own admin file and needs no
# narrow credential; seeding one here would be a second long-lived token on the
# machine that holds the unrestricted one. Refused in --dry-run too: the role is
# profile DATA, so a plan that could never be executed must not be printed as
# though it could.
[ "$ROLE" = agent ] || die "${PROFILE_PATH_ARG}: CLUSTER_ROLE is '${ROLE}', not 'agent'. Only an agent lacks a node-status credential; a server patches node status through its own ${SERVER_ADMIN_KUBECONFIG}. Nothing was written."

TARGET="${CFG[CHURN_KUBECONFIG_FILE]}"

[ -n "$TARGET" ] || die "${PROFILE_PATH_ARG}: CHURN_KUBECONFIG_FILE is empty, so this node names no path for the node-status kubeconfig. Set it to the path the node-local churn-slot timer reads before seeding. Nothing was written."

# The one path it must not be. A profile naming the server's admin file would
# make this script overwrite k3s's own credential on a server, or manufacture a
# lookalike of it on an agent — either way the next reader could not tell a
# narrow credential from cluster-admin by its path, which is the whole reason
# this file has a name of its own.
[ "$TARGET" != "$SERVER_ADMIN_KUBECONFIG" ] || die "${PROFILE_PATH_ARG}: CHURN_KUBECONFIG_FILE is '${SERVER_ADMIN_KUBECONFIG}', the k3s SERVER's admin kubeconfig. This credential is deliberately NOT that file -- it grants get+patch on one node's nodes/status and nothing else -- and writing it under that name would make cluster-admin and this indistinguishable by path. Nothing was written."

TARGET_DIR="$(dirname "$TARGET")"

# in_k3s_config_tree PATH — true iff PATH is the k3s configuration directory
# itself or a directory beneath it. Matched on the path's TAIL, on whole
# components, exactly as ./seed-k3s-agent-join-token.sh matches it and for the
# same reason: the exit tests exercise the creation under their own scratch root
# through the SAME predicate a real node is judged by, rather than through a
# lever that could also widen what a live run is willing to make.
in_k3s_config_tree() {
  case "$1" in
    *"$K3S_CONFIG_DIR") return 0 ;;
    *"${K3S_CONFIG_DIR}/"*) return 0 ;;
    *) return 1 ;;
  esac
}

# exists | create | refuse — decided once, reported by the plan in both modes
# and acted on below.
if [ -d "$TARGET_DIR" ]; then
  PARENT_STATE=exists
elif in_k3s_config_tree "$TARGET_DIR"; then
  PARENT_STATE=create
else
  PARENT_STATE=refuse
fi

PARENT_CREATE_CMD=(sudo install -d -m "$PARENT_MODE" -o "$TARGET_OWNER" -g "$TARGET_GROUP" "$TARGET_DIR")

print_plan() {
  printf '== %s plan ==\n' "$SCRIPT_NAME"
  printf 'profile:  %s\n' "$PROFILE_PATH_ARG"
  printf 'node:     %s\n' "${CFG[NODE_NAME]}"
  printf 'role:     %s\n' "$ROLE"
  printf 'variable: %s (injected from the github-ci-runners 1Password Environment by with-github-ci-runners-env.sh)\n' "$KUBECONFIG_VAR"
  printf 'target:   %s\n' "$TARGET"
  printf 'grants:   get,patch on nodes/status for %s only -- NOT %s\n' "${CFG[NODE_NAME]}" "$SERVER_ADMIN_KUBECONFIG"
  case "$PARENT_STATE" in
    exists) printf 'parent:   %s (exists -- left exactly as it is)\n' "$TARGET_DIR" ;;
    create)
      printf 'parent:   %s (absent, and it is the k3s configuration directory: will be created %s %s:%s)\n' \
        "$TARGET_DIR" "$PARENT_MODE" "$TARGET_OWNER" "$TARGET_GROUP"
      printf '+ %s\n' "${PARENT_CREATE_CMD[*]}" ;;
    refuse) printf 'parent:   %s (absent, and NOT under %s: would refuse -- see the FATAL below)\n' \
      "$TARGET_DIR" "$K3S_CONFIG_DIR" ;;
  esac
  printf 'mode:     %s %s:%s\n' "$TARGET_MODE" "$TARGET_OWNER" "$TARGET_GROUP"
  printf 'write:    sudo install -m %s -o %s -g %s /dev/stdin %s   (the kubeconfig arrives on STDIN, never on argv)\n' \
    "$TARGET_MODE" "$TARGET_OWNER" "$TARGET_GROUP" "$TARGET"
  printf 'skip:     an existing %s whose bytes already equal the injected value is REPORTED, not rewritten\n' "$TARGET"
}

print_plan

# ---------------------------------------------------------------------------
# A parent this script will not create is refused HERE, after the plan and
# before the credential — in --dry-run too, for the same reason the wrong role
# is: the path is profile DATA, so a plan that could never be executed must not
# be printed as though it could.
# ---------------------------------------------------------------------------
[ "$PARENT_STATE" != refuse ] || die "${PROFILE_PATH_ARG}: CHURN_KUBECONFIG_FILE '${TARGET}' names parent directory '${TARGET_DIR}', which does not exist on this node and is not the k3s configuration directory '${K3S_CONFIG_DIR}' (the only tree this script creates). Create it deliberately first (sudo install -d -m ${PARENT_MODE} -o ${TARGET_OWNER} -g ${TARGET_GROUP} '${TARGET_DIR}'), so a mistyped path is refused rather than made."

# ---------------------------------------------------------------------------
# --dry-run stops here, having touched nothing at all — and having required no
# credential: an operator reading the plan is deciding WHETHER to seed, so the
# plan must be printable outside the 1Password wrapper.
# ---------------------------------------------------------------------------
if [ "$DRY_RUN" -eq 1 ]; then
  printf '\n-- --dry-run: the plan above was printed and NOTHING was executed --\n'
  exit 0
fi

# The write and the comparison both need root — the target is owner-only root
# under /etc. Checked here rather than at the top so `--dry-run` stays a pure
# read of the profile, executable anywhere.
command -v sudo >/dev/null || die "sudo not found on PATH, and both the comparison and the write need root (the target is ${TARGET_MODE} ${TARGET_OWNER}:${TARGET_GROUP})"

# ---------------------------------------------------------------------------
# 1. The value was injected, and is not empty
#
# `${!KUBECONFIG_VAR+set}` is bash INDIRECT expansion asking only whether the
# variable EXISTS — it expands to the word `set` or to nothing, never to the
# credential. The length probe is a byte COUNT from `printenv` (which appends a
# newline, so a set-but-empty variable counts 1). Neither surface can print the
# value.
# ---------------------------------------------------------------------------
if [ -z "${!KUBECONFIG_VAR+set}" ]; then
  die "${KUBECONFIG_VAR} is not set. Run this UNDER the github-ci-runners 1Password wrapper: with-github-ci-runners-env.sh -- ${SCRIPT_NAME} ${PROFILE_PATH_ARG}"
fi
if [ "$(printenv "$KUBECONFIG_VAR" 2>/dev/null | wc -c)" -le 1 ]; then
  die "${KUBECONFIG_VAR} is set but EMPTY. The value is the kubeconfig ../phase2/node-status-credential/provision-node-status-credential.sh renders on the SERVER; store it in the github-ci-runners 1Password Environment under that name before seeding."
fi

# ---------------------------------------------------------------------------
# 2. The target's parent directory
#
# Created only when it is the k3s configuration directory or a directory beneath
# it. Any other missing parent was refused above, so a mistyped
# CHURN_KUBECONFIG_FILE never has a directory tree manufactured for it. An
# EXISTING parent is left exactly as it is: its mode and ownership are the
# node's, not this script's.
# ---------------------------------------------------------------------------
if [ "$PARENT_STATE" = create ]; then
  "${PARENT_CREATE_CMD[@]}"
  printf '\ncreated: %s (%s %s:%s) -- the k3s configuration directory this node had not had yet\n' \
    "$TARGET_DIR" "$PARENT_MODE" "$TARGET_OWNER" "$TARGET_GROUP"
fi

# ---------------------------------------------------------------------------
# 3. Idempotence: byte-identical content is REPORTED, not rewritten
#
# `cmp` reads the injected value from STDIN and the target through sudo (the
# file is owner-only root, so an unprivileged read would fail as "absent" and
# rewrite a file that was already correct).
# ---------------------------------------------------------------------------
if sudo test -e "$TARGET" && printf '%s' "${!KUBECONFIG_VAR}" | sudo cmp -s - "$TARGET"; then
  printf '\nunchanged: %s already holds the value of %s, byte for byte — not rewritten.\n' "$TARGET" "$KUBECONFIG_VAR"
  exit 0
fi

# ---------------------------------------------------------------------------
# 4. The write. ${!KUBECONFIG_VAR} is bash INDIRECT expansion into the `printf`
# BUILTIN, so the value reaches `install` only over the pipe `/dev/stdin` names;
# `install -m/-o/-g` sets the mode and ownership as it creates the file, so the
# credential is never momentarily readable beyond its owner.
# ---------------------------------------------------------------------------
printf '%s' "${!KUBECONFIG_VAR}" | sudo install -m "$TARGET_MODE" -o "$TARGET_OWNER" -g "$TARGET_GROUP" /dev/stdin "$TARGET"

printf '\nseeded: %s -> %s (%s %s:%s)\n' "$KUBECONFIG_VAR" "$TARGET" "$TARGET_MODE" "$TARGET_OWNER" "$TARGET_GROUP"
printf 'It grants get+patch on nodes/status for %s and nothing else.\n' "${CFG[NODE_NAME]}"
