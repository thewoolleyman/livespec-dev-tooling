# Metadata-invariance audit of the shared check inventory

Work-item livespec-dev-tooling-yfqvqm (child B of plan `red-master-self-healing`, epic
livespec-dev-tooling-zcp5vb). Audited 2026-10-14 against `livespec-dev-tooling` master at the commit this note
lands on.

The question this note answers, and the only one: **for each check in the shared check inventory, can a commit and
its rebase-merge replay — differing ONLY in SHA, committer date and committer timezone — receive different
verdicts?**

## Why the three fields, and nothing else

GitHub's rebase-merge does not land the commit a pull request's CI judged. It mints a new one:

| Field | Under rebase-merge |
| --- | --- |
| tree | PRESERVED |
| author name / email / date | PRESERVED |
| commit message (subject, body, trailers) | PRESERVED |
| commit SHA | NEW |
| committer date | NEW (the merge instant) |
| committer timezone offset | NEW (the web-flow committer's) |
| committer name / email | NEW (`GitHub <noreply@github.com>`) |

The first three rows are why most of the inventory is invariant without having been designed for it: a check that
reads the tree, the author, or the message is already reading something a replay carries unchanged. The audit is
therefore a hunt for reads of rows four through six.

Row seven — the committer IDENTITY — is outside this work-item's assertion (it names SHA, committer date and
committer timezone). It is recorded here anyway, with its one site, because it is the same class of hazard and a
reader of this note will ask.

## The incident this generalizes

Orchestrator PR #2917 passed CI (run 38493306513). Rebase-merge minted `35fea321` with committer date
`2026-10-13T18:12:41-07:00`. Master run 38494465107 then failed `check-heading-coverage-debt-register`, which read
`%cs` — the committer date in the COMMIT'S OWN TIMEZONE — so one instant carried two different calendar dates and
the recorded `first_seen` read as inflated. Master was red ~01:17Z to ~01:55Z and the green-master gate refused
every factory dispatch from that repository for the whole window.

Nothing observable at pull-request time could have caught it. That is the property that makes this defect class
worth a standing guard rather than a fix.

## Method

1. **Mechanical, over the pretty-format surface.** `livespec_dev_tooling/commit_metadata_invariance.py` parses every
   first-party `.py` of the shipped library and reports each git pretty-format read of a variant field, requiring a
   git format introducer (`--format`, `--pretty`, `--date`) in the same argument vector. It is armed by
   `tests/livespec_dev_tooling/test_commit_metadata_invariance.py`, which enumerates `canonical_check_slugs()` plus
   the `workflow_checks/` members and asserts the scanned file set is a SUPERSET of the inventory before asserting
   the scan is clean. Coverage is proven, not assumed.
2. **By hand, over everything that is not a pretty-format read.** `rev-parse`, `rev-list`, `diff`, `diff-tree`,
   `show`, `merge-base`, `verify-commit`, `for-each-ref`, `cherry`, `ls-tree`, `symbolic-ref`, and the `TDD-*`
   trailer surface. Every git-invoking module in the library was read, and each public check that delegates to a
   private helper was traced to that helper.

The scan universe is the WHOLE shipped library rather than the slug modules alone, because a check's verdict is
computed by whatever it delegates to: `check-heading-coverage-debt-register` reads its git evidence through
`_heading_coverage_first_seen` and `heading_coverage_debt`, and neither of those is a slug.

## Every check in the inventory that reads commit metadata

Checks absent from this table reach no git commit object at all. The inventory holds 67 canonical slugs (measured
from `canonical_check_slugs()` at this commit) plus two `workflow_checks/` members; 58 of the 67, and every helper
they delegate to, read only the filesystem, the consumer config, the ledger (`bd`), or the forge API. The table is
the complete remainder, and it also carries `check-shipped-path-release-guard`, which is wired into `just check` and
into lefthook's commit-msg hook but is NOT a canonical slug (its module is `shipped_path_release_guard_check.py`, a
top-level module rather than a `checks/` member), because it reads a commit range and therefore belongs in this
audit.

