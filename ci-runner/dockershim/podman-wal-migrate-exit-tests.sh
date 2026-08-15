#!/usr/bin/env bash
# podman-wal-migrate-exit-tests.sh — exit tests for podman-wal-migrate.sh.
#
# Reproduces the contract podman-wal-migrate.sh must hold WITHOUT a real
# podman instance or a live host database: a real, throwaway SQLite file
# (created via python3's stdlib sqlite3 module -- present anywhere python3
# is, unlike the sqlite3 CLI, which is confirmed ABSENT on poweredge-xubuntu)
# stands in for podman's db.sql, and CI_RUNNER_WAL_MIGRATE_READ_CMD /
# CI_RUNNER_WAL_MIGRATE_SET_CMD are swapped for fakes only where a test needs
# to simulate a switch that cannot take (a concurrent transaction elsewhere)
# -- the same override pattern dockershim-exit-tests.sh and wedge-guard.sh
# use for CI_RUNNER_REAL_DOCKER / CI_RUNNER_WEDGE_PROCS_CMD.
#
# Contract under test:
#   * a fresh (rollback-journal) db is switched to journal_mode=wal, and the
#     switch is idempotent -- running again is a confirmed no-op;
#   * --check-only reports the mode and exits non-zero when it is not wal,
#     WITHOUT mutating anything;
#   * a switch attempt that keeps reporting the unchanged (non-wal) mode is
#     retried up to the configured attempt count, then exits 1 -- it never
#     reports false success;
#   * a switch that succeeds on a LATER attempt (simulating a concurrent
#     transaction clearing mid-retry) is detected and reported as success;
#   * a missing db file is treated as "nothing to migrate yet", exit 0, not
#     an error -- a freshly provisioned host has not created db.sql yet.
#
# Run anywhere with python3: ./podman-wal-migrate-exit-tests.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

pass=0
fail=0
ok()  { printf '  PASS  %s\n' "$1"; pass=$((pass + 1)); }
bad() { printf '  FAIL  %s\n' "$1"; fail=$((fail + 1)); }

# A real, throwaway SQLite db in rollback-journal mode (SQLite's on-disk
# default -- the same mode confirmed live on poweredge-xubuntu's db.sql).
make_db() {
  python3 -c '
import sqlite3, sys
con = sqlite3.connect(sys.argv[1])
con.execute("CREATE TABLE t (x INTEGER)")
con.commit()
con.close()
' "$1"
}

read_mode() {
  python3 -c '
import sqlite3, sys
con = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
print(con.execute("PRAGMA journal_mode").fetchone()[0])
con.close()
' "$1"
}

run_migrate() {
  env CI_RUNNER_PODMAN_DB="$1" \
      CI_RUNNER_WAL_MIGRATE_ATTEMPTS="${WAL_ATTEMPTS:-10}" \
      CI_RUNNER_WAL_MIGRATE_SLEEP_SECONDS=0 \
      ${WAL_SET_CMD:+CI_RUNNER_WAL_MIGRATE_SET_CMD="$WAL_SET_CMD"} \
      "$HERE/podman-wal-migrate.sh" "${@:2}"
}

# T1: fresh db starts rollback-journal (sanity check on the test fixture
# itself, not the script under test).
DB1="$TMP/t1.sql"
make_db "$DB1"
mode="$(read_mode "$DB1")"
if [ "$mode" != "wal" ]; then
  ok "T1 fixture sanity: fresh db is not wal by default (got $mode)"
else
  bad "T1 fixture sanity: fresh db is not wal by default (got $mode)"
fi

# T2: migrate switches it to wal.
run_migrate "$DB1" >"$TMP/t2.out" 2>&1
status=$?
mode="$(read_mode "$DB1")"
if [ "$status" -eq 0 ] && [ "$mode" = "wal" ]; then
  ok "T2 migrate switches a fresh db to journal_mode=wal"
else
  bad "T2 migrate switches a fresh db to journal_mode=wal (status=$status mode=$mode)"
fi

