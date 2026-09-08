---
proposal: pin-uses-ref-template-scan-set.md
decision: accept
revised_at: 2026-09-08T02:45:36Z
author_human: thewoolleyman <chad@thewoolleyman.com>
author_llm: claude-opus-5
---

## Decision and Rationale

Accepted as proposed. The defect is measured, not argued: reusable-workflow `uses:` pins living in copier templates at templates/*/.github/workflows/*.jinja are missed on BOTH the directory and the suffix count, so the pin-rewrite walk discovers none of them. Measured 2026-08-21 against a real livespec checkout, its five root pins sat at v1.31.1 while the five template pins sat at v1.20.4 and v0.32.0 — the root pins had been bumped repeatedly and the template pins had never moved. An earlier fix that corrected those template pins from @master to a concrete tag converted 'never stale, never reproducible' into 'reproducible, and now silently rotting', because the automation that would bump them cannot see them. Of the three axes, only the SUFFIX axis genuinely extends the format; the DIRECTORY axis removes an unstated root restriction that lives only in the implementation (the clause already read 'any GitHub Actions workflow file (under .github/workflows/)' with no root qualifier), and the EXCLUSION axis narrows the walk to the consumer repository the section already scopes it to. That exclusion is not optional tidiness: measured the same day, livespec/.pi/git/... holds full clones of other fleet repositories carrying their own real pins, and livespec-overseer carries agent worktrees under .claude/worktrees/ with three more. An unqualified any-depth widening would attribute those to the consumer and a bump would REWRITE another repository's checkout. The walk is purely filesystem-based, so neither git tracking nor .gitignore prevents that — every measured false positive sat under a directory carrying a .git entry and the legitimate template tree carried none, so the .git-entry test discriminates exactly. Record semantics, pin_key, current_value and the covered-format count are unchanged, so no downstream currency row or rewrite rule is disturbed.

## Resulting Changes

- contracts.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: fable
reviewer_identity: fable
separate_reviewer: True
read_only: True
reviewed_at: 2026-09-08T02:42:03Z
verdict: NO BLOCKERS
proposal_stem: pin-uses-ref-template-scan-set
content_digest: 2f8fbd3397098346120236208a8ad1ccf8ce9d610a11d1c14fad05a0224da5d2
