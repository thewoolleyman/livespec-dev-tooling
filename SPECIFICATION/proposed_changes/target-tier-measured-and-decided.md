---
topic: target-tier-measured-and-decided
author: fable
created_at: 2026-09-06T15:46:35Z
---

## Proposal: target-directory tier: seeded, key-scoped to shapes the compilation cache cannot serve; the array-gate and measure-first obligations discharged

### Target specification files

- SPECIFICATION/non-functional-requirements.md

### Summary

Replace the Tiers paragraph's target-directory sentence. The current text permits the tier 'through the copy mechanism', forbids shipping it while the work-volume tier lives on the array, and requires a one-time measured decision. All three are now resolved facts: the work-volume tier is on the reflink-capable NVMe, the measurement was taken (plan/ci-runner-cache-tiers/research/012, merged 18d54cc4; D5 RESOLVED on epic livespec-dev-tooling-efqeip), and the tier shipped as a reflink SEED for one key (the console's ASAN fuzz tree, c4b70c2c: compile 78 s -> 4 s at P50, n = 21) while the dev/test key was dropped by measured headroom (<= 20 s per job over the compilation cache). The new text states the standing rule those facts produced: seeded never byte-copied; key-scoped to compile shapes the compilation cache cannot serve; populator-built under the guardrails; every further key measured and recorded before it ships; no general dev/test key.

### Motivation

Work item livespec-dev-tooling-c5byjh carries this clause's spec commitment (v054 id_hint target-warm-cache-measured); the plan's child-disposition primitive refuses to close it as a session disposition because of that commitment, so the measured decision must land in the spec before the item can close. The clause as written also misdescribes what shipped: 'through the copy mechanism' names the byte copy that research/005 rejected on the array and that the reflink seed replaced, and the array gate and the measure-first obligation are discharged rather than standing. No Gherkin scenario is added: this paragraph and its siblings (Storage placement, Populator guardrails) are contributor-facing pool-infrastructure requirements verified by the plan store and the host-side acceptance recipes, and none of them carries a scenarios.md entry today; adding one only to this sentence would be inconsistent with the section. The 'one host service, two consumers' sentence in the same paragraph is deliberately untouched by this proposal: the factory's compilation-cache design changed under the console plan (livespec-console-beads-fabro-di6fn5, a factory-local backend) and that drift is a separate proposal for its owner.

### Proposed Changes

In `SPECIFICATION/non-functional-requirements.md` §"Runner-pool build cache tiers", **Tiers** paragraph, the target-directory sentence MUST read as the `+` line below; the array-gate and measure-first obligations of the `-` line are discharged, not carried forward.

```diff
--- SPECIFICATION/non-functional-requirements.md
+++ SPECIFICATION/non-functional-requirements.md
@@ **Tiers.** (the fourth sentence of the paragraph) @@
-The pool MAY provide a per-repository warm target-directory cache through the copy mechanism, but MUST NOT ship it while the pod work-volume tier lives on the array, and MUST decide whether to ship it on faster media by measurement against the sccache-only shape on the routed Rust repository's full matrix, recording the decision in the plan store.
+The pool MAY provide a per-repository warm target-directory cache only as a SEEDED tree — a host-side generation the provisioner seeds into each work volume exactly as it seeds the dependency tier, under the reflink rule of **Storage placement** — and MUST NOT provide it as a per-start byte copy. Such a tree MUST be key-scoped: each key names one compile shape the shared compilation cache cannot serve (a build whose objects no other job in the fleet produces, such as a sanitizer-instrumented fuzz build), and MUST be built only by the populator under **Populator guardrails**, rebuilt only when the consuming repository's default-branch commit or that key's toolchain changes. A key MUST NOT ship until the plan store records its measured before/after on the consuming job against the compilation-cache-only shape together with the generation's size and file count, and a key whose measured headroom over the compilation cache is within that job's run-to-run variance MUST NOT ship. The pool MUST NOT provide a general dev-profile or test-profile target-directory key: the measurement the previous form of this clause required was taken once the work-volume tier reached the reflink-capable medium, and the decision it produced — rely on the compilation cache for every compile shape it reaches — is the standing one; the plan store record that carries it is the evidence a future proposal MUST supersede to reintroduce such a key.
```

Everything else in the paragraph — the dependency tiers, the host-served preference, the compilation cache and its two consumers — MUST remain as it is.
