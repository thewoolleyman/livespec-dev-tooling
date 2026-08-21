---
topic: pin-uses-ref-template-scan-set
author: claude-opus-5
created_at: 2026-08-21T08:00:16Z
---

## Proposal: Workflow-template pins are in scope for the uses: ref format, and nested repositories are not

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Extend the `uses:` ref pin format's scan set so it covers reusable-workflow pins held in workflow TEMPLATE files, and state explicitly that the walk must not descend into a nested repository. The format's scan set is amended along three axes stated separately because they sit in different positions: the DIRECTORY axis (any-depth `.github/workflows/`, which brings the implementation into conformance with the clause's existing unqualified wording), the SUFFIX axis (`.jinja` template files, which genuinely EXTENDS the format and is the part this amendment exists to ratify), and the EXCLUSION axis (a directory carrying a `.git` entry is another repository's tree and is out of scope, which narrows the walk to what the clause already scopes it to).

### Motivation

Work-item livespec-dev-tooling-ep8n. Reusable-workflow `uses:` pins living in copier templates at `templates/*/.github/workflows/*.jinja` are missed on BOTH the directory and the suffix count, so the pin-rewrite walk discovers none of them and they rot invisibly. Measured 2026-08-21: a walk against a real `livespec` checkout returns its five own root pins at v1.31.1, while the five template pins sit at v1.20.4 and v0.32.0 -- the root pins have been bumped repeatedly while the template pins have not moved, which is the drift this amendment closes. An earlier fix that corrected those template pins from `@master` to a concrete tag converted 'never stale, never reproducible' into 'reproducible, and now silently rotting', because the automation that would bump them cannot see them.

The exclusion axis is required because the obvious any-depth widening is unsafe as stated. Measured 2026-08-21: `livespec/.pi/git/github.com/thewoolleyman/` holds full clones of OTHER fleet repositories, each carrying its own `.github/workflows/` with real pins (livespec-driver-pi 4, livespec-orchestrator-beads-fabro 4), and `livespec-overseer` carries agent worktrees under `.claude/worktrees/` with 3 more. An unqualified any-depth walk would attribute those pins to the consumer and a bump would REWRITE another repository's checkout. The walk is purely filesystem-based, so neither git tracking nor gitignore prevents this: `.claude/worktrees/` is gitignored and `.pi` is tracked, and neither fact changes the outcome. Every measured false positive sits under a directory carrying a `.git` entry, while the legitimate template tree carries none, so the exclusion discriminates exactly.

### Proposed Changes

In section "Pin autodiscovery rules", replace the `uses:` ref format bullet's scan-set wording so that the format is defined over THREE explicit axes rather than a single root-relative directory glob.

1. TITLE AND DIRECTORY AXIS. Retitle the bullet from "**`.github/workflows/*.yml` / `*.yaml` `uses:` ref**" to "**`.github/workflows/` `uses:` ref (workflow files and workflow templates)**", and state that the walk covers every `.github/workflows/` directory at ANY DEPTH beneath the walk root, not only the one at the repository root. This axis does not change what the clause already says -- the existing text reads "any GitHub Actions workflow file (under `.github/workflows/`)" with no root qualifier -- it removes an unstated restriction that lives only in the implementation.

2. SUFFIX AXIS (the ratifying change). State that the scan set covers `*.yml` and `*.yaml` workflow files AND `*.jinja` workflow-TEMPLATE files, where a template is a file that RENDERS a GitHub Actions workflow rather than being one. A template's `uses:` line has the identical line shape, so it is the same pin in the same format; only the file's suffix and its rendered-vs-literal status differ. This is a genuine EXTENSION of the format and is the axis requiring ratification.

3. EXCLUSION AXIS. State that the walk MUST NOT descend into any directory that carries a `.git` entry -- a DIRECTORY for a nested clone, a FILE for a linked worktree -- because such a tree belongs to a DIFFERENT repository and its pins are not the consumer's pins. A record sourced from a nested repository would misattribute another repository's pin to this consumer, and the corresponding rewrite would mutate that other repository's checkout. This exclusion narrows the walk to the "consumer repository" the section already scopes it to.

Also state that the source-repo derivation, `pin_key`, and `current_value` semantics are UNCHANGED across all three axes: a template pin yields the same `(pin_format, file_path, pin_key, current_value)` record shape as a literal workflow pin, with `file_path` naming the template file. The existing normative sentences on tolerance of missing files, on the typed can't-parse outcome, and on unrecognized formats continue to apply unchanged.

Finally, if the section or the walk's module docstring states a covered-format COUNT, that count is unchanged by this amendment: this widens one existing format's scan set rather than adding a new format.
