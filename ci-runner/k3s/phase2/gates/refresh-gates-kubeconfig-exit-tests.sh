#!/usr/bin/env bash
# refresh-gates-kubeconfig-exit-tests.sh — prove the gates-kubeconfig runtime
# re-fetch tool routes its ssh FETCH through the tailnet-identity user when it
# runs as root, WITHOUT touching any host, contacting any cluster, or holding a
# real credential. Follow-up #2 of livespec plan k3s-on-gmktec-for-vps-usage
# (epic livespec-sab5gn): root on the VPS has no tailnet ssh identity, so an
# `ssh poweredge` issued as root fails; the tool must drop the fetch to
# GATES_SSH_USER via `sudo -u` while keeping the write under root.
#
# HOW IT STAYS OFF THE HOST. `id`, `sudo` and `ssh` are FAKES on this suite's own
# PATH: `id` reports a EUID this suite chooses, and `sudo`/`ssh` log their argv
# and emit a fixture kubeconfig on stdout (standing in for the remote
# `sudo cat`). No real ssh, sudo, cluster or credential is involved, and every
# path is inside the scratch dir.
#
# THE WRITE ITSELF IS REAL, AND `install` IS A LENS RATHER THAN A FAKE. The write
# used to be faked too, which is exactly why this suite could not see
# livespec-dev-tooling-74q6iw: uutils coreutils (what Ubuntu 25.10 and 26.04 ship
# instead of GNU coreutils, on the VPS and on the node alike) fails `install`
# with `install: No such file or directory` whenever the DESTINATION already
# exists, so every refresh after the first one failed while this suite stayed
# green. `mktemp`, `tee`, `chmod` and `mv` are therefore the REAL binaries here
# and the write lands on the real filesystem inside the scratch dir, while
# `install` is a lens that logs its argv and REFUSES an existing destination
# exactly as uutils' does — so a write path that depends on an `install` able to
# overwrite fails here, on a GNU host, where the defect is otherwise invisible.
#
# Exit 0 iff every test passes; mutates nothing outside the scratch dir.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOL="${SCRIPT_DIR}/../../../../ansible/roles/gates_kubeconfig/files/refresh-gates-kubeconfig"

fail=0
ok()  { printf 'ok   - %s\n' "$*"; }
no()  { printf 'FAIL - %s\n' "$*"; fail=1; }

[ -x "${TOOL}" ] || { echo "FATAL: tool not found or not executable: ${TOOL}" >&2; exit 2; }

SCRATCH="$(mktemp -d)"
trap 'rm -rf "${SCRATCH}"' EXIT
BIN="${SCRATCH}/bin"
mkdir -p "${BIN}"

# A syntactically-valid fixture kubeconfig carrying the two markers the tool
# requires. Never a real credential.
FIXTURE=$'kind: Config\napiVersion: v1\nclusters:\n- cluster:\n    server: https://127.0.0.1:6443\n'

# --- fakes -----------------------------------------------------------------
# id: EUID comes from FAKE_EUID; every other `id` call falls through to nothing
# this tool needs.
cat > "${BIN}/id" <<'EOF'
#!/usr/bin/env bash
if [ "${1:-}" = "-u" ]; then printf '%s\n' "${FAKE_EUID:-1000}"; exit 0; fi
exit 0
EOF

# sudo: log argv; if this is the `sudo -u <user> -H ssh ... "sudo cat ..."`
# fetch wrapper, emit the fixture (the wrapped ssh's stdout). A remote `sudo`
# never runs here because ssh is faked, so the only sudo this suite sees is the
# local fetch wrapper.
cat > "${BIN}/sudo" <<'EOF'
#!/usr/bin/env bash
printf 'sudo %s\n' "$*" >> "${ARGV_LOG}"
printf '%s' "${FIXTURE_OUT}"
exit 0
EOF

