# livespec fleet Fabro sandbox image — AGENT layer.
#
# The agent-only payload: bubblewrap plus BOTH preinstalled ACP adapters.
# Built TWICE from this one file — once atop `python` (published as
# `python-agent-*`) and once atop `python-rust` (published as
# `python-rust-agent-*`) — because the Fabro sandbox needs the toolchain
# AND the adapters, so this cannot be a sibling branch off `base`.
#
# WHY THIS PAYLOAD IS NOT IN `base`: the two consumer classes of this
# image chain want different things. GitHub Actions CI jobs across the
# fleet want only the toolchain, while the Fabro agent sandbox wants the
# toolchain plus the adapters. The adapters are 316.6 MB compressed
# (bubblewrap 0.3 MB, @agentclientprotocol/claude-agent-acp 165.9 MB,
# @zed-industries/codex-acp 150.4 MB) that CI never executes; hoisting
# them out of `base` into this on-top layer cuts CI's pull from 751 MB to
# 435 MB (~42%) while keeping CI and the sandbox on BYTE-IDENTICAL
# toolchain layers — there is no separate slim CI image and therefore no
# CI-vs-sandbox drift.
#
# Contents:
#   - bubblewrap (HARD codex-acp requirement — for BOTH its
#     require_escalated command execution AND its apply_patch edit tool;
#     dropping it silently breaks Codex-driven runs)
#   - BOTH ACP adapters preinstalled globally so `npx -y <adapter>`
#     resolves locally: @agentclientprotocol/claude-agent-acp (Claude)
#     and @zed-industries/codex-acp (the orchestrator's Codex adapter,
#     baked not per-run npx-fetched)
#
# node itself stays in `base`: CI genuinely needs it (pyright shells out
# to npm), so it is toolchain, not agent payload. NO secrets are baked;
# credentials reach the sandbox per run via the Fabro environment env
# table.
#
# PARENT_IMAGE is passed by the build pipeline as the exact python or
# python-rust image reference just built (digest-pinned, not a floating
# tag, so the CI chain is hermetic). Its default is the documented python
# local-development tag, which keeps standalone Dockerfile validation valid;
# CI always overrides it with the exact python or python-rust digest. The name
# is generic rather than `PYTHON_IMAGE` / `PYTHON_RUST_IMAGE` because this one
# file is built atop two different parents.
#
# Build (context = REPO ROOT; the adjacent Dockerfile.dockerignore
# excludes everything — this layer COPYs nothing):
#   docker build -f docker/fabro-sandbox/agent/Dockerfile \
#     --build-arg PARENT_IMAGE=livespec-fabro-sandbox:python-dev \
#     -t livespec-fabro-sandbox:python-agent-dev .
#
# Published as ghcr.io/<owner>/livespec-fabro-sandbox with immutable
# python-agent-sha-<short> / python-agent-v<X.Y.Z> and
# python-rust-agent-sha-<short> / python-rust-agent-v<X.Y.Z> tags.
ARG PARENT_IMAGE=livespec-fabro-sandbox:python-dev
FROM ${PARENT_IMAGE}

# ---------------------------------------------------------------
# Adapter pins — ARG form so `just check-fabro-image-pin-lockstep` can
# parse them mechanically across the layer Dockerfiles.
# CLAUDE_AGENT_ACP_VERSION has no repo-side pin source — it mirrors the
# host toolchain and is tracked only here.
#
# CODEX_ACP_VERSION is DIFFERENT: this ARG is the SINGLE SOURCE OF TRUTH
# for the baked @zed-industries/codex-acp adapter version — it does not
# merely mirror the orchestrator's hardcoded implementer-adapter pin. The
# pin-autodiscovery walk emits it (pin_format `codex_acp_docker_arg`)
# autodiscovered from the npm registry, and the pin-freshness surface
# opens a bump PR on any npm `latest` difference, gated by a live
# Codex-provider factory run before the bump may merge. See
# livespec-dev-tooling/SPECIFICATION/contracts.md §"codex-acp factory
# gate" and tracker bd-ib-ss7rkr.
#
# WHERE THAT GATE RUNS: on an ON-DEMAND PRIVILEGED runner (ci-runner/
# gate-runner/), not the contained CI runner — the golden master needs
# Docker, the host Codex credential, and the operator's secrets, all of
# which the CI containment denies. No privileged runner idles: one
# single-use runner is minted only for a queued gate-workflow run on a
# write-access-gated event, so a bump PR (and nothing else) can reach it.
# ---------------------------------------------------------------
ARG CLAUDE_AGENT_ACP_VERSION=0.44.0
ARG CODEX_ACP_VERSION=0.16.0

# bubblewrap — required by the codex-acp adapter. The chain's root
# (buildpack-deps:noble-scm) is Debian/Ubuntu, so apt is correct; clean
# the apt lists in the same layer to keep the image lean.
RUN apt-get -o Acquire::Retries=5 update \
    && apt-get -o Acquire::Retries=5 install -y --no-install-recommends bubblewrap \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# npm retries by default, but only twice; raise it to match the other fetchers
# here. npm applies its own exponential backoff between attempts.
RUN npm install -g --fetch-retries=5 \
        @agentclientprotocol/claude-agent-acp@${CLAUDE_AGENT_ACP_VERSION}

RUN npm install -g --fetch-retries=5 \
        @zed-industries/codex-acp@${CODEX_ACP_VERSION}
