# Livespec Operation Gotchas

Use this when touching livespec-driven spec mutation, heading coverage, or
commit classification. It is agent-facing operational guidance; the normative
contracts remain in `SPECIFICATION/` and livespec core.

## Revise Payloads

The revise wrapper consumes one `decisions[]` entry per proposed-change file,
not one entry per `## Proposal:` subsection. If a proposed-change file contains
multiple proposal subsections, accept, modify, or reject that file as a whole
and put the cumulative file contents in that decision's `resulting_files[]`.
Split proposed changes into separate files when independent verdicts are
required.

`resulting_files[].path` is relative to the selected spec target. For files
inside `SPECIFICATION/`, use paths such as `spec.md`, `contracts.md`, or
`constraints.md`; do not prefix them with `SPECIFICATION/`. For a co-edit
outside the spec target, use a relative path from the spec target, such as
`../tests/heading-coverage.json`.

When revise/propose-change validation fails without useful stderr, inspect the
wrapper's validation helpers directly or increase structured logging rather
than guessing at the payload shape.

### Delegated-mode evidence

This repository revises in `delegated` mode, with `auto-spawn` review and
`ratification_reviewer_model: ["sonnet"]`. Measured on v119 (2026-11-03):

- `ratification_evidence.reviewer_identity` must EQUAL `reviewer_model`, for
  example both `"sonnet"`. A descriptive identity is refused with "ratification
  reviewer identity/model mismatch" (exit 4). See core
  `_revise_ratification_errors._reviewer_error`.
- Compute `content_digest` with core's
  `livespec.commands._revise_ratification._canonical_ratification_digest(
  decision={"resulting_files": rf}, proposal_bytes=<the proposed-change file's
  bytes>)`. `delegated_decision_evidence` carries the same digest.
- The reviewer is a separate read-only agent on the configured model. Have it
  recompute the digest itself and report `NO BLOCKERS` with a `date -u`
  timestamp, so its verdict binds to the exact bytes.
- The CLI numbers the new version from `history/`. When another revise PR is
  open, let it merge first, rebase, and build `resulting_files` from the new
  master. Otherwise the two PRs claim the same version.
