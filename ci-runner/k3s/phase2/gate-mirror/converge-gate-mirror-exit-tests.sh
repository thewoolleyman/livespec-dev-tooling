#!/usr/bin/env bash
# converge-gate-mirror-exit-tests.sh — prove the gate mirror's two load-bearing
# behaviours, and its read-only posture, WITHOUT touching any host:
#
#   A. ./ensure-gate-mirror.sh is IDEMPOTENT — a second run against an
#      already-created mirror changes nothing and, in particular, keeps the refs
#      of the gates in flight; and it REFUSES /var/lib/git, the packaged
#      git-daemon base path on the root volume that this unit exists not to use;
#   B. ./prune-gate-refs.sh's CUTOFF IS ONE DAY with no flag given — a ref a
#      minute past a day is deleted and a ref a minute short of one is kept —
#      it touches nothing outside `refs/gates/`, it honours an explicit cutoff,
#      it deletes nothing under --dry-run, and it ages a hand-packed ref by
#      committer date and says so;
#   C. ./gate-mirror.yaml serves the mirror READ-ONLY with export-all OFF;
#   D. the tailnet-ACL grant the receive path needs is NAMED, and no ACL is
#      edited in this repository.
#
# HOW IT STAYS OFF THE HOST. Every case operates on scratch git repositories
# under one `mktemp -d`, created by this suite. The converge itself is only ever
# run with `--dry-run`, which by construction executes nothing — no mirror is
# created and no cluster is contacted — and on top of that the dry runs are
# given a scratch PATH of TRIPWIRES for every tool the converge would mutate
# with (`kubectl`, `findmnt`, `install`), which case A asserts stayed empty.
# The suite never runs as root and never needs to.
#
# Exit 0 iff every test passes. Mutates nothing outside its own scratch dir.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${HERE}/../../../.." && pwd)"
ENSURE="${HERE}/ensure-gate-mirror.sh"
PRUNE="${HERE}/prune-gate-refs.sh"
CONVERGE="${HERE}/converge-gate-mirror.sh"
MANIFEST="${HERE}/gate-mirror.yaml"
README="${HERE}/README.md"
DAY=86400

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

# A committer identity of this suite's own, so no case depends on whatever
# git identity the machine running it happens to carry.
export GIT_AUTHOR_NAME="gate mirror exit tests" GIT_AUTHOR_EMAIL="exit-tests@invalid"
export GIT_COMMITTER_NAME="gate mirror exit tests" GIT_COMMITTER_EMAIL="exit-tests@invalid"

TRIPWIRE="${TMPROOT}/tripwire"
: > "$TRIPWIRE"
export TRIPWIRE

FAKEBIN="${TMPROOT}/fakebin"
mkdir -p "$FAKEBIN"
for tool in kubectl findmnt install; do
  # Single-quoted on purpose: the body is the FAKE's source, expanded when the
  # fake runs, not when this suite writes it.
  printf '#!/usr/bin/env bash\nprintf "%%s %%s\\n" "$(basename "$0")" "$*" >> "$TRIPWIRE"; exit 0\n' \
    > "${FAKEBIN}/${tool}"
  chmod +x "${FAKEBIN}/${tool}"
done

NOW="$(date +%s)"

# snapshot MIRROR -> a stable description of the mirror's tree: every path with
# its mode, plus every ref with the object it points at. This is what
# "idempotent" has to mean for a directory that survives a boot.
snapshot() {
  ( cd "$1" && find . -printf '%M %P\n' | sort )
  git --git-dir="$1" for-each-ref --format='ref %(refname) %(objectname)'
  git --git-dir="$1" config --list | sort
}

# seed_ref MIRROR REF [COMMITTER_DATE] — push one commit into the mirror at REF.
seed_ref() {
  local mirror="$1" ref="$2" when="${3:-}" src
  src="$(mktemp -d "${TMPROOT}/src.XXXXXX")"
  git init -q -b main "$src"
  printf '%s\n' "$ref" > "${src}/tree-content"
  git -C "$src" add tree-content
  if [ -n "$when" ]; then
    GIT_COMMITTER_DATE="$when" GIT_AUTHOR_DATE="$when" git -C "$src" commit -q -m "gate ${ref}"
  else
    git -C "$src" commit -q -m "gate ${ref}"
  fi
  git -C "$src" push -q "$mirror" "HEAD:${ref}"
}

