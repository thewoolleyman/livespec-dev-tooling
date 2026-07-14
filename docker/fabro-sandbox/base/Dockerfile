# livespec fleet Fabro sandbox image — BASE layer.
#
# The bottom of the base → python → python-rust chain. Bakes the
# harness-neutral toolchain every consumer needs regardless of language:
#   - bubblewrap (HARD codex-acp requirement — for BOTH its
#     require_escalated command execution AND its apply_patch edit tool;
#     dropping it silently breaks Codex-driven runs)
#   - mise (single tool manager; version mirrors the host)
#   - just / lefthook at this repo's .mise.toml pins
#   - node (required by the ACP adapters; Fabro does not install
#     node/npx at runtime; mirrors the host)
#   - gh (the pr node's CLI; mirrors the host)
#   - BOTH ACP adapters preinstalled globally so `npx -y <adapter>`
#     resolves locally: @agentclientprotocol/claude-agent-acp (Claude)
#     and @zed-industries/codex-acp (the orchestrator's Codex adapter,
#     baked not per-run npx-fetched; version mirrors the orchestrator pin)
#   - livespec-step-timer: the stdlib-only sandbox prepare-step timing
#     wrapper (each dispatched workflow.toml prepare step runs as
#     `livespec-step-timer <slug> -- <cmd>`; see livespec-dev-tooling
#     otel_step_timer.py). It lives in BASE so it is on PATH for every
#     consumer's prepare steps, before the first `uv sync`.
#
# uv + CPython live in the `python` layer; rustc/cargo in `python-rust`.
# NO secrets are baked; credentials reach the sandbox per run via the
# Fabro environment env table.
#
# Build (context = REPO ROOT so the livespec-step-timer COPY below reads
# this repo's own file; the adjacent Dockerfile.dockerignore allowlists
# only that file into the context):
#   docker build -f docker/fabro-sandbox/base/Dockerfile -t livespec-fabro-sandbox:base-dev .
#
# Published by .github/workflows/fabro-sandbox-image.yml as
# ghcr.io/<owner>/livespec-fabro-sandbox with immutable base-sha-<short>
# (per master build) and base-v<X.Y.Z> (per release) tags.
FROM buildpack-deps:noble

# ---------------------------------------------------------------
# Tool pins — ARG form so `just check-fabro-image-pin-lockstep` can
# parse them mechanically across the layer Dockerfiles. JUST_VERSION /
# LEFTHOOK_VERSION MUST match this repo's .mise.toml `[tools]` pins (the
# check fails the build pipeline on drift). MISE_VERSION / NODE_VERSION /
# GH_VERSION / CLAUDE_AGENT_ACP_VERSION have no repo-side pin source —
# they mirror the host toolchain and are tracked only here.
#
# CODEX_ACP_VERSION is DIFFERENT: this ARG is now the SINGLE SOURCE OF
# TRUTH for the baked @zed-industries/codex-acp adapter version — it no
# longer merely mirrors the orchestrator's hardcoded implementer-adapter
# pin. The pin-autodiscovery walk emits it (pin_format
# `codex_acp_docker_arg`) autodiscovered from the npm registry, and the
# pin-freshness surface opens a bump PR on any npm `latest` difference,
# gated by a live Codex-provider factory run before the bump may merge.
# See livespec-dev-tooling/SPECIFICATION/contracts.md §"codex-acp factory
# gate" and tracker bd-ib-ss7rkr.
#
# WHERE THAT GATE RUNS: on an ON-DEMAND PRIVILEGED runner (ci-runner/
# gate-runner/), not the contained CI runner — the golden master needs
# Docker, the host Codex credential, and the operator's secrets, all of
# which the CI containment denies. No privileged runner idles: one
# single-use runner is minted only for a queued gate-workflow run on a
# write-access-gated event, so a bump PR (and nothing else) can reach it.
# ---------------------------------------------------------------
ARG MISE_VERSION=v2026.2.7
ARG JUST_VERSION=1.36.0
ARG LEFTHOOK_VERSION=1.13.6
ARG NODE_VERSION=26.3.0
ARG GH_VERSION=2.46.0
ARG CLAUDE_AGENT_ACP_VERSION=0.44.0
ARG CODEX_ACP_VERSION=0.16.0

# bubblewrap — required by the codex-acp adapter. The base
# (buildpack-deps:noble) is Debian/Ubuntu, so apt is correct; clean the
# apt lists in the same layer to keep the image lean.
RUN apt-get update \
    && apt-get install -y --no-install-recommends bubblewrap \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# The mise.run installer reads MISE_VERSION from the environment.
ENV MISE_VERSION=${MISE_VERSION}
RUN curl -fsSL https://mise.run | sh
ENV PATH=/root/.local/share/mise/shims:/root/.local/bin:$PATH

RUN mise use -g just@${JUST_VERSION} lefthook@${LEFTHOOK_VERSION} \
        node@${NODE_VERSION} gh@${GH_VERSION} \
    && mise reshim

RUN npm install -g @agentclientprotocol/claude-agent-acp@${CLAUDE_AGENT_ACP_VERSION}

RUN npm install -g @zed-industries/codex-acp@${CODEX_ACP_VERSION}

# Neutral committer identity for in-sandbox commits (matches the host
# checkout identity so RGR trailer authorship is consistent).
RUN git config --system user.name "E2E Test" \
    && git config --system user.email "e2e-test@example.com" \
    && git config --system init.defaultBranch master

# Bake the sandbox prepare-step timing wrapper onto PATH. It is
# stdlib-only so it resolves via the base image's python3 BEFORE the
# first `uv sync` in the python layer. The adjacent
# Dockerfile.dockerignore allowlists this one file into the (repo-root)
# build context.
COPY --chmod=0755 livespec_dev_tooling/otel_step_timer.py /usr/local/bin/livespec-step-timer
