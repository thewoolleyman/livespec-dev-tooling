---
topic: sandbox-image-warm-keeps-only-current-tags
author: claude-opus-5-5
created_at: 2026-11-02T05:57:47Z
---

## Proposal: The sandbox image warm keeps only the current pinned tags in both image stores

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Adds one clause to §"Fabro factory host provisioning", with no new H2 heading in that file. Once the current pinned set is present, the sandbox image warm (`ansible/roles/sandbox_image_warm`) removes the sandbox image tags it pulled itself for earlier pins. This applies to both stores it fills: k3s containerd on factory nodes, and a Docker factory host's image store. The warm never removes a tag that a running pod or sandbox container uses, or a tag it did not pull. Two scenarios state the removal and the protection of in-use tags. Each store therefore holds at most the current pinned set plus the tags in use, and its disk use no longer grows with the number of fleet releases.

### Motivation

Filed for work-item livespec-dev-tooling-xknoqf, on the order of coordinator legacy-coordinator-agent (epic livespec-dev-tooling-6tgd2z) and its 2026-11-02 ruling, which replaced retiring gmktec's Docker warm. xknoqf's filing classified it as spec-change tier: no ratified clause states that the warm removes tags or that it protects tags running pods use. Evidence measured read-only on gmktec-xubuntu on 2026-11-02: the Docker warm pulls two new sandbox tags per fleet release, python-agent at about 4.52 GB and python-rust-agent at about 6.01 GB. On 2026-11-01 alone it pulled v1.145.0, v1.145.1, v1.146.0 and v1.146.1. docker-prune keeps images younger than 72 h, so about 135 G accumulated before disk_guard's emergency prune freed it at 01:14Z, and the warm re-pulled both v1.146.1 tags two minutes later. The new containerd warm pulls the same two tags per release into k3s containerd on every factory node. Kubelet image GC reclaims those only when disk use crosses its high threshold (85 percent by default), so the same accumulation recurs there and is cleared only near-full. The Docker warm itself MUST stay, because gmktec's livespec-ci-rust environment is still Docker-backed and the warm is what closes the first-pull race of livespec-dev-tooling-dq3km7. That is why this clause bounds what the warm keeps rather than retiring it.

### Proposed Changes

In `SPECIFICATION/non-functional-requirements.md` §"Fabro factory host provisioning", insert the following paragraph after the **Sandbox resource envelope.** paragraph:

> **The sandbox image warm keeps only current tags.** This clause governs every sandbox image warm the `sandbox_image_warm` role installs, whether it fills a k3s node's containerd store or a Docker factory host's image store. Once every tag of the warm's currently pinned set is present in its store, the warm MUST remove from that store each sandbox image tag it pulled itself for an earlier pin. The store then holds no more than the current pinned set plus the tags in use, and its disk use does not grow with the number of releases. The warm MUST NOT remove a tag that a running pod uses (containerd store) or that a running sandbox container uses (Docker store). It MUST NOT remove a tag it did not pull itself. It MUST NOT start a removal pass while any tag of the current pinned set is absent from its store, so a failed or partial pull never leaves the host without a usable sandbox image. The warm MUST tell the tags it pulled apart from tags it did not pull, and that distinction MUST survive a reboot. A removal that fails MUST leave the tag in place and MUST make that warm run exit non-zero, naming the tag. The role's `HOST_VARS.md` MUST document how the warm records the tags it pulled, and how the removal pass is rolled back. This clause does not change how other images in either store are retained, such as kubelet image garbage collection or a host's docker prune.

In `SPECIFICATION/scenarios.md`, append these two scenarios directly after `## Scenario: converging the Fabro sandbox envelope never restarts dockerd outside a drained window`:

```
## Scenario: the sandbox image warm removes the tags it pulled for an earlier pin once the current pin is present

Given a factory host whose sandbox image warm previously pulled the tags of an earlier pin into its image store

And the store also holds a sandbox image tag the warm did not pull

When a release bump moves the warm's pin and a warm run has pulled every tag of the new pinned set

Then the store MUST hold every tag of the new pinned set

And the store MUST NOT hold any tag the warm pulled for the earlier pin that no running pod or sandbox container uses

And the tag the warm did not pull MUST still be present

And this MUST hold alike for a k3s node's containerd store and for a Docker factory host's image store

## Scenario: the sandbox image warm keeps an earlier-pin tag that a running sandbox still uses

Given a factory host whose sandbox image warm pulled the tag of an earlier pin, and a running pod or sandbox container on that host uses that tag

When a warm run pulls every tag of a newer pinned set and makes its removal pass

Then the tag the running pod or sandbox container uses MUST still be present in the store

And a later warm run, made after that pod or container has ended, MUST remove that tag

And a warm run in which any tag of the current pinned set is absent MUST NOT remove any tag
```

Because this adds two new `## ` headings to `scenarios.md`, the same change MUST add one `tests/heading-coverage.json` entry for each heading. Each entry MUST carry `"test": "TODO"`, a non-empty `reason` saying that a host-captured exercise of the role on a real factory node is owed, and `"work_item": "livespec-dev-tooling-xknoqf"`. The section heading `## Fabro factory host provisioning` is unchanged, so its existing coverage entry MUST NOT change.
