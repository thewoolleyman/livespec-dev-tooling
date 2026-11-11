---
proposal: gate-resources-lane-capacity-follow-ups.md
decision: modify
revised_at: 2026-11-11T15:37:19Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Modify: all five proposals applied, with clarifications from a pre-merge doctor pass. These are the gate-job-resources follow-ups (plan epic livespec-dev-tooling-ukoeah) that the v187 doctor LLM phase found, and they must land before C1b (livespec-dev-tooling-yznwz7) implements Lane capacity. (1) Lane capacity's comparison, and its read-or-parse refusal, now apply only to a repository that declares gate_cpu or gate_memory. A repository that declares neither requests the renderer's default, which Gate lane headroom keeps admissible, so it is never compared and never refused over the queue file; a new scenario states that. (2) The installed client parses cluster-queue-gates.yaml with a YAML parser that livespec_dev_tooling vendors, because the wheel's runtime dependencies are only anyio and typing-extensions and _vendor/ carries no YAML parser. (3) The lane-capacity scenario derives its threshold from the committed file instead of the stale literal 15 CPU / 24Gi (PowerEdge's lane is 30 cpu / 48Gi since livespec-dev-tooling#4139), per Tests never pin committed configuration values. (4) The largest lane is the flavor with the greatest nominal CPU quota, ties broken by memory and then file order, and the refusal names it. (5) The Spec-first note now names c3nd2h (livespec-dev-tooling#4148) as delivered and yznwz7 as the owner of Lane capacity. Proposal 1's sentence that gate_parallelism alone does not trigger the comparison is carried into the spec text, and proposal 2's unimportable-parser sentence follows the read-or-parse sentence it refers to. Delegated decision; a fresh independent read-only sonnet reviewer returned NO BLOCKERS on these exact bytes (an earlier review of the as-filed bytes also returned NO BLOCKERS; the doctor findings came after it).

## Modifications

A pre-merge doctor pass walked the as-filed text through live code (1 high, 2 medium findings that bind C1b). Lane capacity now also states: (a) the requests compared are the Job's effective requests, each declared value and otherwise the renderer default for that key, compared as Kubernetes quantities by value, not spelling; (b) the queue file is read from the same source the client chose for its renderer (resolve_renderer prefers the in-tree copy), and the wheel packages it at livespec_dev_tooling/gates/cluster-queue-gates.yaml beside the renderer; (c) the vendored YAML parser MUST NOT shadow a YAML library the consuming process imports under the same top-level name, because vendored libraries are put on sys.path at index 0 as top-level names; (d) proposal 2's 'a parser that the installed client cannot import' sentence is replaced by 'A file from which the gates-cq flavors and their nominal quotas cannot be extracted is a file the client cannot parse', since a vendored parser is always importable; (e) the container-worker-flavor sentence adds that the comparison MAY refuse a declaration only such a flavor could admit. The Kueue sentence stays directly after the comparison it explains.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-11T15:36:49Z
verdict: NO BLOCKERS
proposal_stem: gate-resources-lane-capacity-follow-ups
content_digest: a89ddcad460f1ec8d9b5b098dfeadbf38a6eebed2de9072362fad7dfe591efa0
