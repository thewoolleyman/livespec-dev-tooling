---
proposal: every-repository-that-records-the-green-token-refuses-an-undecla.md
decision: modify
revised_at: 2026-11-12T06:58:42Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

The proposal's intent is accepted unchanged in substance: the aggregate refusal of an undeclared purity member, already binding every repository that records the green token on DECLARING, now binds them on REFUSING too, naming the shared `green_token undeclared` command and the `check-targets.txt` inventory. A pre-merge doctor pass confirmed against live code that the command's behaviour matches (green_token.py), that the consumers it inspected that record the token already refuse before their members run (livespec-overseer, livespec-orchestrator-git-jsonl, livespec-runtime, livespec-driver-claude/codex/pi), and that all 72 shipped checks/ modules declare CHECK_PURITY. CORRECTION recorded after legacy-coordinator-agent's grade (2026-11-12): livespec is an exception. Its origin/master a74effd6 records the green token (justfile:338) but carries no `green_token undeclared` refusal and no `# purity:` lines, so livespec does not conform to the widened MUST from ratification. Nothing turns red, because no check enforces this MUST. livespec's adoption is owned by livespec-kjpjq6 (livespec tenant, one of the eight krc2yd slices), whose Definition of Done requires livespec's `just check` aggregate to fail, naming the member, when a member carries no purity declaration. Two wording corrections: the inventory line is an annotation beside any other annotation the line carries (live lines also carry incident-timing), and 'a check this repository ships' becomes 'a canonical check (a module under livespec_dev_tooling/checks/)', because the purity resolver reads only checks/ and a shipped workflow check is declared in the consumer's inventory. resulting_files carry the cumulative text of both decisions. The independent sonnet review returned NO BLOCKERS on these exact bytes.

## Modifications

1. The inventory declaration is a `# purity: tree-pure` or `# purity: world-reading` annotation on the member's check-targets.txt line, beside any other annotation. 2. 'A check this repository ships' becomes 'a canonical check (a module under `livespec_dev_tooling/checks/`)' in the precedence sentence and in the new scenario's Given, and the bullet's earlier sentence 'A check this repository ships declares its own purity, so the declaration reaches every consuming repository with the library.' becomes 'A canonical check this repository ships declares its own purity in its module, so the declaration reaches every consuming repository with the library.'; every other member, including a consumer recipe that invokes a workflow check, declares in check-targets.txt. 3. resulting_files carry the cumulative text with the a-consumer-verifies decision.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-12T06:57:48Z
verdict: NO BLOCKERS
proposal_stem: every-repository-that-records-the-green-token-refuses-an-undecla
content_digest: ec6efe1a0a2a0ac67375f433dead2429fd32b4da36dae1a08b75452f349dcc14
