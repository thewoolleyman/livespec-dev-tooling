---
proposal: sandbox-image-warm-keeps-only-current-tags.md
decision: modify
revised_at: 2026-11-02T06:08:24Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

MODIFY. This ratifies the sandbox image warm's keep-only-current-tags behaviour for both image stores, the k3s containerd store on factory nodes and a Docker factory host's image store. It is the spec-change tier that work-item livespec-dev-tooling-xknoqf's filing found missing. It was filed and decided by seat kubernetes-sandbox-backend (orchestrator plan epic bd-ib-nmuyjc) at the order of coordinator legacy-coordinator-agent (epic livespec-dev-tooling-6tgd2z), under delegated revise_decision_mode. It is spec-led from measurement (the Docker warm accumulated about 135 G on gmktec-xubuntu on 2026-11-01), not drift-origin. No design record is contradicted. Independent review: five separately spawned read-only sonnet reviewers, each fresh, ran over successive drafts. Rounds 1 to 4 each returned BLOCKERS, and every blocker was folded in. Round 5 returned NO BLOCKERS on these exact bytes. Its remaining nits are left to xknoqf's implementation: make removal untag only the single name, because containerd's CRI RemoveImage may drop every name of an image; qualify 'each warm run MUST make a removal pass' with 'unless the disabling variable is set'; add a scenario for a tag pulled by another party after the record exists; and add an exit-zero assertion for a collateral skip.

## Modifications

Relative to the filed proposal, the clause was rewritten.

It now defines three terms:
- the pinned set, per store;
- 'pulled', meaning a successful pull the warm itself recorded, held durably across a reboot; a pre-record tag counts as not pulled, and a no-op pull of a present tag is never recorded;
- 'in use', meaning referenced by any container on the host in any state, including through its image ID or a sibling tag.

It adds these rules:
- Each removal deletes only its one reference and never collaterally deletes a pinned, unpulled or in-use reference.
- The check-versus-removal race is closed per store. A refusing store (Docker without a force flag) may rely on its refusal and must never be forced. A non-refusing store (containerd CRI RemoveImage) must re-check after the removal, re-pull, and exit non-zero.
- A run that has not pulled the whole pinned set, or could not read every source of it, removes nothing; an unreadable source exits non-zero, naming it.
- Skipping a protected tag is not a failure. A refused or erroring removal keeps the tag and exits non-zero, naming it.
- 'Rolled back' is replaced by a variable that disables the removal pass, documented in HOST_VARS.md with the record's mechanism and location.
- The absolute 'never exceeds' bound is restated as intent.

The two proposed scenarios became seven: removal with shared-image collateral cases; an in-use tag kept; an unresolved or partial pinned set removes nothing; a container starting during removal; a rejected removal; a disabled pass; and reboot survival of the record.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-02T06:08:22Z
verdict: NO BLOCKERS
proposal_stem: sandbox-image-warm-keeps-only-current-tags
content_digest: 0013d92082d99045c08de25762791865fe4ac347dec8bafe048db5a26bea6cdc
