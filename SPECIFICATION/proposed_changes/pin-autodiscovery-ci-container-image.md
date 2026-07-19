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

**Implementation warning carried from the independent review:** the existing
fabro-sandbox walk is FIRST-MATCH-PER-FILE (`_FABRO_DOCKER_RE.search()`), and its
tests assert exactly one record per `workflow.toml`. The CI surface is not like
that — every cut-over consumer's `ci.yml` carries several matching lines (measured
2026-07-19: `livespec` 2, `livespec-dev-tooling` 2, `livespec-driver-claude` 3,
`livespec-driver-codex` 3, `livespec-runtime` 3, `livespec-console-beads-fabro` 3,
`livespec-orchestrator-git-jsonl` 5). The implementation MUST find ALL matches per
file and MUST carry a multi-job fixture, or jobs 2..N silently keep the stale tag.

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
- The amendment deliberately states the multiple-records-per-`pin_key` consequence,
  because a consumer that carries BOTH a Fabro `workflow.toml` and a cut-over
  `ci.yml` now yields two records sharing one `pin_key`, distinguished only by
  `file_path`.
- The source repo for the new surface stays HARDCODED to `livespec-dev-tooling`,
  exactly as the existing format specifies — it is not derived from the file.