# age_ref MIRROR REF SECONDS — backdate the LOOSE ref file to SECONDS ago,
# which is how the sweep reads the instant the driver host pushed it.
age_ref() {
  touch -d "@$(( NOW - $3 ))" "$1/$2"
}

refs_of() { git --git-dir="$1" for-each-ref --format='%(refname)' | sort; }

# ---------------------------------------------------------------------------
printf '== A. the mirror is created idempotently, on the tier and never in /var/lib/git ==\n'
# ---------------------------------------------------------------------------
MIRROR="${TMPROOT}/gate-mirror.git"

OUT="$("$ENSURE" "$MIRROR" 2>&1)"; RC=$?
if [ "$RC" -eq 0 ]; then ok "first run exits 0"; else no "first run exits 0 (got ${RC})"; printf '%s\n' "$OUT"; fi

if [ "$(git --git-dir="$MIRROR" rev-parse --is-bare-repository 2>/dev/null)" = true ]; then
  ok "the mirror is a BARE repository"
else
  no "the mirror is a BARE repository"
fi
if [ -f "${MIRROR}/git-daemon-export-ok" ]; then
  ok "the git-daemon-export-ok marker is written (the daemon serves no repository without it)"
else
  no "the git-daemon-export-ok marker is written"
fi
# gc off is not cosmetic: `git gc --auto` packs refs, and a packed ref has no
# per-ref mtime, which is the only per-push timestamp the sweep has.
for key_expected in "gc.auto=0" "receive.autogc=false" "core.logAllRefUpdates=true" "receive.denyDeletes=false"; do
  key="${key_expected%%=*}"; expected="${key_expected#*=}"
  actual="$(git --git-dir="$MIRROR" config --get "$key")"
  if [ "$actual" = "$expected" ]; then
    ok "config ${key} is ${expected}"
  else
    no "config ${key} is ${expected} (got '${actual}')"
  fi
done

# A ref pushed between the two runs stands in for a gate in flight: an
# "idempotent" re-create that threw it away would be the worst kind of pass.
seed_ref "$MIRROR" refs/gates/inflight
BEFORE="$(snapshot "$MIRROR")"
OUT="$("$ENSURE" "$MIRROR" 2>&1)"; RC=$?
AFTER="$(snapshot "$MIRROR")"
if [ "$RC" -eq 0 ]; then ok "second run exits 0"; else no "second run exits 0 (got ${RC})"; printf '%s\n' "$OUT"; fi
if [ "$BEFORE" = "$AFTER" ]; then
  ok "second run leaves the mirror byte-identical (paths, modes, refs, config)"
else
  no "second run leaves the mirror byte-identical (paths, modes, refs, config)"
  diff <(printf '%s\n' "$BEFORE") <(printf '%s\n' "$AFTER") || true
fi
if git --git-dir="$MIRROR" rev-parse --verify -q refs/gates/inflight >/dev/null; then
  ok "the in-flight gate ref survives the second run"
else
  no "the in-flight gate ref survives the second run"
fi

# The correction this slice exists to honour, asserted as a refusal rather than
# as a comment: /var/lib/git belongs to the git package and is on the root
# volume, so it is not somewhere this mirror may be created even by mistake.
OUT="$("$ENSURE" /var/lib/git/gate-mirror.git 2>&1)"; RC=$?
if [ "$RC" -ne 0 ] && printf '%s' "$OUT" | grep -q '/var/lib/git'; then
  ok "a mirror under /var/lib/git is refused, naming the path"
else
  no "a mirror under /var/lib/git is refused, naming the path (rc=${RC}: ${OUT})"
fi

# And the converge's own PLAN puts the mirror on the ci-cache tier, with no
# /var/lib/git path anywhere in it.
PLAN="$(PATH="${FAKEBIN}:${PATH}" "$CONVERGE" --dry-run 2>&1)"; RC=$?
if [ "$RC" -eq 0 ]; then ok "the converge --dry-run exits 0"; else no "the converge --dry-run exits 0 (got ${RC})"; printf '%s\n' "$PLAN"; fi
if printf '%s\n' "$PLAN" | grep -q '/var/cache/ci-runner/gate-mirror.git'; then
  ok "the converge plans the mirror on the ci-cache tier"
else
  no "the converge plans the mirror on the ci-cache tier"
fi
if printf '%s\n' "$PLAN" | grep -q '/var/lib/git'; then
  no "the converge plan names no /var/lib/git path"
