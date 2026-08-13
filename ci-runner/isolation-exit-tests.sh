#!/usr/bin/env bash
# isolation-exit-tests.sh — Phase 0 runner containment exit criteria (the 11
# isolation tests from plan/fabro-ci-image-factoring/phase0-runner-containment-
# design.md), runnable + re-runnable against the live host. Exit 0 iff every
# non-skipped test passes. Read-only w.r.t. host state (throwaway containers only).
#
# Validated live 2026-07-12. Durable home: livespec-dev-tooling.
set -uo pipefail
RU=ci-runner
XDG=/run/user/$(id -u "$RU" 2>/dev/null || echo 1001)
POD=(sudo -n -u "$RU" env HOME="/home/$RU" XDG_RUNTIME_DIR="$XDG" podman)
# The image under test is DERIVED from this repo's own ci.yml container pin, not
# hardcoded. That pin is auto-reconciled to every release by the
# `self-reconcile-pins` job in fabro-sandbox-image.yml (livespec-dev-tooling-5r3),
# so this suite tracks the released image with no manual step.
#
# It used to hardcode a default, which had silently drifted SEVEN releases
# (python-v0.43.2 while the repo ran python-v0.50.1). An unparameterized run
# therefore exercised a stale artifact and still reported success — the exact
# failure mode a containment suite must not have, since "14 pass" on the wrong
# image proves nothing about the image actually in use. Per the repo discipline
# that a recurring drift is handled AT ITS SOURCE rather than worked around, the
# value is now derived; `LIVESPEC_CI_RUNNER_IMAGE` still overrides for ad-hoc runs
# against a specific tag.
#
# Fails LOUD rather than falling back to a literal: a silent fallback would
# reintroduce exactly the stale-default bug this replaces.
_ISO_REPO_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
_ISO_CI_YML="$_ISO_REPO_ROOT/.github/workflows/ci.yml"
if [[ -z ${LIVESPEC_CI_RUNNER_IMAGE:-} ]]; then
  _ISO_DERIVED=$(grep -oE 'ghcr\.io/thewoolleyman/livespec-fabro-sandbox:[A-Za-z0-9._-]+' \
    "$_ISO_CI_YML" 2>/dev/null | head -1)
  if [[ -z $_ISO_DERIVED ]]; then
    echo "FATAL: could not derive the sandbox image from $_ISO_CI_YML" >&2
    echo "  Set LIVESPEC_CI_RUNNER_IMAGE=<image>:<tag> to run against an explicit tag." >&2
    exit 2
  fi
fi
IMG=${LIVESPEC_CI_RUNNER_IMAGE:-$_ISO_DERIVED}
echo "== image under test: $IMG =="
KIND2=(/var/lib/doltdb /data/projects/1password-env-wrapper/.env.local)
WF=${1:-/data/projects/livespec/.github/workflows}   # workflows dir for static audit
# Resolve before the chdir below, so a RELATIVE workflows argument still works.
[ -d "$WF" ] && WF=$(cd "$WF" && pwd)

# RUN FROM A NEUTRAL DIRECTORY. Most tests below drop privileges to $RU, and an
# invoker's cwd is routinely unreadable by that account — a maintainer home is
# mode 0750, so `sudo -u $RU podman ...` launched from it dies with
#   cannot chdir to /home/<invoker>: Permission denied
#   Error: setting up the process
# before the container ever starts. The probes then capture EMPTY output, and
# empty compares unequal to the expected value, so T7, T8, T10 and T11 all report
# FAIL. Observed 2026-08-13: the identical host scored 5 fail from a home
# directory and 0 fail from /tmp. That failure mode is worse than a crash — it
# accuses a correctly contained host of breaching containment, and the natural
# next move is to go "fix" containment that was never broken.
cd / || exit 1
P=0 F=0 S=0
pass(){ echo "  PASS $1"; P=$((P+1)); }
fail(){ echo "  FAIL $1"; F=$((F+1)); }
skip(){ echo "  SKIP $1"; S=$((S+1)); }

echo "== T1: ci-runner in NONE of docker/sudo/dolt, no sudoers =="
g=$(id -nG "$RU"); echo "  groups: $g"
echo " $g " | grep -qE ' (docker|sudo|dolt) ' && fail "forbidden group" || pass "not in docker/sudo/dolt"
sudo -n grep -rqE "^\s*$RU\b" /etc/sudoers /etc/sudoers.d/ 2>/dev/null && fail "sudoers entry" || pass "no sudoers entry"

echo "== T2: ci-runner cannot read Kind-2 secret paths =="
for p in "${KIND2[@]}"; do sudo -n -u "$RU" test -r "$p" 2>/dev/null && fail "can read $p" || pass "cannot read $p"; done

echo "== T3: ci-runner sudo -n fails =="
sudo -n -u "$RU" sudo -n true 2>/dev/null && fail "sudo succeeded" || pass "sudo denied"