# ssh: log argv and emit the fixture (the non-root direct-fetch path).
cat > "${BIN}/ssh" <<'EOF'
#!/usr/bin/env bash
printf 'ssh %s\n' "$*" >> "${ARGV_LOG}"
printf '%s' "${FIXTURE_OUT}"
exit 0
EOF

# install: the uutils LENS. `-d` (directory creation) is delegated to the real
# binary untouched — uutils accepts an existing directory there, and the parent
# step is not what the regression was about. Anything else whose destination
# already exists is REFUSED with uutils' own message and exit code.
cat > "${BIN}/install" <<'EOF'
#!/usr/bin/env bash
printf 'install %s\n' "$*" >> "${ARGV_LOG}"
for arg in "$@"; do
  [ "$arg" = -d ] && exec "${REAL_INSTALL}" "$@"
done
dest=""
for arg in "$@"; do dest="$arg"; done
if [ -e "$dest" ]; then
  printf 'install: No such file or directory\n' >&2
  exit 1
fi
exec "${REAL_INSTALL}" "$@"
EOF

# mktemp / tee / chmod / mv: the REAL binaries behind a logger, so the write the
# tool performs is a real filesystem write into this suite's scratch dir.
for tool in mktemp tee chmod mv; do
  real="$(command -v "$tool")"
  printf '#!/usr/bin/env bash\nprintf "%s %%s\\n" "$*" >> "${ARGV_LOG}"\nexec %s "$@"\n' \
    "$tool" "$real" > "${BIN}/${tool}"