else
  ok "the converge plan names no /var/lib/git path"
fi
if printf '%s\n' "$PLAN" | grep -q 'would require /var/cache/ci-runner to be a mountpoint'; then
  ok "the converge pre-gates on the tier being mounted"
else
  no "the converge pre-gates on the tier being mounted"
fi
if [ -s "$TRIPWIRE" ]; then
  no "the converge --dry-run executed no host- or cluster-mutating command"
  cat "$TRIPWIRE"
else
  ok "the converge --dry-run executed no host- or cluster-mutating command"
fi

# ---------------------------------------------------------------------------
printf '\n== B. the sweep prunes refs/gates/* past a one-day cutoff ==\n'
# ---------------------------------------------------------------------------
SWEPT="${TMPROOT}/swept.git"
"$ENSURE" "$SWEPT" >/dev/null 2>&1
seed_ref "$SWEPT" refs/gates/stale
seed_ref "$SWEPT" refs/gates/fresh
seed_ref "$SWEPT" refs/heads/master
# One minute either side of the cutoff. THE CUTOFF IS ASSERTED WITH NO FLAG
# GIVEN: the default is the contract, and a default that drifted to an hour or
# a week would still pass a test that always passed --max-age-seconds.
age_ref "$SWEPT" refs/gates/stale $(( DAY + 60 ))
age_ref "$SWEPT" refs/gates/fresh $(( DAY - 60 ))
age_ref "$SWEPT" refs/heads/master $(( DAY * 30 ))

OUT="$("$PRUNE" --dry-run "$SWEPT" 2>&1)"; RC=$?
if [ "$RC" -eq 0 ] && [ "$(refs_of "$SWEPT")" = "$(printf 'refs/gates/fresh\nrefs/gates/stale\nrefs/heads/master')" ]; then
  ok "--dry-run deletes nothing"
else
  no "--dry-run deletes nothing (rc=${RC})"
  printf '%s\n' "$OUT"
fi
if printf '%s\n' "$OUT" | grep -q 'would delete refs/gates/stale'; then
  ok "--dry-run names the ref it would delete"
else
  no "--dry-run names the ref it would delete"
fi

OUT="$("$PRUNE" "$SWEPT" 2>&1)"; RC=$?
if [ "$RC" -eq 0 ]; then ok "the sweep exits 0"; else no "the sweep exits 0 (got ${RC})"; printf '%s\n' "$OUT"; fi
if git --git-dir="$SWEPT" rev-parse --verify -q refs/gates/stale >/dev/null; then
  no "a gate ref one minute PAST one day is deleted"
else
  ok "a gate ref one minute PAST one day is deleted"
fi
if git --git-dir="$SWEPT" rev-parse --verify -q refs/gates/fresh >/dev/null; then
  ok "a gate ref one minute SHORT of one day is kept"
else
  no "a gate ref one minute SHORT of one day is kept"
fi
# refs/heads/master is thirty days old and must be untouched: this sweep owns
# refs/gates/ and nothing else in the mirror.
if git --git-dir="$SWEPT" rev-parse --verify -q refs/heads/master >/dev/null; then
  ok "a ref outside refs/gates/ is never swept, however old"
else
  no "a ref outside refs/gates/ is never swept, however old"
fi

# An explicit cutoff is honoured, which is also the control proving the day
# above came from the default rather than from the ages happening to line up.
OUT="$("$PRUNE" --max-age-seconds 30 "$SWEPT" 2>&1)"; RC=$?
if [ "$RC" -eq 0 ] && ! git --git-dir="$SWEPT" rev-parse --verify -q refs/gates/fresh >/dev/null; then
  ok "--max-age-seconds 30 sweeps the ref the one-day default kept"
else
  no "--max-age-seconds 30 sweeps the ref the one-day default kept (rc=${RC})"
  printf '%s\n' "$OUT"
fi
OUT="$("$PRUNE" --max-age-seconds nope "$SWEPT" 2>&1)"; RC=$?
if [ "$RC" -ne 0 ] && printf '%s' "$OUT" | grep -q 'whole number of seconds'; then
  ok "a non-numeric --max-age-seconds is refused rather than silently taken as 0"
else
  no "a non-numeric --max-age-seconds is refused rather than silently taken as 0 (rc=${RC})"
fi

