---
topic: an-apply-never-installs-a
author: claude-opus-5-5:kubernetes-sandbox-backend
created_at: 2026-11-03T14:09:09Z
---

## Proposal: An apply never installs a sandbox-driver plugin binary whose digest differs from a Fabro instance's pin, and drift compares each live pin to the installed binary

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Add a paragraph to non-functional-requirements.md §"Fabro factory host provisioning" stating that the role installing a sandbox-provider plugin binary on a factory host MUST refuse, before downloading or moving anything, when the binary's sha256 differs from the sha256 that any fabro_server instance on that host pins for that binary's path, naming each disagreeing instance and both digests. It MUST install as before when every instance's pin agrees. `just ansible-drift ansible/fabro-hosts.yml` MUST report, per instance and per sandbox provider, whether the sha256 in that instance's live settings.toml equals the sha256 of the binary installed at that provider's path, and MUST mark a disagreement as drift. Add one scenario to scenarios.md stating that behaviour.

### Motivation

On 2026-11-03 at 09:01:10Z an apply of the sandbox_driver_kubernetes role (livespec-dev-tooling PR #3178) replaced /usr/local/bin/sandbox-driver-kubernetes on gmktec-xubuntu with v0.7.0 (sha256 93ca024d). Every live Fabro instance's settings.toml still pinned v0.5.0 (d93437f0). Fabro verifies the plugin's sha256 against the instance's pin at EVERY plugin launch, not only at server start, so every launch failed with 'sha256: checksum mismatch' and six factory runs died before the binary was restored at 09:14:51Z. Nothing in the committed automation compared the role's binary digest with the instance pins in fabro_server host_vars, and no drift run compared a live pin with the installed binary. Git had already drifted before the incident (role default and fleet pin at v0.6.0, live at v0.5.0) and no drift report flagged it. Work-item livespec-dev-tooling-rnsfgg implements the guard and the drift comparison. The dispatcher holds it as spec-change tier because no ratified heading states this behaviour: §"Fabro factory host provisioning" governs the play, the instances and the warm, but says nothing about plugin binaries or their pins.

### Proposed Changes

In `SPECIFICATION/non-functional-requirements.md` §"Fabro factory host provisioning", add this paragraph after **One instance per mapping.**:

**A plugin binary and every pin on it agree.** A Fabro server instance pins each sandbox-provider plugin it launches by path and sha256 in its rendered `settings.toml`, and Fabro verifies that sha256 at every plugin launch. The role that installs a sandbox-provider plugin binary on a factory host MUST therefore refuse, before it downloads, moves or replaces any file, an apply in which the binary's sha256 differs from the sha256 that any `fabro_server_instances` mapping on the same host declares for that binary's path. The refusal MUST name each disagreeing instance and both digests. When every instance on the host that declares that path declares the same sha256 as the binary, the role MUST install the binary as it does today. `just ansible-drift ansible/fabro-hosts.yml` MUST report, for each Fabro server instance on a host and for each sandbox provider that instance pins, whether the sha256 in the instance's LIVE `settings.toml` equals the sha256 of the file installed at that provider's path, and MUST report a disagreement as drift. A change of plugin version therefore MUST change the binary and every pin on it together; a rollout that needs instances on different versions MUST give each version its own install path.

In `SPECIFICATION/scenarios.md`, add after "## Scenario: the fabro_server role deletes an instance's retired sandbox environments":

## Scenario: an apply refuses a plugin binary whose digest differs from an instance pin, and drift compares live pins to the installed binary

Given a factory host whose `fabro_server_instances` declare sha256 `d93437f0...` for the sandbox provider at `/usr/local/bin/sandbox-driver-kubernetes`

When an apply of the role that installs that plugin carries sha256 `93ca024d...` for the same path

Then the apply MUST fail before the binary is downloaded or moved, naming each disagreeing instance and both digests

And the file at that path MUST be unchanged

And an apply whose plugin sha256 equals every instance's declared pin for that path MUST install the binary

And `just ansible-drift ansible/fabro-hosts.yml` MUST report as drift any instance whose live `settings.toml` sha256 for that provider differs from the sha256 of the installed binary

The heading-coverage map `tests/heading-coverage.json` MUST gain an entry for the new scenario heading in the same revision; its `test` MAY be `"TODO"` with a reason naming livespec-dev-tooling-rnsfgg until that item lands its test.
