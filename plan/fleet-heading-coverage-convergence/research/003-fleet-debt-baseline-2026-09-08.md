# Fleet heading-coverage TODO baseline — frozen 2026-09-08

This is the ratchet's seed (charter D3): the set of `test: "TODO"` rows that
existed across every governed repository when this plan was chartered. The
ratchet register (mechanism child 1) is generated FROM the live files by a
mechanical read at P1 landing time, keyed by `(repository, spec_root,
spec_file, heading)`; this document records the counts and provenance so the
generated register can be audited against a human-readable record. Counts
here are NOT status — status is read from the ledgers and the files.

## Method

Read-only survey, 2026-09-08, over every directory under `/data/projects/`
that is a git repository AND has `tests/heading-coverage.json` AND a
`.beads/config.yaml` (11 repositories). A TODO row is `test == "TODO"`. Owner
class was resolved against each repository's OWN tenant with
`bd show <id> --json` (an id absent from the tenant is NONEXISTENT; an
absent/empty/non-string `work_item` is UNOWNED).

## Before the re-home (the state the rollout found)

| repository | TODO rows | owned-OPEN | owned-CLOSED | NONEXISTENT | UNOWNED |
|---|---:|---:|---:|---:|---:|
| dolt-server | 43 | 0 | 0 | 0 | 43 |
| livespec-console-beads-fabro | 13 | 0 | 0 | 0 | 13 |
| livespec-dev-tooling | 57 | 0 | 16 | 41 | 0 |
| livespec-driver-claude | 41 | 0 | 0 | 0 | 41 |
| livespec-driver-codex | 36 | 0 | 0 | 0 | 36 |
| livespec-driver-pi | 42 | 0 | 0 | 0 | 42 |
| livespec-orchestrator-beads-fabro | 85 | 1 | 17 | 0 | 67 |
| livespec-orchestrator-git-jsonl | 25 | 0 | 0 | 0 | 25 |
| livespec-overseer | 2 | 0 | 2 | 0 | 0 |
| livespec-runtime | 22 | 0 | 22 | 0 | 0 |
| livespec (core) | 7 | 1 | 6 | 0 | 0 |
| **total** | **373** | **2** | **63** | **41** | **267** |

Closed/nonexistent owners at freeze (the ids the re-home replaced):
dev-tooling `li-ldtv03` (33, cross-tenant id filed against the wrong tenant),
`livespec-dev-tooling-3ztbdq` (8), `livespec-dev-tooling-efqeip` (8),
`livespec-s43svm.5` (6), `livespec-sab5gn` (2, cross-tenant); runtime
`livespec-runtime-x87` (22); orch-beads twelve closed `bd-ib-*` ids (17);
core `livespec-jvdvx4` (5), `livespec-hipozh` (1); overseer
`overseer-54k2za.12/.13` (2).

## After the re-home (the state this plan inherits)

Every one of the 373 rows is owned by a LIVE item as of 2026-09-08/09
(charter D8 standing owners, or the two pre-existing open owners
`livespec-sab5gn` and `bd-ib-nt3cjv`). The armed release-tier gate is green in
all 11 repositories, proven non-vacuously (reader reaches the tenant; zero
`liveness_unverified`). **Every row still says `TODO`.** That is the debt
this plan burns down.

## Distribution by spec file (runtime, as a worked example of the shape)

constraints.md 4, contracts.md 3, non-functional-requirements.md 10,
spec.md 5 — all 22 carry a reason of the "no independently testable
assertion" / "enforced by checks" family authored by `eab57b40` (2026-09-06).
Under charter D1 every one gets a real test; under D4 every such reason is
rejected once the guard lands.

## What the generated register must contain

For each repository: one entry per TODO row keyed by `(spec_root,
spec_file, heading)`, the `work_item` at freeze, and the first-seen date
(from `git log --diff-filter=A` on the row, or the freeze date when git
cannot say). The register is shrink-only: a check fails if the live file
contains a TODO row not in the register (a NEW cop-out), and passes as rows
disappear. Reaching empty in every repository is the plan's exit gate (D9).
