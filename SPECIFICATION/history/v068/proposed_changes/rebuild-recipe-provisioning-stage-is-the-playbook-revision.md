---
proposal: rebuild-recipe-provisioning-stage-is-the-playbook.md
decision: accept
revised_at: 2026-10-10T06:34:55Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-fable-5-1
---

## Decision and Rationale

Accepted as filed. The ratified recipe's node-provisioning stage named the node-local shell runbook `ci-runner/k3s/phase2/install-node.sh`, which sibling item C5 (`livespec-lfie5z`) retires because the committed Ansible playbook `ansible/ci-pool.yml` (livespec-dev-tooling PR #2274, merged 2026-09-12) is the layer the automation applies; the amendment makes the specification name the surviving layer, per livespec plan `gitops-deployment-discipline` research 000 §3 failure 2 (inverted layers: a mechanism change lands in the layer the automation APPLIES) and research 001 §"What the statement keeps and what it defers" (C12 `livespec-obsinx`). Both quoted replace-targets exist verbatim exactly once in the live file and are applied byte-exactly; the `## ` heading set is unchanged (18 H2 before and after), so `tests/heading-coverage.json` needs no co-edit; the mapped test module and `ci-runner/k3s/README.md` step 4 are rewritten in the same branch. No design-record contradiction; no steering intent. Independent read-only Fable 5.1 reviewer returned NO BLOCKERS for these exact bytes.

## Resulting Changes

- non-functional-requirements.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: fable
reviewer_identity: fable
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-10T06:33:37Z
verdict: NO BLOCKERS
proposal_stem: rebuild-recipe-provisioning-stage-is-the-playbook
content_digest: 17003d84746319b0583f65beb8e6809652805c802721a9f3a7f65d9d10bf52f0