| Check (slug) | Reads | Field class | Verdict moves under a replay? | Repair / carrier |
| --- | --- | --- | --- | --- |
| `check-heading-coverage-debt-register` | `git log --format=%H %cI` over `tests/heading-coverage.json`, then `git show <rev>:<path>` | commit SHA; committer date | **NO, repaired.** Was `%cs` and DID move — this is the incident. | Repaired: reads `%cI` and normalizes the instant to UTC in `heading_coverage_debt._utc_calendar_date`. Carried by **livespec-dev-tooling-a6gq5n** under plan `fleet-heading-coverage-convergence` (epic livespec-dev-tooling-0bse) — a cross-plan carrier, NOT re-fixed here. Both reads are now registered in `INVARIANCE_PROOFS` with their arguments. |
| `check-red-green-replay` | `git rev-list --no-merges origin/master..HEAD`; `git rev-parse HEAD`; `git diff-tree ... <sha>`; `git log -1 --format=%B <sha>` | commit SHA; commit message | NO | No repair needed. Every SHA is a HANDLE — it enumerates the range and addresses trees and messages; the one SHA that becomes a VALUE (`current_head_sha()`) is written into a `TDD-Green-Parent-Reflog` trailer as evidence and is read by no verdict (the only other mention is a remedy-hint string). Trailer TIMESTAMPS (`TDD-Red-Captured-At`, `TDD-Green-Verified-At`) are checked for KEY PRESENCE only and are never compared against a committer date. |
| `check-red-green-replay` (server-side-revert exemption, `_red_green_replay_revert.py`) | `git verify-commit --raw <sha>` against pinned web-flow keys; `git log -1 --format=%B <sha>`; `git rev-list --parents -n 1 <sha>`; `git merge-base --is-ancestor`; `git diff --quiet <reverted>^ <sha> -- <paths>` | commit SIGNATURE; message; ancestry; TREE CONTENT | NO for the three fields. | No repair needed. The reverted SHA is read from the PRESERVED message and `<reverted>^` is an ancestor of master either way; the decisive comparison is a byte diff of product paths, which is tree content. ⚠️ The signature arm is sensitive to WHO created the commit (row seven), not to SHA/date/timezone: a replay of a web-flow revert is itself web-flow signed, so the exemption holds — but a mechanism that re-created such a commit WITHOUT web-flow signing would lose it. Outside this assertion; recorded for child C1, which relies on this exemption. |
| `check-commit-pairs-source-and-test` | `git log -1 --format=%B`; `git diff --cached --name-only` | commit message; staged paths | NO | No repair needed. |
| `check-no-todo-registry` | `git show HEAD:<path>` (via `_branch_diff`) | tree blob | NO | No repair needed. |
| `check-check-coverage-incremental` | `git show <ref>:<path>`, `git diff --name-only` (via `_branch_diff`, `_docs_only_change`) | tree blobs; paths | NO | No repair needed. |
| `check-plan-no-live-handoff-file` | `git diff --name-only` (via `_branch_diff`) | paths | NO | No repair needed. |
| `check-shipped-path-release-guard` | `git rev-list --reverse --no-merges origin/master..HEAD`; `git log -1 --format=%B <sha>`; `git show --name-only <sha>` | commit SHA (handle); message; paths | NO | No repair needed. The guard is additionally INERT in this repository (no `.claude-plugin/` manifest), but the reasoning above is what makes it invariant in the repositories where it bites. |
| `check-primary-checkout-commit-refuse-hook-installed` | `git rev-parse --is-inside-work-tree` / `--git-dir` / `--git-common-dir` | repository layout | NO — reads no commit object | No repair needed. |
| `check-branch-protection-alignment` | `git remote get-url`; `git symbolic-ref refs/remotes/origin/HEAD` | ref names | NO — reads no commit object | No repair needed. |
| `check-master-ci-green` | forge API for master's CI status | world state at master's head | NO — judges master, not the inspected commit | No repair needed. |
| `no_stale_revise_branches` (workflow check) | `git for-each-ref --format=%(refname:short)`; `git log -1 --format=%s <branch>`; `git cherry` | ref names; subject; PATCH-ID | NO — patch-id is content-derived and the subject is preserved | No repair needed. |
| `release_bump_classification` (workflow check) | `git tag --list`; `git ls-tree`; `git show <rev>:<path>`; `git log --format=%s%x00%b%x1e` | tags; tree blobs; subject + body | NO | No repair needed. |

### Reads that look like a hazard and are not