- An open-PR search for `history/vNNN` does not prove the version is free. It
  only sees revises that have already been pushed. A peer's revise can still be
  inside its local commit gate, which takes about 15 minutes in
  livespec-orchestrator-beads-fabro. On 2026-11-05 two seats both cut
  orchestrator v305 that way (#4472 and a peer's revise), and the coordinator
  had the second seat re-cut as v306. In a repository that several seats
  revise, tell the coordinator which version you are claiming BEFORE starting
  the commit gate.

A spec-change-tier dispatch hold does not always need a revise. When the
dispatch judgement's own rationale says the ratified text already states the
behaviour, and the item's Definition of Done only adds extras, rewrite the
Definition of Done to the ratified text. The behaviour digest changes, so the
next dispatch retakes the classification. `dispatcher.py classify-tier` only
reports the standing record, so it cannot preview that (bd-ib-nesy77,
2026-11-03).

## Heading-Coverage Co-Edits

Any change that adds, renames, or removes a live `## ` H2 heading in
`SPECIFICATION/*.md` must update `tests/heading-coverage.json` in the same
commit. The registry tracks exact heading text, including punctuation. Copy
the heading from the spec file instead of retyping it.

The registry intentionally tracks H2 headings. Edits that only add lower-level
headings, such as `### ` or `#### `, do not need a heading-coverage entry unless
they also change the H2 set.

`test: "TODO"` is acceptable only as a transition state with a clear reason.
Release-tag CI rejects TODO registry entries, so replace TODOs with real test
node IDs before release.

## Commit Prefix Selection

Use a Conventional Commits prefix that matches the changed surface. For docs,
spec, workflow, configuration, dependency, or hook wiring work, prefer `docs:`,
`chore:`, `ci:`, or `build:` over `feat:` or `fix:`.

In livespec-family repositories that enforce red-green-replay, `feat:` and
`fix:` imply product behavior and require the Red -> Green replay ritual. If a
commit hook rejects the prefix, the commit did not happen; choose the correct
prefix and rerun `git commit` rather than amending a nonexistent commit.

## `ls` Is Aliased To lsd — Never Capture A Path From It

HOST-WIDE, not role-scoped: on this machine `ls` is an alias for
`lsd --inode --long --all`, and lsd decorates its output EVEN FOR `ls -d`. So
`GR=$(ls -d <path>)` captures a decorated line such as
`31197817 .rwxrwxr-x … /dispatcher.py`, not a path, and the NEXT command fails
with `No such file or directory` (or `python3: can't open file ...`) naming a
path built out of that decoration.

**The symptom is a FALSE ABSENCE.** The failure presents as the path being
missing, not as a quoting or capture bug — which is why it gets written up as a
finding about the system instead of a defect in the command. A surprising "No
such file or directory" from anything that resolved its path through a listing
is RE-CHECKED with `find` before it is treated as a finding, reported as a
blocker, or recorded as evidence.

Rules:

- Never capture a path from `ls` in a command substitution. Not `$(ls -d …)`,
  not `$(ls -1dt …)`, not `$(ls -td … | head -1)`.
- Resolve paths with `find`, e.g.
  `find <dir> -maxdepth 1 -name '<pat>' -printf '%T@ %p\n' | sort -rn | head -1`,
  or use a literal path. `/bin/ls` bypasses the alias but is not the habit to
  build; prefer `find -printf`.
- Non-interactive `bash -c` / script contexts do not expand the interactive
  alias, so the same line can work there and fail when a session runs it
  directly. A green script is not evidence the form is safe.

Measured 2026-07-28, 2026-08-21, and 2026-09-08 — three different agent roles
across 42 days, each rediscovering it from scratch. The supervisor-role record
of the first instance, with its role-specific context (a build path captured
once and reused after the release moved, and a 20s watcher), stays where it is:
see correction C6 in `.ai/supervisor-protocol.md`. This section is the
host-wide subset, kept here because the trap hits ANY role on this host and
`.ai/supervisor-protocol.md` is loaded only by supervisor handoffs.

## A Clean Filing Display Is Not Evidence Of Admissibility

`filing_display` can print `definition-of-done findings: none` for an item whose
pre-dispatch screen then refuses it on a governing heading. Measured 2026-11-07
on homelab item `hl-sj74nd`. It displayed no findings, and its screen at
16:08:19Z failed with "the Definition of Done reference line does not name
'## Constraints', which the spec-stated judgement returned as a clause governing
this item's assertions". After that heading was added to the `References:` line,
the 16:15Z screen was clean.

An earlier handoff recorded this gap as closed in code, because both builds
default `filing_display` to `host_governing_heading_reader`. That was wrong: the
display and the screen still disagreed on one unchanged item. The cause is not
established. `bd-ib-e3vbbo` owns the fix, and the earlier refusals of this shape
are `bejgoo`, `n6vnhp`, `sts554` and `rhivsm`.

How to apply: until `bd-ib-e3vbbo` closes, an item is admissible only once its
pre-dispatch screen has passed. Read that verdict rather than the display. When
the screen refuses on a heading, add the heading it names to the `References:`
line, written with its literal `## ` marker, beside the scenario heading, and ask
the dispatcher seat to screen it again.

## bd Resolves The Tenant From The Working Directory

`bd` auto-discovers its tenant from the nearest `.beads/` config, so the SAME
command names DIFFERENT work-item stores depending on the shell's cwd. Running
`bd show livespec-dev-tooling-<id>` from another fleet repo's checkout fails
with "no issue found" (or worse, a `bd create`/`bd comment` lands in the wrong
tenant silently). This bit a live session twice in one day — both times right
after a `cd /data/projects/<other-repo> && ...` compound command whose cwd
leaked into the next `bd` call.

Rule: run `bd` for a repo's items from THAT repo's checkout
(`/data/projects/livespec-dev-tooling` for this repo), and after any compound
command that `cd`s into a sibling repo, treat the cwd as poisoned for `bd`
until reset. Cross-tenant filing (a bug owned by a sibling) is done by
deliberately `cd`-ing into the OWNING repo first — make that explicit in the
command, never inherited.