done
chmod +x "${BIN}"/*

REAL_INSTALL="$(command -v install)"
export REAL_INSTALL

export FIXTURE_OUT="${FIXTURE}"

# run TOOL with the fakes first on PATH and a chosen EUID / env-file.
run_tool() {
  ARGV_LOG="${SCRATCH}/argv.$$.$RANDOM"
  export ARGV_LOG
  : > "${ARGV_LOG}"
  PATH="${BIN}:${PATH}" \
  FAKE_EUID="$1" \
  GATES_SSH_ENV="$2" \
  GATES_KUBECONFIG="${SCRATCH}/dest.kubeconfig" \
  GATES_REMOTE_HOST="poweredge-xubuntu" \
    "${TOOL}" > "${SCRATCH}/out.$$" 2>&1
  RUN_RC=$?
}

# --- A. as root, default identity: fetch goes through `sudo -u ubuntu -H ssh` --
run_tool 0 /nonexistent-env
if [ "${RUN_RC}" -eq 0 ] \
   && grep -qE '^sudo -u ubuntu -H ssh .* poweredge-xubuntu sudo cat ' "${ARGV_LOG}" \
   && ! grep -qE '^ssh ' "${ARGV_LOG}"; then
  ok "A: as root with no env-file, fetch runs as ubuntu via sudo -u; no bare ssh"
else
  no "A: as root the fetch did not route through 'sudo -u ubuntu -H ssh' (argv: $(tr '\n' '|' < "${ARGV_LOG}"))"
fi

# --- B. as root, env-file overrides the identity ---------------------------
ENVF="${SCRATCH}/gates-refresh.env"
printf 'GATES_SSH_USER=cwoolley\n' > "${ENVF}"
run_tool 0 "${ENVF}"
if [ "${RUN_RC}" -eq 0 ] && grep -qE '^sudo -u cwoolley -H ssh ' "${ARGV_LOG}"; then
  ok "B: the env-file's GATES_SSH_USER selects the sudo -u identity"
else
  no "B: the env-file identity was not honoured (argv: $(tr '\n' '|' < "${ARGV_LOG}"))"
fi

# --- C. NOT root: a plain ssh, never sudo -u -------------------------------
run_tool 1000 /nonexistent-env
if [ "${RUN_RC}" -eq 0 ] \
   && grep -qE '^ssh .* poweredge-xubuntu sudo cat ' "${ARGV_LOG}" \
   && ! grep -qE '^sudo -u ' "${ARGV_LOG}"; then
  ok "C: run by a normal user, the fetch is a direct ssh with no sudo -u"
else
  no "C: the non-root path did not use a bare ssh (argv: $(tr '\n' '|' < "${ARGV_LOG}"))"
fi

# --- D. the write happens under root (the current euid), not as the ssh user -
# Only the FETCH drops privilege: no write command may be wrapped in `sudo -u`.
# The destination is checked for real, because the write is real now.
rm -f "${SCRATCH}/dest.kubeconfig"
run_tool 0 /nonexistent-env
DEST_MODE="$(stat -c '%a' "${SCRATCH}/dest.kubeconfig" 2>/dev/null)"
if [ "${RUN_RC}" -eq 0 ] && [ "${DEST_MODE}" = 600 ] \
   && [ "$(cat "${SCRATCH}/dest.kubeconfig")" = "${FIXTURE%$'\n'}" ] \
   && ! grep -qE '^sudo -u .* (tee|mv|chmod|install) ' "${ARGV_LOG}"; then
  ok "D: the destination is written at 0600 by the current euid, not via sudo -u"
else
  no "D: the write path was wrong (rc=${RUN_RC}, mode='${DEST_MODE}', argv: $(tr '\n' '|' < "${ARGV_LOG}"))"
fi

# --- E. a non-kubeconfig fetch refuses to overwrite ------------------------
# Asserted on the FILE rather than on an absent argv line: what matters is that
# the good credential already on disk survives a truthful-looking bad answer.
DEST_BEFORE="$(cat "${SCRATCH}/dest.kubeconfig")"
export FIXTURE_OUT="not a kubeconfig at all"
run_tool 0 /nonexistent-env
if [ "${RUN_RC}" -ne 0 ] && [ "$(cat "${SCRATCH}/dest.kubeconfig")" = "${DEST_BEFORE}" ]; then
  ok "E: a fetched non-kubeconfig is refused and the existing credential is untouched"
else
  no "E: a non-kubeconfig fetch was not refused, or it damaged the destination (rc=${RUN_RC})"
fi
export FIXTURE_OUT="${FIXTURE}"

# --- F. THE RE-RUN: an EXISTING destination is replaced, not refused -------
# The defect livespec-dev-tooling-74q6iw fixed, asserted where it lived. The
# destination is pre-created on purpose and the write path is real, so a tool
# that reaches for an `install` able to overwrite fails here against the uutils
# lens — on a GNU host, where the live symptom cannot otherwise be reproduced.
printf 'stale: the kubeconfig a refresh must replace\n' > "${SCRATCH}/dest.kubeconfig"
chmod 0644 "${SCRATCH}/dest.kubeconfig"
run_tool 0 /nonexistent-env
DEST_MODE="$(stat -c '%a' "${SCRATCH}/dest.kubeconfig" 2>/dev/null)"
if [ "${RUN_RC}" -eq 0 ] \
   && [ "$(cat "${SCRATCH}/dest.kubeconfig")" = "${FIXTURE%$'\n'}" ] \
   && [ "${DEST_MODE}" = 600 ]; then
  ok "F: a re-run over an existing destination replaces it at 0600 and exits 0"
else
  no "F: the re-run over an existing destination failed (rc=${RUN_RC}, mode='${DEST_MODE}')"
fi

# The rename leaves no temp file behind, and the temp it used was never readable
# beyond its owner — a 0644 stand-in next to a 0600 credential is the exposure
# the umask-plus-rename shape exists to prevent.
if [ -z "$(find "$(dirname "${SCRATCH}/dest.kubeconfig")" -name 'dest.kubeconfig.refresh.*' -print -quit)" ]; then
  ok "F2: the write left no temp file beside the destination"
else
  no "F2: a temp file survived the write"
fi

if [ "${fail}" -eq 0 ]; then
  echo "PASS refresh-gates-kubeconfig-exit-tests (7 passed, 0 failed)"
  exit 0
fi
echo "FAIL refresh-gates-kubeconfig-exit-tests" >&2
exit 1
