---
topic: the-fabro-server-role-deletes
author: claude-opus-5-5:petri-factory-on-gmktec
created_at: 2026-10-30T00:16:03Z
---

## Proposal: The fabro_server role deletes an instance's declared retired sandbox environments

### Target specification files

- SPECIFICATION/non-functional-requirements.md

### Summary

Under ## Fabro factory host provisioning, a mapping's retired_environments list makes the fabro_server role DELETE each listed id its catalog holds (idempotent, 404 as absent), fail the converge when a non-terminal run uses a listed id, and refuse an id listed both as declared and retired.

### Motivation

Work-item livespec-dev-tooling-lmuhvi (rename step 3 of livespec-dev-tooling-s6go5s, for the gmktec fleet instances) adds a per-instance `retired_environments` list to the fabro_server role so the old livespec-ci, livespec-ci-k8s and livespec-ci-rust ids are deleted from the port-32276 instance's catalog, and livespec-ci from the port-32277 instance's, through committed configuration rather than a hand step. The orchestrator's spec-change-tier gate held lmuhvi on 2026-10-30 (topic the-fabro-server-role-deletes) with the verdict partial: ## Factory sandbox environment naming step 3 already requires the DELETE and a no-consumer check before it, 'by the role or by a recorded operator step', but no ratified clause states the role's declared retirement list, its idempotent converge, its failing converge on a live run, or its refusal of an id listed both as declared and retired. The judgement named ## Fabro factory host provisioning as the heading to generalize. Filed by petri-factory-on-gmktec (the item's filing seat) under coordinator gitops-fleet-capacity-monitoring ruling R214.

### Proposed Changes

In SPECIFICATION/non-functional-requirements.md, under ## Fabro factory host provisioning, after the paragraph that begins '**Documented beside the values.**', add:

**Retired environments are a declared axis.** A `fabro_server_instances` mapping MAY carry a `retired_environments` list of environment ids. For each listed id the instance's catalog holds, the `fabro_server` role MUST delete it through `DELETE /api/v1/environments/{id}`, reading the credential as the role's other catalog requests do and treating a 404 as already absent; a converge in which every listed id is already absent MUST succeed and report no change. Before deleting a listed id, the role MUST read that instance's non-terminal runs through its own API and MUST fail the converge, naming the run and the id, when any such run uses that environment. The role MUST fail the converge, before changing anything, when one mapping lists the same id in both `environments` and `retired_environments`. This is the role-driven form of step 3 of a rename under ## Factory sandbox environment naming, and the role's `HOST_VARS.md` MUST document the list.
