---
topic: pin-autodiscovery-ci-container-image
author: claude-opus-4-8
created_at: 2026-07-19T05:00:00Z
---

## Proposal: pin autodiscovery covers the CI container image tag

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Extends the **fabro-sandbox docker image tag** pin format in §"Pin autodiscovery
rules" so the walk ALSO discovers the job `container:` block's `image:` line in
`.github/workflows/*.yml`, not only the `docker =` line in Fabro `workflow.toml`
files. Today that CI line is an UNMANAGED pin: the release fan-out cannot see it,
so it is never rewritten and drifts from the sandbox image on every release.

### Motivation

Work-item `livespec-dev-tooling-xb7` (P1). The CI cutover introduced a new pin
surface — the job `container:` block's `image:` tag in each cut-over consumer's
`.github/workflows/ci.yml` — that bump-pin autodiscovery does not scan. Measured
2026-07-16, the Python repos' CI pinned `python-v0.43.2` while their Fabro sandbox
pinned `python-v0.48.1`: five releases apart, widening every release.

That directly defeats the guarantee the CI cutover exists to deliver — that CI runs
the SAME image the Fabro sandbox uses, collapsing green-in-CI / red-in-sandbox
drift. Today the drift is not collapsed, only RELOCATED.

The drift is currently LATENT, not active: the CI-relevant toolchain is identical
across the drifted tags, so nothing is broken right now. That is luck rather than
design — nothing stops the next release from moving a tool and making it real. The
motivation is therefore to stop the rot AUTOMATICALLY. A one-off hand-bump of the
affected repos is explicitly the WRONG fix: it re-rots on the next release, which is
precisely the bug.

Extending this format is not a No-Circular-Dependency violation. bump-pin is the
fan-out tool and ALREADY scans consumers' `.github/workflows/*.yml` (for `uses:`
refs) and their `workflow.toml` (for the `docker =` pin). This adds one more line of
a file the tool already reads — the same producer-rewrites-consumer-pin pattern, with
no new upstream-reads-downstream edge.

The prefix-preserving TAG COMPUTATION is reused unchanged:
`fabro_image_pin_rewrite.rewrite_layered_docker_tag` already rewrites only the
trailing `vX.Y.Z` portion and preserves the `python-` / `python-rust-` layer prefix
the image layer split depends on.

**The LINE MATCHER, however, must be extended — do not assume otherwise.** Verified
against `origin/master` 2026-07-19: `fabro_image_pin_rewrite.rewrite_pin_in_text`
compiles a pattern anchored to the TOML form
`^\s*docker\s*=\s*"<image_key>:<tag>"`, which cannot match a YAML `image:` line.
Its `main()` treats any match count other than 1 as fatal (`::error::` + non-zero
exit), so a discovered-but-unmatchable CI record would FAIL the fan-out rather than
silently no-op. The implementation must teach `rewrite_pin_in_text` the YAML form,
matching whichever form the record's `file_path` carries while keeping the
count-exactly-1 discipline PER RECORD (with N identical lines in one file, the
sequential per-record rewrites converge because each count-1 rewrite consumes the
next unrewritten occurrence). Emitting discovery records without extending the
matcher would convert a silent drift into a hard fan-out failure — strictly worse
than the status quo.

**Implementation warnings carried from the independent reviews.** The existing
fabro-sandbox walk is FIRST-MATCH-PER-FILE (`_FABRO_DOCKER_RE.search()`), and its
tests assert exactly one record per `workflow.toml`. The CI surface is NOT like
that, in two distinct ways an implementer must handle:

- **Many matching lines per FILE.** Every cut-over consumer repeats a job
  `container:` block per containerized job. Measured in `ci.yml` on each repo's
  `origin/master`, 2026-07-19: `livespec` 2, `livespec-dev-tooling` 2,
  `livespec-driver-claude` 3, `livespec-driver-codex` 3, `livespec-runtime` 3,
  `livespec-console-beads-fabro` 3, `livespec-orchestrator-git-jsonl` 5.
- **Many matching FILES per repo.** `ci.yml` is not the only workflow carrying the
  pin: `livespec` also carries 3 matching lines in
  `.github/workflows/ci-selfhosted-shadow.yml`, so its true surface is 5 lines
  across 2 files. Counting every workflow file, the real fan-out rewrites
  **24 lines across 8 files in 7 repos** (`livespec-orchestrator-beads-fabro` has
  none — it is not cut over).

So the implementation MUST find ALL matches per file, and its fixtures MUST include
BOTH a multi-job consumer AND a multi-FILE consumer. A first-match walk leaves jobs
2..N — and entire additional workflow files — pinned to the stale tag.

Two further implementation notes: the per-line rule now binds the WHOLE format,
including the `workflow.toml` surface, which stays conformant today only because
every real `workflow.toml` happens to carry exactly one `docker =` line — unify both
surfaces to find-all semantics rather than leaving a latent single-match assumption.
And the one-line `container: <image>` shorthand the amendment covers is currently
unexercised fleet-wide (zero uses), so it needs its own fixture or the clause
becomes dead prose.

