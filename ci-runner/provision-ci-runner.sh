#!/usr/bin/env bash
# provision-ci-runner.sh — idempotently provision the Phase 0 local CI runner
# containment on a fresh host, EXACTLY as validated live 2026-07-12.
#
# Design + exit tests: livespec plan/fabro-ci-image-factoring/
#   phase0-runner-containment-design.md (11 isolation tests).
# Recreatability: this script + the sanitize-hook.js + the ci-runner
# containers.conf are the durable artifacts; re-running it converges the host.
#
# HARD invariants (never traded away):
#   * ci-runner is in NONE of docker/sudo/dolt; no sudoers entry.
#   * AppArmor userns sysctls stay =1 (host-wide hardening intact); rootless
#     userns comes from the SHIPPED bwrap/podman profiles, never a sysctl
#     downgrade and never a setuid-root runtime.
#   * jobs run rootless (container-root -> ci-runner host uid, NOT host root),
#     socket-less (no docker.sock), host-loopback-isolated, agent/job PID+userns
#     separated (ACTIONS_RUNNER_CONTAINER_HOOKS + sanitize-hook.js).
#
# Requires: run as a sudo-capable admin (installs packages, creates the user).
# The runner registration itself is a SEPARATE step (supervisor / JIT), not here.
set -euo pipefail

RUNNER_USER=ci-runner
# shellcheck disable=SC2034
# Informational uid target retained for operator comparisons; useradd assigns.
RUNNER_UID_HINT=1001            # informational; useradd assigns
RUNNER_HOME=/home/${RUNNER_USER}
RUNNER_DIR=${RUNNER_HOME}/actions-runner
RUNNER_VERSION=2.335.1
HOOKS_VERSION=0.8.1

log() { printf '\n== %s ==\n' "$*"; }

# ---------------------------------------------------------------------------
log "0. Pre-gate: verify shipped AppArmor userns backbone (no mutation)"
u=$(sysctl -n kernel.apparmor_restrict_unprivileged_userns)
c=$(sysctl -n kernel.apparmor_restrict_unprivileged_unconfined)
[ "$u" = 1 ] && [ "$c" = 1 ] || { echo "FATAL: AppArmor userns sysctls must be =1 (got $u/$c)"; exit 1; }
for prof in /etc/apparmor.d/bwrap-userns-restrict /etc/apparmor.d/podman; do
  [ -f "$prof" ] || { echo "FATAL: missing shipped AppArmor profile $prof"; exit 1; }
done
# bwrap must be present and NOT setuid-root
command -v bwrap >/dev/null || { echo "FATAL: bwrap absent"; exit 1; }
[ -n "$(find "$(command -v bwrap)" -perm -4000 2>/dev/null)" ] && { echo "FATAL: bwrap is setuid-root"; exit 1; }
bwrap --ro-bind / / --unshare-user --uid 0 -- /usr/bin/true \
  || { echo "FATAL: profiled bwrap userns does not work"; exit 1; }

# ---------------------------------------------------------------------------
log "1. Install rootless stack (25.10-validated; reversible)"
export DEBIAN_FRONTEND=noninteractive
# podman-docker provides /usr/bin/docker as a thin podman wrapper — NO daemon and
# NO docker group, so it adds nothing to the containment surface. It is REQUIRED,
# not a convenience: the container hooks shell out to `docker` by name, and the
# serialization shim installed in step 7 execs $CI_RUNNER_REAL_DOCKER, default
# /usr/bin/docker. Without it, every containerized job dies in PrepareJobAsync with
#   Error: Unable to locate executable file: docker
# before a single step runs. This went unnoticed because the host this script was
# authored against already carried a docker CLI from an unrelated daemon install,
# so /usr/bin/docker existed for reasons provisioning never established. Observed
# 2026-08-13 on a fresh Ubuntu 26.04 host with podman but no docker.
apt-get install -y --no-install-recommends \
  podman podman-docker uidmap slirp4netns passt crun catatonit fuse-overlayfs aardvark-dns
