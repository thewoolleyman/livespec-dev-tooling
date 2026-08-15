#!/usr/bin/env bash
# podman-wal-migrate.sh — switch podman's shared libpod SQLite state database
# from rollback-journal (SQLite's on-disk default) to WAL mode.
#
# WHY THIS EXISTS (livespec-s43svm.11)
# -------------------------------------
# All CI runner slots on a host share ONE rootless podman instance — one
# storage root, one libpod state database (see ci-runner/dockershim/docker's
# header for the shared-instance write-up). Since podman 5.x, that state
# database is SQLite by default (`database_backend=""` in containers.conf
# resolves to sqlite for any install with no pre-existing boltdb — confirmed
# via `man containers.conf` on poweredge-xubuntu, podman 5.7.0, no boltdb
# present). Every container create/start/stop/exec on every concurrently
# running job on the host writes through THIS ONE FILE:
#   ~/.local/share/containers/storage/db.sql
#
# Read live from poweredge-xubuntu 2026-08-15 (read-only PRAGMA probe, no
# mutation): `PRAGMA journal_mode` reports "delete" — SQLite's default
# ROLLBACK-JOURNAL mode, not WAL. Podman's own sqlite driver does not appear
# to request WAL explicitly (confirmed no `database_backend`/journal-mode
# knob exists in `containers.conf` — verified against the shipped man page;
# journal mode is not a podman-exposed setting at all). Under rollback-journal
# mode, ANY write transaction takes an EXCLUSIVE lock on the whole database,
# so concurrent writers (container state updates from every slot's job
# containers churning simultaneously) queue behind one another. This is a
# textbook match for two symptom families recorded on livespec-s43svm.11/.12:
#   * `Error: ... beginning transaction ...: database is locked`, dockershim
#     exit 125 -- a writer that could not acquire the exclusive lock before
#     its retry budget (podman's internal busy-wait) ran out.
#   * multi-minute "Initialize containers" / "Stop containers" hangs -- a
#     writer that eventually acquired the lock, but only after a long queue,
#     worsened by iowait (65-89% observed live on this host during a
#     contended run, per .12) since every lock handoff under rollback-journal
#     mode is also a journal-file fsync.
#
# WAL (write-ahead-log) mode is SQLite's standard fix for exactly this
# contention shape: it allows any number of concurrent READERS to proceed
# without blocking, and lets a single writer append to the WAL file instead
# of taking a whole-database exclusive lock for the journal. It does not
# eliminate write/write contention (still one writer at a time), but it
# removes the read-blocks-write and write-blocks-read stalls that dominate
# under this host's job-churn concurrency, and removes the per-transaction
# journal-file fsync that couples lock hold time to iowait.
#
# This script does NOT patch podman or change its Go source; journal_mode is
# a property PERSISTED IN THE SQLITE FILE ITSELF (unlike busy_timeout, which
# is a per-connection setting the file cannot record), so a one-time external
# `PRAGMA journal_mode=WAL;` against the file persists across every future
# podman connection, including podman's own, without any podman-side
# configuration existing or being required.
#
# STAGED APPLICATION -- see the PR body / livespec-s43svm.11 for the full
# rollout plan. This script is SAFE TO RUN AGAINST A LIVE, BUSY DATABASE: the
# underlying `PRAGMA journal_mode=WAL;` call either succeeds outright, or (if
# another connection is mid-transaction at that exact instant) leaves the
# mode UNCHANGED and reports it back truthfully -- SQLite never leaves a
# database in a partial/corrupt journal state as a side effect of a failed
# mode switch. This script retries on that specific "unchanged" outcome
# rather than treating it as success. It performs NO PODMAN OR SYSTEMD
# MUTATION and starts/stops nothing.
set -uo pipefail

# Overridable for tests and for a non-default install layout. Real default is
# the ci-runner account's podman libpod state database.
CI_RUNNER_PODMAN_DB="${CI_RUNNER_PODMAN_DB:-$HOME/.local/share/containers/storage/db.sql}"
CI_RUNNER_WAL_MIGRATE_ATTEMPTS="${CI_RUNNER_WAL_MIGRATE_ATTEMPTS:-10}"
CI_RUNNER_WAL_MIGRATE_SLEEP_SECONDS="${CI_RUNNER_WAL_MIGRATE_SLEEP_SECONDS:-3}"
# Overridable for tests: must print the DB's current journal_mode on stdout
# (lowercase, e.g. "wal" or "delete") given the db path as $1, and nothing
# else. Real default reads it via python3's stdlib sqlite3 module -- no
# sqlite3 CLI is guaranteed present (confirmed absent on poweredge-xubuntu).
CI_RUNNER_WAL_MIGRATE_READ_CMD="${CI_RUNNER_WAL_MIGRATE_READ_CMD:-_podman_wal_migrate_real_read}"
# Overridable for tests: must attempt `PRAGMA journal_mode=WAL;` against the
# db at $1 and print the RESULTING journal_mode on stdout (which is WAL only
# if the switch actually took).
CI_RUNNER_WAL_MIGRATE_SET_CMD="${CI_RUNNER_WAL_MIGRATE_SET_CMD:-_podman_wal_migrate_real_set}"