### Proposed Changes

ONE verbatim replace-target in `SPECIFICATION/contracts.md`. It exists exactly once
in the live file; re-verify against `origin/master` before applying.

=== Replace-target A (REQUIRED — extend the fabro-sandbox bullet) ===

FIND (verbatim):
```
- **fabro-sandbox docker image tag** — the `docker = "ghcr.io/thewoolleyman/livespec-fabro-sandbox:<tag>"` line in every Fabro `workflow.toml` under either `.claude-plugin/.fabro/workflows/*/` or the top-level `.fabro/workflows/*/` (fleet consumers carry the config at one root or the other — the orchestrator under `.claude-plugin/.fabro/`, the console under the top-level `.fabro/` — and BOTH are walked so no consumer is missed). `pin_key` is the image reference WITHOUT the tag (`ghcr.io/thewoolleyman/livespec-fabro-sandbox`); `current_value` is `<tag>`. Unlike the other formats, the source repo is NOT derived from the file — it is HARDCODED to `livespec-dev-tooling`, because the fabro-sandbox image is built and released by livespec-dev-tooling and its tag tracks the dev-tooling release version. This is what lets a dev-tooling release fan-out (`--source-repo livespec-dev-tooling`) rewrite the docker tag in the SAME bump commit as the pyproject/compat dev-tooling pins. The record is emitted only when the `--source-repo` filter is absent or equals `livespec-dev-tooling`, per the standard source-repo-filter semantics.
```

REPLACE WITH:
```
- **fabro-sandbox docker image tag** — the `docker = "ghcr.io/thewoolleyman/livespec-fabro-sandbox:<tag>"` line in every Fabro `workflow.toml` under either `.claude-plugin/.fabro/workflows/*/` or the top-level `.fabro/workflows/*/` (fleet consumers carry the config at one root or the other — the orchestrator under `.claude-plugin/.fabro/`, the console under the top-level `.fabro/` — and BOTH are walked so no consumer is missed). The SAME image reference is ALSO pinned in GitHub Actions workflow files under `.github/workflows/` (`*.yml` / `*.yaml`), where a cut-over consumer runs its CI jobs inside the baked sandbox image. The matched line is the `image: ghcr.io/thewoolleyman/livespec-fabro-sandbox:<tag>` line nested under a job's `container:` block — GitHub Actions has no workflow-level `container:`, so a consumer repeats that block PER JOB (the one-line `container: <image>` shorthand is covered by the same scoped match). EVERY such line is walked as THIS SAME format, yielding ONE RECORD PER MATCHING LINE — across files AND within a single file — so one release fan-out reconciles a consumer's CI image and its Fabro sandbox image together instead of leaving CI behind. This is a SECOND surface inside `.github/workflows/` beyond the `uses:` ref format above; the two formats scan the same files for different lines and never overlap. The match MUST be scoped to the `ghcr.io/thewoolleyman/livespec-fabro-sandbox` image so an unrelated `container:` / `image:` line yields no record. `pin_key` is the image reference WITHOUT the tag (`ghcr.io/thewoolleyman/livespec-fabro-sandbox`); `current_value` is `<tag>`. Records of this format are NOT unique per `pin_key`. A consumer may carry the pin at MORE THAN ONE path (a Fabro `workflow.toml` AND one or more `.github/workflows/` files) and MANY TIMES WITHIN ONE FILE (once per job `container:` block). The walk therefore makes NO uniqueness claim: it yields one record per matching line, and each record's `file_path` together with its `current_value` targets that record's own rewrite. EVERY matching line in EVERY file MUST be rewritten in the same bump commit. A walk that stopped at the FIRST match per file would leave jobs 2..N pinned to the stale tag, recreating inside a single file exactly the drift this format exists to eliminate. Unlike the other formats, the source repo is NOT derived from the file — it is HARDCODED to `livespec-dev-tooling`, because the fabro-sandbox image is built and released by livespec-dev-tooling and its tag tracks the dev-tooling release version. This is what lets a dev-tooling release fan-out (`--source-repo livespec-dev-tooling`) rewrite the docker tag in the SAME bump commit as the pyproject/compat dev-tooling pins. The record is emitted only when the `--source-repo` filter is absent or equals `livespec-dev-tooling`, per the standard source-repo-filter semantics.
```

### Notes for the reviewer

- No `## ` heading is added, changed, or removed by this proposal, so no
  `tests/heading-coverage.json` co-edit is required.
- The amendment deliberately states the multiple-records-per-`pin_key` consequence.
  A consumer now yields MULTIPLE records sharing one `pin_key` — ONE PER MATCHING
  LINE. They are NOT all distinguishable by `file_path`: several records routinely
  come from the SAME file (one per job `container:` block), so `file_path` alone
  identifies a file, not a record. `livespec-console-beads-fabro`, for example,
  yields 4 records for this one `pin_key` (1 in `workflow.toml` + 3 in `ci.yml`).
- The source repo for the new surface stays HARDCODED to `livespec-dev-tooling`,
  exactly as the existing format specifies — it is not derived from the file.
