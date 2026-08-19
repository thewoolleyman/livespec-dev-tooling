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