_podman_wal_migrate_real_read() {
  python3 -c '
import sqlite3, sys
db = sys.argv[1]
con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5.0)
try:
    print(con.execute("PRAGMA journal_mode").fetchone()[0])
finally:
    con.close()
' "$1"
}

_podman_wal_migrate_real_set() {
  python3 -c '
import sqlite3, sys
db = sys.argv[1]
con = sqlite3.connect(db, timeout=5.0)
try:
    print(con.execute("PRAGMA journal_mode=WAL").fetchone()[0])
finally:
    con.close()
' "$1"
}

# check_only: prints the current mode and exits 0 if "wal", exits 1 otherwise
# (for observability/alerting use -- e.g. wire into a periodic check without
# it ever mutating anything). Never mutates.
podman_wal_migrate_check() {
  local db="$1" mode
  [ -f "$db" ] || { printf 'podman-wal-migrate: no db at %s (nothing to check)\n' "$db"; return 0; }
  mode="$("$CI_RUNNER_WAL_MIGRATE_READ_CMD" "$db" 2>/dev/null)" || {
    printf 'podman-wal-migrate: could not read journal_mode from %s\n' "$db" >&2
    return 1
  }
  printf 'podman-wal-migrate: %s journal_mode=%s\n' "$db" "$mode"
  [ "$mode" = "wal" ]
}

# Idempotent migrate: no-ops if already WAL; otherwise retries the switch up
# to CI_RUNNER_WAL_MIGRATE_ATTEMPTS times (a concurrent transaction elsewhere
# can transiently prevent the switch -- SQLite reports this by returning the
# UNCHANGED mode, never by corrupting state). Exits 0 once WAL is confirmed,
# exits 1 if every attempt failed to reach it.
podman_wal_migrate_apply() {
  local db="$1" mode attempt=1
  [ -f "$db" ] || {
    printf 'podman-wal-migrate: no db at %s (nothing to migrate yet)\n' "$db"
    return 0
  }
  mode="$("$CI_RUNNER_WAL_MIGRATE_READ_CMD" "$db" 2>/dev/null)" || {
    printf 'podman-wal-migrate: could not read journal_mode from %s\n' "$db" >&2
    return 1
  }
  if [ "$mode" = "wal" ]; then
    printf 'podman-wal-migrate: %s already journal_mode=wal (no-op)\n' "$db"
    return 0
  fi
  printf 'podman-wal-migrate: %s journal_mode=%s -> attempting wal\n' "$db" "$mode"
  while [ "$attempt" -le "$CI_RUNNER_WAL_MIGRATE_ATTEMPTS" ]; do
    mode="$("$CI_RUNNER_WAL_MIGRATE_SET_CMD" "$db" 2>/dev/null)" || mode=""
    if [ "$mode" = "wal" ]; then
      printf 'podman-wal-migrate: %s switched to journal_mode=wal (attempt %s)\n' "$db" "$attempt"
      return 0
    fi
    printf 'podman-wal-migrate: attempt %s/%s did not reach wal (got %s) -- retrying in %ss\n' \
      "$attempt" "$CI_RUNNER_WAL_MIGRATE_ATTEMPTS" "${mode:-<none>}" "$CI_RUNNER_WAL_MIGRATE_SLEEP_SECONDS" >&2
    attempt=$((attempt + 1))
    sleep "$CI_RUNNER_WAL_MIGRATE_SLEEP_SECONDS"
  done
  printf 'podman-wal-migrate: FAILED to reach journal_mode=wal on %s after %s attempts (last seen: %s)\n' \
    "$db" "$CI_RUNNER_WAL_MIGRATE_ATTEMPTS" "${mode:-<none>}" >&2
  return 1
}

if [ "${1:-}" = "--check-only" ]; then
  podman_wal_migrate_check "$CI_RUNNER_PODMAN_DB"
  exit $?
fi

podman_wal_migrate_apply "$CI_RUNNER_PODMAN_DB"
exit $?
