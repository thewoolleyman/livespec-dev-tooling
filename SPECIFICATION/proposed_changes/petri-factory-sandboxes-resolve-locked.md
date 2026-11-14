---
topic: petri-factory-sandboxes-resolve-locked
author: claude-opus-5-5
created_at: 2026-11-12T05:46:00Z
---

## Proposal: Fabro factory sandboxes resolve locked Python packages through the pool's host-served PyPI files cache, falling through to the public index

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Extend §"Runner-pool build cache tiers" so the host-served uv dependency cache, like the compilation cache already, has fabro factory sandboxes as a consumer. A factory sandbox's uv installs of locked packages take the pool's PyPI files cache for every distribution it holds, by swapping the locked file-host prefix for the call, and fall through to the public index when the cache is unreachable or lacks a distribution. Every cache-served distribution is still verified against the lock file's hash, and a mismatch fails the install rather than falling through. A factory sandbox is made a job for the trust rules. Add the matching scenario. Graded PASS with the hash clause added by legacy-coordinator-agent, 2026-11-12.

### Motivation

Factory sandboxes fetch locked Python distributions straight from files.pythonhosted.org during their prepare steps, so a PyPI timeout fails a run before any work starts. Measured 2026-11-12 by the ci-runtime-and-cost session: petri run 01M773D4RYKY (livespec-dev-tooling-5ua57h, on gmktec-xubuntu) failed at run_prepare_4 (`uv run lefthook install`) at 05:27:55Z, after uv's download of pytest_icdiff-0.9 from files.pythonhosted.org timed out on all 5 retries.

The section today requires the warm dependency cache only for routed repositories' jobs, and names fabro factory sandboxes only as a second consumer of the compilation cache. So no clause requires, or bounds, a factory sandbox's use of the PyPI files cache. Work item livespec-dev-tooling-uqmdor carries the implementation. legacy-coordinator-agent holds it at spec-change tier, as an unstated generalization of this section, until this topic ratifies.

The mechanism already exists for other consumers: ci-runner/k3s/phase2/warm-cache/pypi-proxy/ serves the cache, the populator and gate Jobs read it, and runner-only hp-xubuntu workflow pods reach it through a read-only uv wrapper that probes the cache and rewrites only the locked file-host prefix for the call. Its README records why a prefix swap and not an index: `uv sync --frozen` downloads from the absolute file URLs in uv.lock, and a global index can make a locked `uv run` unsatisfiable.

In-flight survey (2026-11-12 ~06:45Z): two in-flight proposals touch this section, both in other paragraphs, and this proposal ALIGNS with both. the-crates-proxy-serves-the (livespec-dev-tooling#3785) adds a **Release assets.** paragraph after **Tiers.** whose "a consumer MUST verify the pinned sha256 itself; the proxy is a cache, never a trust root" is the same trust stance as this proposal's hash clause. the-arc-container-hook-crashes (pending) adds a paragraph after **Fail-soft and kill switch.**. This proposal inserts sentences inside **Tiers.**, **Trust by construction.** and **Fail-soft and kill switch.** and adds one scenario, so none of them conflicts.

### Proposed Changes

In `non-functional-requirements.md` §"Runner-pool build cache tiers", in the **Tiers.** paragraph, directly after the sentence ending "so that one host service has two consumers.", insert:

> The pool's host-served cache of the Python package file host MUST likewise be reachable from every fabro factory sandbox. A factory sandbox's uv install of locked packages MUST download every locked distribution that cache holds through it, by rewriting the locked file-host prefix for that call only and never by setting a global index. A factory sandbox whose cache is unreachable, or that lacks a distribution, MUST download that distribution from the public index, as it would without the tier. Every distribution downloaded through the cache MUST still be verified against the hash the lock file records, and a hash mismatch MUST fail the install rather than fall through.

In the same section, in the **Trust by construction.** paragraph, directly after the sentence "A delegated gate Job is a job for every rule of this paragraph.", insert:

> A fabro factory sandbox is a job for every rule of this paragraph.

In the same section, in the **Fail-soft and kill switch.** paragraph, after "that disables every tier for every job", insert: ", and every factory sandbox route of this section".

In `scenarios.md`, add the following scenario directly after the last scenario that governs §"Runner-pool build cache tiers":

~~~markdown
## Scenario: a fabro factory sandbox resolves locked Python packages through the pool's PyPI files cache and falls through to the public index when the cache is unreachable

Given a petri factory run whose prepare steps install the target repository's locked Python packages with uv, and the pool's host-served cache of the Python package file host
When the run's prepare steps install those packages while the cache holds every locked distribution
Then every locked distribution MUST be downloaded through the cache, and no download from the public file host MUST occur for a distribution the cache holds
And when the cache is unreachable, the same prepare steps MUST install every locked distribution from the public index and the run MUST continue to its next stage
And with the fleet kill switch set, the same prepare steps MUST download from the public index without consulting the cache
And when the cache returns bytes for a locked distribution that do not match the hash the lock file records, the install MUST fail and MUST NOT fall through to the public index
~~~

Because the revise adds a `## ` heading to `scenarios.md`, it co-edits `tests/heading-coverage.json` with an entry for the new scenario heading. Its `test` MAY be "TODO" with a non-empty reason until livespec-dev-tooling-uqmdor binds a test.
