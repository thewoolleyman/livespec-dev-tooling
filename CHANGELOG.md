# Changelog

## Unreleased

### Features

* **fleet:** assert beads tenant-connection consistency between `.beads/config.yaml` and `.livespec.jsonc`'s impl-plugin `connection` block, making per-repo tenant-connection drift un-mergeable (qg0f.2).

### Bug Fixes

* **checks:** make `branch_protection_alignment` exit 0 cleanly when `.github/workflows/ci.yml` is absent (graceful absence-handling, epic li-univck Phase 1.1, li-chkabs).
* **checks:** drop the dead pre-rename `livespec_impl_*` impl prefixes from the red-green-replay `_IMPL_PREFIXES`, and prefer the `livespec-orchestrator-git-jsonl` `canonical_branch` key in `no_stale_revise_branches`; flip stale `livespec-impl-*` references in comments/docstrings to the renamed orchestrators (qg0f.5).

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

## [0.34.2](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.34.1...v0.34.2) (2026-07-08)


### Bug Fixes

* reroute file_lloc coverage to the git-derived first-party universe ([4562773](https://github.com/thewoolleyman/livespec-dev-tooling/commit/4562773557ddd7c0ffd38a5ffcc09386a994c4d0))

## [0.34.1](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.34.0...v0.34.1) (2026-07-08)


### Bug Fixes

* recognize [@generated](https://github.com/generated) marker in C-family block comments ([c0eca10](https://github.com/thewoolleyman/livespec-dev-tooling/commit/c0eca10705057d9856e60fcdf75cca7af36ce5a4))

## [0.34.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.33.5...v0.34.0) (2026-07-08)


### Features

* git-derived first-party .py universe primitive (foundation, no reroute) ([70b4cc0](https://github.com/thewoolleyman/livespec-dev-tooling/commit/70b4cc060760ae975689aba16f387ad2de3ada13))

## [0.33.5](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.33.4...v0.33.5) (2026-07-06)


### Bug Fixes

* re-wrap collapsed single-line App-key PEM before setting fleet secret ([f4b4428](https://github.com/thewoolleyman/livespec-dev-tooling/commit/f4b44286b0d79c7c2a0ba78a48d3e0b00fc05adf))

## [0.33.4](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.33.3...v0.33.4) (2026-07-04)


### Bug Fixes

* restore claude plugin currency errors ([8707ef7](https://github.com/thewoolleyman/livespec-dev-tooling/commit/8707ef79ccccae5c196e89fb35dd2d111a561ba0))

## [0.33.3](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.33.2...v0.33.3) (2026-07-04)


### Bug Fixes

* **fleet:** reconcile merged branch cleanup setting ([f0459fa](https://github.com/thewoolleyman/livespec-dev-tooling/commit/f0459faac9a5111ef13fc7054e05448f2de5dcc5))

## [0.33.2](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.33.1...v0.33.2) (2026-07-04)


### Bug Fixes

* expose merged branch sweep API failures ([e25ebf5](https://github.com/thewoolleyman/livespec-dev-tooling/commit/e25ebf509a48cfbc204bb4d4253c3583f3e65837))
* parse gh jq object streams ([6c0de90](https://github.com/thewoolleyman/livespec-dev-tooling/commit/6c0de907fa5b78c858ded1dfb08104951d499c3f))

## [0.33.1](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.33.0...v0.33.1) (2026-07-04)


### Bug Fixes

* verify fleet delete-branch cleanup setting ([3d4e231](https://github.com/thewoolleyman/livespec-dev-tooling/commit/3d4e231d01e54504536c2d98e24fa808fc34fde9))

## [0.33.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.32.2...v0.33.0) (2026-07-04)


### Features

* add merged branch sweep tests ([3a2959a](https://github.com/thewoolleyman/livespec-dev-tooling/commit/3a2959a1c203b08ebd1dde2cf690e02449b7b2f5))

## [0.32.2](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.32.1...v0.32.2) (2026-07-04)


### Bug Fixes

* remove the master_ci_green repair lever — no escape gates on CI-green gates ([188bca6](https://github.com/thewoolleyman/livespec-dev-tooling/commit/188bca68018caef3e8b339d71797ff6d17ef7fb6))

## [0.32.1](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.32.0...v0.32.1) (2026-07-04)


### Bug Fixes

* repair the three fleet-check postures reddening the fleet ([caab92a](https://github.com/thewoolleyman/livespec-dev-tooling/commit/caab92ae4840dc16ebd30d9e462a71d207463e08))

## [0.32.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.31.3...v0.32.0) (2026-07-03)


### Features

* enforce Claude plugin currency wiring ([ad807ea](https://github.com/thewoolleyman/livespec-dev-tooling/commit/ad807ea13bc0028640aadf4bbdf5eb20fdf6095b))

## [0.31.3](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.31.2...v0.31.3) (2026-07-03)


### Bug Fixes

* guard marketplace sources ([41598f9](https://github.com/thewoolleyman/livespec-dev-tooling/commit/41598f9b061d54a65caf866d8dd400d0536d63f6))

## [0.31.2](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.31.1...v0.31.2) (2026-07-03)


### Bug Fixes

* provision worktree pack on create ([6ca1b8e](https://github.com/thewoolleyman/livespec-dev-tooling/commit/6ca1b8ec62dd7dbacdda866a610659ee5b5d2570))

## [0.31.1](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.31.0...v0.31.1) (2026-07-03)


### Bug Fixes

* **fleet:** gate committed uv.lock against the dev-tooling pin ([ea6e362](https://github.com/thewoolleyman/livespec-dev-tooling/commit/ea6e362cf5206927d49a2f85127ff6deb0211d78))
* **fleet:** pin file_text to canonical master ref to match tree() ([50b559c](https://github.com/thewoolleyman/livespec-dev-tooling/commit/50b559cc2f471a55a9b09fb144e9375e1853ca12))

## [0.31.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.30.1...v0.31.0) (2026-06-28)


### Features

* **governed-lifecycle:** livespec-jsonc-complete verb row — machine-fill connection, detect-and-guide harnesses (livespec-zs22.8.6) ([584082d](https://github.com/thewoolleyman/livespec-dev-tooling/commit/584082d0c479459f72c3fd6bff33873e835631bf))

## [0.30.1](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.30.0...v0.30.1) (2026-06-28)


### Bug Fixes

* **governed-lifecycle:** verb plugin rows skip when the recipe is absent (livespec-zs22.8.5) ([0b92960](https://github.com/thewoolleyman/livespec-dev-tooling/commit/0b92960c6656206cbe257f9b2be6c68df04af88b))

## [0.30.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.29.1...v0.30.0) (2026-06-28)


### Features

* **governed-lifecycle:** beads-runtime detect-and-guide rows (livespec-zs22.8.4) ([ac60e60](https://github.com/thewoolleyman/livespec-dev-tooling/commit/ac60e6088dfdf674150619151a60173ddd3f08b2))

## [0.29.1](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.29.0...v0.29.1) (2026-06-28)


### Bug Fixes

* **governed-lifecycle:** genuine-absence guard closes the vacuous-pass hole (livespec-zs22.8.3) ([5a338f0](https://github.com/thewoolleyman/livespec-dev-tooling/commit/5a338f05e9ba715bcde5b906953f135ea62e3bec))

## [0.29.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.28.1...v0.29.0) (2026-06-28)


### Features

* **governed-lifecycle:** local first-touch reconcile verb (livespec-zs22.8.2) ([38072c2](https://github.com/thewoolleyman/livespec-dev-tooling/commit/38072c2f160b47412b7518efc2a668775e828cb5))


### Bug Fixes

* document fleet wiring uv path wrapper ([b82ad8b](https://github.com/thewoolleyman/livespec-dev-tooling/commit/b82ad8b7f5a5843b9435bfd18e9d0c163477fbd6))
* read fleet secret values from GitHub env projection ([9d06f02](https://github.com/thewoolleyman/livespec-dev-tooling/commit/9d06f0266a39a5a750205dc894e32b51f8c2a8c6))
* **subagent-stop-guard:** scope worktrees to those THIS agent CREATED, not merely mentioned ([230747a](https://github.com/thewoolleyman/livespec-dev-tooling/commit/230747aa4728df202830f20378f0765e309230cd))

## [0.28.1](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.28.0...v0.28.1) (2026-06-27)


### Bug Fixes

* **i05g:** bump-pin gates on consumer's own CI, not an in-Action just check ([c3fe66b](https://github.com/thewoolleyman/livespec-dev-tooling/commit/c3fe66b02d9feca79cf6b9532e33534a380f027e))

## [0.28.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.27.0...v0.28.0) (2026-06-27)


### Features

* **jzpx:** single-source branch-protection recipes via branch-protection.just (+ usd3 docstring fix) ([43912a9](https://github.com/thewoolleyman/livespec-dev-tooling/commit/43912a9693abc441b3aa5f63f33ff9e83fd0f395))

## [0.27.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.26.0...v0.27.0) (2026-06-27)


### Features

* **zs22.7.9:** ship worktree lifecycle recipes (worktree.just) as single-source package-data (W2c/.4) ([ad3ccf8](https://github.com/thewoolleyman/livespec-dev-tooling/commit/ad3ccf80645cde5eea6accb9b744d6d60c0e4997))

## [0.26.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.25.1...v0.26.0) (2026-06-27)


### Features

* **zs22.7.9.3:** ship worktree-discipline pack as package-data + installer ([a1f2633](https://github.com/thewoolleyman/livespec-dev-tooling/commit/a1f26330a8e2c435cc6b336b53e18f45ecba52c9))


### Bug Fixes

* **zs22.7.9.6:** drop copier_answers_commit from bump-pin autodiscovery ([f9b84a3](https://github.com/thewoolleyman/livespec-dev-tooling/commit/f9b84a3fc085b3782fe0310ac09ac47571d5af1b))

## [0.25.1](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.25.0...v0.25.1) (2026-06-27)


### Bug Fixes

* relocate driver-only plugin_structure out of the canonical checks/ set + fail soft (livespec-2exa) ([0057bd6](https://github.com/thewoolleyman/livespec-dev-tooling/commit/0057bd698e225fa1f48aa0795abc0cb80b79b8ff))

## [0.25.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.24.0...v0.25.0) (2026-06-27)


### Features

* strict byte-identity commit-refuse-hook verifier (zs22.7.9.5) ([03bfc93](https://github.com/thewoolleyman/livespec-dev-tooling/commit/03bfc93fed6b8b457c4090de8395f8abd2f4ed54))

## [0.24.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.23.0...v0.24.0) (2026-06-27)


### Features

* port check_plugin_structure into the dev-tooling package (zs22.7.9.2) ([ef6b9d5](https://github.com/thewoolleyman/livespec-dev-tooling/commit/ef6b9d5041bc0da6485e7e8596175ce7ec0c2500))


### Bug Fixes

* red_green_replay drops .py deletions from commit-msg and range checks ([2cde6c8](https://github.com/thewoolleyman/livespec-dev-tooling/commit/2cde6c873797a6fcf095a9455b9665863f2956ba))

## [0.23.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.22.0...v0.23.0) (2026-06-27)


### Features

* add console fleet repo class — scope pin-and-bump shim rows (zs22.7.8) ([1428d2d](https://github.com/thewoolleyman/livespec-dev-tooling/commit/1428d2d6929f0db22489ad3236a029e4e24d82a2))

## [0.22.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.21.2...v0.22.0) (2026-06-26)


### Features

* **checks:** require harnesses declaration fleet-wide (zs22.7.7 M6-g) ([8e41be2](https://github.com/thewoolleyman/livespec-dev-tooling/commit/8e41be2b118f84654fbc9b3a072af685d1cee266))
* **fleet:** report baseline harnesses-declaration conformance (zs22.7.7 M6-c) ([67c5080](https://github.com/thewoolleyman/livespec-dev-tooling/commit/67c5080858973232c2b431e095e6e469855f1954))

## [0.21.2](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.21.1...v0.21.2) (2026-06-26)


### Bug Fixes

* **ci:** bump cross-repo coordination reusable-workflow pins v0.17.0-&gt;v0.21.1 (livespec-2rab) ([32345ba](https://github.com/thewoolleyman/livespec-dev-tooling/commit/32345bab0afeed1fa26e551ed08b31ea91010ef6))

## [0.21.1](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.21.0...v0.21.1) (2026-06-26)


### Bug Fixes

* **ci:** fan-out reads fleet manifest via raw.githubusercontent.com (livespec-2rab) ([19e1603](https://github.com/thewoolleyman/livespec-dev-tooling/commit/19e16030f6b96440d731b4e25872eb5258188f19))

## [0.21.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.20.0...v0.21.0) (2026-06-26)


### Features

* **checks:** add cross-harness plugin-resolution Verifier (concern [#2](https://github.com/thewoolleyman/livespec-dev-tooling/issues/2)) ([80dab47](https://github.com/thewoolleyman/livespec-dev-tooling/commit/80dab475b00f00eded6d6f163641d4c7e12ef7f7))
* **checks:** assert AGENTS.md .ai/&lt;topic&gt;.md references resolve ([0353f79](https://github.com/thewoolleyman/livespec-dev-tooling/commit/0353f797a11663aa5dc2812f10d9498d4a8b8889))


### Bug Fixes

* **checks:** route plugin-resolution live smoke per-harness so codex does not mis-route through claude ([a31eb4f](https://github.com/thewoolleyman/livespec-dev-tooling/commit/a31eb4f499ffa135f4bf851c130c06cff389c197))

## [0.20.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.19.0...v0.20.0) (2026-06-26)


### Features

* **fleet:** accept manifest fleet key + parse adopters array ([74a4011](https://github.com/thewoolleyman/livespec-dev-tooling/commit/74a4011bf00217b9aa3e2ed74866336f00b71f3f))

## [0.19.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.18.0...v0.19.0) (2026-06-25)


### Features

* add baseline check profile and structural commit-refuse hook installer ([1018fdf](https://github.com/thewoolleyman/livespec-dev-tooling/commit/1018fdf0c21504043968659aea9b2705c9a8fd7e))


### Refactoring

* make the commit-refuse installer the sole canonical-body source (M2-1) ([8dac46b](https://github.com/thewoolleyman/livespec-dev-tooling/commit/8dac46b01a35a97af4b966704250921b1f6f67f1))

## [0.18.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.17.0...v0.18.0) (2026-06-25)


### Features

* **checks:** recognize the structural commit-refuse hook body ([de22d6a](https://github.com/thewoolleyman/livespec-dev-tooling/commit/de22d6afa3f7b7a944fff982962af898977bd72b))

## [0.17.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.16.0...v0.17.0) (2026-06-24)


### Features

* assert agent-instruction surface in the fleet contract (livespec-3yebgl) ([90f2cd5](https://github.com/thewoolleyman/livespec-dev-tooling/commit/90f2cd5ef1c14bdefe9744ad585b01358810476a))
* **fleet:** assert beads tenant-connection consistency across config sources (qg0f.2) ([693f11b](https://github.com/thewoolleyman/livespec-dev-tooling/commit/693f11b1ccc8810081522e08ff01fb80ed04ee8d))


### Bug Fixes

* add assert_merge_settings fleet conformance row ([1a5ee52](https://github.com/thewoolleyman/livespec-dev-tooling/commit/1a5ee5207f5235031c33fd4320c9b93c53bda3f4))
* add reconcile_merge_settings to wire-fleet-member ([3ebdd44](https://github.com/thewoolleyman/livespec-dev-tooling/commit/3ebdd4436f4cab1d046342077ac2844ce8ea3a8e))
* add strict_enabled fail branch to standalone branch_protection_alignment check ([e5cb8f4](https://github.com/thewoolleyman/livespec-dev-tooling/commit/e5cb8f44a91743ad7b584b38e5cd3d04901f3e64))
* **agent-hooks:** recognize ~/.worktrees/&lt;repo&gt;/&lt;branch&gt; in stop-guard ([d6564a6](https://github.com/thewoolleyman/livespec-dev-tooling/commit/d6564a64f763e64716e11a57a9fa3204f562d94c))
* drop dead pre-rename impl prefixes from RGR _IMPL_PREFIXES (qg0f.5) ([b9b8733](https://github.com/thewoolleyman/livespec-dev-tooling/commit/b9b8733b4a51ef92ad270bedd2b4608efe1d6e41))
* flag strict-enabled branch protection in fleet assert_branch_protection ([f0badc9](https://github.com/thewoolleyman/livespec-dev-tooling/commit/f0badc9e12568e6fb41623ab08425f8320f5da6e))
* migrate fleet terminology ([7dfc218](https://github.com/thewoolleyman/livespec-dev-tooling/commit/7dfc2186335dc889e53da55cac72b2831281d200))
* prefer livespec-orchestrator-git-jsonl canonical_branch key in no_stale_revise_branches (qg0f.5) ([8caf5f8](https://github.com/thewoolleyman/livespec-dev-tooling/commit/8caf5f8b408796d65dd0dd71908435404d3bc21e))
* read renamed livespec fleet manifest ([cc7e4e4](https://github.com/thewoolleyman/livespec-dev-tooling/commit/cc7e4e42634688dd6f451e3c8c48b96391c6b585))
* reconcile master branch protection with strict OFF ([2e896ff](https://github.com/thewoolleyman/livespec-dev-tooling/commit/2e896ff577ec3222afdcb5cad9379a0a8e7c6c6e))
* wire the merge-settings row into the fleet obligation table ([e21a2e7](https://github.com/thewoolleyman/livespec-dev-tooling/commit/e21a2e7d702f89249553386c4894a4f72396baf7))

## [0.16.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.15.0...v0.16.0) (2026-06-21)


### Features

* recognize livespec_orchestrator_* package dirs in RGR product-path detection ([e3a86bb](https://github.com/thewoolleyman/livespec-dev-tooling/commit/e3a86bb22acc9e3e1a66f0c72c3dff0aca686c19))

## [0.15.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.14.0...v0.15.0) (2026-06-21)


### Features

* flag test-spawned python subprocesses; steer to in-process main() (4i5) ([4df086f](https://github.com/thewoolleyman/livespec-dev-tooling/commit/4df086f1a3fdfb5f2812400e0d4a6fba3c909306))
* **parallel-check:** parallel dispatcher with core-budget cap and per-target timing ([cb353fc](https://github.com/thewoolleyman/livespec-dev-tooling/commit/cb353fcc42d7fb23c8f46db5b464d747fccde11b))
* relocate vendor_update into livespec_dev_tooling package ([b843ca3](https://github.com/thewoolleyman/livespec-dev-tooling/commit/b843ca360b138f68232e61afa2f46abc2d69941c))
* scope RGR Red-leg pytest by staged-path class (7us.6) ([689738b](https://github.com/thewoolleyman/livespec-dev-tooling/commit/689738b0f683c5a3a900ffd0787dbb00119a0b42))


### Bug Fixes

* exclude deleted impl files from check-coverage-incremental derive ([17b5c66](https://github.com/thewoolleyman/livespec-dev-tooling/commit/17b5c66414acb9884fd379fa3f5901e88667ad99))
* isolate per-target coverage data by construction in the parallel check dispatcher (cmn) ([9f9d910](https://github.com/thewoolleyman/livespec-dev-tooling/commit/9f9d910996133fb9d9cc62cd2e092b59d6d2858a))
* parse mutmut-3.x results + nested-layout staging cwd in check_mutation ([5a7be94](https://github.com/thewoolleyman/livespec-dev-tooling/commit/5a7be941c4dac37e75a3efcccfe3650533772076))
* serialize check-coverage-incremental after per-file-coverage (7us.6) ([62ab1f9](https://github.com/thewoolleyman/livespec-dev-tooling/commit/62ab1f96cf55ba14ccbe48acbf366beeec753f74))

## [0.14.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.13.0...v0.14.0) (2026-06-12)


### Features

* **agent-hooks:** block premature sub-agent turn-ends while a dispatch is in flight (7us.2) ([e27c560](https://github.com/thewoolleyman/livespec-dev-tooling/commit/e27c560d708778cb26f65710cf6fca2da200e90e))
* **agent-hooks:** deny run_in_background for gate commands (7us.2) ([f1011dd](https://github.com/thewoolleyman/livespec-dev-tooling/commit/f1011dd8449f432ae8fb5ec6dfef0b416416df8f))
* **green-token:** advisory pre-push green-token tree-hash short-circuit ([ad8445a](https://github.com/thewoolleyman/livespec-dev-tooling/commit/ad8445a6d7d9f1f71bd07fa66621763248a591aa))

## [0.13.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.12.1...v0.13.0) (2026-06-12)


### Features

* **fleet:** central fleet-conformance check (assert mode) ([181d704](https://github.com/thewoolleyman/livespec-dev-tooling/commit/181d7049c877ca2cbe521e755d0fc879d15dc97b))
* **fleet:** committed-file obligation rows (workflows, pin, gitlinks) ([7c1efe1](https://github.com/thewoolleyman/livespec-dev-tooling/commit/7c1efe1de8f419fa703ec3cfcd12d8e9670dcbec))
* **fleet:** GitHub-side state obligation rows (secrets, App, protection, topic) ([bdf1e54](https://github.com/thewoolleyman/livespec-dev-tooling/commit/bdf1e54fc91aff3dba09923273d77d9fa3c6f4c9))
* **fleet:** shared types + GitHub-access seam for the fleet contract ([dfbda0a](https://github.com/thewoolleyman/livespec-dev-tooling/commit/dfbda0a6275c9e4f4f6170ce824fb1c7c4b05c07))
* **fleet:** the shared contract definition (manifest + obligation table) ([3662c26](https://github.com/thewoolleyman/livespec-dev-tooling/commit/3662c26433ee641d93f617f98962ee7313a02a36))
* **fleet:** wire-fleet-member CLI (idempotent reconcile engine) ([55e9341](https://github.com/thewoolleyman/livespec-dev-tooling/commit/55e93412443f44065739cc112865c7ec16b36685))
* **fleet:** wire-fleet-member reconcile operations ([91076e1](https://github.com/thewoolleyman/livespec-dev-tooling/commit/91076e1f70291ac324dd23c3148c0d9b1c0f5332))
* gate Fabro sandbox image pins in lockstep with repo pins ([ea684ad](https://github.com/thewoolleyman/livespec-dev-tooling/commit/ea684ad0d3019fc81ee45ce77ff5e52a93b12d9e))


### Bug Fixes

* **check_coverage_incremental:** align derive mode with tests_mirror_pairing on underscore-private helpers ([c7c2bac](https://github.com/thewoolleyman/livespec-dev-tooling/commit/c7c2bacfd42d56d7ef13bc7bcbf11b18ef06cbef))
* **keyword_only_args:** exempt sort/sorted key= callables from kw-only check ([c5a8a4d](https://github.com/thewoolleyman/livespec-dev-tooling/commit/c5a8a4d8b66d921e3588810082f89202f3a8f694))

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
