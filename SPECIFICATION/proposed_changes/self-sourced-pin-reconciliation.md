---
topic: self-sourced-pin-reconciliation
author: claude-opus-4-8
created_at: 2026-07-19T09:00:00Z
---

## Proposal: a self-sourced pin is reconciled by the producer at release time

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Qualifies §"Self-hosting". The contract states that this library is a sibling
consumer of its own coordination surface and "pin-and-bumps itself when livespec
releases". That is true only of pins sourced from ANOTHER repository. A
SELF-SOURCED pin — one whose source repo is this library — can never arrive by
dispatch, because the fan-out deliberately excludes the publishing repo so a
release does not echo back to itself. The amendment states that such a pin MUST be
reconciled by the producer at release time instead, and names BOTH self-sourced
pin formats the repository carries today.

### Motivation

Work-item `livespec-dev-tooling-5r3` (P1), found while live-verifying the `xb7`
fan-out on 2026-07-19.

The `xb7` change taught pin autodiscovery to see the fabro-sandbox image tag in
`.github/workflows/*.yml`, and the `v0.49.2` release fan-out then reconciled it
across the fleet — measured on `origin/master`:

| Repo | CI image pins | Tag |
|---|---|---|
| `livespec` | 5 | `python-v0.49.2` |
| `livespec-driver-claude` | 3 | `python-v0.49.2` |
| `livespec-driver-codex` | 3 | `python-v0.49.2` |
| `livespec-runtime` | 3 | `python-v0.49.2` |
| `livespec-orchestrator-git-jsonl` | 5 | `python-v0.49.2` |
| `livespec-orchestrator-beads-fabro` | 5 | `python-v0.49.2` |
| `livespec-console-beads-fabro` | 3 | `python-rust-v0.49.2` |
| **`livespec-dev-tooling`** | **2** | **`python-v0.43.2`** |

Every consumer is now self-healing. The PRODUCER is not: it sits **16 releases**
(six minor lines, 0.44–0.49) behind the image it builds. That is the one repository
where the guarantee the CI cutover exists to deliver — CI runs the SAME image the
Fabro sandbox uses — remains false, and it is the worst place for it, since this
repo builds the image and so tests against a stale one.

The cause is structural, not a defect in `xb7`. `reusable-release-dispatch.yml`
discovers siblings and excludes the publishing repository from the dispatch matrix
"so a release does not echo back to itself" — a deliberate, correct design. The
consequence is simply unstated: the exclusion that prevents an echo loop also
guarantees a self-sourced pin is never reconciled.

**The class has more members than the image tag, verified by running the walk.**
`pin_autodiscovery.discover(source_repo="livespec-dev-tooling")` against this repo
returns SIX self-sourced records: the two `fabro_sandbox_docker_image` pins in
`ci.yml` (at `python-v0.43.2`), and FOUR `github_workflow_uses_ref` pins — the
three consumer shims `release-dispatch.yml`, `bump-pin-from-dispatch.yml`,
`pin-freshness.yml`, PLUS `release-park.yml` — all at `v0.46.5`, **8 releases**
behind. Those `uses:` refs point at this library's own reusable workflows, so their
source repo derives to this library and they are dispatch-unreachable for the
identical structural reason. An earlier draft of this proposal defined the class
generally but wrote an operative clause covering only the image tag; that would
have let an implementer satisfy the letter while leaving four pins rotting, and
would have re-created the very discoverability gap this amendment exists to close.

This belongs in the contract rather than in code alone because it is an
architectural commitment — WHICH mechanism is responsible for WHICH class of pin —
not an implementation detail. §"Self-hosting" today implies complete
self-consumption; a reader cannot discover from the contract that a whole pin class
is structurally exempt.

**Do NOT fix by hand-bumping.** A manual bump re-rots on the next release, which is
precisely the bug `xb7` was filed against. The rule must be automatic.

Three constraints the amendment states explicitly because each is load-bearing:

- **It cannot recurse.** The reconciliation opens a `chore(deps):` PR, and per
  §"PR commit-message convention" a `chore:` commit cuts no release — so the
  release → reconcile → release cycle the fan-out's self-exclusion guards against
  cannot form by this path either.
- **Ordering matters, but only for the image.** The reconciliation must not run
  before the released image exists, or it pins CI to an unpushed tag and the bump
  PR's own CI cannot pass. A `uses:` ref carries no such constraint: the tag exists
  the moment the release is published.
- **Freshness is a weaker net, not a substitute.** §"reusable-pin-freshness.yml"
  does contract a bump PR per `(source_repo, current_pin, latest_tag)` triple, so
  the periodic scan is entitled to catch these pins — at best a cron cycle late and
  never release-coupled. The amendment therefore claims only that no
  RELEASE-DRIVEN path exists, not that nothing catches it. (Separately: the shipped
  freshness scan collapsed each source to one representative record and so did NOT
  catch it in practice — filed and fixed as `livespec-dev-tooling-p73`. The
  contract text here deliberately does not lean on that defect.)

### Proposed Changes

TWO verbatim replace-targets in `SPECIFICATION/contracts.md`, both in
§"Self-hosting". Each exists exactly once in the live file; re-verify against
`origin/master` before applying.

