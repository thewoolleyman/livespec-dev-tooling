---
proposal: arc-listener-pods-run-only.md
decision: modify
revised_at: 2026-11-13T19:47:20Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-fable-5-2:homelab-k8s-worker-nodes
---

## Decision and Rationale

Accepted (graded PASS by legacy-coordinator-agent), with one clause reworded as stated under Modifications, and with one deviation in the co-edit the proposal asked of this revise. The proposal asked for a `tests/heading-coverage.json` row owned by livespec-dev-tooling-crvvxt for the scenario "every scale set's listener pod runs on an always-on node", and a unit-tier test row (`tests/livespec_dev_tooling/test_always_on_node_label.py`, from livespec-dev-tooling#4414) for "the listener read-back fails when a listener is on a node that is not always on". Neither row was written that way: livespec-dev-tooling-crvvxt is closed, so it cannot own an open debt, and a `scenarios.md` heading's coverage floor is the integration tier, so a unit-tier test cannot satisfy the second row. Both headings instead carry a spec-first `"test": "TODO"` row owned by the open item livespec-dev-tooling-zrsyfp, each naming the tier its test is owed at, and both are registered in `tests/heading-coverage-debt.json`. The proposal states the always-on posture key, its node label, listener placement by that label, and the committed read-back, all implemented by livespec-dev-tooling#4414 and host-verified on livespec-dev-tooling-crvvxt. One clause was then reworded by the doctor's LLM-driven objective pass, run on this cut on legacy-coordinator-agent's grade of livespec-dev-tooling#4562 (2026-11-13).

## Modifications

In non-functional-requirements.md §"Runner-pool node rebuild recipe", in the always-on posture paragraph, "while a committed profile names no node" becomes "while some committed profile cannot be read far enough to tell which node it names": the proposed words could be read as contradicting the rule, earlier in the same paragraph, that the reconcile removes the label from a node with no profile. No scenario changes.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-13T19:45:58Z
verdict: NO BLOCKERS
proposal_stem: arc-listener-pods-run-only
content_digest: dedf113373b464016633effdd50ccdec98b5401c98e56f3af494c199c0688768
