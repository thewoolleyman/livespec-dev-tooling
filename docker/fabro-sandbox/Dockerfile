# livespec family Fabro sandbox image.
#
# Bakes the family-pinned toolchain so a Fabro C-mode docker run needs
# no per-run installs:
#   - mise (single tool manager; version mirrors the host)
#   - uv / just / lefthook at this repo's .mise.toml pins
#   - node (required for the ACP adapter — Fabro does not install
#     node/npx at runtime; mirrors the host)
#   - gh (the pr node's CLI; mirrors the host)
#   - uv-managed CPython at this repo's .python-version pin
#   - @agentclientprotocol/claude-agent-acp preinstalled globally so
#     `npx -y @agentclientprotocol/claude-agent-acp` resolves locally
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
# CLAUDE_AGENT_ACP_VERSION have no repo-side pin source — they mirror
# the host toolchain and are tracked only here.
# ---------------------------------------------------------------
ARG MISE_VERSION=v2026.2.7
ARG UV_VERSION=0.9.26
ARG JUST_VERSION=1.36.0
ARG LEFTHOOK_VERSION=1.13.6
ARG NODE_VERSION=26.3.0
ARG GH_VERSION=2.46.0
ARG PYTHON_VERSION=3.10.16
ARG CLAUDE_AGENT_ACP_VERSION=0.44.0

# The mise.run installer reads MISE_VERSION from the environment.
ENV MISE_VERSION=${MISE_VERSION}
RUN curl -fsSL https://mise.run | sh
ENV PATH=/root/.local/share/mise/shims:/root/.local/bin:$PATH

RUN mise use -g uv@${UV_VERSION} just@${JUST_VERSION} lefthook@${LEFTHOOK_VERSION} \
        node@${NODE_VERSION} gh@${GH_VERSION} \
    && mise reshim

RUN uv python install ${PYTHON_VERSION}

RUN npm install -g @agentclientprotocol/claude-agent-acp@${CLAUDE_AGENT_ACP_VERSION}

# Neutral committer identity for in-sandbox commits (matches the host
# checkout identity so RGR trailer authorship is consistent).
RUN git config --system user.name "E2E Test" \
    && git config --system user.email "e2e-test@example.com" \
    && git config --system init.defaultBranch master

# Pre-warm the uv wheel/build cache against this repo's lockfile so
# the in-run `uv sync` is cache-hits only. The throwaway project dir
# is removed; the cache under /root/.cache/uv persists in the image.
COPY pyproject.toml uv.lock /tmp/uv-warm/
RUN cd /tmp/uv-warm \
    && uv sync --all-groups --frozen --no-install-project \
    && rm -rf /tmp/uv-warm
