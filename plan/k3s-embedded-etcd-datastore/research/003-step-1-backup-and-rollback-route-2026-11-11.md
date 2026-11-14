# 003 — Step 1: the committed datastore backup, and the rollback route (2026-11-11)

Ownership: on 2026-11-11 legacy-coordinator-agent assigned execution of this plan to the kubernetes-observability seat, after the maintainer approved the plan. That seat holds the plan's live evidence: lease losses #4 (2026-11-10T14:20Z) and #5 (2026-11-11T02:31Z). Both were kine post-compaction `PRAGMA wal_checkpoint(FULL)` stalls of 30.0s and 25.3s, recorded on epic livespec-dev-tooling-qql3lo.

The coordinator's constraints for this plan:
- the first step is a committed, read-back backup of the current kine/SQLite state plus a written rollback route;
- the etcd cut-over happens only in a factory-quiet window;
- no hand writes on the host;
- each step goes to the coordinator before any apply.

## What the datastore is today (read 2026-11-11 ~05:50Z)

- `/var/lib/rancher/k3s/server/db` on poweredge-xubuntu is a 2 GB tmpfs. It holds `state.db` (263 MB) and `state.db-wal` (104 MB).
- k3s is v1.36.2+k3s1, and `/usr/bin/sqlite3` is present.
- The server token, `cred/` and `tls/` live on the root disk under `/var/lib/rancher/k3s/server`, not on the tmpfs.
- The datastore is VOLATILE by design. Every boot starts from an empty tmpfs, and `converge-ci-stack.service` rebuilds the cluster from committed source (note 000, "Constraints learned on the archived plan").

## Step 1 — `ansible/k3s-datastore-backup.yml`

The playbook has three actions, each behind its own confirmation variable naming the host:

- **backup** (`k3s_datastore_backup_confirm`)
  - Takes an online `sqlite3 .backup` of `state.db`, plus a tarball of `token`, `cred/` and `tls/`.
  - Writes both into a new 0700 set under `/var/backups/k3s-datastore/<UTC>`.
  - The run FAILS unless the read-back passes: `PRAGMA integrity_check` returns `ok`; the copy's max(`kine.id`) lies between the live max(id) read just before and just after the backup; and the set's sha256 manifest re-verifies.
  - The same run keeps the newest 3 sets and prunes older ones.
  - Output carries set names, file names and sha256 values only.
- **stop** (`k3s_datastore_stop_confirm`)
  - Stops `k3s.service` and does nothing else.
  - It exists because the restore refuses while k3s runs, and no other committed path stops the server unit.
  - Restricted by coordinator ruling (2026-11-11): stopping the k3s server stops the whole control plane, so `stop` runs only as part of a DECLARED ROLLBACK inside a factory-quiet window. The board must first be drained by legacy-dispatcher-agent, and live runs cancelled through the factory server's `POST /api/v1/runs/{id}/cancel` per `.ai/factory-restart-cancels-runs.md`. It is never a routine operation.
- **restore** (`k3s_datastore_restore_confirm` plus `k3s_datastore_restore_set`)
  - Refuses unless all of these hold: k3s is inactive; the datastore dir is on its tmpfs; no `etcd/` dir is present; and the set's manifest verifies.
  - Only then does it copy `state.db` into the tmpfs, drop the stale `-wal`/`-shm`, check the copied file's sha256 against the manifest, and start k3s.

A run that confirms more than one action is refused.

## Step 2's shape: an in-place conversion

The k3s documentation states the conversion directly. From k3s-io/docs `docs/datastore/ha-embedded.md`, §"Existing single-node clusters", at commit 2936f00759b3c639bdf98797797018514f1ba4ad (last edited 2026-07-24):

> If you have an existing cluster using the default embedded SQLite database, you can convert it to etcd by simply restarting your K3s server with the `--cluster-init` flag. Once you've done that, you'll be able to add additional instances as described above.

The same page continues:

> If an etcd datastore is found on disk either because that node has either initialized or joined a cluster already, the datastore arguments (`--cluster-init`, `--server`, `--datastore-endpoint`, etc) are ignored.

The k3s docs are not versioned per release. That page is the current text, which is the text for v1.36. Step 2 is therefore planned as an in-place conversion:
- one committed change adds `cluster-init: true` and the etcd maintenance keys (assertion 2) to the committed k3s `config.yaml`;
- it is applied by `ansible/ci-pool.yml` in a factory-quiet window;
- the window plan goes back to the coordinator before any apply.

If the conversion does not take on the live server, step 2 falls back to a rebuild-from-empty cut-over (below).

## The rollback route

1. **Primary: revert and reboot.**
   - Revert the step-2 commit and apply `ansible/ci-pool.yml`, then reboot through `just ansible-apply ansible/reboot-ci-server.yml -e ci_server_reboot_confirm=poweredge-xubuntu`.
   - The etcd data dir (`db/etcd`) lives on the same tmpfs, so the boot comes up with no etcd files. k3s selects SQLite, and `converge-ci-stack.service` rebuilds the cluster from committed source. That is the unattended recovery the archived k3s-on-gmktec plan already proved (its assertion 2).
   - The empty tmpfs is also what makes the revert clean: k3s will not fall back to SQLite while an `etcd/` dir exists (the second quoted sentence).
2. **Secondary: restore the step-1 set.** This is a declared rollback, so it runs inside a factory-quiet window (see `stop` above).
   - For the case where a rebuild from empty is not acceptable, run the playbook's `stop` action, then its `restore` action with the newest verified set.
   - The restore refuses while any `etcd/` dir is present. After a cut-over, therefore, it runs only after the reboot in route 1 has emptied the tmpfs.

## Open before step 2

- Take the first backup set and post its manifest and read-back on epic qql3lo.
- Write the factory-quiet window plan: legacy-dispatcher-agent drains the board, live runs are cancelled through `POST /api/v1/runs/{id}/cancel` and re-dispatched at once per `.ai/factory-restart-cancels-runs.md`, then the apply and verify. It goes to the coordinator, who coordinates the drain.
- Note 002's kine-vs-scheduling measurement rides with step 2's before-and-after read of control-plane stability.
