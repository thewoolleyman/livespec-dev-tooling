# Changelog

## Unreleased

### Bug Fixes

* **checks:** make `branch_protection_alignment` exit 0 cleanly when `.github/workflows/ci.yml` is absent (graceful absence-handling, epic li-univck Phase 1.1, li-chkabs).

### Notes

#### Graceful absence-handling audit (epic li-univck Phase 1.1, li-chkabs)

Every check shipped by livespec-dev-tooling MUST exit 0 with no
findings when invoked in a consumer repo that lacks the check's
precondition. This makes the canonical aggregate (Phase 1.3+,
li-aggchk) safe to wire universally across the fleet.

Reference pattern: `no_stale_revise_branches.py` enumerates
`refs/heads/spec/*` first, then iterates — empty list ⇒ exit 0.

Audit results (all checks under `livespec_dev_tooling/checks/`):

| Check                          | Precondition                              | Status            |
| ------------------------------ | ----------------------------------------- | ----------------- |
| `vendor_manifest`              | `.vendor.jsonc` present                   | ALREADY-GRACEFUL  |
| `wrapper_shape`                | `.claude-plugin/scripts/bin/` directory   | ALREADY-GRACEFUL  |
| `heading_coverage`             | `tests/heading-coverage.json` + spec tree | ALREADY-GRACEFUL  |
| `claude_md_coverage`           | scope roots present                       | ALREADY-GRACEFUL  |
| `branch_protection_alignment`  | `.github/workflows/ci.yml`                | FIXED (this PR)   |
| `master_ci_green`              | GitHub CI configured                      | ALREADY-GRACEFUL  |
| `no_stale_revise_branches`     | `refs/heads/spec/*` branches              | ALREADY-GRACEFUL (reference) |
| `rop_pipeline_shape`           | `.claude-plugin/scripts/livespec/` tree   | ALREADY-GRACEFUL  |
| `no_raise_outside_io`          | `.claude-plugin/scripts/livespec/` tree   | ALREADY-GRACEFUL  |
| `supervisor_discipline`        | `.claude-plugin/scripts/livespec/` tree   | ALREADY-GRACEFUL  |
| `public_api_result_typed`      | `.claude-plugin/scripts/livespec/` tree   | ALREADY-GRACEFUL  |
| `newtype_domain_primitives`    | dataclasses tree                          | ALREADY-GRACEFUL  |
| `no_inheritance`               | `.claude-plugin/scripts/livespec/` tree   | ALREADY-GRACEFUL  |
| `no_write_direct`              | source trees                              | ALREADY-GRACEFUL  |
| `private_calls`                | `.claude-plugin/scripts/livespec/` tree   | ALREADY-GRACEFUL  |
| `global_writes`                | `.claude-plugin/scripts/livespec/` tree   | ALREADY-GRACEFUL  |
| `keyword_only_args`            | `.claude-plugin/scripts/livespec/` tree   | ALREADY-GRACEFUL  |
| `match_keyword_only`           | `.claude-plugin/scripts/livespec/` tree   | ALREADY-GRACEFUL  |
| `all_declared`                 | `.claude-plugin/scripts/livespec/` tree   | ALREADY-GRACEFUL  |
| `main_guard`                   | `.claude-plugin/scripts/livespec/` tree   | ALREADY-GRACEFUL  |
| `assert_never_exhaustiveness`  | `.claude-plugin/scripts/livespec/` tree   | ALREADY-GRACEFUL  |
| `pbt_coverage_pure_modules`    | pure-modules source trees                 | ALREADY-GRACEFUL  |
| `comment_line_anchors`         | configured target roots                   | ALREADY-GRACEFUL  |

22 of 23 audited checks already enumerated their precondition
first and exited 0 cleanly on absence. The single FIXED check
(`branch_protection_alignment`) previously logged an error and
returned exit 1 when `.github/workflows/ci.yml` was missing; it
now returns exit 0 silently, with the test renamed from
`test_missing_ci_yml_fails` to `test_missing_ci_yml_is_graceful`.

## [0.12.1](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.12.0...v0.12.1) (2026-06-12)


### Bug Fixes

