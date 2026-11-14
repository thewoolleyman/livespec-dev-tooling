---
topic: check-red-green-replay-never
author: claude-opus-5-5
created_at: 2026-11-14T05:35:23Z
---

## Proposal: The replay legs count repository-shipped Python outside the source prefixes as implementation, so its Green leg is reachable

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add a bullet to contracts.md section "Suite-green replay leg": for the replay gate's Red and Green legs and for the range validation's missing-trailers rule, a .py file outside tests/ counts as product implementation even when it lies outside the prefixes config.derive_source_prefixes returns. The exceptions are a file under a _vendor/ directory, a conftest.py, and a test-named module. The source_tree_prefixes key's bullet gains one sentence naming that widening and stating that the other consumers of the key are unchanged. Two scenarios are added to scenarios.md.

### Motivation

Work item livespec-dev-tooling-csis4y was recorded at the spec-change tier on 2026-11-14 (verdict unstated, linked topic check-red-green-replay-never). red_green_replay counts a staged .py as product implementation only under config.derive_source_prefixes, which in this repository is livespec_dev_tooling/. Repository-shipped Python elsewhere is neither product .py nor in the livespec-dev-tooling-9yrr non-.py set. An Ansible role's files/*.py, deployed by its role, is the measured case. The Green leg runs only when product .py is staged, so a Red commit whose implementation is such a file can never be completed. legacy-coordinator-agent measured livespec-dev-tooling#4639 (the scratch mover) and the factory_sandbox_reaper commit carrying only TDD-Red-* trailers, and this repository ships at least four non-vendored role files/*.py. Widening source_tree_prefixes instead is wrong: commit_pairs_source_and_test, check_coverage_incremental and tests_mirror_pairing read the same key, and role files keep their tests under tests/livespec_dev_tooling/, not at a mirror path. This proposal rides the same revise as check-red-green-replay-passes (livespec-dev-tooling#4610) and check-red-green-replay-records (livespec-dev-tooling#4622), per legacy-coordinator-agent's ruling of 2026-11-14. It aligns with both. #4622's open range rule already defers a commit that touches product impl .py to the missing-trailers rule, so after this change a Red-only role-file commit is judged by the missing-trailers rule instead, and both rules agree that such a commit fails. Its implementing item blocks livespec-dev-tooling-kz6n3a, so the Green leg is reachable before any range rule judges these commits.

### Proposed Changes

In SPECIFICATION/contracts.md, section "## Suite-green replay leg", add this bullet immediately after the bullet "Range validation collects a Red+Green commit's recorded test", and before any bullet the check-red-green-replay-passes or check-red-green-replay-records proposals add after it:

- **Replay implementation classification.** For the commit-msg replay gate's Red and Green legs, and for the commit-range validation's missing-trailers rule, a staged or changed `.py` file is product implementation when it lies under a prefix `config.derive_source_prefixes` returns. It is ALSO product implementation, when it lies outside those prefixes, if every one of these holds: it lies outside `tests/`; no directory on its path is named `_vendor`; its name is not `conftest.py`; and its name matches neither `test_*.py` nor `*_test.py`. An Ansible role's `files/<name>.py` is the measured case. A Green amend that stages such a file beside its Red commit's recorded test MUST run the Green leg and, when that test passes, record the `TDD-Green-*` trailers, exactly as for a product `.py` under the prefixes. This widening applies to `red_green_replay` ONLY: `commit_pairs_source_and_test`, `check_coverage_incremental` and `tests_mirror_pairing` MUST keep classifying by `source_tree_prefixes` (with the `source_trees` union) alone, so a staged role file never acquires a mirror-pairing demand. Fleet scope: every consumer whose commit-msg hook or CI runs the shared `red_green_replay` check; a consumer that ships no Python outside its prefixes is unaffected. Spec-first: the shipped gate classifies by the prefixes alone, and work item livespec-dev-tooling-csis4y owns the change.

In the same file, section "## Consumer configuration schema", append this sentence to the end of the `source_tree_prefixes` bullet: "`red_green_replay` additionally counts repository-shipped Python outside these prefixes as implementation, under §\"Suite-green replay leg\" **Replay implementation classification**; that widening changes no other consumer's reading of this key."

In SPECIFICATION/scenarios.md, add these two scenarios after "## Scenario: the commit-range validation fails a Red+Green commit whose recorded test cannot be collected on its own tree", and before any scenario the check-red-green-replay-passes or check-red-green-replay-records proposals add there:

## Scenario: a Green amend that stages an Ansible role's Python file records the Green trailers

Given a repository whose source prefixes are `livespec_dev_tooling/`

And a Red commit whose recorded test `tests/livespec_dev_tooling/test_reaper.py` fails

When the commit is amended to stage `ansible/roles/reaper/files/reaper.py` and the recorded test now passes

Then the commit-msg replay gate MUST run the Green leg and record the `TDD-Green-*` trailers

And `commit_pairs_source_and_test` MUST judge that staged role file exactly as it judges a file outside the source prefixes

And a staged `ansible/roles/reaper/files/_vendor/guard.py` MUST NOT count as product implementation for the replay legs

## Scenario: the commit-range validation fails a Red-only commit that changes an Ansible role's Python file

Given a branch whose range from origin/master holds a commit that changes `ansible/roles/reaper/files/reaper.py` and carries `TDD-Red-*` trailers and no `TDD-Green-*` trailer

When check-red-green-replay validates the range

Then the check MUST fail with its missing-trailers finding naming that commit

And a commit that changes `ansible/roles/reaper/files/reaper.py` and carries both the `TDD-Red-*` and the `TDD-Green-*` trailers MUST pass the missing-trailers rule

### Revise-time co-edits

The revise that accepts this proposal MUST add one `tests/heading-coverage.json` row for each of the two new scenario headings. Each is a spec-first `"test": "TODO"` row whose `reason` names the tier its owed test runs at (an integration-tier test of the commit-msg hook and of the range validation respectively) and whose `work_item` key is `livespec-dev-tooling-csis4y`. The revise MUST also regenerate and stage `tests/heading-coverage-debt.json` with `just generate-heading-coverage-debt-register`.
