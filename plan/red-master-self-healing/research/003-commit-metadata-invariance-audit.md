# 003 — Commit-metadata invariance audit and repair (child B, livespec-dev-tooling-yfqvqm)

Audited 2026-10-15 against `master` at `04df2dc9`. This note is the record charter design item 1 asks for: every fleet check
that reads commit metadata, the field it reads, and its repair or the work item that carries the repair. One defect was found
and it was already repaired; the rest of the inventory reads only fields a rebase-merge preserves. The forward guard is
`tests/spec/test_commit_metadata_invariance.py`.

Child A (livespec-dev-tooling-4v2yrw) carries the spec rule in livespec; this note carries the measurement.

## What a rebase-merge actually rewrites

The invariance question has an exact answer, and the whole audit rests on it. GitHub's rebase-merge replays each commit onto
the target branch, minting a NEW commit object. It REWRITES:

- the commit SHA (new parent, so a new object even when the tree is byte-identical),
- the committer date, re-stamped to the merge instant,
- the committer timezone, taken from the merging account rather than the author's clock,
- the committer identity, which becomes the forge's web-flow account.

It PRESERVES the tree, the commit message (subject, body and trailers), and the author identity and author date. The
2026-10-14 incident is the first list meeting a check that read from it: PR #2917's commits carried `2026-10-14T00:44:17Z`, the
rebase-merge re-stamped the unchanged tree under a Pacific offset, and a `%cs` read turned that instant into `2026-10-13` —
convicting master on the date the PR had just certified. See charter §"The triggering incident".

So "invariant" has a mechanical test: a check is invariant if its verdict is a function only of the preserved list.

## Method

- **Primary scan — this repository, exhaustively.** Every `.py` under `livespec_dev_tooling/` (minus `_vendor` and
  `__pycache__`) was read for git invocations and for date handling: the pretty-format placeholders (`%c*`, `%a*`, `%H`, `%h`,
  `%B`, `%s`, `%(trailers)`), the subcommands (`log`, `show`, `rev-list`, `rev-parse`, `for-each-ref`), the committer-date log
  filters (`--since`, `--until`, `--before`, `--after`), `GIT_COMMITTER_*`, and the Python date surfaces (`datetime.now`,
  `fromisoformat`, `astimezone`, `strftime`). This repository is the right primary scope because it is where the shared check
  inventory LIVES — every consumer runs these modules from the pinned wheel, so a repair here is the fleet's repair.
- **Secondary scan — the other fleet repos, read-only.** `gh search code --owner thewoolleyman` for each volatile placeholder
  and for `GIT_COMMITTER_DATE`. Nothing was cloned, read for write, or changed. Limit recorded honestly: code search is an
  INDEX, so a very recent commit may not be in it, and the installation token could not read `contents` for the sibling repos.
  The exposure this leaves is small and bounded — a consumer's REPO-PRIVATE check is the only surface the primary scan does not
  cover, and the search found no such check reading a volatile field.
- **Verification of the scan itself.** The guard was run against the PRE-REPAIR tree (`0dd5a62d^`'s
  `heading_coverage_debt.py`, carrying `--format=%H %cs`) and it FAILED, naming the read. A detector that convicts the one
  historical defect is worth more than one that merely passes over today's clean tree.

## The inventory

Every commit-metadata read in the shipped package. Reads are cited by module and by the argv they issue rather than by line
number, so the row survives the next edit above it.

| Module | Check target | Field read | Invariant? | Repair / carrier |
| --- | --- | --- | --- | --- |
| `heading_coverage_debt` | `check-heading-coverage-debt-register`, `check-heading-coverage` | `--format=%H %cI` (was `%cs`) | YES, after repair | **livespec-dev-tooling-a6gq5n**, plan `fleet-heading-coverage-convergence` (epic `-0bse`); landed in `0dd5a62d`. A cross-plan carrier: not re-fixed here. |
| `heading_coverage_debt` | same | `%H`, used only as the revision a `git show <rev>:<path>` blob read addresses | YES — the verdict rests on blob bytes, not on the SHA value | none needed |
| `heading_coverage_debt` | same | `git show <rev>` / `git show <rev>:<path>` | YES — tree content | none needed |
| `checks/red_green_replay` | `check-red-green-replay` | `log -1 --format=%B <sha>`; `rev-list --no-merges origin/master..HEAD` | YES — the message is preserved, and a range is topology rather than metadata | none needed |
| `checks/_red_green_replay_trailers` | `check-red-green-replay` | `log -1 --format=%B`; `log -1 --pretty=%(trailers:…)`; `rev-parse HEAD` | YES — trailers ride the preserved message; the `rev-parse` names HEAD, it does not judge it | none needed |
| `checks/_red_green_replay_revert` | `check-red-green-replay` | `log -1 --format=%B <sha>`; `rev-list --parents -n 1 <sha>`; the commit's OpenPGP signature; per-path blob byte-identity | YES — and deliberately so: the exemption keys on the forge signature plus content identity. The `This reverts commit <sha>` SHA is a lookup HINT with no authority. | none needed |
| `checks/commit_pairs_source_and_test` | `check-commit-pairs-source-and-test` | `log -1 --format=%B` | YES | none needed |
| `checks/_docs_only_change` | `check-check-coverage-incremental`, `check-commit-pairs-source-and-test` | `git show <ref>:<path>` | YES — blob content | none needed |
| `checks/no_todo_registry` | `check-no-todo-registry` | `git show HEAD:<path>` | YES — blob content | none needed |
| `checks/master_ci_green` | `check-master-ci-green` | master's newest CI conclusion, via `gh`, addressed from the gate repository | YES — it reads the state of the BRANCH, never a field of the commit under test. A replay cannot change this check's answer, because this check never looks at the replay. | none needed |
| `_shipped_path_release_guard_range` | `check-shipped-path-release-guard` | `log -1 --format=%B <sha>`; `show --no-commit-id --name-only --format= <sha>`; `rev-list --reverse --no-merges <base>..HEAD` | YES — message, changed paths and range topology | none needed |
| `workflow_checks/no_stale_revise_branches` | revise-workflow check (not in the `just check` aggregate) | `log -1 --format=%s <branch>`; `rev-parse --short <branch>`; `for-each-ref --format=%(refname:short)` | YES — the subject is preserved, and the short SHA is DISPLAY only. Landed-ness is judged by patch-id equivalence, which v060 adopted precisely because a rebase-merge rewrites commits. | none needed |
| `workflow_checks/release_bump_classification` | release-workflow check | `log --format=%s%x00%b <tag>..HEAD`; `show <rev>:<path>` | YES — subject, body and blob | none needed |
| `fleet/git_identity_audit`, `fleet/_git_identity_host_canary` | `check-fleet-conformance` | `show -s --format=%an%x00%ae` | YES — AUTHOR identity, which a rebase-merge preserves. Reading `%cn`/`%ce` here would NOT be invariant; it does not. | none needed |
| `green_token`, `gate_remote_delegate` | gate transport (`just gate-start` / delegated gate) | `rev-parse HEAD^{tree}` | YES, and it is the model the rest of the inventory should be read against: the gate's identity is the TREE, so a re-stamped commit over identical content resolves to the same token. | none needed |
| `otel_cargo_phase`, `agent_hooks/subagent_stop_guard` | not checks (telemetry span attribute; a Stop-hook guard) | `rev-parse HEAD`; `rev-list --count` ranges | YES — a span label and two unpushed-commit counts; neither contributes to a check verdict | none needed |