* **bump-pin:** install commit-refuse hook before just check in composite action ([1c14ca8](https://github.com/thewoolleyman/livespec-dev-tooling/commit/1c14ca87da296142631abc50641cc75dfc3c0632))
* **bump-pin:** never commit the support-module checkout as a stray gitlink ([40244f1](https://github.com/thewoolleyman/livespec-dev-tooling/commit/40244f18c68b85c3faafd99f663b549492a5bf34))

## [0.12.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.11.0...v0.12.0) (2026-06-11)


### Features

* **pin-autodiscovery:** add github_workflow_uses_ref format (red) ([a274648](https://github.com/thewoolleyman/livespec-dev-tooling/commit/a2746486c7fdfc7fe822825b434321e25bbd3875))


### Bug Fixes

* **red-green-replay:** Branch-4 routing requires Red WITHOUT Green at HEAD ([2220eea](https://github.com/thewoolleyman/livespec-dev-tooling/commit/2220eeaa4c858c0269445de3bce760f3327a42e4))

## [0.11.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.10.2...v0.11.0) (2026-06-11)


### Features

* **red-green-replay:** content-based trigger + commit-range validation; retire prefix-fallthrough ([bb9a641](https://github.com/thewoolleyman/livespec-dev-tooling/commit/bb9a64159878b3929ae3e36801a90cb5d5f6bb8b))
* shared no_direct_destructive_cli check (destructive-default CLI wrapping) ([6896651](https://github.com/thewoolleyman/livespec-dev-tooling/commit/6896651358e57b49b2c32f2f1150bd9a8fa891d1))


### Bug Fixes

* **red-green-replay:** green-verified leg replaces the product-mislabel reject ([a11feb8](https://github.com/thewoolleyman/livespec-dev-tooling/commit/a11feb86101c4af4af25d1b1bcf6ea6172ca631c))

## [0.10.2](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.10.1...v0.10.2) (2026-06-10)


### Bug Fixes

* prefer the livespec-impl-git-jsonl block in no_stale_revise_branches ([5cd8b37](https://github.com/thewoolleyman/livespec-dev-tooling/commit/5cd8b37f41c29502a413eb72d601f4d4b06793af))
* recognize livespec_impl_git_jsonl impl prefix in red_green_replay ([b1f274a](https://github.com/thewoolleyman/livespec-dev-tooling/commit/b1f274a4151ef3456a7a2fee7cc16e19c06fa0db))

## [0.10.1](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.10.0...v0.10.1) (2026-06-08)


### Bug Fixes

* recognize livespec-impl-beads impl path in Red-Green-Replay check ([48e3a38](https://github.com/thewoolleyman/livespec-dev-tooling/commit/48e3a3814cf21effeb90e65a1995ccc98e834a8b))

## [0.10.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.9.1...v0.10.0) (2026-06-02)


### Features

* relocate no_stale_revise_branches to workflow_checks; drop --allow-stale-branches ([d4e1ecc](https://github.com/thewoolleyman/livespec-dev-tooling/commit/d4e1eccffd772854b0c472c096fcfec82fd50759))

## [0.9.1](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.9.0...v0.9.1) (2026-06-02)


### Bug Fixes

* **cvnoarg:** check_coverage_incremental derives --paths from git diff ([ec023de](https://github.com/thewoolleyman/livespec-dev-tooling/commit/ec023de47c6aec99b019596b99155fe3041038c9))
* **cvnoarg:** red_green_replay derives commit msg from HEAD with no argv ([8ba35bc](https://github.com/thewoolleyman/livespec-dev-tooling/commit/8ba35bc059d0baf1235d7367e1ced206183c5da0))
* **cvtodo:** check_mutation RUN/SKIP lever replaces release-gate skip ([aad7727](https://github.com/thewoolleyman/livespec-dev-tooling/commit/aad7727b71a37d45736893095bd5be7e456ba049))
* **cvtodo:** no_lloc_soft_warnings severity lever replaces release-gate skip ([a6ed10c](https://github.com/thewoolleyman/livespec-dev-tooling/commit/a6ed10c446387b3da5542115ae1f48e44a885586))
* **cvtodo:** no_todo_registry severity lever replaces release-gate skip ([66b3688](https://github.com/thewoolleyman/livespec-dev-tooling/commit/66b3688dd4df99dc4e45adb4553a23d70d40eba8))

## [0.9.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.8.0...v0.9.0) (2026-05-31)


### Features

* enforce scenarios.md integration-tier coverage in heading_coverage (epic li-scetier W1) ([b4e43dd](https://github.com/thewoolleyman/livespec-dev-tooling/commit/b4e43dd76c6a06efce645794f4558f714337cb9f))
* read scenario_tiers allowlist from pyproject (epic li-scetier W1) ([09c60c7](https://github.com/thewoolleyman/livespec-dev-tooling/commit/09c60c7eb08d8ebd7ea1dc7c6826ec7b68d86219))
* require granular registry entries for scenarios.md scenario headings ([7ac151f](https://github.com/thewoolleyman/livespec-dev-tooling/commit/7ac151fe91c4a6c0f0cf4f40eef10cd341cafaf5))

## [0.8.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.7.0...v0.8.0) (2026-05-31)


### Features

* CLI end-to-end harness (epic li-e2ecli Phase 2; li-e2ecdt) ([df60126](https://github.com/thewoolleyman/livespec-dev-tooling/commit/df60126c2341eeffb65991c00703b99f853a6d08))

## [0.7.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.6.0...v0.7.0) (2026-05-30)


### Features

* add tdd-commit helper mechanizing the Red-Green-Replay ritual ([4fc6c2a](https://github.com/thewoolleyman/livespec-dev-tooling/commit/4fc6c2ad588a547ebe0784d81ea8b161d850edcc))
* config loader for consumer source-tree layout (li-asybpo) ([391662a](https://github.com/thewoolleyman/livespec-dev-tooling/commit/391662a9363ceaff5d130d2d14b53397e3c71970))
* shared checks read source trees from config (li-asybpo) ([977adb8](https://github.com/thewoolleyman/livespec-dev-tooling/commit/977adb81b597f88624b75c3bf416c47ed22c5f56))
* tool-backed-check completeness meta-check (li-pyright-gate-wi3) ([0945771](https://github.com/thewoolleyman/livespec-dev-tooling/commit/094577179c2a494fd0c292ba66f81e5b10ae2031))

## [0.6.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.5.1...v0.6.0) (2026-05-29)


### Features

* shared skill_invocation_paths check (fenced SKILL.md wrapper invocations) ([0cbd890](https://github.com/thewoolleyman/livespec-dev-tooling/commit/0cbd890d51096a051aa3a160f1330c26f87bec75))


### Bug Fixes

* red-green-replay rejections print the full 2-step protocol ([15704f7](https://github.com/thewoolleyman/livespec-dev-tooling/commit/15704f73516342622360c36591b09a725934f469))

## [0.5.1](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.5.0...v0.5.1) (2026-05-29)


### Bug Fixes

* **branch-protection:** fail when master is definitively unprotected ([5512ae4](https://github.com/thewoolleyman/livespec-dev-tooling/commit/5512ae492dab2e6e113a2a2eef33599168b72c71))
* **check:** fail on core.bare=true in commit-refuse-hook-installed check ([dfa3edc](https://github.com/thewoolleyman/livespec-dev-tooling/commit/dfa3edc3326e0581b91729a29fc81ff262372a36))
* **lint:** replace en-dash with hyphen in v091-v094 docstring (RUF002) ([447878d](https://github.com/thewoolleyman/livespec-dev-tooling/commit/447878d51ebd6e1588402c6f0200ad72697681a9))
* relax wrapper_shape livespec-prefix coupling for impl-plugin wrappers (li-ini4rz) ([fa8f436](https://github.com/thewoolleyman/livespec-dev-tooling/commit/fa8f4362bf8c6f46d6324a702efc54c9b649ec4c))

## [0.5.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.4.0...v0.5.0) (2026-05-28)


### Features

* **checks:** add primary_checkout_commit_refuse_hook_installed outside-in tests (Red, li-unbardct) ([716f736](https://github.com/thewoolleyman/livespec-dev-tooling/commit/716f7365010fbc9c26530ebefd77955920b6dfd3))
* **checks:** flip primary-checkout invariant from bare-flag to commit-refuse-hook (Green, li-unbardct, epic li-unbare Phase 2) ([99fb8d1](https://github.com/thewoolleyman/livespec-dev-tooling/commit/99fb8d1035a62a6353e55a240347e8f4381b03b4))


### Bug Fixes

* **lint:** resolve E501/RUF002/G004 in primary_checkout_commit_refuse_hook_installed (post-PR-42) ([b813628](https://github.com/thewoolleyman/livespec-dev-tooling/commit/b8136283f2ac534f128d002a9445131fec72bb27))

## [0.4.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.3.0...v0.4.0) (2026-05-28)


### Features

* **checks:** add aggregate_completeness in-repo gate (Green, li-aggchk) ([efaa3cc](https://github.com/thewoolleyman/livespec-dev-tooling/commit/efaa3cc6645a4f753f5c7181c62df42cdec14e80))
* **checks:** add canonical_checks enumeration (Green, li-canon) ([39feba1](https://github.com/thewoolleyman/livespec-dev-tooling/commit/39feba1595d914b70f7f98382e59b9cabe65e964))
* **check:** self-host full canonical aggregate (li-ldtv03, epic li-univck Phase 1.4) ([13acd85](https://github.com/thewoolleyman/livespec-dev-tooling/commit/13acd859808640030937ec44a749852e80d53c99))


### Bug Fixes

* **checks:** graceful absence-handling audit (li-chkabs, epic li-univck Phase 1.1) ([7637854](https://github.com/thewoolleyman/livespec-dev-tooling/commit/76378544684d5c8318185ccb002ee06ec98dc4f6))

## [0.3.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.2.1...v0.3.0) (2026-05-27)


### Features

* **checks:** add no_stale_revise_branches shared check (li-hy6pfb) ([5f3b5aa](https://github.com/thewoolleyman/livespec-dev-tooling/commit/5f3b5aa33120fb5c19c62818d8189048a36ecfad))
* **checks:** port primary_checkout_bare_flag_set shared check (Phase 1 family migration) ([#35](https://github.com/thewoolleyman/livespec-dev-tooling/issues/35)) ([d665b98](https://github.com/thewoolleyman/livespec-dev-tooling/commit/d665b987fd62ee701499621a6b4be5a921e7b605))


### Refactoring

* **workflows:** extract bump-pin-rewrite into composite Action (li-b4yiuv) ([0bf3a61](https://github.com/thewoolleyman/livespec-dev-tooling/commit/0bf3a618687f30339a6d8e054f6b21b7525bbc96))

## [0.2.1](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.2.0...v0.2.1) (2026-05-25)


### Bug Fixes

* **checks:** path-portability — resolve repo from git remote, restore fail_under=100 ([d63be8d](https://github.com/thewoolleyman/livespec-dev-tooling/commit/d63be8d14966768173f228c4682e77e566632968))

## [0.2.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.1.1...v0.2.0) (2026-05-25)


### Features

* **cross-repo:** reusable workflows + pin-autodiscovery (Phase 3) ([#6](https://github.com/thewoolleyman/livespec-dev-tooling/issues/6)) ([cbfd7a4](https://github.com/thewoolleyman/livespec-dev-tooling/commit/cbfd7a45f769569bac681ab4d616889090247811))

## [0.1.1](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.1.0...v0.1.1) (2026-05-23)


### Bug Fixes

* **checks:** recognize sibling-library impl prefixes (mm-mjgigw) ([0e4c81a](https://github.com/thewoolleyman/livespec-dev-tooling/commit/0e4c81a97fb8fb42cf12a89ab2e2deac44786743))

## 0.1.0 (2026-05-21)


### Features

* **actions:** composite Actions + reusable check-matrix workflow ([772c70b](https://github.com/thewoolleyman/livespec-dev-tooling/commit/772c70be40d2c931a2e78006c30b13eea998daf3))
* **checks:** migrate shared enforcement-suite from livespec-core ([c7d9603](https://github.com/thewoolleyman/livespec-dev-tooling/commit/c7d960386ec72fbacfd6d164b81287049d4a604d))
* **spec:** seed livespec-dev-tooling SPECIFICATION/ ([dfe4de6](https://github.com/thewoolleyman/livespec-dev-tooling/commit/dfe4de6acd554e931686bca875a3271fbc20d644))