# T3: running again is an idempotent no-op that still exits 0.
run_migrate "$DB1" >"$TMP/t3.out" 2>&1
status=$?
if [ "$status" -eq 0 ] && grep -q "no-op" "$TMP/t3.out"; then
  ok "T3 migrate is idempotent on an already-wal db"
else
  bad "T3 migrate is idempotent on an already-wal db (status=$status)"
fi

# T4: --check-only exits 0 and reports wal for the now-migrated db.
run_migrate "$DB1" --check-only >"$TMP/t4.out" 2>&1
status=$?
if [ "$status" -eq 0 ] && grep -q "journal_mode=wal" "$TMP/t4.out"; then
  ok "T4 --check-only exits 0 and reports wal once migrated"
else
  bad "T4 --check-only exits 0 and reports wal once migrated (status=$status)"
fi

# T5: --check-only on a NOT-yet-migrated db exits 1, and does not mutate it.
DB5="$TMP/t5.sql"
make_db "$DB5"
run_migrate "$DB5" --check-only >"$TMP/t5.out" 2>&1
status=$?
mode="$(read_mode "$DB5")"
if [ "$status" -eq 1 ] && [ "$mode" != "wal" ]; then
  ok "T5 --check-only exits 1 on a non-wal db and never mutates it"
else
  bad "T5 --check-only exits 1 on a non-wal db and never mutates it (status=$status mode=$mode)"
fi

# T6: a missing db file is "nothing to migrate yet" -- exit 0, no error.
run_migrate "$TMP/does-not-exist.sql" >"$TMP/t6.out" 2>&1
status=$?
if [ "$status" -eq 0 ] && grep -q "nothing to migrate" "$TMP/t6.out"; then
  ok "T6 a missing db file exits 0 (nothing to migrate yet)"
else
  bad "T6 a missing db file exits 0 (nothing to migrate yet) (status=$status)"
fi

# T7: a switch that NEVER takes (fault-injected SET_CMD that always reports
# the unchanged mode, simulating a permanently-busy concurrent writer) is
# retried the configured number of times, then exits 1 -- never a false
# success.
FAKE_SET_NEVER="$TMP/fake-set-never.sh"
cat >"$FAKE_SET_NEVER" <<'EOF'
#!/usr/bin/env bash
printf 'delete\n'
EOF
chmod +x "$FAKE_SET_NEVER"
DB7="$TMP/t7.sql"
make_db "$DB7"
WAL_SET_CMD="$FAKE_SET_NEVER" WAL_ATTEMPTS=3 run_migrate "$DB7" >"$TMP/t7.out" 2>&1
status=$?
attempts_logged="$(grep -c "did not reach wal" "$TMP/t7.out")"
if [ "$status" -eq 1 ] && [ "$attempts_logged" -eq 3 ] && grep -q "FAILED" "$TMP/t7.out"; then
  ok "T7 a switch that never takes retries the configured count then exits 1"
else
  bad "T7 a switch that never takes retries the configured count then exits 1 (status=$status attempts=$attempts_logged)"
fi

# T8: a switch that succeeds on a LATER attempt (simulating a concurrent
# transaction clearing mid-retry) is detected and reported as success.
FAKE_SET_LATER="$TMP/fake-set-later.sh"
COUNTER_FILE="$TMP/t8-counter"
: >"$COUNTER_FILE"
cat >"$FAKE_SET_LATER" <<EOF
#!/usr/bin/env bash
n=\$(wc -l <"$COUNTER_FILE")
printf 'x\n' >>"$COUNTER_FILE"
if [ "\$n" -ge 2 ]; then printf 'wal\n'; else printf 'delete\n'; fi
EOF
chmod +x "$FAKE_SET_LATER"
DB8="$TMP/t8.sql"
make_db "$DB8"
WAL_SET_CMD="$FAKE_SET_LATER" WAL_ATTEMPTS=5 run_migrate "$DB8" >"$TMP/t8.out" 2>&1
status=$?
if [ "$status" -eq 0 ] && grep -q "attempt 3" "$TMP/t8.out"; then
  ok "T8 a switch that succeeds on a later attempt is detected as success"
else
  bad "T8 a switch that succeeds on a later attempt is detected as success (status=$status)"
fi

printf '\nresult: %s passed, %s failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