### Two false positives, recorded because they cost a cycle

`%H` and `%h` are the commit SHA in git and the hour and abbreviated month in `strftime`. The first draft of the guard read
them everywhere and convicted four `strftime("%Y-%m-%dT%H:%M:%SZ")` timestamps in `vendor_update` and
`checks/_red_green_replay_modes` — reads that touch no commit. The guard now reads the SHA tier only inside a literal that is a
git pretty-format spec, and asserts the collision in both directions so the narrowing cannot silently widen back.

### The other fleet repos

One read surfaced, and it is out of scope on examination: livespec-orchestrator-beads-fabro's
`tests/livespec_orchestrator_beads_fabro/commands/test_dispatcher_git_author.py` reads `--format=%an <%ae>|%cn <%ce>`. It is a
unit test asserting that the DISPATCHER set the operator identity on a commit the test itself just created in a temporary
repository; it never reads a rebase-merge replay, so no verdict of it can move with merge metadata. The `GIT_COMMITTER_DATE`
hits in livespec and livespec-overseer are test fixtures SETTING the variable, not checks reading it.

## Outcome

- **Checks reading a rebase-merge-volatile field in a verdict-bearing way: one, and it was already repaired.** a6gq5n is both
  the first instance and the only instance. No second repair was needed, so this child ships the audit and the forward guard
  rather than a fix.
- **The property now holds by construction, not by inspection.** `tests/spec/test_commit_metadata_invariance.py` asserts it
  over the whole shipped package: no timezone-rendered committer date or committer identity anywhere, no committer-date log
  filter anywhere, and every instant-exact or SHA read declared with the argument for why a replay cannot move its verdict. The
  registry is asserted in both directions, so a declaration whose read is gone fails too and the list cannot rot into an
  unexamined exemption.
- **Why the walk set is the package rather than `checks/`.** The read that reddened master did not live in `checks/` — it lived
  in the top-level `heading_coverage_debt` that `checks/heading_coverage_debt_register` reaches through. A scan scoped to the
  canonical check directory would have acquitted the one defect it exists to convict.
- **Why no new check target.** A module under `livespec_dev_tooling/checks/` becomes a canonical slug by filesystem
  derivation, and a canonical slug obliges EVERY consumer to wire it into `just check` and its CI matrix — arming a check ahead
  of adoption, the failure mode `46c5dab` paid for by reddening five repos. A repo-private target would instead need a CI job,
  which a factory branch may not add. The guard is therefore a test in the suite `just check` already runs, in the
  `tests/spec/` tree whose charter is exactly this: the gates a change to this repository must satisfy.

### Residual risk

The guard reads string literals in the AST. It is blind to a format spec assembled at runtime (`f"--format=%c{letter}"`) and
to a placeholder reaching git through a variable built elsewhere; neither shape exists in the package, and both would be a
strange way to spell a git format. It also does not see a check that depends on commit metadata through a THIRD PARTY — a
`gh api` read of `committedDate`, say. No such read exists today, and the forge-side date reads that DO exist were each checked
and are not commit metadata: `fleet/_settle_window` reads a release's `published_at` (a release is published once, so a replay
cannot move it), `cross_repo/release_lane_watch` reads a workflow run's `created_at`, and `checks/_plan_record_comments` and
`checks/work_item_interpolation_delimiters` read a beads ledger comment's `created_at`. `master_ci_green` is the only check
that calls out to the forge for commit-addressed state at all, and it asks for a CI conclusion rather than a date. That
boundary is the one to watch: the self-healing reconciler this plan builds will read commit-addressed forge state by design,
and `committedDate` is sitting right next to the fields it legitimately needs.
