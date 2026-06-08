# Frozen pre-cutover plaintext store

This repo (`livespec-dev-tooling`) cut over from the plaintext JSONL
work-item store (`livespec-impl-plaintext`) to the beads-on-Dolt
impl-plugin (`livespec-impl-beads`) in the PR that introduced this
directory, as part of epic work-item **li-ws2iv4** ("Phase 5 — Flip each
repo's `.livespec.jsonc` to livespec-impl-beads; archive/freeze plaintext
store").

After the cutover, this repo's own impl tracking lives in a per-repo
beads/Dolt **tenant** database on the shared dolt-server. The tenant
identity is the load-bearing rule `tenant == prefix == database ==
server_user == "livespec-dev-tooling"`; the connection block lives in
the repo-root `.livespec.jsonc` under the `livespec-impl-beads` key
(`.beads/config.yaml` carries the matching `dolt.*` connection keys).

The two files frozen here:

- `work-items.jsonl`
- `memos.jsonl`

are the **byte-for-byte pre-cutover snapshot** of the plaintext store,
retained read-only for audit and rollback. They are NOT the live store
any longer — do not read or write them as the source of truth. The
canonical work-item state is the live `livespec-dev-tooling` Dolt tenant.

## Rollback

To revert to the plaintext store, revert the flip PR: that restores
`.livespec.jsonc` to `livespec-impl-plaintext`, removes the tracked
`.beads/` config, and moves these two files back to the repo root
unchanged.
