# Agent-instruction inheritance — fleet gap audit

Audit deliverable for work-item `livespec-4g2pg3`, the read-only audit
slice of the agent-instruction-inheritance coordinating epic
(`livespec-ad4ov7`). A point-in-time gap matrix of the livespec fleet's
agent-instruction surface, taken 2026-06-22.

## Why

The fleet inherits its **spec** cleanly (copier template plus the
"inherited from livespec" convention), but its **agent-instruction
surface** was inherited only partially and drifted by hand. The trigger
was a real, multi-turn interactive `bd` access failure: the rule "all
beads/Dolt access goes through `with-livespec-env.sh`; an auth failure
means you are outside the wrapper; never touch the DB directly" lived
only in upstream `livespec/AGENTS.md` and never reached the impl repos.

## Members in scope

- `livespec` — upstream: spec, the impl-plugin copier template, and the
  canonical (~325-line, 12 H2-section) `AGENTS.md`.
- `livespec-dev-tooling`, `livespec-runtime`, `livespec-driver-claude` —
  each carries its own `AGENTS.md`.
- `livespec-orchestrator-beads-fabro`, `livespec-orchestrator-git-jsonl` —
  the impl/orchestrator plugins generated from the impl-plugin template.

## Gap matrix (at audit time)

Dimensions: **Core** = the fleet-universal agent-instruction core
present in `AGENTS.md`; **Symlink** = `.claude/CLAUDE.md` is a symlink to
`../AGENTS.md`; **Beads-prereqs** = the Beads runtime prerequisites
section present (beads-backed members); **Guard** = the beads-access
`PreToolUse` guard hook present.

| Member | Core | Symlink | Beads-prereqs | Guard |
|---|---|---|---|---|
| `livespec` (upstream) | full | n/a (real AGENTS.md) | yes | no |
| impl-plugin template | no (~30 ln, RGR only) -> yes after PR #519 | yes (symlink) | no -> yes after PR #519 | no |
| `livespec-orchestrator-beads-fabro` | thin (RGR + repo-mutation) | NO — regressed to a divergent real file | no | no |
| `livespec-orchestrator-git-jsonl` | thin | yes (symlink) | no | no |
| `livespec-dev-tooling` | own AGENTS.md | n/a | n/a | no |
| `livespec-runtime` | own AGENTS.md | n/a | n/a | no |
| `livespec-driver-claude` | own AGENTS.md | n/a | n/a | no |

## Key findings

1. **Template underfill is the root cause.** `templates/impl-plugin/AGENTS.md`
   carried only the Red-Green-Replay protocol (~30 lines) versus upstream
   `livespec/AGENTS.md` (~325 lines / 12 H2 sections), so every impl repo
   inherited a near-empty `AGENTS.md`. Remediation: enrich the template
   with the universal core (PR #519, slice `livespec-x2zitb`).
2. **CLAUDE.md symlink regression in one repo.** The template ships
   `.claude/CLAUDE.md -> ../AGENTS.md`; `git-jsonl` kept it, but
   `livespec-orchestrator-beads-fabro` clobbered it into a divergent
   real-file duplicate post-generation. Remediation: propagation slice
   `livespec-2lpgec`.
3. **Beads-access rule was unreachable from impl repos.** The collapsed
   bare-`BEADS_DOLT_PASSWORD` model and the `with-livespec-env.sh` wrapper
   lived only upstream. Remediation: folded into the template's Beads
   runtime prerequisites (PR #519), with the cwd-auto-discovery gotcha and
   the "auth-fail means you are outside the wrapper" correction.
4. **No beads-access guard anywhere.** A `PreToolUse` hook that blocks a
   bare `bd`/`dolt`/`mysql` invocation outside the wrapper is absent
   fleet-wide. Remediation: slice `livespec-zam76c` adds it to the
   template.
5. **Enforcement gap.** Nothing mechanically catches instruction-surface
   drift. Remediation: slice `livespec-3yebgl` extends the dev-tooling
   fleet `OBLIGATION_ROWS` (mirroring the beads tenant-connection
   consistency row added under qg0f.2).

## Adjacent findings (outside this slice's scope; recorded for follow-ups)

- **Tenant prefix drift.** `livespec-orchestrator-beads-fabro` tenant:
  live data `livespec-impl-beads-*`, `bd create` enforces `bd-ib-`, and
  config diverges; `livespec-orchestrator-git-jsonl`: config
  `livespec-orchestrator-git-jsonl` versus live `bd-gj`. Only
  `livespec-dev-tooling` is consistent. (Slice `livespec-th53uv`.)
- **Cross-repo dependency persistence gap.** The beads store writes only
  intra-tenant `blocks` edges; non-local `depends_on` kinds are dropped on
  write and absent on read, so cross-repo sequencing cannot be persisted
  in the store today even though `resolve_ref` plus the
  `cross_repo_targets` manifest are read-capable.
- **groom files single-ledger.** `groom.file_approved_slices` files every
  slice into the one passed tenant and treats `repo_target` as description
  metadata, contradicting the contract's "one slice maps to one ledger".

## Spec backing

The contract this audit informs was ratified as `contracts.md` section
"Fleet agent-instruction core" (livespec v125, PR #517).
