---
topic: gate-private-cross-repo-siblings
author: claude-opus-5-5
created_at: 2026-10-22T01:29:35Z
---

## Proposal: the delegated gate clones private cross-repository siblings with a read-only App installation token

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add a "Cross-repository siblings" bullet to contracts.md §"Delegated pre-push gate": the gate Job clones every cross_repo_targets sibling before the recipe and is red naming any it cannot clone. A private sibling is cloned with a short-lived installation token that the pushing host mints from the fleet's existing GitHub App, scoped to those siblings and to read-only contents, never in the manifest text, logs or termination message, and never a long-lived or newly named Secret. Add one scenario.

### Motivation

Coordinator R543 (2026-10-22): the delegated gate for livespec-orchestrator-beads-fabro fails with `FATAL: cannot clone cross-repo sibling dolt-server` (gate Job gate-livespec-orchestrator-beads-fabro-pgvtw, orchestrator PR #3479 context). Its `cross_repo_targets` name two PRIVATE siblings, dolt-server and livespec-tdd-proof. `render-gate-job.sh` accepts only anonymous https sibling urls, because the pod was designed to hold no credential, so every delegated push of that repository is red before its recipe runs. The repository therefore cannot use the delegated venue at all. Sibling cloning is not in the spec today: the anonymous-only rule lives only in the renderer's comments. So the fix has no governing heading, and the credential design needs ratifying rather than being improvised in a run. Design choices. The coordinator directed the fleet App's installation token with read-only contents, not a new secret and not a duplicate name. Minting on the PUSHING HOST matches the v082 principle that authority stays with the host that already holds it: the VPS already carries the App's id and key through the credential wrapper. The pod gets only a token that expires within the hour and is scoped to the named siblings and to contents:read. Keeping the token out of manifest text, logs and the termination message closes the channels the gate already writes evidence to. A host that cannot mint the token is the Verdict bullet's 'credential cannot be refreshed' case, so it refuses the push and does not skip the sibling. A skipped sibling is exactly the silent-green the existing unclonable refusal exists to prevent.

### Proposed Changes

In `SPECIFICATION/contracts.md` §"Delegated pre-push gate", insert this bullet immediately after the bullet beginning `- **The consumer's own recipe, and a missing one.**`:

- **Cross-repository siblings.** Before it runs the recipe, the gate Job MUST clone, shallowly at its default-branch head, every sibling repository that the consumer's `.livespec.jsonc` `cross_repo_targets` names. When any one of them cannot be cloned, the Job MUST report a red verdict naming that sibling and MUST NOT run the recipe against the absent clone. A public sibling is cloned anonymously. A private sibling is cloned with a GitHub App installation token that the pushing host mints at submission from the fleet's existing GitHub App. The token MUST be scoped to exactly the private siblings this gate run names and to read-only repository contents, and MUST expire within one hour. It reaches the gate Job for that one run only: it MUST NOT appear in the rendered manifest's text, in a log or in the termination message, and it MUST NOT be stored as a long-lived Secret or under any new standing credential name. A pushing host that cannot mint the token refuses the push as a missing verdict, as the Verdict bullet below requires.

In `SPECIFICATION/scenarios.md`, append:

## Scenario: an opted-in push whose consumer names a private cross-repository sibling clones it with a read-only installation token

Given a consumer repository whose `[tool.livespec_dev_tooling]` table sets `delegated_gate = true`

And whose `.livespec.jsonc` `cross_repo_targets` names a private sibling repository

And a pushing host where the pushing user can read the gates kubeconfig and the fleet GitHub App's credentials

When a git push of a tree that has no green token runs the pre-push gate

Then the gate Job MUST clone that sibling with an installation token scoped to that sibling and to read-only repository contents

And the rendered gate manifest MUST NOT contain that token

And the gate Job MUST run the consumer's recipe with that sibling's clone present

The new scenario heading needs a `tests/heading-coverage.json` entry (test `TODO`, owed by the implementing work-item, integration-tier) and a regenerated `tests/heading-coverage-debt.json` row, co-edited in the revise.