- **`strftime` patterns.** `_red_green_replay_modes.py` (three sites) and `vendor_update.py` stamp
  `"%Y-%m-%dT%H:%M:%SZ"`. `%H` is the HOUR there, not the commit SHA. A specifier scan without the format-introducer
  requirement convicts all four, which is why the detector requires the introducer.
- **Wall-clock reads.** `_heading_coverage_age_bound.py`, `heading_coverage_debt.py`, `fleet/_settle_window.py`,
  `fleet/_git_identity_audit_report.py` all read `datetime.now(timezone.utc)`. That is the clock, not commit
  metadata, and every one of them is already UTC-based.
- **Author identity.** `fleet/git_identity_audit.py` and `fleet/_git_identity_host_canary.py` read
  `--format=%an%x00%ae` — the AUTHOR, which a replay preserves. Had either read `%cn`/`%ce` it would see
  `GitHub <noreply@github.com>` on every rebase-merged commit. Neither is in the canonical inventory (they are fleet
  tooling, not `just check` slugs), and both are invariant as written.

## The standing guard against reintroduction

`livespec_dev_tooling/commit_metadata_invariance.py` keeps three classes apart because their remedies differ:

- **Banned outright, never registrable** — `%cs`, `%cd`, `%cD`, `%ci`, `%cr`: the committer date rendered in the
  commit's own timezone. One instant renders as two calendar dates depending on the offset the committer's clock was
  set to, so there is no invariance argument to record. The remedy is `%cI` normalized to UTC, the author date, or
  the tree.
- **Registrable with a recorded reason** — `%cI`, `%ct`: one instant on one basis. Timezone-invariant, but a replay
  still RE-STAMPS the instant, so the proof must say why a later instant cannot flip the verdict. The `%cI` proof is
  that the only verdict it reaches is MONOTONE in it: `first_seen` must not be LATER than the evidence, so a later
  evidence date loosens the bound.
- **Registrable with a recorded reason** — `%H`, `%h`: a SHA used as a HANDLE is invariant; a SHA used as a VALUE
  (compared, matched, or recorded as evidence a later verdict reads) is not. Which one it is cannot be decided
  statically, so the proof says which, and why.

A proof that outlives its read is reported STALE and fails the arming test, so the registry cannot quietly become an
exemption list. The registry holds exactly two entries today, both for `heading_coverage_debt.py`.

The guard deliberately does NOT ship as a canonical check slug: a module under `checks/` becomes a slug, and a slug
obliges every consumer to wire it into `just check` and its CI matrix. The shared check inventory ships from this
repository alone, so this repository's own test suite is the right enforcement point — the same mechanical reasoning
`SPECIFICATION/contracts.md` records for `charters/` and `workflow_checks/`.

## Limits of this audit, stated rather than hidden

- **The mechanical half is a reintroduction guard, not a proof of impossibility.** It sees literals, f-strings, and
  module-level `NAME = "<literal>"` constants substituted into an argument vector. A format assembled at runtime —
  read from a config file, concatenated from a function parameter, built in a loop — is beyond it. No such site
  exists today; the hand audit is what establishes that.
- **It governs the SHARED inventory, not consumer-private checks.** `livespec`'s two private checks
  (`schema_dataclass_pairing`, `copier_template_smoke`) reach no git commit object, so the fleet surface is covered
  today — but a consumer that authors a private check reading `%cs` is outside this guard's reach. Making the rule
  binding on consumers is the spec amendment child A carries (livespec-dev-tooling-4v2yrw), which is where it
  belongs: a rule, not a scan.
- **Committer IDENTITY is audited but not asserted.** One site depends on it (the server-side-revert signature arm,
  above) and it holds. Child C1 should re-read that paragraph before relying on the exemption for a revert it creates
  by any mechanism other than the forge's own revert API.

## Dispositions

- **Repair required: none beyond a6gq5n.** The single check whose verdict moved under rebase-merge metadata is
  `check-heading-coverage-debt-register`, already repaired, and its carrier stays
  **livespec-dev-tooling-a6gq5n** under plan `fleet-heading-coverage-convergence`.
- **Standing guard: landed here** — the detector, its registry, and the arming test over the enumerated inventory.
- **Carried elsewhere:** the binding rule for consumer-private checks → child A (livespec-dev-tooling-4v2yrw). The
  committer-identity dependence of the revert exemption → noted for child C1 (livespec-dev-tooling-hrpcgl); it is
  not a defect and carries no work item of its own.
