---
proposal: state-writing-cli-requires-explicit-state-path.md
decision: modify
revised_at: 2026-11-12T11:16:15Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

The rule is accepted as the coordinator okayed it on 2026-11-12 (~04:05Z, GO on livespec-dev-tooling#4258): a livespec_dev_tooling entry point that writes host state takes each state location only from an explicit flag, refuses without it while touching nothing, and every committed invoker passes the flag, with the test suite failing on one that does not. It is placed in non-functional-requirements.md §"Testing approach" because it is a contributor-side test-isolation rule. A pre-review doctor pass that walked the draft through live code found that the literal text would have broken the Docker engine install guard's dead-man: §"Docker engine install guard" **Arm and the dead-man** fixes the dead-man command as `rollback <run>`, and `_docker_engine_guard_model.py` builds that argv (and the observe-triggered rollback) with no root flags, so a flag-required guard would refuse its own safety net, and the invoker scan would not see it. Its committed invokers are also ansible task files, not templates, and `install_guard.yml` probes the guard with `--help`. The modifications close each of those. The independent sonnet review returned NO BLOCKERS on the exact bytes. No design record is contradicted: the guard section's paths stay true as production flag values.

## Modifications

Relative to the proposal: (1) a `-h`/`--help` invocation is exempt and still exits 0; (2) committed invokers are named as systemd units, ansible task files or templates, or scripts; (3) every argv the entry point builds to re-invoke itself (a transient unit or timer started through `systemd-run`) must also pass the flags, and a command another section names, such as the Docker guard's dead-man and observe-triggered `rollback <run>`, carries the state-location flags in addition; (4) a wrapper that only forwards its arguments is judged through its callers; (5) the Docker guard section's `/var/lib/docker-engine-guard` and `/run/docker-engine-guard` are stated to be the production values of `--state-root` and `--runtime-root`, with the flag check before that section's first-ensure step; (6) a spec-first note names livespec-dev-tooling-6cgj2e; (7) the second scenario's Given names ansible task files or templates, and the first scenario's last line names the location the flag would have defaulted to.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-12T11:15:24Z
verdict: NO BLOCKERS
proposal_stem: state-writing-cli-requires-explicit-state-path
content_digest: d95df0f4554b94bf19282d72423ca88cb140339bd7fb0f13e28c2555f06a6de3
