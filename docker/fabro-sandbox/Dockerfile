# livespec fleet Fabro sandbox image.
#
# Bakes the fleet-pinned toolchain so a Fabro C-mode docker run needs
# no per-run installs:
#   - mise (single tool manager; version mirrors the host)
#   - uv / just / lefthook at this repo's .mise.toml pins
#   - node (required for the ACP adapter — Fabro does not install
#     node/npx at runtime; mirrors the host)
#   - gh (the pr node's CLI; mirrors the host)
#   - bubblewrap (required by the codex-acp adapter for BOTH its
#     require_escalated command execution AND its apply_patch edit
#     tool — without it every command/edit degrades to fragile
#     escalated local writes; mirrors the host)
#   - uv-managed CPython at this repo's .python-version pin
#   - @agentclientprotocol/claude-agent-acp preinstalled globally so
#     `npx -y @agentclientprotocol/claude-agent-acp` resolves locally
#   - @zed-industries/codex-acp preinstalled globally so
#     `npx -y @zed-industries/codex-acp` resolves locally (the
#     orchestrator's Codex implementer adapter, baked not per-run
#     npx-fetched; version mirrors the orchestrator's pin)
#   - uv package cache pre-warmed from this repo's uv.lock
#
# NO secrets are baked. Credentials reach the sandbox per run via the
# Fabro environment env table (GitHub token: Fabro's vault-backed
# integration; Anthropic credential: host-local Fabro settings env
# merge).
#
# Build (context = REPO ROOT so the uv cache pre-warm COPY below reads
# this repo's own pyproject.toml + uv.lock; the adjacent
# Dockerfile.dockerignore allowlists only those two files into the
# context):
#   docker build -f docker/fabro-sandbox/Dockerfile -t livespec-fabro-sandbox:dev .
#
# Published by .github/workflows/fabro-sandbox-image.yml as
# ghcr.io/<owner>/livespec-fabro-sandbox with immutable sha-<short>
# (per master build) and v<X.Y.Z> (per release) tags.
FROM buildpack-deps:noble

# ---------------------------------------------------------------
# Tool pins — ARG form so `just check-fabro-image-pin-lockstep` can
# parse them mechanically. UV_VERSION / JUST_VERSION /
# LEFTHOOK_VERSION MUST match this repo's .mise.toml `[tools]` pins
# and PYTHON_VERSION MUST match .python-version (the check fails the
# build pipeline on drift). MISE_VERSION / NODE_VERSION / GH_VERSION /
# CLAUDE_AGENT_ACP_VERSION / CODEX_ACP_VERSION have no repo-side pin
# source — they mirror the host toolchain (CODEX_ACP_VERSION mirrors
# the orchestrator's hardcoded implementer-adapter pin) and are
# tracked only here.
# ---------------------------------------------------------------
ARG MISE_VERSION=v2026.2.7
ARG UV_VERSION=0.9.26
ARG JUST_VERSION=1.36.0
ARG LEFTHOOK_VERSION=1.13.6
ARG NODE_VERSION=26.3.0
ARG GH_VERSION=2.46.0
ARG PYTHON_VERSION=3.10.16
ARG CLAUDE_AGENT_ACP_VERSION=0.44.0
ARG CODEX_ACP_VERSION=0.16.0

# bubblewrap — required by the codex-acp adapter for BOTH its
# require_escalated command execution AND its apply_patch edit tool.
# The base (buildpack-deps:noble) is Debian/Ubuntu, so apt is correct;
# clean the apt lists in the same layer to keep the image lean.
RUN apt-get update \
    && apt-get install -y --no-install-recommends bubblewrap \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# The mise.run installer reads MISE_VERSION from the environment.
ENV MISE_VERSION=${MISE_VERSION}
RUN curl -fsSL https://mise.run | sh
ENV PATH=/root/.local/share/mise/shims:/root/.local/bin:$PATH

RUN mise use -g uv@${UV_VERSION} just@${JUST_VERSION} lefthook@${LEFTHOOK_VERSION} \
        node@${NODE_VERSION} gh@${GH_VERSION} \
    && mise reshim

RUN uv python install ${PYTHON_VERSION}

RUN npm install -g @agentclientprotocol/claude-agent-acp@${CLAUDE_AGENT_ACP_VERSION}

RUN npm install -g @zed-industries/codex-acp@${CODEX_ACP_VERSION}

# Neutral committer identity for in-sandbox commits (matches the host
# checkout identity so RGR trailer authorship is consistent).
RUN git config --system user.name "E2E Test" \
    && git config --system user.email "e2e-test@example.com" \
    && git config --system init.defaultBranch master

# Bake the sandbox prepare-step timing wrapper onto PATH. Each prepare
# step in the dispatched workflow.toml runs as
# `livespec-step-timer <slug> -- <cmd>`: it times <cmd>, passes its exit
# code + stdin/stdout/stderr through UNCHANGED, and best-effort POSTs one
# OTLP span to the host receiver ($LIVESPEC_SANDBOX_OTEL_ENDPOINT) so the
# in-sandbox setup/janitor timing is MEASURED in the fabro-sandbox
# dataset. It is stdlib-only so it resolves via the base image's python3
# BEFORE the first `uv sync`. The adjacent Dockerfile.dockerignore
# allowlists this one file into the (repo-root) build context.
COPY --chmod=0755 livespec_dev_tooling/otel_step_timer.py /usr/local/bin/livespec-step-timer

# Pre-warm the uv wheel/build cache against this repo's lockfile so
# the in-run `uv sync` is cache-hits only. The throwaway project dir
# is removed; the cache under /root/.cache/uv persists in the image.
COPY pyproject.toml uv.lock /tmp/uv-warm/
RUN cd /tmp/uv-warm \
    && uv sync --all-groups --frozen --no-install-project \
    && rm -rf /tmp/uv-warm