=== Replace-target A (REQUIRED — the class rule) ===

FIND (verbatim):
```
The library is itself a sibling consumer of its own coordination automation surface. The library's own `.github/workflows/` MUST include the three consumer shims (`release-dispatch.yml`, `bump-pin-from-dispatch.yml`, `pin-freshness.yml`) and the repository MUST carry the `livespec-sibling` topic. The shims delegate to the reusable workflows at the library's own currently-pinned release tag; consequently the library pin-and-bumps itself when livespec releases.
```

REPLACE WITH:
```
The library is itself a sibling consumer of its own coordination automation surface. The library's own `.github/workflows/` MUST include the three consumer shims (`release-dispatch.yml`, `bump-pin-from-dispatch.yml`, `pin-freshness.yml`) and the repository MUST carry the `livespec-sibling` topic. The shims delegate to the reusable workflows at the library's own currently-pinned release tag; consequently the library pin-and-bumps itself when livespec releases. That sibling-dispatch path reconciles every pin whose SOURCE is ANOTHER repository. It structurally CANNOT reconcile a SELF-SOURCED pin — one whose source repo is this library itself — because the fan-out deliberately excludes the publishing repository from its dispatch matrix so a release does not echo back to itself, so no `sibling-released` dispatch ANNOUNCING THIS LIBRARY'S OWN RELEASE ever arrives here. Two pin formats are self-sourced today, and the rule below governs BOTH: (i) the fabro-sandbox docker image tag (§"Pin autodiscovery rules"), whose source repo is HARDCODED to `livespec-dev-tooling`, the repository that builds and releases the image; and (ii) this library's OWN `.github/workflows/*.yml` `uses:` refs into its own reusable workflows — the consumer shims named above plus any other self-referencing `uses:` — whose source repo derives to this library from the `<repo>` segment. A self-sourced pin of EITHER format MUST be reconciled by the PRODUCER at release time rather than by dispatch: on publishing a release, this library MUST rewrite its own occurrences of every self-sourced pin to the released tag and open an auto-merge bump PR, using the same rewrite machinery and the same `chore(deps):` commit convention as the dispatch path (§"PR commit-message convention"). Because a `chore:` commit cuts no release (§"PR commit-message convention"), this cannot recurse. For the image tag ONLY, the reconciliation MUST NOT run before the released image exists, or it would pin CI to an unpushed tag; a `uses:` ref carries no such ordering constraint, because the tag exists the moment the release is published. Without this rule the producer has NO release-driven path that tracks either the image it builds or the reusable workflows it publishes; the periodic freshness scan (§"reusable-pin-freshness.yml") is then the only remaining catch — at worst a full cron cycle late, and never release-coupled.
```

=== Replace-target B (REQUIRED — the perpetuation claim it would otherwise falsify) ===

The bootstrap paragraph is specifically about the shim `uses:` pins, and its
"perpetuates via its own dispatches" claim is contradicted for exactly those pins
once Replace-target A lands. Empirically they have only ever advanced via freshness
bumps and have stalled at `v0.46.5`.

FIND (verbatim):
```
The self-hosting bootstrap is a one-time manual step: a human contributor authors the three consumer shims with their `uses:` lines pinned to a hand-chosen bootstrap tag (typically the first tag of this library that ships all three reusable workflows under `.github/workflows/`), tags the bootstrap release, and verifies that the first dispatch from a sibling release reaches this library and opens a bump-PR. Thereafter the system perpetuates via its own dispatches and the manual step is never repeated.
```

REPLACE WITH:
```
The self-hosting bootstrap is a one-time manual step: a human contributor authors the three consumer shims with their `uses:` lines pinned to a hand-chosen bootstrap tag (typically the first tag of this library that ships all three reusable workflows under `.github/workflows/`), tags the bootstrap release, and verifies that the first dispatch from a sibling release reaches this library and opens a bump-PR. Thereafter the system perpetuates via its own dispatches and the manual step is never repeated. That perpetuation covers only the pins this library holds on OTHER sources. It does NOT cover the shims' own self-referencing `uses:` refs, which are self-sourced pins per the paragraph above and therefore never advanced by any incoming dispatch; those are reconciled by the producer-at-release-time rule, not by the dispatch cycle.
```

### Notes for the reviewer

- No `## ` or `### ` heading is added, changed, or removed by either target, so no
  `tests/heading-coverage.json` co-edit is required.
- The amendment deliberately does NOT name a specific workflow file or job. Which
  workflow carries the step is mechanism; the contract states only that the
  producer reconciles at release time, after the image exists, via the shared
  rewrite machinery and commit convention.
- Semver shape is MINOR: a purely additive obligation that removes, renames, or
  breaks nothing enumerated in §"Semver discipline", and names no workflow path, so
  §"Semver coverage extension" needs no edit.
- This redraft answers a prior independent review that found the class-scope
  ambiguity (Blocker 1), the freshness contradiction (Blocker 2), and the
  paragraph-2 drift. Running the walk while fixing Blocker 1 surfaced a FOURTH
  `uses:` pin (`release-park.yml`) beyond the three shims the review named.
