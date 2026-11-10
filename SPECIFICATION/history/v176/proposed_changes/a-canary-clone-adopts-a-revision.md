---
proposal: a-canary-clone-adopts-a.md
decision: modify
revised_at: 2026-11-10T02:03:18Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

MODIFY. The proposal gives the #4749 ruling (orchestrator spec v337: release advances only after a canary's samples pass; canary clones move by a named-build adopt of the tag) its executable route in this repository, on a tag-adopt mechanism proven on 2026-11-10 in a scratch home (builder home install, cache-directory copy, single-record atomic rewrite; the host marketplace slot is never touched). The pre-commit live-state doctor walk confirmed the record shape, sha12 cache directories, markers, cache-manifest.json, tag releases and remote ancestry against live state, and found the defects corrected in Modifications. It is on expedited-incident-response-flag's critical path (legacy-coordinator-agent, 2026-11-10 ~00:2xZ). Linked: livespec-dev-tooling-zpqvnr (plan gmktec-factory-placement, epic livespec-dev-tooling-me5aqz). No design record is contradicted.

## Modifications

Built on the proposal's eight contracts.md edits and its scenario, then corrected by a pre-commit live-state doctor walk (1 HIGH, 7 MEDIUM, 5 LOW on the verbatim text; 2 MEDIUM, 3 LOW on the first modification) and a sonnet ratification blocker on the verbatim text:
1. Adopt step: `<build>` may be a release tag per Tag adopt; the marketplace refresh, `claude plugin update` and the availability sentence are scoped to a full commit id (the verbatim text left them unconditional, contradicting Tag adopt's ban on touching the host marketplace clone).
2. Tag adopt: a non-draft release, and an unanswered release read refuses; commits are resolved, and ancestry is decided, from the remote through the forge's comparison, never from the host's shallow marketplace clone; it MUST NOT refresh or update; every `claude plugin` command runs with HOME set to the builder home and CLAUDE_CONFIG_DIR unset or inside it.
3. Hold probe: the package installed in the clone's environment (a livespec-dev-tooling checkout's own source tree), probed by `python -m livespec_dev_tooling.fleet.orchestrator_hold_probe`, where a missing module refuses; the recipe also requires a committed SessionStart hook that runs `just ensure-plugins`.
4. Copy: staged on the plugin cache's filesystem (/tmp is tmpfs here); a husk directory lacking a required path is moved aside on the same filesystem, replaced, and removed after the record is written.
5. Record: names the lost-write residual (another clone's update can revert). Verify: parsed-JSON comparison, and each re-read also checks the required paths.
6. Adoption lock: fixed path ~/.local/state/livespec-dev-tooling/orchestrator-adoption.lock, resolved before any HOME override.
7. Canaries and rolls: the operator rule refers to Tag adopt's hold probe and to SessionStart hooks that run no other plugin install or update.
8. Reach: the recipe runs the library build installed in the clone's environment, which follows the pin once synced (measured: livespec pins v1.189.1, its environment holds 1.188.1).
9. Scenario: adds the precondition that A's ensure-plugins package provides the hold and A's SessionStart runs it.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-10T02:02:26Z
verdict: NO BLOCKERS
proposal_stem: a-canary-clone-adopts-a
content_digest: bc0fb911f18bc65bfdee45b6a4488a76b9d854365ca30d672b570169870e3d7c