echo "== T4: job container has NO docker.sock (sanitizer strips it) =="
"${POD[@]}" run --rm "$IMG" test -S /var/run/docker.sock 2>/dev/null && fail "docker.sock present" || pass "no docker.sock in container"

echo "== T5: no Kind-2 secret in a container env; SKIP full live-job env check =="
skip "T5 needs a live moved job (verify printenv shows no App key/JIT/1P/Dolt pw; GITHUB_TOKEN read-scoped)"

echo "== T6: honest fork PR routes to ubuntu-latest =="
skip "T6 external — honest fork PR must not trigger a self-hosted job (manual/CI check)"

echo "== T7: rootless; container-root != host root; sysctls =1; runtime not setuid =="
rl=$("${POD[@]}" info --format '{{.Host.Security.Rootless}}' 2>/dev/null); [ "$rl" = true ] && pass "podman rootless" || fail "rootless=$rl"
SC=/home/$RU/.exittest; sudo -n -u "$RU" mkdir -p "$SC" 2>/dev/null; "${POD[@]}" run --rm -v "$SC:/o:Z" "$IMG" sh -c 'touch /o/m' 2>/dev/null
ho=$(sudo -n stat -c '%u' "$SC/m" 2>/dev/null); sudo -n rm -rf "$SC" 2>/dev/null
[ -n "$ho" ] && [ "$ho" != 0 ] && pass "container-root -> host uid $ho (not root)" || fail "mapping ho=$ho"
s1=$(sysctl -n kernel.apparmor_restrict_unprivileged_userns); s2=$(sysctl -n kernel.apparmor_restrict_unprivileged_unconfined)
[ "$s1" = 1 ] && [ "$s2" = 1 ] && pass "sysctls =1" || fail "sysctls $s1/$s2"
[ -z "$(find /usr/bin/crun /usr/sbin/runc /usr/bin/bwrap /usr/bin/podman -perm -4000 2>/dev/null)" ] && pass "no setuid runtime" || fail "setuid runtime"

echo "== T8: no host-loopback route by any path; internet OK (dynamic enumeration) =="
# dynamic loopback listener set
mapfile -t LISTEN < <(ss -tlnH 2>/dev/null | awk '{print $4}' | grep -oE '(127\.[0-9.]+|\[::1\]):[0-9]+' | sed -E 's/\[::1\]/::1/' )
"${POD[@]}" run --rm "$IMG" bash -c '
f=0
deny(){ timeout 3 bash -c "exec 3<>/dev/tcp/$1/$2" 2>/dev/null && { echo "REACH $1:$2"; f=1; } || true; }
for hp in 127.0.0.1:3307 host.containers.internal:3307 169.254.169.254:80 '"${LISTEN[*]}"'; do deny "${hp%:*}" "${hp##*:}"; done
timeout 6 bash -c "exec 3<>/dev/tcp/1.1.1.1/443" 2>/dev/null || echo "NO-INTERNET"
exit $f' 2>/dev/null && pass "all host-loopback denied" || fail "a host-loopback route reachable"

