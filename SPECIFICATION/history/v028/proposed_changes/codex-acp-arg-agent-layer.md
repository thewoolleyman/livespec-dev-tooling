---
topic: codex-acp-arg-agent-layer
author: claude-opus-4-8
created_at: 2026-07-20T00:40:00Z
---

## Proposal: relocate the codex-acp `ARG` pin home to the agent layer

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Re-points the `codex-acp Dockerfile `ARG`` pin format in §"Pin autodiscovery rules" from `docker/fabro-sandbox/base/Dockerfile` to `docker/fabro-sandbox/agent/Dockerfile`. The fabro-sandbox layer chain gains an `agent` layer that carries the agent-only payload (bubblewrap and both ACP adapters), and the `ARG CODEX_ACP_VERSION` pin moves with the `npm install -g` line it governs. Nothing else about the format changes — the pin key, the bare-npm-semver value shape, the external npm source, the emit-filter rule, and the factory gate are all untouched.

### Motivation

Work-item `livespec-dev-tooling-a46`. Measured on release `v0.50.3`: the `base` layer is 706.6 MB compressed, of which **316.6 MB (45%) is agent-only payload** — bubblewrap (0.3 MB), `@agentclientprotocol/claude-agent-acp` (165.9 MB), and `@zed-industries/codex-acp` (150.4 MB). CI jobs across all eight fleet repos pull that payload on every job and use none of it: on a fast check job, 39s of a ~46s job is the image pull, for 1s of actual work.

Moving the agent payload out of `base` into an `agent` layer that sits ON TOP of `python` / `python-rust` takes CI's pull from 751 MB to 435 MB (−42%) for the seven `python-` consumers, and from 975 MB to 658 MB (−32%) for the one `python-rust-` consumer. The Fabro sandbox pulls the same total bytes as before.

The layer sits on top rather than beside `python` because the Fabro sandbox needs Python AND the adapters together; a sibling branch off `base` could not supply both. CI and the sandbox therefore continue to share byte-identical toolchain layers, which is the property the epic's "CI runs the SAME image the Fabro sandbox uses" guarantee actually depends on — this is a layer restructure, NOT a separate slim CI image.

The `ARG CODEX_ACP_VERSION` line must move with the `npm install -g @zed-industries/codex-acp` line it governs, because an ARG left behind in `base` would declare a pin home that installs nothing. Since §"Pin autodiscovery rules" names that path as contract surface, the contract must be amended in lockstep. Two mechanical surfaces that also name the path are NOT contract surface and are being updated in the implementation change: the `_CODEX_ACP_DOCKERFILE` constant in `livespec_dev_tooling/cross_repo/_pin_directory_scan_formats.py`, and its tests.

### Proposed Changes

Two verbatim replace-targets in `SPECIFICATION/contracts.md`, both inside the `codex-acp Dockerfile `ARG`` bullet of §"Pin autodiscovery rules". Each exists exactly once in the live file (verified against `origin/master` at `e787546`); re-verify before applying.

=== Replace-target A (REQUIRED — the pin's declared file home) ===

FIND (verbatim):
```
the `ARG CODEX_ACP_VERSION=<version>` line in `docker/fabro-sandbox/base/Dockerfile`
```

REPLACE WITH:
```
the `ARG CODEX_ACP_VERSION=<version>` line in `docker/fabro-sandbox/agent/Dockerfile`
```

=== Replace-target B (REQUIRED — the parenthetical naming the baking Dockerfile) ===

FIND (verbatim):
```
the `latest` dist-tag published to the same npm package the base Dockerfile's `npm install -g` bakes from
```

REPLACE WITH:
```
the `latest` dist-tag published to the same npm package the agent Dockerfile's `npm install -g` bakes from
```

### Drift sweep

Checked for neighbouring statements this change would falsify:

- §"codex-acp factory gate" (`### codex-acp factory gate`) refers to "the codex-acp Dockerfile `ARG` pin (§"Pin autodiscovery rules")" by reference only and names no Dockerfile path. Its version-less-adapter requirement (`npx --no-install`) is unaffected — the baked global still resolves, it is simply baked one layer higher. **No amendment needed.**
- No other statement in `SPECIFICATION/contracts.md`, `spec.md`, `constraints.md`, `non-functional-requirements.md`, or `scenarios.md` names `docker/fabro-sandbox/base/Dockerfile` or "base Dockerfile" (verified by ripgrep across the live spec tree; the only other hits are under `SPECIFICATION/history/`, which is frozen).
- The `fabro_sandbox_docker_image` pin format is untouched: it matches the untagged image name and is tag-prefix-agnostic, so the new `python-agent-` / `python-rust-agent-` tags need no contract change.

### Heading coverage

No `## ` heading is added, changed, or removed — both edits are inside an existing bullet under an existing H2. **No `tests/heading-coverage.json` co-edit is required.**