# The fallback path: a hand-packed mirror has no loose ref file and therefore no
# push timestamp, so the sweep ages the ref by its committer date and REPORTS
# that it did (the fallback judges a ref older than it really is, so it must
# never be silent).
PACKED="${TMPROOT}/packed.git"
"$ENSURE" "$PACKED" >/dev/null 2>&1
seed_ref "$PACKED" refs/gates/old "@$(( NOW - DAY * 2 ))"
seed_ref "$PACKED" refs/gates/new "@$(( NOW - 3600 ))"
git --git-dir="$PACKED" pack-refs --all
OUT="$("$PRUNE" "$PACKED" 2>&1)"; RC=$?
if [ "$RC" -eq 0 ] && [ "$(refs_of "$PACKED")" = "refs/gates/new" ]; then
  ok "a packed ref is aged by committer date: the two-day one goes, the one-hour one stays"
else
  no "a packed ref is aged by committer date (rc=${RC})"
  printf '%s\n' "$OUT"
fi
if printf '%s\n' "$OUT" | grep -q 'FALLBACK refs/gates/old'; then
  ok "the committer-date fallback is reported, never silent"
else
  no "the committer-date fallback is reported, never silent"
fi

# ---------------------------------------------------------------------------
printf '\n== C. the daemon serves the mirror read-only, with export-all off ==\n'
# ---------------------------------------------------------------------------
# Read the manifest with its COMMENTS STRIPPED for every posture assertion
# below: the header explains at length why `--export-all` is absent, and a
# file-wide grep would fail on the explanation while a manifest that actually
# passed the flag in a comment-free line would pass.
DIRECTIVES="${TMPROOT}/gate-mirror.directives.yaml"
grep -v '^[[:space:]]*#' "$MANIFEST" > "$DIRECTIVES"

if grep -q -- '--export-all' "$DIRECTIVES"; then
  no "the manifest passes no --export-all (only a marked repository is served)"
else
  ok "the manifest passes no --export-all (only a marked repository is served)"
fi
for flag in '--disable=receive-pack' '--disable=upload-archive' \
            '--forbid-override=receive-pack' '--forbid-override=upload-archive'; do
  if grep -qF -- "$flag" "$DIRECTIVES"; then
    ok "the daemon is started with ${flag}"
  else
    no "the daemon is started with ${flag}"
  fi
done
# The daemon's own mount of the mirror is read-only; the sweep's is not, and
# must not be, so this asserts the daemon's specifically.
if awk '/name: gate-mirror-daemon/,/kind: Service/' "$DIRECTIVES" \
     | grep -A2 'mountPath: /srv/gate-mirror.git' | grep -q 'readOnly: true'; then
  ok "the daemon mounts the mirror readOnly"
else
  no "the daemon mounts the mirror readOnly"
fi
if grep -q 'type: DirectoryOrCreate' "$DIRECTIVES"; then
  no "the mirror hostPath is type Directory, not DirectoryOrCreate (an empty auto-created dir serves nothing while looking healthy)"
else
  ok "the mirror hostPath is type Directory, not DirectoryOrCreate (an empty auto-created dir serves nothing while looking healthy)"
fi
if grep -q 'path: /var/cache/ci-runner/gate-mirror.git' "$DIRECTIVES"; then
  ok "the hostPath is the mirror on the ci-cache tier"
else
  no "the hostPath is the mirror on the ci-cache tier"
fi

# ---------------------------------------------------------------------------
printf '\n== D. the tailnet-ACL grant is named here and edited nowhere here ==\n'
# ---------------------------------------------------------------------------
for phrase in 'tailscale-admin' 'refs/gates/' 'cwoolley' 'tcp:22' '"action": "accept"'; do
  if grep -qF -- "$phrase" "$README"; then
    ok "the receive path documents '${phrase}'"
  else
    no "the receive path documents '${phrase}'"
  fi
done
# The grant is NAMED, not COPIED: this repository holds no tailnet policy file,
# so there is nothing here for a well-meaning edit to change out from under the
# repository that owns it.
POLICY_FILES="$(git -C "$REPO_ROOT" ls-files -- '*policy.hujson' '*acl.hujson' '*tailscale*.json' '*tailscale*.hujson')"
if [ -z "$POLICY_FILES" ]; then
  ok "this repository carries no tailnet policy file to edit"
else
  no "this repository carries a tailnet policy file: ${POLICY_FILES}"
fi

# ---------------------------------------------------------------------------
printf '\n%s passed, %s failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