# runtimes must NOT be setuid-root (newuidmap/newgidmap ARE, and that is allowed)
for rt in /usr/bin/crun /usr/sbin/runc /usr/bin/bwrap /usr/bin/podman; do
  [ -e "$rt" ] && [ -n "$(find "$rt" -perm -4000 2>/dev/null)" ] && { echo "FATAL: $rt is setuid-root"; exit 1; }
done

# ---------------------------------------------------------------------------
log "2. Create ci-runner in NONE of docker/sudo/dolt (idempotent)"
if ! id "$RUNNER_USER" >/dev/null 2>&1; then
  useradd --create-home --shell /usr/sbin/nologin \
    --comment "livespec local CI runner (contained; none of docker/sudo/dolt)" "$RUNNER_USER"
fi
# assert containment
for g in docker sudo dolt; do
  id -nG "$RUNNER_USER" | tr ' ' '\n' | grep -qx "$g" && { echo "FATAL: $RUNNER_USER in forbidden group $g"; exit 1; }
done
grep -rqE "^\s*${RUNNER_USER}\b" /etc/sudoers /etc/sudoers.d/ 2>/dev/null && { echo "FATAL: $RUNNER_USER has sudoers entry"; exit 1; }
grep -q "^${RUNNER_USER}:" /etc/subuid || echo "WARN: no subuid range for $RUNNER_USER (useradd usually assigns)"
loginctl enable-linger "$RUNNER_USER"
# `enable-linger` RETURNS BEFORE the user manager is running, and step 4 below
# talks to that manager's D-Bus socket. On a host where $RUNNER_USER is created
# in the same run, provisioning therefore RACES the manager it is about to use
# and dies with:
#   Failed to connect to user scope bus via local transport: No such file or directory
# Observed on a fresh Ubuntu 26.04 host 2026-08-13; a second run of this
# idempotent script then succeeded, which is precisely what makes the race easy
# to mistake for a transient and "fix" by re-running. Wait for the socket
# instead, so a first run on a fresh host converges like every later one.
RUNNER_UID=$(id -u "$RUNNER_USER")
systemctl start "user@${RUNNER_UID}.service"
for _ in $(seq 1 30); do
  [ -S "/run/user/${RUNNER_UID}/bus" ] && break
  sleep 1
done
[ -S "/run/user/${RUNNER_UID}/bus" ] \
  || { echo "FATAL: user bus for $RUNNER_USER did not appear within 30s"; exit 1; }
runuser -u "$RUNNER_USER" -- mkdir -p "${RUNNER_HOME}/.cache/uv" "${RUNNER_HOME}/.cargo/registry" "${RUNNER_HOME}/.config/containers"

# ---------------------------------------------------------------------------
log "3. ci-runner containers.conf — public DNS + private netns"
install -o "$RUNNER_USER" -g "$RUNNER_USER" -m 0644 \
  "$(dirname "$0")/containers.conf" "${RUNNER_HOME}/.config/containers/containers.conf"

# ---------------------------------------------------------------------------
log "4. Rootless podman API socket for the container-hooks DOCKER_HOST"
XDG=/run/user/$(id -u "$RUNNER_USER")
runuser -u "$RUNNER_USER" -- env XDG_RUNTIME_DIR="$XDG" DBUS_SESSION_BUS_ADDRESS="unix:path=$XDG/bus" \
  systemctl --user enable --now podman.socket

