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

## [1.43.1](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.43.0...v1.43.1) (2026-09-04)


### Bug Fixes

* **otel:** resolve build.env per lane and skip the endpoint-less CI-lane POST (livespec-dev-tooling-efqeip.2) ([cb4889a](https://github.com/thewoolleyman/livespec-dev-tooling/commit/cb4889ab42d7e9d0089e81f6be117891c788d094))

## [1.43.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.42.1...v1.43.0) (2026-09-04)


### Features

* **checks:** ci_gate_parity — enforce PR gate ≡ master gate (livespec-citqsd) ([6be4593](https://github.com/thewoolleyman/livespec-dev-tooling/commit/6be45934a5a3cfec922c27726997c16237149d6d))

## [1.42.1](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.42.0...v1.42.1) (2026-09-04)


### Bug Fixes

* **otel:** registry_hit reads an unreadable CARGO_HOME as absent instead of raising out of the cargo span (livespec-dev-tooling-efqeip.1) ([9f3a331](https://github.com/thewoolleyman/livespec-dev-tooling/commit/9f3a331d1d739ce94d08d4774612cd299f684497))

## [1.42.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.41.0...v1.42.0) (2026-09-04)


### Features

* **otel:** attach build.cache.sccache.* + build.cache.registry.hit to factory cargo spans ([c1584b8](https://github.com/thewoolleyman/livespec-dev-tooling/commit/c1584b83b93cda1237486fdc5137df6420f58d95))

## [1.41.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.40.2...v1.41.0) (2026-09-04)


### Features

* **ci-runner:** storage-layout/migrate-tier.sh — move a CI tier to new media by copy + relabel, fstab untouched (livespec-e2vcqf) ([2152319](https://github.com/thewoolleyman/livespec-dev-tooling/commit/21523197ec6bdd92591df5a60ff0195ae1f9aca4))

## [1.40.2](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.40.1...v1.40.2) (2026-09-04)


### Bug Fixes

* **ci-runner:** drop the warm-generation ownership step -- uv cannot use an unmapped-owner cache; record the open trust decision (livespec-lvtu) ([899cc80](https://github.com/thewoolleyman/livespec-dev-tooling/commit/899cc8036cf5076a04eaeac387c7fd77395c354c))

## [1.40.1](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.40.0...v1.40.1) (2026-09-02)


### Bug Fixes

* **ci-runner:** order the Kueue-webhook probe after the reconstruct chain at boot ([5b13939](https://github.com/thewoolleyman/livespec-dev-tooling/commit/5b13939e6692a3c3bc888ba9dd44fc56fbd76266))
* **ci-runner:** wait for the labeled node before patching churn-slot capacity ([7ad791c](https://github.com/thewoolleyman/livespec-dev-tooling/commit/7ad791c7a92ea7273e8eca9ca6bcfe0be66025f8))

## [1.40.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.39.1...v1.40.0) (2026-09-02)


### Features

* **ci-runner:** every boot rebuilds the full desired CI host config from git ([4de2427](https://github.com/thewoolleyman/livespec-dev-tooling/commit/4de2427d7c5a31903df8075546a90595e648a8f3))
* **ci-runner:** ship the last node-local state with no git source ([db6e416](https://github.com/thewoolleyman/livespec-dev-tooling/commit/db6e416624ff09b3c6b07ae079046fa8aa9fe1be))


### Bug Fixes

* **ci-runner:** provision-k3s.sh version check refused every re-run on an installed host ([e2a3437](https://github.com/thewoolleyman/livespec-dev-tooling/commit/e2a34379c83807e9bd8b3226fe0b98264aaa7aed))

## [1.39.1](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.39.0...v1.39.1) (2026-09-02)


### Bug Fixes

* **ci-runner:** count the reconstructed secret's keys correctly in inject-github-app-secret.sh ([a0b74cc](https://github.com/thewoolleyman/livespec-dev-tooling/commit/a0b74ccc45c8f366474757933a24b99847dd5a59))

## [1.39.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.38.1...v1.39.0) (2026-09-02)


### Features

* **ci-runner:** boot-time reinjection of arc-github-app-installation secret ([03dc339](https://github.com/thewoolleyman/livespec-dev-tooling/commit/03dc339f32a58de7f0722ad3113826620e94130e))
* **ci-runner:** reconstruct-on-boot converge for the CI cluster stack ([061b4db](https://github.com/thewoolleyman/livespec-dev-tooling/commit/061b4db7c55a34454944eb8352cd3056d1054266))
* **ci-runner:** switch secret reinjection to a local systemd-creds credstore model ([facd66c](https://github.com/thewoolleyman/livespec-dev-tooling/commit/facd66cafd134057e65c8d677b7097e1669f903a))

## [1.38.1](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.38.0...v1.38.1) (2026-09-02)


### Bug Fixes

* **ci-runner:** raise console maxRunners 16-&gt;64 to match the C=64 pool ([20a7c8a](https://github.com/thewoolleyman/livespec-dev-tooling/commit/20a7c8a99aab01cd8eaec1bce523c1a61c3166a3))
* **ci-runner:** raise livespec (local-ci) maxRunners 36-&gt;64 to match the C=64 pool ([d64effb](https://github.com/thewoolleyman/livespec-dev-tooling/commit/d64effbe763c28279dc410ec1ce26557cc7b215e))

## [1.38.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.37.1...v1.38.0) (2026-09-02)


### Features

* **ci-runner:** durable per-user inotify instance budget install mechanism ([a45e6be](https://github.com/thewoolleyman/livespec-dev-tooling/commit/a45e6be4d7e33722007eba4cdde6f5b4dbf77d49))

## [1.37.1](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.37.0...v1.37.1) (2026-09-01)


### Bug Fixes

* **factory:** make cargo shim survive a consumer .mise.toml ~/.cargo/bin prepend ([14763b2](https://github.com/thewoolleyman/livespec-dev-tooling/commit/14763b26762a9eb095944fb1adebeb35b2a2f8eb))

## [1.37.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.36.0...v1.37.0) (2026-08-31)


### Features

* **factory:** emit build.env=factory cargo-phase telemetry spans ([239378b](https://github.com/thewoolleyman/livespec-dev-tooling/commit/239378b4a8da0fc9627d07a103116d2892e922ab))

## [1.36.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.35.0...v1.36.0) (2026-08-28)


### Features

* **ci-runner:** emit host and kubepods I/O-stall gauges from the heartbeat ([9db4eff](https://github.com/thewoolleyman/livespec-dev-tooling/commit/9db4effcde68b6248a3f3e8768da0440fbf1c4fd))

## [1.35.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.34.0...v1.35.0) (2026-08-26)


### Features

* **fabro-sandbox:** succeed the baked Codex ACP adapter with @agentclientprotocol/codex-acp ([43a4901](https://github.com/thewoolleyman/livespec-dev-tooling/commit/43a4901f235541e34b1e7944fc87ad3ba5a139b1))

## [1.34.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.33.1...v1.34.0) (2026-08-26)


### Features

* **workflow-checks:** model the invocation set in release_bump_classification ([b54f5dd](https://github.com/thewoolleyman/livespec-dev-tooling/commit/b54f5ddc562efc904b9aa548ef6722811c47d01b))

## [1.33.1](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.33.0...v1.33.1) (2026-08-26)


### Bug Fixes

* **workflow-checks:** reference the spec at file level, not heading level ([c1ff9fa](https://github.com/thewoolleyman/livespec-dev-tooling/commit/c1ff9fa9df563a5e3a82660fabdedacb764edfc6))

## [1.33.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.32.1...v1.33.0) (2026-08-26)


### Features

* **workflow-checks:** bind the ratified version classification to the computed release bump ([c973d8e](https://github.com/thewoolleyman/livespec-dev-tooling/commit/c973d8e7852e6c8f6e89e4fb8040cb5147ff3336))

## [1.32.1](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.32.0...v1.32.1) (2026-08-23)


### Bug Fixes

* **ci-runner:** run k3s workflow pods in a user namespace (livespec-s43svm.44) ([dda8ee3](https://github.com/thewoolleyman/livespec-dev-tooling/commit/dda8ee3ace294040c85b53d6698dddb3b4812296))

## [1.32.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.31.1...v1.32.0) (2026-08-21)


### Features

* assert every governed member declares a foreman valve disposition ([bc980fc](https://github.com/thewoolleyman/livespec-dev-tooling/commit/bc980fca0fbbbfa2be736c1f5f71d7c1fd701e40))

## [1.31.1](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.31.0...v1.31.1) (2026-08-20)


### Bug Fixes

* **fleet:** the armed decision-authority row documented itself as disarmed ([bb29e7f](https://github.com/thewoolleyman/livespec-dev-tooling/commit/bb29e7f8ff1614d35c038d11117013cd14efe6fa))

## [1.31.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.30.0...v1.31.0) (2026-08-20)


### Features

* **fleet:** arm the decision-authority AGENTS.md row ([5cfd759](https://github.com/thewoolleyman/livespec-dev-tooling/commit/5cfd759573350f6f18aef71b3bea04c851acbfd2))

## [1.30.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.29.3...v1.30.0) (2026-08-20)


### Features

* **fleet:** author the decision-authority AGENTS.md row, shipped disarmed ([1c2aa2d](https://github.com/thewoolleyman/livespec-dev-tooling/commit/1c2aa2dd76c5077377265c3a18e58fb5902901c5))

## [1.29.3](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.29.2...v1.29.3) (2026-08-20)


### Bug Fixes

* **cross-repo:** mirror adopted slugs into the batched ci.yml aggregate form ([b641901](https://github.com/thewoolleyman/livespec-dev-tooling/commit/b641901f55560f3fccf151b2f8723cffa7093812))

## [1.29.2](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.29.1...v1.29.2) (2026-08-20)


### Bug Fixes

* discover Claude marketplace source ref pins ([d7b5b8b](https://github.com/thewoolleyman/livespec-dev-tooling/commit/d7b5b8ba8d5a417da22ae89b48118fc8007a7dbf))

## [1.29.1](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.29.0...v1.29.1) (2026-08-19)


### Bug Fixes

* **cross-repo:** reconcile the inventory the aggregate gate actually reads ([cee1b28](https://github.com/thewoolleyman/livespec-dev-tooling/commit/cee1b282ac15211a0190d75d8431a13c14baa4e1))

## [1.29.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.28.13...v1.29.0) (2026-08-19)


### Features

* **checks:** self-hosted-routing workflows must bound uv fetch concurrency ([a47c0bf](https://github.com/thewoolleyman/livespec-dev-tooling/commit/a47c0bf5707a4c5d82259d35cd831d1a5884a3c2))

## [1.28.13](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.28.12...v1.28.13) (2026-08-19)


### Bug Fixes

* ignore installed worktree pack files ([971e2f2](https://github.com/thewoolleyman/livespec-dev-tooling/commit/971e2f22f1f89812f25f858b39a55c187c7a14c6))

## [1.28.12](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.28.11...v1.28.12) (2026-08-19)


### Refactoring

* **rop:** dispatch defects_in detectors directly instead of through the registry ([1f276e1](https://github.com/thewoolleyman/livespec-dev-tooling/commit/1f276e1094011f84b3cb6ada4b821fe332c90d8e))

## [1.28.11](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.28.10...v1.28.11) (2026-08-19)


### Bug Fixes

* **rop:** return charters_in on the IOResult railway ([531d798](https://github.com/thewoolleyman/livespec-dev-tooling/commit/531d798a2e536525843a7f11f9e80775406a544c))

## [1.28.10](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.28.9...v1.28.10) (2026-08-19)


### Bug Fixes

* **ci-runner:** give ARC workflow pods an AppArmor profile that permits intra-pod ptrace and signal ([2ebebf9](https://github.com/thewoolleyman/livespec-dev-tooling/commit/2ebebf98139dbf769b4d6ef15be9ed389b867622))
* **rop:** return canonical_check_renames on the IOResult railway ([39c408b](https://github.com/thewoolleyman/livespec-dev-tooling/commit/39c408bec5bb9d9816dd051e48fca1a4e773f6ca))

## [1.28.9](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.28.8...v1.28.9) (2026-08-18)


### Bug Fixes

* **fleet:** repair incomplete plugin caches ([5c5ad18](https://github.com/thewoolleyman/livespec-dev-tooling/commit/5c5ad18aa3bcb5e21de1479b56aa0a8de8c0daf1))

## [1.28.8](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.28.7...v1.28.8) (2026-08-18)


### Bug Fixes

* port charter detector drift ([45a51ec](https://github.com/thewoolleyman/livespec-dev-tooling/commit/45a51ec40af2016d6192142f2712152821e0c9d8))

## [1.28.7](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.28.6...v1.28.7) (2026-08-18)


### Bug Fixes

* **ci:** update check-per-file-coverage/check-coverage needs off the retired select-ci-runner job ([a540ccb](https://github.com/thewoolleyman/livespec-dev-tooling/commit/a540ccb317ddcb5b33fd8ef28737ca11f1be7708))
* **fleet:** paginate the App installation-repositories read ([164804a](https://github.com/thewoolleyman/livespec-dev-tooling/commit/164804adcdf88ffa34d19310aff461e7904f84dc))

## [1.28.6](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.28.5...v1.28.6) (2026-08-18)


### Bug Fixes

* **ci:** restore the node-PATH shim in the coverage-pair producer/consumer jobs ([395589e](https://github.com/thewoolleyman/livespec-dev-tooling/commit/395589ed69b19560f8ab79574da3716667e1de7c))

## [1.28.5](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.28.4...v1.28.5) (2026-08-17)


### Bug Fixes

* **master-ci:** classify rejected gh credentials ([c3e1ca7](https://github.com/thewoolleyman/livespec-dev-tooling/commit/c3e1ca7550ab331aeb39e2ce0d06d18f479d8da7))

## [1.28.4](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.28.3...v1.28.4) (2026-08-17)


### Bug Fixes

* **checks:** reject pi zero-exit model failures ([9c5472e](https://github.com/thewoolleyman/livespec-dev-tooling/commit/9c5472e1aea5b994c2b850a9f7e89df947e46315))
* paginate fleet discovery sweep ([3963358](https://github.com/thewoolleyman/livespec-dev-tooling/commit/3963358c0cd5c1d9988e3dc6fd7dbb3366ac7cf1))

## [1.28.3](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.28.2...v1.28.3) (2026-08-17)


### Bug Fixes

* **dev-tooling:** add canonical_check_renames() RED test ([5be1ac1](https://github.com/thewoolleyman/livespec-dev-tooling/commit/5be1ac1b48299cf8058ec4cc2e5326297d684ddd))
* **dev-tooling:** add ci.yml reconcile rename-rewrite RED test ([9872764](https://github.com/thewoolleyman/livespec-dev-tooling/commit/9872764e0a3f4c6c421a28d5938651b289e18b56))
* **dev-tooling:** add justfile reconcile rename-rewrite RED test ([af64976](https://github.com/thewoolleyman/livespec-dev-tooling/commit/af649766263dd1e3fe22476a9f01c31cabee82ed))
* **dev-tooling:** cover renamed-slug no-op and hand-authored-recipe branches ([213a877](https://github.com/thewoolleyman/livespec-dev-tooling/commit/213a8771fe2382d5aeb481cc185200835f2524cf))

## [1.28.2](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.28.1...v1.28.2) (2026-08-17)


### Bug Fixes

* **docs:** correct the false k3s real-traffic cutover claim in AGENTS.md ([4857770](https://github.com/thewoolleyman/livespec-dev-tooling/commit/4857770c00550f6fd6e5f7e2478f7510dcf5b558))

## [1.28.1](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.28.0...v1.28.1) (2026-08-17)


### Bug Fixes

* verify ensured plugin artifacts ([11938bb](https://github.com/thewoolleyman/livespec-dev-tooling/commit/11938bb46cb1d8c63c149f7ba737aaed3e8e036c))

## [1.28.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.27.1...v1.28.0) (2026-08-17)


### Features

* support pi plugin resolution harness ([01b4a39](https://github.com/thewoolleyman/livespec-dev-tooling/commit/01b4a39f251327c07a0bbce015a623415ed58c9e))

## [1.27.1](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.27.0...v1.27.1) (2026-08-17)


### Bug Fixes

* **ci-runner:** shorten ARC scale-set names below the 63-char workflow-pod limit ([1409bbf](https://github.com/thewoolleyman/livespec-dev-tooling/commit/1409bbfe13d6f24040657dc36e3ed809ced9ef5e))

## [1.27.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.26.0...v1.27.0) (2026-08-17)


### Features

* **worktree-pack:** ship the detached gate runner as a fifth pack file ([34f7af0](https://github.com/thewoolleyman/livespec-dev-tooling/commit/34f7af06d6d8767eff79d8e91262b8caad212fa8))

## [1.26.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.25.0...v1.26.0) (2026-08-17)


### Features

* **ci:** batch the cheap checks — 60 matrix jobs become 5 gating jobs ([547895f](https://github.com/thewoolleyman/livespec-dev-tooling/commit/547895f8a378aab97f6299270dbba5f6b8a50ccb))


### Bug Fixes

* **ci:** keep tool-backed lint/format as literal matrix legs ([bfdbe43](https://github.com/thewoolleyman/livespec-dev-tooling/commit/bfdbe435788f0dfb95428031c0d32f8f0aabc6d2))

## [1.25.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.24.9...v1.25.0) (2026-08-17)


### Features

* **telemetry:** export per-job queue time to Honeycomb (ci.job.queue_ms) ([5e4af91](https://github.com/thewoolleyman/livespec-dev-tooling/commit/5e4af91d749e78120c3d34068019e517e01909d3))

## [1.24.9](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.24.8...v1.24.9) (2026-08-17)


### Bug Fixes

* **ci-runner:** route dockershim podman calls through the daemon, not local SQLite ([7b6d75b](https://github.com/thewoolleyman/livespec-dev-tooling/commit/7b6d75bdaccd01934cd29f073cd235a80c24a111))

## [1.24.8](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.24.7...v1.24.8) (2026-08-16)


### Bug Fixes

* **check:** dedup the full pytest suite via a clean-env coverage producer ([4caf7f5](https://github.com/thewoolleyman/livespec-dev-tooling/commit/4caf7f592f151376d081220a311333dec6e515e1))

## [1.24.7](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.24.6...v1.24.7) (2026-08-16)


### Bug Fixes

* **pre-commit:** wire repo-state checks into the doc-only subset ([21fbd8a](https://github.com/thewoolleyman/livespec-dev-tooling/commit/21fbd8ac0657a10535f6edb78977cc370a0f8b3d))

## [1.24.6](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.24.5...v1.24.6) (2026-08-16)


### Bug Fixes

* **dev-tooling:** retire 'plan thread' vocabulary in check module names, slugs, and shipped output ([89aa3a9](https://github.com/thewoolleyman/livespec-dev-tooling/commit/89aa3a995f873d6ae64675cf14d04b219aed6595))

## [1.24.5](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.24.4...v1.24.5) (2026-08-16)


### Bug Fixes

* **gate-run:** preflight-install the worktree pack before a gate run ([4e0a7e3](https://github.com/thewoolleyman/livespec-dev-tooling/commit/4e0a7e3a3683bb379a52c23e821f12536d2b6216))

## [1.24.4](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.24.3...v1.24.4) (2026-08-16)


### Bug Fixes

* **dev-tooling:** re-derive plan-lifecycle checks against the ratified Planning Lane contract ([6c38d0b](https://github.com/thewoolleyman/livespec-dev-tooling/commit/6c38d0b8401e0460306401612072473d89053450))

## [1.24.3](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.24.2...v1.24.3) (2026-08-16)


### Bug Fixes

* **ci-runner:** target the ARC scale set by name, not a label array ([ece8085](https://github.com/thewoolleyman/livespec-dev-tooling/commit/ece80853ed98297aa2ce1106d94c369bc3da0880))

## [1.24.2](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.24.1...v1.24.2) (2026-08-16)


### Bug Fixes

* **ci-runner:** scope ARC githubConfigUrl to a repository, not account-root ([2372b03](https://github.com/thewoolleyman/livespec-dev-tooling/commit/2372b03e61eee565226ffe54baa8d2989fff4c93))

## [1.24.1](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.24.0...v1.24.1) (2026-08-15)


### Bug Fixes

* **ci-runner:** install-arc.sh pre-gate checks the wrong namespace for the ARC secret ([3fbb35f](https://github.com/thewoolleyman/livespec-dev-tooling/commit/3fbb35f7a29de82f8181914de5c601d9386f3f26))

## [1.24.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.23.3...v1.24.0) (2026-08-15)


### Features

* **ci-runner:** provision k3s + ARC + Kueue alongside the podman pool ([427abef](https://github.com/thewoolleyman/livespec-dev-tooling/commit/427abef90bc171f8081e0de7e9426a995000b3f3))

## [1.23.3](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.23.2...v1.23.3) (2026-08-15)


### Bug Fixes

* **ci-runner:** migrate podman libpod state db to SQLite WAL mode ([d662f1f](https://github.com/thewoolleyman/livespec-dev-tooling/commit/d662f1fbfc20e2ed25cb4886b17f9397efe98afc))

## [1.23.2](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.23.1...v1.23.2) (2026-08-15)


### Bug Fixes

* **ci-runner:** add mid-job dockershim wedge-guard backstop ([658cc02](https://github.com/thewoolleyman/livespec-dev-tooling/commit/658cc02aa12af9f6a6515c9b5dd086e13bae4ad1))

## [1.23.1](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.23.0...v1.23.1) (2026-08-15)


### Bug Fixes

* teach plan checks migrated planning lane ([ac51e45](https://github.com/thewoolleyman/livespec-dev-tooling/commit/ac51e45cd239d5202c77c02a098b57ba5f937dd4))

## [1.23.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.22.0...v1.23.0) (2026-08-14)


### Features

* distinguish saturation from outage in CI runner failover probe ([d366476](https://github.com/thewoolleyman/livespec-dev-tooling/commit/d366476065504795c402a213c71793989f375b93))

## [1.22.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.21.1...v1.22.0) (2026-08-14)


### Features

* **ci:** guard reusable runner router triggers ([ecf0504](https://github.com/thewoolleyman/livespec-dev-tooling/commit/ecf05040452cb3edfa258f7e9285a677e9e6c66a))

## [1.21.1](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.21.0...v1.21.1) (2026-08-13)


### Bug Fixes

* **ci-runner:** raise dockershim exec retry from 3 to 10 attempts for podman SQLite race ([a283d7f](https://github.com/thewoolleyman/livespec-dev-tooling/commit/a283d7f0704fe58bf3941addc20645206c184186))

## [1.21.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.20.9...v1.21.0) (2026-08-13)


### Features

* **ci-runner:** support per-repo slot counts in the supervisor ([775728c](https://github.com/thewoolleyman/livespec-dev-tooling/commit/775728c34857ec71dddb2ecdbc7363b8e82fb9c0))

## [1.20.9](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.20.8...v1.20.9) (2026-08-13)


### Bug Fixes

* **ci-runner:** retry the masked podman SQLite exec-state race ([4cdcc73](https://github.com/thewoolleyman/livespec-dev-tooling/commit/4cdcc73d4995ec9d73591f9abf7a522cb82b9d85))
* **ci:** bake every declared tool into the sandbox image ([c46ad38](https://github.com/thewoolleyman/livespec-dev-tooling/commit/c46ad381316bf6beeedde8ac90d91932a25c5c5e))
* **ci:** retry every dependency fetch in the sandbox image build ([6784850](https://github.com/thewoolleyman/livespec-dev-tooling/commit/678485038741b33a6074a22cf2265bbfb8f71f38))
* **ci:** retry mise fetches from the GitHub releases CDN ([bb50c8b](https://github.com/thewoolleyman/livespec-dev-tooling/commit/bb50c8bb80e391333cf42afaf5024ed2fa346238))

## [1.20.8](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.20.7...v1.20.8) (2026-08-13)


### Bug Fixes

* **ci-runner:** create missing bind sources, as dockerd would ([d712b7b](https://github.com/thewoolleyman/livespec-dev-tooling/commit/d712b7bcaf4ac7b2aefcb54d279dd6b9fcca11e0))
* **ci-runner:** preserve the ORIGINAL HOME baked into a bare -e HOME at create ([e877c3e](https://github.com/thewoolleyman/livespec-dev-tooling/commit/e877c3e7210ae7ca6a7232c444ccc362399de881))

## [1.20.7](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.20.6...v1.20.7) (2026-08-13)


### Bug Fixes

* reject archived regroomed anchors with open descendants ([fe9921d](https://github.com/thewoolleyman/livespec-dev-tooling/commit/fe9921dfe0165566a3045716d07c8f4fa5a4c332))

## [1.20.6](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.20.5...v1.20.6) (2026-08-13)


### Bug Fixes

* **ci-runner:** copy run-helper.sh.template, not run-helper.sh, into instance dirs ([df8d45a](https://github.com/thewoolleyman/livespec-dev-tooling/commit/df8d45ae4e34512519fd3b5c8ac0b2359a75c03b))
* **ci-runner:** install podman-docker, without which every containerized job dies ([4319f8a](https://github.com/thewoolleyman/livespec-dev-tooling/commit/4319f8a2df793b36d5e7afdcd1924c461b44d93c))
* **ci-runner:** repair the scrubbed environment the container hooks hand podman ([d67265c](https://github.com/thewoolleyman/livespec-dev-tooling/commit/d67265c6889771bdaaf5c18e206d7b6563dde679))
* **ci-runner:** stop provisioning racing the user manager, and the exit suite failing on cwd ([d0dc8f7](https://github.com/thewoolleyman/livespec-dev-tooling/commit/d0dc8f799fd4c0a49a6d5d54a62c4e39489b8b29))

## [1.20.5](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.20.4...v1.20.5) (2026-08-12)


### Bug Fixes

* assert the converse — an archived thread may not name an open epic ([201cabb](https://github.com/thewoolleyman/livespec-dev-tooling/commit/201cabbdfb7f8626e4097093d3f7a2d315f0fad6))

## [1.20.4](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.20.3...v1.20.4) (2026-08-07)


### Bug Fixes

* **checks:** no_lloc_soft_warnings release tier narrows to unowned files ([6e0efb5](https://github.com/thewoolleyman/livespec-dev-tooling/commit/6e0efb5d5d6b6338d318326cad4f77cbee2e46f0))

## [1.20.3](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.20.2...v1.20.3) (2026-08-07)


### Bug Fixes

* **checks:** no_todo_registry release tier narrows to unowned entries ([dd5112e](https://github.com/thewoolleyman/livespec-dev-tooling/commit/dd5112e3fe5d46334935553fa3c0a0c3df1481f3))

## [1.20.2](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.20.1...v1.20.2) (2026-08-06)


### Bug Fixes

* stop detector (d) flagging a capture-free search accumulator ([23cf9ae](https://github.com/thewoolleyman/livespec-dev-tooling/commit/23cf9ae2f07866fd48270d443772f9afb1e80388))

## [1.20.1](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.20.0...v1.20.1) (2026-08-05)


### Bug Fixes

* **fleet:** grade the self member from its local checkout ([6072318](https://github.com/thewoolleyman/livespec-dev-tooling/commit/607231840e09c125e6b869ab5d008f60907738d2))

## [1.20.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.19.9...v1.20.0) (2026-08-05)


### Features

* expose importable charter-defect detectors ([61048d7](https://github.com/thewoolleyman/livespec-dev-tooling/commit/61048d7731ee24fd5235b608eeb826841e6831a2))

## [1.19.9](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.19.8...v1.19.9) (2026-08-05)


### Bug Fixes

* accept formatted plan thread anchors ([f1e19f7](https://github.com/thewoolleyman/livespec-dev-tooling/commit/f1e19f7045454861c65a6143cdf589854c0ed435))

## [1.19.8](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.19.7...v1.19.8) (2026-08-05)


### Bug Fixes

* **gate:** point the background-guard deny at the detached runner ([b2e08c2](https://github.com/thewoolleyman/livespec-dev-tooling/commit/b2e08c20858fe632b509d1bf1442c154208e3ed7))

## [1.19.7](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.19.6...v1.19.7) (2026-08-05)


### Bug Fixes

* **cross-repo:** recognise every fleet aggregate layout in the ShellCheck pin gate ([9263274](https://github.com/thewoolleyman/livespec-dev-tooling/commit/926327449e98353390002bfca543deddb345be7a))
* **cross-repo:** treat a delegated-script aggregate as wired in the ShellCheck pin gate ([0af74ad](https://github.com/thewoolleyman/livespec-dev-tooling/commit/0af74ad672103d6f4a495d77de7f30bfbab7893d))

## [1.19.6](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.19.5...v1.19.6) (2026-08-04)


### Bug Fixes

* **checks:** restore the pure_trees gate on public_api_result_typed ([f424711](https://github.com/thewoolleyman/livespec-dev-tooling/commit/f424711063b9a69134c11908b0bb0f8815df092a))

## [1.19.5](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.19.4...v1.19.5) (2026-08-04)


### Bug Fixes

* cover shellcheck pin gate behavior ([ac5defd](https://github.com/thewoolleyman/livespec-dev-tooling/commit/ac5defd15efdd764f71ff67984792fde89aad527))
* fail closed on ungated shellcheck pin ([5800b1f](https://github.com/thewoolleyman/livespec-dev-tooling/commit/5800b1f82bfd4a762c6b76d614e2de6277bd5618))

## [1.19.4](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.19.3...v1.19.4) (2026-08-04)


### Bug Fixes

* require a real errexit rationale for the deviation exemption ([1969bc8](https://github.com/thewoolleyman/livespec-dev-tooling/commit/1969bc85f08546ddca2771b532f74fdfdf579800))

## [1.19.3](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.19.2...v1.19.3) (2026-08-04)


### Bug Fixes

* **checks:** guard consumer-declared self-hosted labels and fail-open routing ([70ec288](https://github.com/thewoolleyman/livespec-dev-tooling/commit/70ec2887f1bf058833c1016100eb0bf0bd794440))

## [1.19.2](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.19.1...v1.19.2) (2026-08-04)


### Bug Fixes

* degrade when claude binary is absent ([4edf171](https://github.com/thewoolleyman/livespec-dev-tooling/commit/4edf171d13dd3dfbef530a99f5308783b83d6797))

## [1.19.1](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.19.0...v1.19.1) (2026-08-04)


### Bug Fixes

* derive plan epic parity tenant prefix ([e81cde7](https://github.com/thewoolleyman/livespec-dev-tooling/commit/e81cde7f090ea73f5d07093fa8a546e917cf7ebe))

## [1.19.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.18.9...v1.19.0) (2026-08-04)


### Features

* ban plan thread tombstones ([2fadd5f](https://github.com/thewoolleyman/livespec-dev-tooling/commit/2fadd5f4536258db6dfee2dea6d4ce6bc6becd95))

## [1.18.9](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.18.8...v1.18.9) (2026-08-04)


### Bug Fixes

* **fabro-sandbox:** track gh 2.97.0 — upstream apt dropped 2.96.0 ([e12b4c9](https://github.com/thewoolleyman/livespec-dev-tooling/commit/e12b4c9e2448005c94f962e16ff2a894fd7dcf92))

## [1.18.8](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.18.7...v1.18.8) (2026-08-04)


### Bug Fixes

* **checks:** scan the first-party universe, not pure_trees ([46c5dab](https://github.com/thewoolleyman/livespec-dev-tooling/commit/46c5daba53b71f9b1cc3143d9f42393689e28578))

## [1.18.7](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.18.6...v1.18.7) (2026-08-04)


### Bug Fixes

* **actions:** project tag-matched ShellCheck pin ([8088022](https://github.com/thewoolleyman/livespec-dev-tooling/commit/808802220ed47ce4ff8a463742d2821a53df4182))
* emit missing shellcheck quality finding ([25735f0](https://github.com/thewoolleyman/livespec-dev-tooling/commit/25735f04db98136106b8cf8ad4fa6bbce9aab33a))
* report missing shellcheck as domain failure ([b422da4](https://github.com/thewoolleyman/livespec-dev-tooling/commit/b422da443c44d86f45689233db7aa3ffbb4f4402))

## [1.18.6](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.18.5...v1.18.6) (2026-08-04)


### Bug Fixes

* **fleet:** pace the gh seam across the sweep, owned by the runner object ([da4add6](https://github.com/thewoolleyman/livespec-dev-tooling/commit/da4add6c3ad5b9944f04f548e8d051fea9cc751c))

## [1.18.5](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.18.4...v1.18.5) (2026-08-03)


### Bug Fixes

* **fleet:** retry a rate-limited gh invocation at the seam, bounded ([ab72840](https://github.com/thewoolleyman/livespec-dev-tooling/commit/ab7284093e913034ce4729ca08d2592dfe1804f3))

## [1.18.4](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.18.3...v1.18.4) (2026-08-03)


### Bug Fixes

* **shell-quality:** keep empty corpus fail closed ([cddb989](https://github.com/thewoolleyman/livespec-dev-tooling/commit/cddb989ea8d60de6dee1888fae75253654263e88))
* **worktree-pack:** cover bootstrapped shell-quality pack ([9feeef5](https://github.com/thewoolleyman/livespec-dev-tooling/commit/9feeef5f272134165530d322fb0551938a31382c))

## [1.18.3](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.18.2...v1.18.3) (2026-08-03)


### Bug Fixes

* **checks:** read `replace` by arity so pure string calls stop counting as I/O ([66bf5ae](https://github.com/thewoolleyman/livespec-dev-tooling/commit/66bf5aea211ac246bd4357b860ef88b09e5276fe))

## [1.18.2](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.18.1...v1.18.2) (2026-08-03)


### Bug Fixes

* **worktree-pack:** pass worktree recipe arguments positionally, not by interpolation ([867d57e](https://github.com/thewoolleyman/livespec-dev-tooling/commit/867d57e6dd5d8ef6674a840f19bcef3a74645e65))

## [1.18.1](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.18.0...v1.18.1) (2026-08-03)


### Bug Fixes

* **checks:** enforce thin justfile shell surfaces ([20a43f8](https://github.com/thewoolleyman/livespec-dev-tooling/commit/20a43f85cad2eb6fc6ad1d2b04f506a31f82e305))

## [1.18.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.17.1...v1.18.0) (2026-08-03)


### Features

* **checks:** encode shell quality policy ([406540c](https://github.com/thewoolleyman/livespec-dev-tooling/commit/406540ce39799572bf9d402f910f436521249399))


### Bug Fixes

* **checks:** enforce shell quality recipes ([df92e0b](https://github.com/thewoolleyman/livespec-dev-tooling/commit/df92e0bbac9442960e76996f56b0be258aab823e))

## [1.17.1](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.17.0...v1.17.1) (2026-08-03)


### Bug Fixes

* validate final GitHub App token budget ([db32737](https://github.com/thewoolleyman/livespec-dev-tooling/commit/db327372c585b06636d787b270d456d46f27b1a8))

## [1.17.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.16.1...v1.17.0) (2026-08-03)


### Features

* **spec:** require final-token budget validation ([391e8c2](https://github.com/thewoolleyman/livespec-dev-tooling/commit/391e8c253696da9d645ae3346c4d7f8fb397c2ae))

## [1.16.1](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.16.0...v1.16.1) (2026-08-03)


### Bug Fixes

* **ci:** gate GitHub App rate budget ([c7b4c85](https://github.com/thewoolleyman/livespec-dev-tooling/commit/c7b4c85aa5671c24fe802f6e714ce26660e4681c))

## [1.16.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.15.1...v1.16.0) (2026-08-03)


### Features

* add GitHub App rate budget gate ([c792eb5](https://github.com/thewoolleyman/livespec-dev-tooling/commit/c792eb51693db72284431189f7c9770960582f38))

## [1.15.1](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.15.0...v1.15.1) (2026-08-03)


### Bug Fixes

* **checks:** resolve clause (d) call edges through re-export shims ([4983487](https://github.com/thewoolleyman/livespec-dev-tooling/commit/4983487c1a37bfa759c6a3db5a5ece93d61ab068))

## [1.15.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.14.6...v1.15.0) (2026-08-03)


### Features

* classify justfile Bash recipe evidence ([8f071bc](https://github.com/thewoolleyman/livespec-dev-tooling/commit/8f071bcb20c224ae82170b3c926754cb34e16510))

## [1.14.6](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.14.5...v1.14.6) (2026-08-02)


### Bug Fixes

* **vendor:** resolve the re-vendor destination from the git index ([6deca80](https://github.com/thewoolleyman/livespec-dev-tooling/commit/6deca806e9f5a132a2a47c24efcc53183da4ba90))

## [1.14.5](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.14.4...v1.14.5) (2026-08-02)


### Bug Fixes

* **docker:** default chain image args ([98cbd83](https://github.com/thewoolleyman/livespec-dev-tooling/commit/98cbd83101fc0c939636aa6b04f30343b68f2b7a))

## [1.14.4](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.14.3...v1.14.4) (2026-08-02)


### Bug Fixes

* **ci:** document the Node 24 runner floor ([6b7daae](https://github.com/thewoolleyman/livespec-dev-tooling/commit/6b7daaefc66e8b6ac866ad50f2ad50d40270dde7))

## [1.14.3](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.14.2...v1.14.3) (2026-08-02)


### Bug Fixes

* **checks:** mechanize v186 — a discharging narrow try is not a failure mode ([8ce991a](https://github.com/thewoolleyman/livespec-dev-tooling/commit/8ce991a722df6b19d5aa153aec6616ee8b296ad9))

## [1.14.2](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.14.1...v1.14.2) (2026-08-02)


### Bug Fixes

* **checks:** exempt os.path's lexical members from clause (c) ([373e8f6](https://github.com/thewoolleyman/livespec-dev-tooling/commit/373e8f697d721d9b310a681a9dc9a329f3ce3725))

## [1.14.1](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.14.0...v1.14.1) (2026-08-02)


### Bug Fixes

* **fleet:** give LocalContext a railway-typed PREDICATE seam ([4cd7cd0](https://github.com/thewoolleyman/livespec-dev-tooling/commit/4cd7cd0ed73e2368dfa680016df7066b822b9885))
* **fleet:** probe the beads directory through the predicate seam ([59e429c](https://github.com/thewoolleyman/livespec-dev-tooling/commit/59e429c17461dbe01ea351b7368237306885bd65))
* **fleet:** route every beads probe through the predicate seam ([2b30f4e](https://github.com/thewoolleyman/livespec-dev-tooling/commit/2b30f4eb0e124a142c6d3295c0d273d960225dc1))

## [1.14.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.13.24...v1.14.0) (2026-08-02)


### Features

* **checks:** consult the v183 condition-3 carrier in public_api_result_typed ([68a099a](https://github.com/thewoolleyman/livespec-dev-tooling/commit/68a099acb0b1003ecca82582e523ae502e2e6839))
* **checks:** recompute v183's structural gate for single_meaning_variants ([6df97c4](https://github.com/thewoolleyman/livespec-dev-tooling/commit/6df97c43345c9fe399b7ff59126dfc4d46ef2d7c))
* **config:** carry livespec v183 condition 3 in a single_meaning_variants key ([a5d99e9](https://github.com/thewoolleyman/livespec-dev-tooling/commit/a5d99e9eaf9a1c79e93deaa04bdfbf021edfd02c))
* **fleet:** report v183 bound 4 — declared unions AND the functions relieved ([2fe61c9](https://github.com/thewoolleyman/livespec-dev-tooling/commit/2fe61c909d41cc7f0ff555c7a4c0b4e26cfc86e2))

## [1.13.24](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.13.23...v1.13.24) (2026-08-02)


### Bug Fixes

* **checks:** carry every failable I/O primitive in the unresolved-receiver set ([e51b37f](https://github.com/thewoolleyman/livespec-dev-tooling/commit/e51b37f2f4cd0c1241078a4ba2294e3e08af2a6d))

## [1.13.23](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.13.22...v1.13.23) (2026-08-02)


### Bug Fixes

* **fleet:** give LocalContext a FILE-read seam, on the railway ([0d90cf0](https://github.com/thewoolleyman/livespec-dev-tooling/commit/0d90cf0f74da6bb656b77282992d8c60198c779f))

## [1.13.22](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.13.21...v1.13.22) (2026-08-02)


### Bug Fixes

* unmask check-per-file-coverage so a red suite cannot report green ([831a87c](https://github.com/thewoolleyman/livespec-dev-tooling/commit/831a87c1a9b24de866d61af4076116a1ae6cefd1))

## [1.13.21](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.13.20...v1.13.21) (2026-08-01)


### Bug Fixes

* **fleet:** put the credential preflight on the Result railway ([1c6ab06](https://github.com/thewoolleyman/livespec-dev-tooling/commit/1c6ab06216bb1c63b238262d6d4bb9ab2b22a457))

## [1.13.20](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.13.19...v1.13.20) (2026-08-01)


### Bug Fixes

* **agent_hooks:** an apostrophe no longer hides a created worktree ([91a9f66](https://github.com/thewoolleyman/livespec-dev-tooling/commit/91a9f661a21cf455f0e3c7ff5378a5a1eeebac6a))

## [1.13.19](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.13.18...v1.13.19) (2026-08-01)


### Bug Fixes

* **checks:** put the scenarios.md tier resolution on the IOResult railway ([d6aafa0](https://github.com/thewoolleyman/livespec-dev-tooling/commit/d6aafa0e0fe68384e8df982bf653b3f30f43a783))

## [1.13.18](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.13.17...v1.13.18) (2026-08-01)


### Bug Fixes

* **checks:** put the docs-only carve-out rule on the IOResult railway ([4005540](https://github.com/thewoolleyman/livespec-dev-tooling/commit/4005540a02307fde878c166ca43d8ab82f119625))

## [1.13.17](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.13.16...v1.13.17) (2026-08-01)


### Bug Fixes

* **checks:** put the ruff BLE001 backstop probe on the IOResult railway ([5cbda23](https://github.com/thewoolleyman/livespec-dev-tooling/commit/5cbda239fa23380d660b5b6133e8ecf58ee2a70e))

## [1.13.16](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.13.15...v1.13.16) (2026-08-01)


### Bug Fixes

* **testing:** put both CLI e2e discovery walks on the IOResult railway ([459baa7](https://github.com/thewoolleyman/livespec-dev-tooling/commit/459baa72072980489f21bcd07175d5906bf59dfd))

## [1.13.15](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.13.14...v1.13.15) (2026-08-01)


### Bug Fixes

* **fleet:** put the origin-remote resolvers on the IOResult railway ([cb2d86a](https://github.com/thewoolleyman/livespec-dev-tooling/commit/cb2d86a0f75d424accdad82cdb6df825c4ba2258))

## [1.13.14](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.13.13...v1.13.14) (2026-08-01)


### Bug Fixes

* **fleet:** RowSkip means NOT EVALUABLE; inapplicability is an excluded pass ([680fdc1](https://github.com/thewoolleyman/livespec-dev-tooling/commit/680fdc1a5c8325fe1c809686b1714bb6d76533d3))

## [1.13.13](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.13.12...v1.13.13) (2026-08-01)


### Bug Fixes

* **fleet:** an unread ci.yml certified a member's phantom required checks as aligned ([e5a5766](https://github.com/thewoolleyman/livespec-dev-tooling/commit/e5a5766d050d6f575f9d9b78d953a3a9f49a9e39))

## [1.13.12](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.13.11...v1.13.12) (2026-08-01)


### Bug Fixes

* **pin-currency:** a stale pin whose PR list never answered claimed the never-fired class ([5ca77da](https://github.com/thewoolleyman/livespec-dev-tooling/commit/5ca77da893aab9abf59ab42d48e8784498c1b717))

## [1.13.11](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.13.10...v1.13.11) (2026-07-31)


### Bug Fixes

* **primary-checkout:** a hook whose BYTES differ passed the byte-identity check ([23bf3d8](https://github.com/thewoolleyman/livespec-dev-tooling/commit/23bf3d881a936419cfd8ca5a6152c5758a13640d))
* **worktree-pack:** a pack file whose BYTES differ was reported as byte-identical ([c907a6c](https://github.com/thewoolleyman/livespec-dev-tooling/commit/c907a6cca0e43d4f05a15df5dd897ebabb3c22b9))

## [1.13.10](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.13.9...v1.13.10) (2026-07-31)


### Bug Fixes

* **driver-checks:** a profile the check could not READ was reported as a profile that VIOLATES ([49498ac](https://github.com/thewoolleyman/livespec-dev-tooling/commit/49498ac5ff2c3ca0441f10126b6c8eb1221f19c2))

## [1.13.9](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.13.8...v1.13.9) (2026-07-31)


### Bug Fixes

* **fleet:** the gh seam fabricated a 127, and the module reached `returns` by luck ([60938fd](https://github.com/thewoolleyman/livespec-dev-tooling/commit/60938fd8dc15fe653b237b300419b3ae5c233284))

## [1.13.8](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.13.7...v1.13.8) (2026-07-31)


### Bug Fixes

* **fleet:** the command seam's fabricated 127 reached rows that read it as an answer ([20dc67c](https://github.com/thewoolleyman/livespec-dev-tooling/commit/20dc67cc7d07d36c35ad96f65c46885413eadb53))

## [1.13.7](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.13.6...v1.13.7) (2026-07-31)


### Bug Fixes

* **fleet:** the downloader seam fabricated a 127 that a real gh could also return ([99a232e](https://github.com/thewoolleyman/livespec-dev-tooling/commit/99a232ee6ddb70c909d4c7cd2959293584b19e7c))

## [1.13.6](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.13.5...v1.13.6) (2026-07-31)


### Bug Fixes

* **checks:** an unreadable CI workflow raised out of the check that reads it ([297e610](https://github.com/thewoolleyman/livespec-dev-tooling/commit/297e610b4f1c249f3832c9038d952f2d343c6406))

## [1.13.5](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.13.4...v1.13.5) (2026-07-31)


### Bug Fixes

* **fleet:** a connection lookup's None covered six conditions, and one of them wrote a duplicate key ([8a4888e](https://github.com/thewoolleyman/livespec-dev-tooling/commit/8a4888e86f0e208fb55021942358144819176db1))

## [1.13.4](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.13.3...v1.13.4) (2026-07-31)


### Bug Fixes

* **cross-repo:** put the pin-walker family on the railway and kill the unrecognized sentinel ([96fc2a3](https://github.com/thewoolleyman/livespec-dev-tooling/commit/96fc2a3ee78dc90e922f1c0eb289131cdae9ee1e))

## [1.13.3](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.13.2...v1.13.3) (2026-07-31)


### Bug Fixes

* **checks:** put the six primary-checkout git probes on the IOResult railway ([c35ea9e](https://github.com/thewoolleyman/livespec-dev-tooling/commit/c35ea9e0d702c7a51c169c01ce8210f416e5cbf6))
* **checks:** put the three Red-Green-Replay HEAD readers on the IOResult railway ([87fd400](https://github.com/thewoolleyman/livespec-dev-tooling/commit/87fd400dae07f537df9a200d54b2f4dc44c42971))

## [1.13.2](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.13.1...v1.13.2) (2026-07-31)


### Bug Fixes

* **checks:** clause (c) convicts io.StringIO and Path() construction as I/O ([f6eeb91](https://github.com/thewoolleyman/livespec-dev-tooling/commit/f6eeb91e014f8bc9f2eaa1055d3e09b8a11ea9de))
* **checks:** the railway check cannot see through a type ALIAS to IOResult ([7382d9c](https://github.com/thewoolleyman/livespec-dev-tooling/commit/7382d9caa19d96b397a76cf413d65df3a86ab08f))

## [1.13.1](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.13.0...v1.13.1) (2026-07-31)


### Bug Fixes

* **fleet:** the public-API graph drops a RE-EXPORTED consumption entirely ([e5ef2b4](https://github.com/thewoolleyman/livespec-dev-tooling/commit/e5ef2b425095204ea977ecaf0c8ed2294f285750))

## [1.13.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.12.1...v1.13.0) (2026-07-30)


### Features

* **fleet:** register the cross-repo public-API row so it actually gates ([6f38105](https://github.com/thewoolleyman/livespec-dev-tooling/commit/6f3810552692ffa01c787647e00bb8f222124a05))


### Bug Fixes

* **fleet:** the manifest roster never reached the rows that need it ([ba65383](https://github.com/thewoolleyman/livespec-dev-tooling/commit/ba65383dd89c0c229b86706284e39d71d2cce6cf))

## [1.12.1](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.12.0...v1.12.1) (2026-07-30)


### Bug Fixes

* **cross-repo:** the release fan-out has been broken fleet-wide since 89296e0 ([e9c2f5e](https://github.com/thewoolleyman/livespec-dev-tooling/commit/e9c2f5e575f4c424082104d8fc37e32e26f2c7bb))

## [1.12.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.11.0...v1.12.0) (2026-07-30)


### Features

* **fleet:** the central row that checks a declared surface against reality ([e20c3ab](https://github.com/thewoolleyman/livespec-dev-tooling/commit/e20c3abb553eb471a72ddae40e090b83339e7d40))


### Bug Fixes

* **fleet:** a member that satisfies an import itself crosses no boundary ([56379a3](https://github.com/thewoolleyman/livespec-dev-tooling/commit/56379a3bd0a5e94517dfab7c708feeff3465efbd))

## [1.11.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.10.0...v1.11.0) (2026-07-30)


### Features

* **fleet:** measure consumption ACROSS members, which no checkout can see ([df04359](https://github.com/thewoolleyman/livespec-dev-tooling/commit/df04359a18fa260d2f029a70f3537168945ac8aa))
* **fleet:** read a member's two source universes from its snapshot ([846c97c](https://github.com/thewoolleyman/livespec-dev-tooling/commit/846c97c20f94e79cd534dc79e4c7757ad6406367))

## [1.10.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.9.0...v1.10.0) (2026-07-30)


### Features

* **fleet:** one archive read per member replaces ~653 per-file reads ([c24e8d4](https://github.com/thewoolleyman/livespec-dev-tooling/commit/c24e8d47a12be419214f4db18d6881a4ba6e79e1))


### Refactoring

* **fleet:** extract the tree-state slice so the context can accept new reads ([5a6002b](https://github.com/thewoolleyman/livespec-dev-tooling/commit/5a6002bb1a92e5c2c62003cd90072555efb91c27))

## [1.9.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.8.4...v1.9.0) (2026-07-30)


### Features

* **checks:** canonical slug discovery joins the railway, and an empty walk FAILS ([89296e0](https://github.com/thewoolleyman/livespec-dev-tooling/commit/89296e0725ca9e008881db07ae820c551c24696b))

## [1.8.4](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.8.3...v1.8.4) (2026-07-30)


### Bug Fixes

* install gh from signed apt repository ([e87c547](https://github.com/thewoolleyman/livespec-dev-tooling/commit/e87c547862ea4f440ad193db74545139f8f801af))

## [1.8.3](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.8.2...v1.8.3) (2026-07-30)


### Bug Fixes

* **checks:** incremental coverage selects the *_edges.py siblings it told authors to write ([226ca91](https://github.com/thewoolleyman/livespec-dev-tooling/commit/226ca915c47fec2323b0a9e7a3c3d7a88b7cc8db))

## [1.8.2](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.8.1...v1.8.2) (2026-07-30)


### Bug Fixes

* pin supported fabro gh version ([d1c4800](https://github.com/thewoolleyman/livespec-dev-tooling/commit/d1c480022b4bba0711e98e1675a2669429959f3e))

## [1.8.1](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.8.0...v1.8.1) (2026-07-30)


### Bug Fixes

* fall back to guarded bd on PATH ([0304d81](https://github.com/thewoolleyman/livespec-dev-tooling/commit/0304d81faff32440e456a6770e3a436fc29e79a5))

## [1.8.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.7.0...v1.8.0) (2026-07-29)


### Features

* **checks:** the check consults total_absence_returns — v179 member 2 wired ([2df1515](https://github.com/thewoolleyman/livespec-dev-tooling/commit/2df1515c2d9caa2cd85d2aa0677daa1d9af4c70c))

## [1.7.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.6.0...v1.7.0) (2026-07-29)


### Features

* **checks:** bounds 1 and 3 of total_absence_returns — one detector, hard-failing ([8afcf42](https://github.com/thewoolleyman/livespec-dev-tooling/commit/8afcf42854fa27cc0fd57b92dff244330cdee2da))
* **config:** the total_absence_returns loader — bound 2, a required written reason ([440e1be](https://github.com/thewoolleyman/livespec-dev-tooling/commit/440e1bec8a5287a1c780fa63f8bf500ffb331bfb))

## [1.6.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.5.0...v1.6.0) (2026-07-29)


### Features

* **checks:** the Result-return rule stops reaching total public functions ([4d38dd9](https://github.com/thewoolleyman/livespec-dev-tooling/commit/4d38dd9d2316d0f9e23ec2dd25913a7c0cc10f41))

## [1.5.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.4.2...v1.5.0) (2026-07-29)


### Features

* **checks:** compute livespec v179 member 1 with the clause-(d) fixpoint ([579f2d5](https://github.com/thewoolleyman/livespec-dev-tooling/commit/579f2d5941bcd111d486261909c9fca7a8934a49))

## [1.4.2](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.4.1...v1.4.2) (2026-07-29)


### Refactoring

* **checks:** extract the import-resolution graph for v179 member 1 ([f2f020c](https://github.com/thewoolleyman/livespec-dev-tooling/commit/f2f020c4a7f4ceb753423122d80714b2b372b6c0))

## [1.4.1](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.4.0...v1.4.1) (2026-07-29)


### Bug Fixes

* **cross-repo:** the pin walk types the file it could not read ([7459989](https://github.com/thewoolleyman/livespec-dev-tooling/commit/7459989b88031c629dcbfce91adee6ce608215cb))

## [1.4.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.3.2...v1.4.0) (2026-07-29)


### Features

* **fleet:** assert every member declares dispatcher.acceptance_mode ([6b24aa1](https://github.com/thewoolleyman/livespec-dev-tooling/commit/6b24aa14bc5ee0a56186c6fc28a7d3107f35ace9))

## [1.3.2](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.3.1...v1.3.2) (2026-07-29)


### Bug Fixes

* **fleet:** fetch_manifest puts its two failures on the railway ([5b0aec2](https://github.com/thewoolleyman/livespec-dev-tooling/commit/5b0aec2cbacc7212dac4e9d85afc302aefc1ac10))

## [1.3.1](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.3.0...v1.3.1) (2026-07-29)


### Bug Fixes

* **fleet:** the credential-class rule answers from an injected token ([d5324be](https://github.com/thewoolleyman/livespec-dev-tooling/commit/d5324be17814cdaca828bb6e1d8e7ad897d68bfc))

## [1.3.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.2.0...v1.3.0) (2026-07-29)


### Features

* **checks:** apply the v178 consumed-across-a-boundary criterion ([0788e93](https://github.com/thewoolleyman/livespec-dev-tooling/commit/0788e93c44ec97b35f98c65af6c71558b5744cf5))

## [1.2.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.1.0...v1.2.0) (2026-07-29)


### Features

* **checks:** the v178 repo-local public-API consumption oracle ([a141df9](https://github.com/thewoolleyman/livespec-dev-tooling/commit/a141df9859e21ccf9213338e6fdbfa486d5f49b4))

## [1.1.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.0.10...v1.1.0) (2026-07-29)


### Features

* **config:** load the cross_repo_public_api declaration key ([c11e8b0](https://github.com/thewoolleyman/livespec-dev-tooling/commit/c11e8b08ec4cd5045bafa5fdf5ecfd8382f7b708))

## [1.0.10](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.0.9...v1.0.10) (2026-07-29)


### Bug Fixes

* **rop:** put the round-trip entry point on the railway — the last violation ([244306b](https://github.com/thewoolleyman/livespec-dev-tooling/commit/244306bc7618bf0d79cb439f6a7dc432a6146ab9))

## [1.0.9](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.0.8...v1.0.9) (2026-07-29)


### Bug Fixes

* **rop:** put select_runner on the railway, unwrapped fail-closed at its one caller ([09f6a9d](https://github.com/thewoolleyman/livespec-dev-tooling/commit/09f6a9d8beb3b833f605e8cc05b1eb8fd9a59e1d))

## [1.0.8](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.0.7...v1.0.8) (2026-07-29)


### Bug Fixes

* **rop:** inject the layout-dependent slug set so the classifier reaches no I/O ([e4b9f8f](https://github.com/thewoolleyman/livespec-dev-tooling/commit/e4b9f8f97d9eeed7a3f1ef269167be200bec675d))

## [1.0.7](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.0.6...v1.0.7) (2026-07-29)


### Reverts

* remove unauthorized rop supervisor change ([7063aaa](https://github.com/thewoolleyman/livespec-dev-tooling/commit/7063aaa5d9177fe6439bf6652bbe84142cd931aa))

## [1.0.6](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.0.5...v1.0.6) (2026-07-29)


### Bug Fixes

* **rop:** narrow otel_step_timer's __all__ to its baked entry point ([6ffadbd](https://github.com/thewoolleyman/livespec-dev-tooling/commit/6ffadbdf9f2f2a07a823a323f9971589025aa613))

## [1.0.5](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.0.4...v1.0.5) (2026-07-29)


### Bug Fixes

* **fleet:** put the dispatch-matrix filter's hand-rolled Either on the railway ([bcbe035](https://github.com/thewoolleyman/livespec-dev-tooling/commit/bcbe03577af5614fe6ecba4ec5a83111104a5df3))

## [1.0.4](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.0.3...v1.0.4) (2026-07-29)


### Bug Fixes

* **fleet:** put the fleet-manifest parser's hand-rolled failure track on the railway ([2ff79a5](https://github.com/thewoolleyman/livespec-dev-tooling/commit/2ff79a57dbeb28621ffab394294ef64811d6f317))

## [1.0.3](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.0.2...v1.0.3) (2026-07-29)


### Bug Fixes

* **checks:** honor supervisor_entry_files as ratified exemption member 4 ([537ec6a](https://github.com/thewoolleyman/livespec-dev-tooling/commit/537ec6a2c9965e189f513e3964f03dbaee80f0ed))

## [1.0.2](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.0.1...v1.0.2) (2026-07-28)


### Bug Fixes

* **cross-repo:** put fabro pin-rewrite's hand-rolled failure track on the railway ([8751a69](https://github.com/thewoolleyman/livespec-dev-tooling/commit/8751a69ffd133c1fcbb76a7396461093dfefb21d))

## [1.0.1](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v1.0.0...v1.0.1) (2026-07-28)


### Bug Fixes

* **checks:** a leading underscore is not public API, even inside __all__ ([b49c744](https://github.com/thewoolleyman/livespec-dev-tooling/commit/b49c744261c4b898e207e3ca7e4f55b9e2c096d2))

## [1.0.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.58.1...v1.0.0) (2026-07-28)


### ⚠ BREAKING CHANGES

* **config:** reject the ambiguous empty spelling on the five union role keys

### Features

* **config:** reject the ambiguous empty spelling on the five union role keys ([b36e0b8](https://github.com/thewoolleyman/livespec-dev-tooling/commit/b36e0b8e5928d9824c3c2a2cbd0ecfc7c9507104))


### Bug Fixes

* **checks:** the missing-role-keys remediation must name every legal spelling for BOTH key groups ([c0c0472](https://github.com/thewoolleyman/livespec-dev-tooling/commit/c0c04727e95f488b452daca0a7bd88e6d4bc656c))

## [0.58.1](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.58.0...v0.58.1) (2026-07-28)


### Bug Fixes

* **fabro-sandbox:** install tmux in base image ([0d933b7](https://github.com/thewoolleyman/livespec-dev-tooling/commit/0d933b72c9ad7f4ac730a8fdd4c6dc73165649b9))

## [0.58.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.57.1...v0.58.0) (2026-07-28)


### Features

* **fleet:** assert every union role key uses a blessed declared-absent spelling ([8dc8027](https://github.com/thewoolleyman/livespec-dev-tooling/commit/8dc8027333f619dabb2046489699fe7b258be63c))
* **fleet:** register role-key-spellings so an engine actually walks it ([606f17b](https://github.com/thewoolleyman/livespec-dev-tooling/commit/606f17b7e0062a8c42510599efe6c3fd65d6c026))

## [0.57.1](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.57.0...v0.57.1) (2026-07-28)


### Refactoring

* **fleet:** extract the github-state slice so the obligation table can accept rows again ([34c05c1](https://github.com/thewoolleyman/livespec-dev-tooling/commit/34c05c134c0ea34f6543fc14e4d343f962196f03))

## [0.57.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.56.7...v0.57.0) (2026-07-28)


### Features

* **config:** accept the four blessed role-key spellings; make legacy empty visible ([8a61df6](https://github.com/thewoolleyman/livespec-dev-tooling/commit/8a61df6f5826f97a2f73b446fb4a8c677ee74a3d))

## [0.56.7](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.56.6...v0.56.7) (2026-07-28)


### Bug Fixes

* **checks:** union source_trees into the commit-pairs prefix universe ([5f82dbe](https://github.com/thewoolleyman/livespec-dev-tooling/commit/5f82dbe45d0f423f743b0d6df8901f7e0f0424d0))

## [0.56.6](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.56.5...v0.56.6) (2026-07-27)


### Bug Fixes

* **checks:** wire the spec's stated railway exemptions into public-api-result-typed ([1af60cb](https://github.com/thewoolleyman/livespec-dev-tooling/commit/1af60cb6d55303918d23cf617ac3fded2ca98669))

## [0.56.5](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.56.4...v0.56.5) (2026-07-27)


### Bug Fixes

* **checks:** treat an all-vendored path set as nothing to gate, not a red ([0a55f5b](https://github.com/thewoolleyman/livespec-dev-tooling/commit/0a55f5be9c9903f06463b9d65291ef6a7048a5ed))

## [0.56.4](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.56.3...v0.56.4) (2026-07-27)


### Bug Fixes

* **checks:** exclude vendored .py from replay bucketing and coverage mirrors ([440acf2](https://github.com/thewoolleyman/livespec-dev-tooling/commit/440acf2c18f0865b50ab0b1b4325aa5a4e71a9ff))

## [0.56.3](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.56.2...v0.56.3) (2026-07-27)


### Bug Fixes

* **checks:** exclude vendored _vendor/**.py from commit-pairs pairing ([9ef068d](https://github.com/thewoolleyman/livespec-dev-tooling/commit/9ef068d9d762a97744ced345539d0aa167818c0c))

## [0.56.2](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.56.1...v0.56.2) (2026-07-27)


### Bug Fixes

* **fleet:** probe the credential once before evaluating any obligation row ([75be7cd](https://github.com/thewoolleyman/livespec-dev-tooling/commit/75be7cd931ef8018acf2aa6a0f0e9cdbaa99f2b1))

## [0.56.1](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.56.0...v0.56.1) (2026-07-27)


### Bug Fixes

* **fleet:** preserve GitHub read-failure causes through FleetContext ([1109c6d](https://github.com/thewoolleyman/livespec-dev-tooling/commit/1109c6d69c19f9a8bf3334a8e45703a9bbca2382))

## [0.56.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.55.1...v0.56.0) (2026-07-27)


### Features

* **checks:** derive the ROP-check universe from the git index ([a880181](https://github.com/thewoolleyman/livespec-dev-tooling/commit/a880181c324c684c9aa748813ed82710a5bcbc13))

## [0.55.1](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.55.0...v0.55.1) (2026-07-27)


### Bug Fixes

* **checks:** stop a ruff-backstop gap from masking position offenses ([4ffae65](https://github.com/thewoolleyman/livespec-dev-tooling/commit/4ffae65702c691feb2615b23b3d3b224ed2babf0))

## [0.55.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.54.28...v0.55.0) (2026-07-27)


### Features

* **checks:** reject hook trees declared in io_trees ([1f89d75](https://github.com/thewoolleyman/livespec-dev-tooling/commit/1f89d75122fc4ee948c2515ef3f1c88e88114f29))

## [0.54.28](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.54.27...v0.54.28) (2026-07-27)


### Bug Fixes

* retire the file_lloc_hard_gate opt-in so the 250 LLOC ceiling is unconditional ([ac54fd6](https://github.com/thewoolleyman/livespec-dev-tooling/commit/ac54fd6d8145cb6856854b3187964b788a275363))

## [0.54.27](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.54.26...v0.54.27) (2026-07-26)


### Bug Fixes

* teach check-keyword-only-args the externally-fixed-calling-convention exception ([b85fed7](https://github.com/thewoolleyman/livespec-dev-tooling/commit/b85fed718d47a99260e3ab91457166065c683930))

## [0.54.26](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.54.25...v0.54.26) (2026-07-26)


### Bug Fixes

* teach check-private-calls the beside-test distinction SLF001 already makes ([8367848](https://github.com/thewoolleyman/livespec-dev-tooling/commit/8367848648b8db3daa9fa95595074f9cbfb33dc7))

## [0.54.25](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.54.24...v0.54.25) (2026-07-26)


### Bug Fixes

* honour the declared sandbox exemption in the worktree-pack presence arm ([5550a93](https://github.com/thewoolleyman/livespec-dev-tooling/commit/5550a93e579c26651ec2576dd4e9ca1cb81fb2ef))

## [0.54.24](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.54.23...v0.54.24) (2026-07-26)


### Bug Fixes

* make an absent worktree_discipline key mean pack required ([313bdd7](https://github.com/thewoolleyman/livespec-dev-tooling/commit/313bdd71782fa78ae8b7fb20e9e88d20418bf376))

## [0.54.23](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.54.22...v0.54.23) (2026-07-26)


### Bug Fixes

* add a worktree-local worktree-pack obligation row before commit-refuse-hooks ([414cc5e](https://github.com/thewoolleyman/livespec-dev-tooling/commit/414cc5e7de0e795ee11077cf59ef933511066232))

## [0.54.22](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.54.21...v0.54.22) (2026-07-26)


### Bug Fixes

* **fleet:** scope a member CI conformance exit to the running member ([08b7bae](https://github.com/thewoolleyman/livespec-dev-tooling/commit/08b7bae6a29c97e14c713e111164fa172f0bef19))

## [0.54.21](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.54.20...v0.54.21) (2026-07-26)


### Bug Fixes

* refuse commits from worktrees outside the sanctioned root ([7cf38db](https://github.com/thewoolleyman/livespec-dev-tooling/commit/7cf38db7567035e9b84b28fca2887c238facc50a))

## [0.54.20](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.54.19...v0.54.20) (2026-07-26)


### Bug Fixes

* **checks:** retire the loop-iteration marker from the closed conforming set ([1e031aa](https://github.com/thewoolleyman/livespec-dev-tooling/commit/1e031aaf888f934e01ffe48d0268bed15fd22aae))

## [0.54.19](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.54.18...v0.54.19) (2026-07-26)


### Bug Fixes

* **docs:** drop the rotted heading-level spec citation from the package docstring ([0b0dca4](https://github.com/thewoolleyman/livespec-dev-tooling/commit/0b0dca4711405ae0fb1d5e4936cb944ef30bff25))

## [0.54.18](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.54.17...v0.54.18) (2026-07-26)


### Bug Fixes

* **checks:** exempt docs-only changes from the incremental coverage gate ([1398d74](https://github.com/thewoolleyman/livespec-dev-tooling/commit/1398d74e99b270188ddcf94f0a400c35550e5599))

## [0.54.17](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.54.16...v0.54.17) (2026-07-26)


### Bug Fixes

* **checks:** commit-pairs requires no paired test for non-Python source files ([a5ad9f1](https://github.com/thewoolleyman/livespec-dev-tooling/commit/a5ad9f183ad093d5a0f4d3dc2180ac0ff0d591e5))
* **docs:** retire fallback-regime prose from three shipped artifacts ([bad21d6](https://github.com/thewoolleyman/livespec-dev-tooling/commit/bad21d65be29548843217f57681ac02785a6d560))

## [0.54.16](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.54.15...v0.54.16) (2026-07-26)


### Bug Fixes

* **checks:** newtype_domain_primitives errors on a declared tree with no Python ([6e69718](https://github.com/thewoolleyman/livespec-dev-tooling/commit/6e697183390e5eb42f4ce216187ca77d429d2566))

## [0.54.15](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.54.14...v0.54.15) (2026-07-25)


### Bug Fixes

* **checks:** enforce per-artifact boundary-catch cardinality ([9695ea3](https://github.com/thewoolleyman/livespec-dev-tooling/commit/9695ea3d47691ef80098247b6d3b00dae24d8505))

## [0.54.14](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.54.13...v0.54.14) (2026-07-25)


### Bug Fixes

* derive red-green replay impl prefixes ([e5de4a9](https://github.com/thewoolleyman/livespec-dev-tooling/commit/e5de4a9d35319c4be18b896f9fbfa9f03b2605b5))

## [0.54.13](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.54.12...v0.54.13) (2026-07-25)


### Bug Fixes

* require declared role keys for layout checks ([b2e82e1](https://github.com/thewoolleyman/livespec-dev-tooling/commit/b2e82e1e1622c754bb4b69112ac9da400578e764))

## [0.54.12](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.54.11...v0.54.12) (2026-07-25)


### Bug Fixes

* enforce declared role keys ([b8ea4e6](https://github.com/thewoolleyman/livespec-dev-tooling/commit/b8ea4e6e9c6d32b154024229d8ff87f63a628845))

## [0.54.11](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.54.10...v0.54.11) (2026-07-25)


### Bug Fixes

* reject broad contextlib suppress outside boundary ([f4158f3](https://github.com/thewoolleyman/livespec-dev-tooling/commit/f4158f3b387d4119265effd4012e17b014d400cb))

## [0.54.10](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.54.9...v0.54.10) (2026-07-25)


### Bug Fixes

* derive shadow ledger pyright config ([518ab4d](https://github.com/thewoolleyman/livespec-dev-tooling/commit/518ab4d1ef18e0587806077c6a31eb743872bd7d))

## [0.54.9](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.54.8...v0.54.9) (2026-07-25)


### Bug Fixes

* inspect except-star broad handlers ([7face5f](https://github.com/thewoolleyman/livespec-dev-tooling/commit/7face5fb925a7f579c387fb2dd44f2884b8084d3))

## [0.54.8](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.54.7...v0.54.8) (2026-07-25)


### Bug Fixes

* parse neutral_hook_body_path "" as declared-none (e9j L0b) ([36228a7](https://github.com/thewoolleyman/livespec-dev-tooling/commit/36228a7f5feef63755a37eacb11976a56dfebb95))

## [0.54.7](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.54.6...v0.54.7) (2026-07-24)


### Bug Fixes

* accept "" as declared-none for dataclasses_tree (e9j L0) ([39ce9fc](https://github.com/thewoolleyman/livespec-dev-tooling/commit/39ce9fc35837fd1b21b1b0a2e0556f45b07ab626))
* add no-workflow-edits janitor recipe ([362340f](https://github.com/thewoolleyman/livespec-dev-tooling/commit/362340f1b973d1f710259c2b1e96ed12c6b87797))

## [0.54.6](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.54.5...v0.54.6) (2026-07-24)


### Bug Fixes

* allow Generic[...] bases in no_inheritance and match subscripted allowlist entries ([462192e](https://github.com/thewoolleyman/livespec-dev-tooling/commit/462192e1895f9528207c679408260d516f2fa56f))
* exempt the declared neutral hook body from the first-party check universe ([614c07e](https://github.com/thewoolleyman/livespec-dev-tooling/commit/614c07ed5cc3250458d6ae7c49db7919b399f99f))

## [0.54.5](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.54.4...v0.54.5) (2026-07-24)


### Bug Fixes

* **fleet:** fail the release fan-out on a conformance finding attributable to no member ([5bb5eae](https://github.com/thewoolleyman/livespec-dev-tooling/commit/5bb5eae7b86010cc22215b815b729e778d2891c7))

## [0.54.4](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.54.3...v0.54.4) (2026-07-24)


### Bug Fixes

* route growing jq inputs to stdin in the CI telemetry export ([e3b3f58](https://github.com/thewoolleyman/livespec-dev-tooling/commit/e3b3f582f87e439d9a4888cf9a2fcded679b7d14))

## [0.54.3](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.54.2...v0.54.3) (2026-07-24)


### Bug Fixes

* **fleet:** escalate a persisting pin gap (stale with an open bump PR for latest) to an error finding ([17ab424](https://github.com/thewoolleyman/livespec-dev-tooling/commit/17ab424188dd286d1711c518288fe71a2d38f3d8))
* **fleet:** scope the persisting-gap escalation to the filter-consuming preflight ([4855a92](https://github.com/thewoolleyman/livespec-dev-tooling/commit/4855a92d95b0f572d7ed0d19934a545b49183db5))

## [0.54.2](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.54.1...v0.54.2) (2026-07-24)


### Bug Fixes

* pairing-gate docs-only carve-out (content-keyed) + two stale-scope docstring fixes (5eow) ([4fa0c79](https://github.com/thewoolleyman/livespec-dev-tooling/commit/4fa0c7916c919564d7f66558ef018388e6f799bf))

## [0.54.1](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.54.0...v0.54.1) (2026-07-24)


### Bug Fixes

* exempt the declared neutral hook body from the commit-pairing gate ([64590bf](https://github.com/thewoolleyman/livespec-dev-tooling/commit/64590bf322bf6a742857aa526979cccf790c5fd2))

## [0.54.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.53.2...v0.54.0) (2026-07-23)


### Features

* type-check the canonical no-shadow-ledger body (render-at-check-time) ([d08ca94](https://github.com/thewoolleyman/livespec-dev-tooling/commit/d08ca94f23a1cfe6025d46694f5dd395f542098a))

## [0.53.2](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.53.1...v0.53.2) (2026-07-23)


### Bug Fixes

* include incremental coverage in red scope ([9e003aa](https://github.com/thewoolleyman/livespec-dev-tooling/commit/9e003aa5cf2b09411a873ce0274dc10d01f4dc8e))

## [0.53.1](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.53.0...v0.53.1) (2026-07-23)


### Bug Fixes

* **fleet:** filter non-conformant members out of the release-dispatch matrix instead of halting the fan-out ([4f6b00b](https://github.com/thewoolleyman/livespec-dev-tooling/commit/4f6b00b9a1fa9bf9ba0745429cbce08310f85754))
* require ruff BLE backstop for no-except ([7c6b834](https://github.com/thewoolleyman/livespec-dev-tooling/commit/7c6b8346de4c4e76e5f001c98cbc3795204ff9be))

## [0.53.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.52.9...v0.53.0) (2026-07-23)


### Features

* **fleet:** warn on all pin currency formats ([e105cec](https://github.com/thewoolleyman/livespec-dev-tooling/commit/e105cec07ffce8bb04d30c1173640062ba45df56))

## [0.52.9](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.52.8...v0.52.9) (2026-07-23)


### Bug Fixes

* **fleet:** classify the admin lane out-of-vantage under a dispatch-class credential ([1e85cd1](https://github.com/thewoolleyman/livespec-dev-tooling/commit/1e85cd1c628e3141aa38aecb2daca09ad7b58ee0))

## [0.52.8](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.52.7...v0.52.8) (2026-07-23)


### Bug Fixes

* **checks:** match sanctioned BLE001 marker wordings exactly in no-except-outside-io ([8dd0e69](https://github.com/thewoolleyman/livespec-dev-tooling/commit/8dd0e6984cc16b6cba2c8b602251818ca45a307b))

## [0.52.7](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.52.6...v0.52.7) (2026-07-23)


### Bug Fixes

* **fleet:** never sweep a repo's default branch, whatever it is named ([4d8dc24](https://github.com/thewoolleyman/livespec-dev-tooling/commit/4d8dc244196144b0a9d86aa7bd130b62485043da))

## [0.52.6](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.52.5...v0.52.6) (2026-07-23)


### Bug Fixes

* **fleet:** complete the vantage model and escalate blind rows to error ([de2d50f](https://github.com/thewoolleyman/livespec-dev-tooling/commit/de2d50ffb40bf2433eef5118c98b9af956802486))

## [0.52.5](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.52.4...v0.52.5) (2026-07-23)


### Bug Fixes

* **fleet:** consume manifest.adopters in an admin-lane currency leg ([69c1427](https://github.com/thewoolleyman/livespec-dev-tooling/commit/69c142747b46e40e3d2d743d3a2c38de75981aac))

## [0.52.4](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.52.3...v0.52.4) (2026-07-23)


### Bug Fixes

* **fleet:** route reconcile writes through the member's resolved default branch ([f3b69bf](https://github.com/thewoolleyman/livespec-dev-tooling/commit/f3b69bf5a6086f4117584a3cae7b740eb97a02f1))

## [0.52.3](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.52.2...v0.52.3) (2026-07-23)


### Bug Fixes

* **fleet:** enforce the two admin-scoped rows in a world-gate lane ([ec66951](https://github.com/thewoolleyman/livespec-dev-tooling/commit/ec669517171fd1e45614b39eee6771528a804b23))

## [0.52.2](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.52.1...v0.52.2) (2026-07-23)


### Bug Fixes

* **ci:** re-base the fabro sandbox chain onto buildpack-deps:noble-scm ([00c5d9f](https://github.com/thewoolleyman/livespec-dev-tooling/commit/00c5d9f2209c9a82ed56f430dbb1d28620057bdf))

## [0.52.1](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.52.0...v0.52.1) (2026-07-23)


### Bug Fixes

* **fleet:** read branch protection at the member's canonical ref ([3e71148](https://github.com/thewoolleyman/livespec-dev-tooling/commit/3e7114864c4cb4903f7a88552819c800c0a6dfbf))

## [0.52.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.51.10...v0.52.0) (2026-07-22)


### Features

* emit fleet member verdicts ([886c76b](https://github.com/thewoolleyman/livespec-dev-tooling/commit/886c76b67c454bc1173bc52e1f90e20e429b40e7))

## [0.51.10](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.51.9...v0.51.10) (2026-07-22)


### Bug Fixes

* **checks:** scope core-package declarations by repo identity, not directory census ([fec2d09](https://github.com/thewoolleyman/livespec-dev-tooling/commit/fec2d0933a39d0b7a5e8c579994f3265a5c29ef6))

## [0.51.9](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.51.8...v0.51.9) (2026-07-22)


### Bug Fixes

* **checks:** make no-except-outside-io breadth-aware ([2be20e1](https://github.com/thewoolleyman/livespec-dev-tooling/commit/2be20e19eb5e7dc1c58232353bebc9d09669f928))

## [0.51.8](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.51.7...v0.51.8) (2026-07-22)


### Bug Fixes

* **fleet:** require the console to ship the two receiving pin shims ([484039d](https://github.com/thewoolleyman/livespec-dev-tooling/commit/484039d14c73291c59a2d0a8c7e90b05752939b8))

## [0.51.7](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.51.6...v0.51.7) (2026-07-21)


### Bug Fixes

* **cross-repo:** compare pin currency by version component, not raw tag string ([9237c80](https://github.com/thewoolleyman/livespec-dev-tooling/commit/9237c80b8567b14c1306b25ea613c4ac7a6c5e56))

## [0.51.6](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.51.5...v0.51.6) (2026-07-21)


### Bug Fixes

* **cross-repo:** gate the codex-acp golden-master steps on the bump changed output ([dbe32f2](https://github.com/thewoolleyman/livespec-dev-tooling/commit/dbe32f2bfa84580e88039ce74fedf35195c29c22))

## [0.51.5](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.51.4...v0.51.5) (2026-07-21)


### Bug Fixes

* **cross-repo:** treat an empty pin-rewrite diff as a clean no-op, not a failure ([c9c6d53](https://github.com/thewoolleyman/livespec-dev-tooling/commit/c9c6d53b24a8016d03cb0fdb8c83cfe6072b08da))

## [0.51.4](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.51.3...v0.51.4) (2026-07-21)


### Bug Fixes

* **fleet:** report unreadable merge settings as not-evaluable, not violated ([61f2d7b](https://github.com/thewoolleyman/livespec-dev-tooling/commit/61f2d7bf97195f3761a0caca052a5585105d9a59))

## [0.51.3](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.51.2...v0.51.3) (2026-07-21)


### Bug Fixes

* **fleet:** report obligation rows that enforced nothing (blind rows) ([a0f8225](https://github.com/thewoolleyman/livespec-dev-tooling/commit/a0f82258f04fa0e94be573ee3ed91edb232467a6))

## [0.51.2](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.51.1...v0.51.2) (2026-07-20)


### Bug Fixes

* **fleet:** accept a top-level ci-green gate job as a valid required check ([c20463c](https://github.com/thewoolleyman/livespec-dev-tooling/commit/c20463c943caf879e55e3da75365680ba98513b8))

## [0.51.1](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.51.0...v0.51.1) (2026-07-20)


### Bug Fixes

* **fleet:** resolve the canonical GitHub ref per repo, not globally ([d01ff43](https://github.com/thewoolleyman/livespec-dev-tooling/commit/d01ff43b095760163339bb1bee1a448361dc9901))

## [0.51.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.50.8...v0.51.0) (2026-07-20)


### Features

* **fleet:** add the control-plane-tool repo class ([0a86807](https://github.com/thewoolleyman/livespec-dev-tooling/commit/0a86807aa9e8dfc9490a7bfe4c0d9c9e98521019))

## [0.50.8](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.50.7...v0.50.8) (2026-07-20)


### Bug Fixes

* **checks:** fail loudly when a credentialed gh cannot reach the API ([d5d1b7c](https://github.com/thewoolleyman/livespec-dev-tooling/commit/d5d1b7cd8ca508882d80cfcefc8d587c98ba1460))

## [0.50.7](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.50.6...v0.50.7) (2026-07-20)


### Bug Fixes

* classify superseded bump prs ([fba6d0a](https://github.com/thewoolleyman/livespec-dev-tooling/commit/fba6d0a7fe11d279605d7b1c986a2435e2a52d9a))
* widen superseded bump pr sweep ([17a5b63](https://github.com/thewoolleyman/livespec-dev-tooling/commit/17a5b633dab37a7114d7378213d1b1ef67b59587))

## [0.50.6](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.50.5...v0.50.6) (2026-07-20)


### Bug Fixes

* **cross-repo:** name the target layer by role in the unrewritable-pin refusal ([1dc3bb0](https://github.com/thewoolleyman/livespec-dev-tooling/commit/1dc3bb0ca2ee7464c55aafbd2acb47146fcc4177))

## [0.50.5](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.50.4...v0.50.5) (2026-07-20)


### Bug Fixes

* **checks:** a crashed mutmut run must fail even when verdicts are present ([2e1cd24](https://github.com/thewoolleyman/livespec-dev-tooling/commit/2e1cd24fd03198bc1311fa3a53e4137a025e4184))
* **checks:** check_mutation must fail when it inspected nothing ([e9dcf46](https://github.com/thewoolleyman/livespec-dev-tooling/commit/e9dcf4696dec9e40fdc73ecea5439e6f9cb2cead))
* **cross-repo:** refuse an unrewritable fabro image pin instead of bumping it bare ([f1274d5](https://github.com/thewoolleyman/livespec-dev-tooling/commit/f1274d53f337293be7dae3d61ef8544c2a8d29ad))

## [0.50.4](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.50.3...v0.50.4) (2026-07-19)


### Refactoring

* **ci:** move agent payload to an on-top image layer ([f1a5a65](https://github.com/thewoolleyman/livespec-dev-tooling/commit/f1a5a654c166aad6e812c103274a1e9c990387f0))

## [0.50.3](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.50.2...v0.50.3) (2026-07-19)


### Bug Fixes

* **ci-runner:** derive the isolation suite's image from ci.yml instead of a stale hardcoded tag ([1ed3d57](https://github.com/thewoolleyman/livespec-dev-tooling/commit/1ed3d57d8c005f3bb0745cd8a95609b15f3159f6))

## [0.50.2](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.50.1...v0.50.2) (2026-07-19)


### Refactoring

* **ci:** restore set -e in bump-pin-rewrite's PR-open step (livespec-dev-tooling-7m1) ([4474b2d](https://github.com/thewoolleyman/livespec-dev-tooling/commit/4474b2d714d591944493f48d905e00ffb779120a))

## [0.50.1](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.50.0...v0.50.1) (2026-07-19)


### Refactoring

* **cross-repo:** resolve pin_staleness from the support checkout, not the consumer env (livespec-dev-tooling-3tu) ([913e244](https://github.com/thewoolleyman/livespec-dev-tooling/commit/913e244ae8fc199573cfc1e789ba62378aea7c45))

## [0.50.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.49.4...v0.50.0) (2026-07-19)


### Features

* **fleet:** enforce install verification in ensure_plugins (livespec-zxf6) ([6233905](https://github.com/thewoolleyman/livespec-dev-tooling/commit/62339057b3cd20477cf80b13e7276e5ce69fb46a))

## [0.49.4](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.49.3...v0.49.4) (2026-07-19)


### Bug Fixes

* **cross-repo:** stop SIGPIPE corrupting the freshness ordinal-distance capture ([bd108ef](https://github.com/thewoolleyman/livespec-dev-tooling/commit/bd108efb08f01c9c8e5b099f90538c3ec3b0cc74))

## [0.49.3](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.49.2...v0.49.3) (2026-07-19)


### Bug Fixes

* **cross-repo:** check every distinct pin per source in the freshness scan ([4ad8344](https://github.com/thewoolleyman/livespec-dev-tooling/commit/4ad83440adea6b8fa3387d4204314926112ffdaa))

## [0.49.2](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.49.1...v0.49.2) (2026-07-19)


### Bug Fixes

* **cross-repo:** walk the fabro-sandbox CI container image pin (xb7) ([b0c320d](https://github.com/thewoolleyman/livespec-dev-tooling/commit/b0c320de654c4d4958680b745f49ac58483a1d37))

## [0.49.1](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.49.0...v0.49.1) (2026-07-18)


### Bug Fixes

* config-gate plan thread anchor check ([2039838](https://github.com/thewoolleyman/livespec-dev-tooling/commit/20398382a392e2744f620bf930411166287b987a))

## [0.49.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.48.2...v0.49.0) (2026-07-18)


### Features

* plan-thread lifecycle checks — static anchor gate + ledger-aware epic-parity companion ([9d1cb68](https://github.com/thewoolleyman/livespec-dev-tooling/commit/9d1cb682fe194fbb233418d76974a49895ce5570))

## [0.48.2](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.48.1...v0.48.2) (2026-07-16)


### Bug Fixes

* make ROP sweep checks config-driven ([3de4223](https://github.com/thewoolleyman/livespec-dev-tooling/commit/3de4223dc105203d5dd05b6b985ca7e400bdc180))

## [0.48.1](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.48.0...v0.48.1) (2026-07-15)


### Bug Fixes

* routing check must see triggers under a quoted "on": key ([ca57678](https://github.com/thewoolleyman/livespec-dev-tooling/commit/ca5767820ab339b57fa32de4e41cccca3a54418d))

## [0.48.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.47.0...v0.48.0) (2026-07-15)


### Features

* self-hosted-routing check — forbidden triggers must not reach a local-ci runner ([2121fcb](https://github.com/thewoolleyman/livespec-dev-tooling/commit/2121fcb8995a80d63963939fcb57697627055776))

## [0.47.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.46.6...v0.47.0) (2026-07-15)


### Features

* handoff dispatch-routing lint — active plan handoffs must route implementation through the factory (work-item livespec-dev-tooling-64x6mb) ([734e92c](https://github.com/thewoolleyman/livespec-dev-tooling/commit/734e92c563ec5b423f26828f1f1bb3ddd77c16e5))

## [0.46.6](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.46.5...v0.46.6) (2026-07-15)


### Bug Fixes

* extract pin rewrite logic ([f366045](https://github.com/thewoolleyman/livespec-dev-tooling/commit/f3660456b5c5303a9e906cafda695e9677405a24))

## [0.46.5](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.46.4...v0.46.5) (2026-07-14)


### Bug Fixes

* **ci-runner:** serialize podman network-prune against container removal ([1dedd17](https://github.com/thewoolleyman/livespec-dev-tooling/commit/1dedd17aa8bc1065e5b44b8b164d55115af8cd17))

## [0.46.4](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.46.3...v0.46.4) (2026-07-14)


### Bug Fixes

* **cross-repo:** reconcile the consumer ci.yml canonical matrix in the pin bump ([7dc0d9b](https://github.com/thewoolleyman/livespec-dev-tooling/commit/7dc0d9b7477e1be443764ba61c2123905231e0e8))

## [0.46.3](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.46.2...v0.46.3) (2026-07-14)


### Bug Fixes

* **ci-runner:** make the runner pool actually multi-runner-capable ([a71139a](https://github.com/thewoolleyman/livespec-dev-tooling/commit/a71139ab9358cce71cd5f5f021bd55638fe5b0bb))

## [0.46.2](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.46.1...v0.46.2) (2026-07-14)


### Bug Fixes

* **ci-runner:** give the ephemeral gate runner an ephemeral workspace ([eb26595](https://github.com/thewoolleyman/livespec-dev-tooling/commit/eb26595419832b58204147444aa3141b4ec07ee6))

## [0.46.1](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.46.0...v0.46.1) (2026-07-13)


### Bug Fixes

* **skill-invocation-paths:** auto-detect runtime-resolving Driver model ([b884881](https://github.com/thewoolleyman/livespec-dev-tooling/commit/b88488153b059628968b62f4650129393541b16d))

## [0.46.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.45.0...v0.46.0) (2026-07-13)


### Features

* add local-memory drift audit ([6ae50e6](https://github.com/thewoolleyman/livespec-dev-tooling/commit/6ae50e634303eda376f415eaf0e8768116db88f9))

## [0.45.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.44.0...v0.45.0) (2026-07-13)


### Features

* codex-acp external-source pin + factory-gated auto-bump ([81b7da3](https://github.com/thewoolleyman/livespec-dev-tooling/commit/81b7da3c62cc5564627bea15c7563905041bb78e))

## [0.44.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.43.2...v0.44.0) (2026-07-13)


### Features

* neutral-shared-hook-body byte-identity Verifier + installer (S2) ([234078e](https://github.com/thewoolleyman/livespec-dev-tooling/commit/234078e52408344d7da549ff3c545a8b1060446d))

## [0.43.2](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.43.1...v0.43.2) (2026-07-13)


### Bug Fixes

* **config:** narrow first-party-.py exemption from .claude/ to .claude/skills/ ([1e4dd51](https://github.com/thewoolleyman/livespec-dev-tooling/commit/1e4dd5125bb4fbae82d2daf80470e737bbe62e92))

## [0.43.1](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.43.0...v0.43.1) (2026-07-13)


### Bug Fixes

* **cross-repo:** prefix-preserving fabro docker pin rewrite ([058b47c](https://github.com/thewoolleyman/livespec-dev-tooling/commit/058b47c485ba4bbb8d862bdc22a0c85b8f9d0735))

## [0.43.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.42.0...v0.43.0) (2026-07-13)


### Features

* **dev-tooling:** split fabro-sandbox image into base/python/python-rust layers ([a03be53](https://github.com/thewoolleyman/livespec-dev-tooling/commit/a03be53858223186f6678253c0eeaba34fa2740f))

## [0.42.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.41.1...v0.42.0) (2026-07-12)


### Features

* **dev-tooling:** livespec-step-timer — bake sandbox prepare-step timing wrapper ([b05c687](https://github.com/thewoolleyman/livespec-dev-tooling/commit/b05c6872044ed81fd175443bb56d57de3e57f774))

## [0.41.1](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.41.0...v0.41.1) (2026-07-12)


### Bug Fixes

* recognize parameterized recipe headers in bump-pin canonical reconcile ([d90494b](https://github.com/thewoolleyman/livespec-dev-tooling/commit/d90494b8926a8b0307df81d3688a5d32b1f35131))

## [0.41.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.40.4...v0.41.0) (2026-07-12)


### Features

* exempt .claude/ agent-runtime infra from the first-party .py universe ([0814815](https://github.com/thewoolleyman/livespec-dev-tooling/commit/0814815f9959dfc6c3dddcce8ff5b9a931be896a))

## [0.40.4](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.40.3...v0.40.4) (2026-07-12)


### Refactoring

* **checks,agent_hooks:** decompose the last 3 files &gt;250 (fleet-check-coverage) ([4eed3f7](https://github.com/thewoolleyman/livespec-dev-tooling/commit/4eed3f753758455b90e5142d513ed1367e096fef))

## [0.40.3](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.40.2...v0.40.3) (2026-07-12)


### Refactoring

* **cross_repo,driver_checks,testing:** decompose pin_autodiscovery + plugin_structure + cli_e2e ≤250 (fleet-check-coverage) ([0a77aac](https://github.com/thewoolleyman/livespec-dev-tooling/commit/0a77aac48dcf6399c40568cad721feac6568836b))

## [0.40.2](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.40.1...v0.40.2) (2026-07-12)


### Refactoring

* **fleet:** decompose contract.py + _rows_files.py ≤250 (fleet-check-coverage) ([e45a66f](https://github.com/thewoolleyman/livespec-dev-tooling/commit/e45a66fbd10d7496cdf202e208ddd7980c8f9783))

## [0.40.1](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.40.0...v0.40.1) (2026-07-12)


### Refactoring

* **checks:** decompose heading_coverage + tool_backed_check_completeness ≤250 (fleet-check-coverage) ([fe70eac](https://github.com/thewoolleyman/livespec-dev-tooling/commit/fe70eac9421e2dcf97f6dfeb067c743bfb7e5700))

## [0.40.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.39.0...v0.40.0) (2026-07-12)


### Features

* cover fabro-sandbox docker image tag as the 5th bump-pin format ([ebf54cc](https://github.com/thewoolleyman/livespec-dev-tooling/commit/ebf54cc4a0c5721f76bbd0ac4f320b607f89297b))

## [0.39.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.38.1...v0.39.0) (2026-07-12)


### Features

* add per-repo file_lloc hard-gate flip lever ([d69210c](https://github.com/thewoolleyman/livespec-dev-tooling/commit/d69210cf6fe140d243fafbda036c806aa462c78f))

## [0.38.1](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.38.0...v0.38.1) (2026-07-11)


### Bug Fixes

* switch check-no-fmt-directives to an env-lever severity model ([8601e3c](https://github.com/thewoolleyman/livespec-dev-tooling/commit/8601e3c137483197b689e97a721e261f7a722db0))

## [0.38.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.37.3...v0.38.0) (2026-07-11)


### Features

* ban formatter-suppression directives to make file_lloc ungameable by line-packing ([5617599](https://github.com/thewoolleyman/livespec-dev-tooling/commit/561759912b6950bc77d777ff4f03a763aeeba3b9))

## [0.37.3](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.37.2...v0.37.3) (2026-07-10)


### Bug Fixes

* recognize the ci-green gate job as a valid required check in branch-protection-alignment ([a2d3fbb](https://github.com/thewoolleyman/livespec-dev-tooling/commit/a2d3fbb1797428d4e31a8b8eff3182e106d82c2f))

## [0.37.2](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.37.1...v0.37.2) (2026-07-10)


### Bug Fixes

* exclude world-gate checks from ci-matrix-completeness CI requirement ([5693955](https://github.com/thewoolleyman/livespec-dev-tooling/commit/569395530f115dbf5bbd72e0567e613321f65b36))

## [0.37.1](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.37.0...v0.37.1) (2026-07-10)


### Bug Fixes

* ci-matrix-completeness (b) covers non-canonical gating jobs (o6b) ([c268fb7](https://github.com/thewoolleyman/livespec-dev-tooling/commit/c268fb78be7a8713f111b689da8371cb3b669410))

## [0.37.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.36.3...v0.37.0) (2026-07-10)


### Features

* add check-ci-matrix-completeness drift-guard (warn-default) ([c442e13](https://github.com/thewoolleyman/livespec-dev-tooling/commit/c442e13c8a402eb907b81b02ea3fc5f7f338d9c3))

## [0.36.3](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.36.2...v0.36.3) (2026-07-10)


### Bug Fixes

* **fabro-sandbox:** bake bubblewrap + codex-acp adapter ([7339303](https://github.com/thewoolleyman/livespec-dev-tooling/commit/733930370790fcd74ebc6ec6e2e468cf30f0e2f6))

## [0.36.2](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.36.1...v0.36.2) (2026-07-10)


### Bug Fixes

* ban --canonical-from override flag in canonical recipe bodies ([5f75348](https://github.com/thewoolleyman/livespec-dev-tooling/commit/5f7534856db5a3b88393ad1056c1afbf091cd506))

## [0.36.1](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.36.0...v0.36.1) (2026-07-10)


### Bug Fixes

* ban sys.{stdout,stderr}.buffer.write in no_write_direct ([8de1fca](https://github.com/thewoolleyman/livespec-dev-tooling/commit/8de1fcadafbe9c59a1e9a135198220f66f1ba72f))

## [0.36.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.35.3...v0.36.0) (2026-07-10)


### Features

* add canonical-recipe-fidelity anti-fork check ([d495016](https://github.com/thewoolleyman/livespec-dev-tooling/commit/d495016e3cb8904d873687778525681c8553d7f6))

## [0.35.3](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.35.2...v0.35.3) (2026-07-10)


### Bug Fixes

* exempt bin/*.py wrappers from all_declared ([0cd2145](https://github.com/thewoolleyman/livespec-dev-tooling/commit/0cd2145db85543de4151a990c4bc13adedcdfe12))

## [0.35.2](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.35.1...v0.35.2) (2026-07-09)


### Bug Fixes

* role-scope main_guard to plugin-packaging trees ([8b88bb2](https://github.com/thewoolleyman/livespec-dev-tooling/commit/8b88bb27afbe9de960c7ed46b1585610433e0116))

## [0.35.1](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.35.0...v0.35.1) (2026-07-09)


### Bug Fixes

* reconcile canonical check wiring in bump pins ([8975025](https://github.com/thewoolleyman/livespec-dev-tooling/commit/8975025f2aaf8e6e17b45eec3f8b5134b1f036d1))

## [0.35.0](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.34.5...v0.35.0) (2026-07-09)


### Features

* add partition completeness check ([b4d0882](https://github.com/thewoolleyman/livespec-dev-tooling/commit/b4d08829946f476ddbef9302d0d538bf7be3f43d))

## [0.34.5](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.34.4...v0.34.5) (2026-07-09)


### Bug Fixes

* cover remaining applies-to-all check stragglers ([c047da1](https://github.com/thewoolleyman/livespec-dev-tooling/commit/c047da19f7f55c1a8ac9c4b263c27588363ff0b4))

## [0.34.4](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.34.3...v0.34.4) (2026-07-09)


### Refactoring

* reshape resolve_check_universe to own root-resolution; drop vacuous empty-walk guard ([c72db0e](https://github.com/thewoolleyman/livespec-dev-tooling/commit/c72db0e6033f302ef8fccf4eafc00d3059e41945))

## [0.34.3](https://github.com/thewoolleyman/livespec-dev-tooling/compare/v0.34.2...v0.34.3) (2026-07-09)


### Bug Fixes

* reroute source_trees structural checks to the git-derived first-party universe ([d3b1441](https://github.com/thewoolleyman/livespec-dev-tooling/commit/d3b144105b12e9d7f382eaf3c8d3c4fd22e3d502))

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
