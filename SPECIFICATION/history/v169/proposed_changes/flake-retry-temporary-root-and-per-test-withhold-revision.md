---
proposal: flake-retry-temporary-root-and-per-test-withhold.md
decision: modify
revised_at: 2026-11-09T17:07:49Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude:fleet-flaky-tests
---

## Decision and Rationale

Modified under delegated mode. All three proposals implement legacy-coordinator-agent's R301 ruling on plan fleet-flaky-tests (epic livespec-dev-tooling-zwveqp), each from a measured missed retry: master run 42445385824 (a tmp_path-rooted join naming .github/workflows/ci.yml withheld every retry in the file), the silent per-test withhold in the same run, and livespec-orchestrator-beads-fabro#4676 (a config-value-only .livespec.jsonc change touched every test through the root conftest). The carve-out is bounded by contracts.md §"Tests never pin committed configuration values", so a listed value-only change cannot cause a test failure unless the test names the key. Undeterminable still means touched in every case. Implementation items: livespec-dev-tooling-jfy23q, livespec-dev-tooling-ln77b6 and livespec-dev-tooling-n3dr3z. A pre-merge doctor LLM pass found that the proposed repository-root recognizer was undecidable and unsafe; the modified text fixes it. The independent read-only reviewer (sonnet) then found no blockers on the exact bytes.

## Modifications

Four modifications, each from the pre-merge doctor LLM pass. (1) The config-value insert's cross-reference reads `contracts.md` §"Config-value fast path at pre-commit", because that section is in contracts.md. (2) The closure-naming sentence defines a repository-rooted base explicitly: a string literal, an expression derived from `__file__`, or a name the closure binds by assignment to a repository-rooted expression. Any other base, a function parameter included, names nothing. As proposed, "a name bound to the repository root" was undefined. It also read `Path(__file__).resolve().parents[2] / "homelab-worker" / "prove-worker.sh"` (tests/spec/test_homelab_worker_prove.py:38) as naming nothing, which would have given a change to that script an unsafe retry. The motivating `root` (tests/consumer/test_delegated_gate_declared_recipe_scenarios.py:323) is a function parameter, so it is still retried. (3) A per-test FLAKE-RETRY-WITHHELD block names the reason when the test is touched because its paths cannot be determined or a module cannot be parsed, since no path or literal exists then. (4) "the dotted path of a changed key" became "a changed key's dotted path as that list names it", and the copy-into-temporary-root scenario assigns `REPO_ROOT` from `Path(__file__)`. No heading changed.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-09T17:07:12Z
verdict: NO BLOCKERS
proposal_stem: flake-retry-temporary-root-and-per-test-withhold
content_digest: 70c3b62a5399308008031ac7c514cd60c2071fb48f11c452fd93836bbd61de88
