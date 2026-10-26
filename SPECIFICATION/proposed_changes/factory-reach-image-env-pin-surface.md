---
topic: factory-reach-image-env-pin-surface
author: claude:delegated-gate-fleet-rollout
created_at: 2026-10-26T20:20:11Z
---

## Proposal: The fabro-sandbox image pin format also walks the factory-reach image env file

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Extend the fabro-sandbox docker image tag format in §"Pin autodiscovery rules" with a THIRD surface: the `FACTORY_REACH_SANDBOX_IMAGE=ghcr.io/thewoolleyman/livespec-fabro-sandbox:<tag>` line of `ci-runner/k3s/phase2/factory/factory-reach-image.env`. A dev-tooling release bump then rewrites that line in the same commit as the workflow `container:` `image:` pins it must equal. Add a scenario stating that.

### Motivation

Work item livespec-dev-tooling-7enfyd. `ci-runner/k3s/phase2/factory/factory-reach-image.env` (added 2026-10-16 under freeze ruling R70) ships a second copy of the fleet sandbox image pin. It exists because the verify-factory-reach converge artifact runs from the node's installed tree, which carries no workflow checkout. `livespec_dev_tooling/fabro_image_pin_lockstep.py` fails whenever it differs from `.github/workflows/ci.yml`'s `container:` `image:` pin, and the file's own header says to bump both in the same change. The pin autodiscovery walk names only the Fabro `workflow.toml` and workflow `container:` surfaces, so the release self-bump rewrites the workflows and never the env file. Every livespec-dev-tooling self-bump since then has gone red on check-metadata-batch (the lockstep check) and check-per-file-coverage (the factory-reach verifier tests). PRs #2852, #2855, #2860, #2865, #2871, #2876 and #2879 closed unmerged and #2882 is red the same way, so master still pins `python-v1.110.0`. The lockstep check is right to go red, and moving the pin into a workflow file would break R70's reason for the file. The bump therefore has to see the env file.

### Proposed Changes

In SPECIFICATION/contracts.md §"Pin autodiscovery rules", the **fabro-sandbox docker image tag** bullet MUST gain the following sentences immediately after the sentence ending "...is covered by the same scoped match).":

> The SAME image reference is ALSO pinned, for livespec-dev-tooling's factory reach check, in `ci-runner/k3s/phase2/factory/factory-reach-image.env`. The matched line is `FACTORY_REACH_SANDBOX_IMAGE=ghcr.io/thewoolleyman/livespec-fabro-sandbox:<tag>`; `#` comment lines and blank lines yield no record. The walk MUST treat that line as THIS SAME format, with the same `pin_key` and `current_value` derivation, so a release bump rewrites it in the SAME commit as the workflow `container:` `image:` pins it MUST equal. A consumer without that file yields no record of this surface. A present file the walk cannot PARSE, for example one naming two `FACTORY_REACH_SANDBOX_IMAGE` values, MUST be surfaced as the typed can't-parse outcome below, never as an unrecognized format and never as a record.

The bullet's later sentence "A consumer may carry the pin at MORE THAN ONE path (a Fabro `workflow.toml` AND one or more `.github/workflows/` files)" MUST read "(a Fabro `workflow.toml`, one or more `.github/workflows/` files, AND the factory-reach image env file)". Every other sentence of the bullet is unchanged; in particular EVERY matching line in EVERY file MUST still be rewritten in the same bump commit.

In SPECIFICATION/scenarios.md a new scenario MUST be added:

```
## Scenario: a dev-tooling release bump rewrites the factory-reach image pin with the workflow image pins

Given a repository whose `.github/workflows/ci.yml` pins `ghcr.io/thewoolleyman/livespec-fabro-sandbox:python-v1.110.0` under a job's `container:` block

And whose `ci-runner/k3s/phase2/factory/factory-reach-image.env` carries `FACTORY_REACH_SANDBOX_IMAGE=ghcr.io/thewoolleyman/livespec-fabro-sandbox:python-v1.110.0`

When a livespec-dev-tooling release v1.134.5 bumps the repository's pins

Then the pin autodiscovery walk MUST yield a fabro-sandbox docker image tag record for the env-file line

And the bump commit MUST rewrite both lines to `python-v1.134.5`
```

The revise that accepts this MUST add a `tests/heading-coverage.json` entry for the new scenario heading in the same change. The entry MAY be `"test": "TODO"` with `work_item` livespec-dev-tooling-7enfyd until that item's test lands.