# ---------------------------------------------------------------------------
log "5. Install Actions runner ${RUNNER_VERSION} + container-hooks ${HOOKS_VERSION} + sanitizer"
runuser -u "$RUNNER_USER" -- bash -eu <<EOF
mkdir -p "${RUNNER_DIR}/container-hooks"
cd "${RUNNER_DIR}"
[ -f config.sh ] || { curl -fsSL -o r.tgz https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz; tar xzf r.tgz; rm r.tgz; }
[ -f container-hooks/index.js ] || { curl -fsSL -o h.zip https://github.com/actions/runner-container-hooks/releases/download/v${HOOKS_VERSION}/actions-runner-hooks-docker-${HOOKS_VERSION}.zip; (cd container-hooks && unzip -oq ../h.zip); rm h.zip; }
EOF
install -o "$RUNNER_USER" -g "$RUNNER_USER" -m 0644 \
  "$(dirname "$0")/sanitize-hook.js" "${RUNNER_DIR}/container-hooks/sanitize-hook.js"
runuser -u "$RUNNER_USER" -- tee "${RUNNER_DIR}/.env" >/dev/null <<EOF
ACTIONS_RUNNER_CONTAINER_HOOKS=${RUNNER_DIR}/container-hooks/sanitize-hook.js
DOCKER_HOST=unix://${XDG}/podman/podman.sock
XDG_RUNTIME_DIR=${XDG}
EOF

# ---------------------------------------------------------------------------
log "6. Per-slot runner INSTANCE dirs (one per concurrent runner — NOT shared)"
# EVERY CONCURRENT RUNNER NEEDS ITS OWN DIRECTORY. The Actions runner materializes
# its JIT config to `.runner` / `.credentials` in its ROOT dir at startup, and it
# writes `_diag` there too; its `_work` folder is likewise per-runner. Point N
# runners at ONE directory and they overwrite each other's session files — the
# symptom is every runner looping "√ Connected to GitHub" every ~30s, GitHub
# reporting them `offline`, and jobs stalling in `queued`.
#
# Phase 0 shipped a single shared dir because it only ever ran ONE slot, so the
# collision was invisible. It surfaced the moment the pool was raised to 18 for the
# Phase 2 CI matrix (2026-07-14). Fixed at the source: a per-slot instance dir.
#
# bin/ and externals/ MUST be real directories, NOT symlinks. Runner.Listener
# resolves its runner ROOT from its OWN executable path, so a symlinked bin/ sends
# it straight back to the shared install and every runner writes .runner /
# .credentials / _diag there anyway — the collision survives, and the runners loop
# "Deleting Runner Session..." forever (observed 2026-07-14; the symlink attempt
# looked right and changed nothing). They are HARD-LINKED copies (`cp -al`), so 18
# instances cost near-zero disk while each still resolves its own root.
SLOTS="${CI_RUNNER_SLOTS:-18}"
REPOSLUGS="${CI_RUNNER_REPOSLUGS:-thewoolleyman-livespec}"
INSTANCES_ROOT=${RUNNER_HOME}/runners
runuser -u "$RUNNER_USER" -- bash -eu <<EOF
mkdir -p "${INSTANCES_ROOT}"
for slug in ${REPOSLUGS}; do
  for n in \$(seq 1 ${SLOTS}); do
    inst="${INSTANCES_ROOT}/\${slug}-\${n}"
    mkdir -p "\$inst/_work" "\$inst/_diag"
    # Hard-linked copies: real dirs (so Runner.Listener resolves THIS root), but
    # sharing inodes with the one install, so N instances cost near-zero disk.
    for d in bin externals container-hooks; do
      [ -d "\$inst/\$d" ] || cp -al "${RUNNER_DIR}/\$d" "\$inst/\$d"
    done
    # Per-instance: the launch scripts + env (so .runner/.credentials land HERE).
    #
    # run-helper.sh.TEMPLATE, not run-helper.sh. A freshly extracted runner
    # tarball ships only the template; run.sh copies it to run-helper.sh at
    # STARTUP and then execs it. Copying "run-helper.sh" therefore matches
    # nothing on a fresh install, the \`|| true\` swallows the miss, and every
    # instance dir is silently built without the file. The runner then dies at
    # first start with:
    #   cp: cannot stat '.../run-helper.sh.template': No such file or directory
    #   ./run.sh: line 18: .../run-helper.sh: No such file or directory
    # This stayed invisible on a host where run.sh had already been run once in
    # the shared install, because that leaves a real run-helper.sh behind for the
    # copy to find — so the bug only ever appears on a genuinely fresh host.
    # Observed 2026-08-13 on Ubuntu 26.04.
    for f in run.sh run-helper.sh.template config.sh env.sh .env; do
      [ -e "${RUNNER_DIR}/\$f" ] \
        || { echo "FATAL: required runner file missing: ${RUNNER_DIR}/\$f"; exit 1; }
      cp -f "${RUNNER_DIR}/\$f" "\$inst/\$f"
    done
    # Genuinely optional: present in some runner releases and not others. These
    # keep the tolerant form ON PURPOSE, so the strict loop above stays a real
    # assertion rather than a list everything drifts into.
    for f in run-helper.cmd.template safe_sleep.sh; do
      [ -e "${RUNNER_DIR}/\$f" ] && cp -f "${RUNNER_DIR}/\$f" "\$inst/\$f" || true
    done
  done
done
EOF
printf 'provisioned %s instance dirs per repo-slug under %s\n' "$SLOTS" "$INSTANCES_ROOT"

# ---------------------------------------------------------------------------
log "7. docker serialization shim (podman network-prune race — REQUIRED for >1 slot)"
# Every slot shares ONE rootless podman. `podman network prune` walks the GLOBAL
# container DB to find in-use networks (the label filter only narrows what it
# DELETES), so it fails when a CONCURRENT job removes a container mid-scan:
#   "Error response from daemon: no container with ID <other job's id> found in database"
# The job's work has already passed; only the runner's "Stop containers" teardown
# fails — but that still reds the job. Invisible at one slot; at 12 concurrent it
# red 8-10 of 12. runner@.service puts this dir FIRST on the agent's PATH, so the
# container hooks resolve THIS `docker`; it readers-writer-locks prune against
# removal and passes everything else (pull/start/exec) straight through unlocked.
mkdir -p /usr/local/lib/ci-runner/dockershim
cp -f "$(dirname "$0")/dockershim/docker" /usr/local/lib/ci-runner/dockershim/docker
chown root:root /usr/local/lib/ci-runner/dockershim/docker
chmod 0755 /usr/local/lib/ci-runner/dockershim/docker

# ---------------------------------------------------------------------------
log "8. T10 cache-tiering — per-repo warm-cache lower dirs (livespec-dev-tooling-9mp)"
# sanitize-hook.js mounts these READ-ONLY into each job via a throwaway overlay
# (the upper is per-job and discarded), so a fork PR job can READ the warm cache
# but can NEVER mutate it — trust-tiering by construction, no forgeable signal.
# We only create the lower dirs here; warm-ci-cache.sh (trusted, host-side)
# populates them. The hook caches a subdir IFF its lower dir EXISTS:
#   uv     — ALL repos (cold uv is cheap but non-zero; closes the .5 follow-on)
#   cargo  — Rust repos only (registry + git; skip the network fetch)
#   target — Rust repos only (the big win: skip the TEN redundant dep recompiles
#            that make the Rust matrix a 2x regression without a cache)
# The CACHE_ROOT's mere existence is the kill switch — remove it and the hook is
# a byte-for-byte no-op of the Phase-0 containment behaviour.
CACHE_ROOT=${CI_RUNNER_CACHE_ROOT:-/var/cache/ci-runner}
RUST_REPOSLUGS="${CI_RUNNER_RUST_REPOSLUGS:-thewoolleyman-livespec-console-beads-fabro}"
runuser -u "$RUNNER_USER" -- bash -eu <<EOF
mkdir -p "${CACHE_ROOT}/.overlay"
for slug in ${REPOSLUGS}; do
  mkdir -p "${CACHE_ROOT}/\${slug}/uv"
done
for slug in ${RUST_REPOSLUGS}; do
  mkdir -p "${CACHE_ROOT}/\${slug}/cargo" "${CACHE_ROOT}/\${slug}/target"
done
EOF
# Reclaim any overlay left mounted under a previous run's instance scratch
# (idempotent; safe because no job container is active during provisioning).
while IFS= read -r m; do
  [ -n "$m" ] && runuser -u "$RUNNER_USER" -- fusermount3 -u "$m" 2>/dev/null || true
done < <(findmnt -rno TARGET 2>/dev/null | grep "^${CACHE_ROOT}/.overlay/" || true)
runuser -u "$RUNNER_USER" -- find "${CACHE_ROOT}/.overlay" -mindepth 1 -maxdepth 1 -exec rm -rf {} + 2>/dev/null || true
printf 'T10 cache lower dirs ready under %s (rust: %s)\n' "$CACHE_ROOT" "$RUST_REPOSLUGS"

log "DONE. Register the runners via the supervisor/JIT step, then run the 11 isolation exit tests."
