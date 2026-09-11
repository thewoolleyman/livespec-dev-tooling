#!/usr/bin/env bash
# refresh-gates-kubeconfig-exit-tests.sh — prove the gates-kubeconfig runtime
# re-fetch tool routes its ssh FETCH through the tailnet-identity user when it
# runs as root, WITHOUT touching any host, contacting any cluster, or holding a
# real credential. Follow-up #2 of livespec plan k3s-on-gmktec-for-vps-usage
# (epic livespec-sab5gn): root on the VPS has no tailnet ssh identity, so an
# `ssh poweredge` issued as root fails; the tool must drop the fetch to
# GATES_SSH_USER via `sudo -u` while keeping the write under root.
#
# HOW IT STAYS OFF THE HOST. `id`, `sudo`, `ssh` and `install` are FAKES on this
# suite's own PATH. `id` reports a EUID this suite chooses; `sudo` and `ssh` log
# their argv and emit a fixture kubeconfig on stdout (standing in for the remote
# `sudo cat`); `install` logs and writes into this suite's scratch dir. No real
# ssh, sudo, cluster or credential is involved. Every path is inside the scratch
# dir. Exit 0 iff every test passes; mutates nothing outside the scratch dir.
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

# install: log argv; for the file write, consume stdin so the pipe closes.
cat > "${BIN}/install" <<'EOF'
#!/usr/bin/env bash
printf 'install %s\n' "$*" >> "${ARGV_LOG}"
case " $* " in *" /dev/stdin "*) cat > /dev/null ;; esac
exit 0
EOF
chmod +x "${BIN}"/*

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
# The install of the destination must NOT be wrapped in sudo -u: only the fetch
# drops privilege. Assert no `sudo -u ... install` line was recorded.
run_tool 0 /nonexistent-env
if grep -qE '^install .* '"${SCRATCH//\//\\/}"'\/dest.kubeconfig' "${ARGV_LOG}" \
   && ! grep -qE '^sudo -u .* install ' "${ARGV_LOG}"; then
  ok "D: the destination is written by install directly (root), not via sudo -u"
else
  no "D: the write path was wrong (argv: $(tr '\n' '|' < "${ARGV_LOG}"))"
fi

# --- E. a non-kubeconfig fetch refuses to overwrite ------------------------
export FIXTURE_OUT="not a kubeconfig at all"
run_tool 0 /nonexistent-env
if [ "${RUN_RC}" -ne 0 ] && ! grep -qE '^install .* /dev/stdin ' "${ARGV_LOG}"; then
  ok "E: a fetched non-kubeconfig is refused and nothing is written"
else
  no "E: a non-kubeconfig fetch was not refused (rc=${RUN_RC})"
fi
export FIXTURE_OUT="${FIXTURE}"

if [ "${fail}" -eq 0 ]; then
  echo "PASS refresh-gates-kubeconfig-exit-tests (5 passed, 0 failed)"
  exit 0
fi
echo "FAIL refresh-gates-kubeconfig-exit-tests" >&2
exit 1
