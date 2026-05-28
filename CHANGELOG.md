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
