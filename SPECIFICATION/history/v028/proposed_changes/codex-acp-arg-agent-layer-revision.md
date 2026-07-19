---
proposal: codex-acp-arg-agent-layer.md
decision: accept
revised_at: 2026-07-19T22:32:00Z
author_human: thewoolleyman <chad@thewoolleyman.com>
author_llm: claude-opus-4-8
---

## Decision and Rationale

Relocates the codex-acp `ARG` pin's declared file home from `docker/fabro-sandbox/base/Dockerfile` to `docker/fabro-sandbox/agent/Dockerfile`, so the pin stays co-located with the `npm install -g @zed-industries/codex-acp` line it governs once the agent-only payload moves out of the base layer (work-item livespec-dev-tooling-a46: 316.6 MB of the 706.6 MB base layer is agent-only payload CI never uses; moving it cuts CI's pull 42%). Independent Fable review returned NO BLOCKERS: both replace-targets verified byte-exact and unique against origin/master e787546, drift sweep independently reproduced across the live spec tree, §"codex-acp factory gate" confirmed to need no amendment (it names the pin by format and section reference, never by path), topic/stem match confirmed, and no `## ` heading changes so no tests/heading-coverage.json co-edit is required. Nothing else about the pin format changes: pin key, bare-npm-semver value shape, external npm source, emit-filter rule, and the factory gate are all untouched.

## Resulting Changes

- contracts.md