echo "== T9: static workflow audit — no self-hosted job on a forbidden trigger =="
# A workflow is a hole iff it BOTH uses a self-hosted runner AND can be
# triggered by a forbidden event (fork-reachable / base-privileged triggers
# that must never reach the unprivileged runner — routing design
# §"Trusted-event routing"). The forbidden set deliberately EXCLUDES the two
# allowed events (`push` to master, same-repo `pull_request`); the same-repo
# predicate + the all_external_contributors approval gate carry the fork case.
#
# The prior check grepped the WHOLE FILE as flat text, so a COMMENT that names
# a forbidden trigger false-failed a safe workflow — e.g. the shadow lane's
# "# NEVER pull_request / merge_group / workflow_dispatch" doc line, which
# DOCUMENTS the safety it was flagged for. YAML comments never carry real
# config, so we strip them and test the actual top-level `on:` trigger block,
# not prose. (Corrected 2026-07-15; a full YAML parser is deferred to the
# Phase-3 fleet-wide CI check — see plan/fabro-ci-image-factoring/handoff.md.)
FORBIDDEN='pull_request_target|workflow_run|issue_comment|repository_dispatch|merge_group|workflow_dispatch'
bad=0
for wf in "$WF"/*.yml "$WF"/*.yaml; do
  [ -f "$wf" ] || continue
  # Strip full-line and trailing (` # ...`) comments so doc prose cannot match.
  stripped=$(sed -E 's/[[:space:]]+#.*$//; /^[[:space:]]*#/d' "$wf")
  # Only workflows that actually use a self-hosted runner are in scope.
  echo "$stripped" | grep -qE 'self-hosted' || continue
  # Extract the top-level `on:` block (block form, inline `[..]` list, or scalar)
  # — a col-0 key line other than `on:` ends it — and test IT for forbidden events.
  on_block=$(echo "$stripped" | awk '
    /^[^[:space:]]/ {
      if ($0 ~ /^([Oo][Nn]|"on"|'\''on'\''):/) { c=1; print; next } else { c=0 }
    }
    c { print }
  ')
  hit=$(echo "$on_block" | grep -oE "$FORBIDDEN" | sort -u | paste -sd, -)
  if [ -n "$hit" ]; then
    echo "  suspect: $wf — self-hosted + forbidden trigger(s): $hit"; bad=1
  fi
done
[ "$bad" = 0 ] && pass "no self-hosted job reachable from a forbidden trigger" || fail "self-hosted job on forbidden trigger"

echo "== T10: trust-tiered cache — a job cannot mutate the shared warm cache =="
# sanitize-hook.js mounts /var/cache/ci-runner/<repo>/{cargo,target,uv} into a
# job READ-ONLY via a throwaway overlay (upper per-job, discarded). Prove the
# security invariant directly: a container writing THROUGH the injected mount
# leaves the shared LOWER byte-for-byte unchanged, so a fork PR job physically
# cannot poison the cache that feeds master builds.
T10D=/home/$RU/.t10-exittest
sudo -n -u "$RU" bash -c "rm -rf '$T10D'; mkdir -p '$T10D'/{lower,upper,work,merged}; echo warm-cache-object > '$T10D/lower/dep.crate'"
if sudo -n -u "$RU" env XDG_RUNTIME_DIR="$XDG" fuse-overlayfs -o "lowerdir=$T10D/lower,upperdir=$T10D/upper,workdir=$T10D/work" "$T10D/merged" 2>/dev/null; then
  "${POD[@]}" run --rm -v "$T10D/merged:/opt/ci-cache/cargo" "$IMG" \
    bash -c 'cat /opt/ci-cache/cargo/dep.crate >/dev/null && echo poison > /opt/ci-cache/cargo/evil.crate' 2>/dev/null
  sudo -n -u "$RU" env XDG_RUNTIME_DIR="$XDG" fusermount3 -u "$T10D/merged" 2>/dev/null || true
  ok=1
  sudo -n -u "$RU" test -e "$T10D/lower/evil.crate" && ok=0   # lower must NOT hold the write
  sudo -n -u "$RU" test -e "$T10D/upper/evil.crate" || ok=0   # write must have landed in upper
  [ "$ok" = 1 ] && pass "job write stayed in throwaway upper; shared lower unchanged" || fail "job mutated the shared lower (cache poison)"
else
  skip "T10 overlay could not mount (fuse-overlayfs unavailable)"
fi
sudo -n -u "$RU" rm -rf "$T10D" 2>/dev/null || true
# Defense-in-depth: the hook STRIPS a workflow-declared raw-cache mount so a fork
# PR cannot bind the lower read-write itself (drives the installed hook via node).
HOOK=${LIVESPEC_SANITIZE_HOOK:-/home/$RU/actions-runner/container-hooks/sanitize-hook.js}
CACHE_ROOT=${LIVESPEC_HOOK_CACHE_ROOT:-/var/cache/ci-runner}
NODE=$(command -v node || true)
if [ -n "$NODE" ] && [ -f "$HOOK" ]; then
  fp="{\"command\":\"prepare_job\",\"args\":{\"container\":{\"image\":\"x\",\"userMountVolumes\":[{\"sourceVolumePath\":\"${CACHE_ROOT}/foo/cargo\",\"targetVolumePath\":\"/evil\",\"readOnly\":false}],\"environmentVariables\":{}}}}"
  out=$(printf '%s\n' "$fp" | LIVESPEC_HOOK_TEST_MODE=1 "$NODE" "$HOOK" 2>/dev/null || echo '{}')
  echo "$out" | grep -q "${CACHE_ROOT}/foo/cargo" \
    && fail "hook did not strip a forged raw-cache mount" \
    || pass "hook strips a forged raw-cache mount"
else
  skip "T10 forged-mount strip check (no node or hook not installed)"
fi

echo "== T11: runner-agent material unreachable from a job (PID/user ns) =="
# job container is private PID ns: cannot see an arbitrary host PID
HPID=$$   # a host PID guaranteed to exist
"${POD[@]}" run --rm -e HPID="$HPID" "$IMG" bash -c '
[ -e "/proc/$HPID" ] && { echo "host PID visible"; exit 1; }
find / -xdev -maxdepth 6 \( -name .credentials -o -name .jitconfig -o -name .runner \) 2>/dev/null | grep -q . && exit 1
exit 0' 2>/dev/null && pass "agent PID ns-isolated; no runner creds in job fs" || fail "agent/job separation breach"

echo
echo "== SUMMARY: $P pass, $F fail, $S skip =="
[ "$F" -eq 0 ]
