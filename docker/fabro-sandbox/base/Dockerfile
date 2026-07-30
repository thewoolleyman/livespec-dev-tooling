# livespec fleet Fabro sandbox image — BASE layer.
#
# The bottom of the base → python → {python-agent, python-rust →
# python-rust-agent} chain. Bakes the harness-neutral toolchain every
# consumer needs regardless of language:
#   - mise (single tool manager; version mirrors the host)
#   - just / lefthook at this repo's .mise.toml pins
#   - node (required by the ACP adapters, AND by CI itself since pyright
#     shells out to npm; Fabro does not install node/npx at runtime;
#     mirrors the host)
#   - gh (the pr node's CLI; mirrors the host)
#   - livespec-step-timer: the stdlib-only sandbox prepare-step timing
#     wrapper (each dispatched workflow.toml prepare step runs as
#     `livespec-step-timer <slug> -- <cmd>`; see livespec-dev-tooling
#     otel_step_timer.py). It lives in BASE so it is on PATH for every
#     consumer's prepare steps, before the first `uv sync`.
#
# NOT here: bubblewrap and the two ACP adapters. That agent-only payload
# lives in the `agent` layer stacked ON TOP of `python` / `python-rust`
# (docker/fabro-sandbox/agent/Dockerfile), together with the
# CLAUDE_AGENT_ACP_VERSION / CODEX_ACP_VERSION ARGs that pin them —
# including the CODEX_ACP_VERSION single-source-of-truth contract. CI
# never runs the adapters, so keeping them out of base cuts CI's pull by
# roughly 42% while CI and the Fabro sandbox still share byte-identical
# toolchain layers.
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
#
# WHY `-scm` AND NOT FULL buildpack-deps: the full variant's extra
# 176.9 MB (compressed) is autoconf/automake and the C dev-header set,
# which nothing in the base or python chain uses — both Python consumers'
# COMPLETE dependency trees (`uv sync --all-groups --frozen`) install
# with NO C compiler present (measured; see livespec-dev-tooling-oik).
# `-scm` retains git, curl, and ca-certificates, which the steps below
# (mise via `curl -fsSL https://mise.run`) and the sandbox's git
# operations need. The ONE consumer that needs a compiler is the Rust
# chain (rustc drives its linker through `cc`), and it re-adds a minimal
# gcc + libc6-dev in the `python-rust` layer — NOT here — so the
# CI-facing `python-` tag keeps the full saving.
FROM buildpack-deps:noble-scm

# libatomic1 — node's binary dynamically links libatomic.so.1. Full
# buildpack-deps shipped it as a side effect of its gcc stack; `-scm`
# does not, and the node install below fails without it ("error while
# loading shared libraries: libatomic.so.1"). It is a 10.5 kB runtime
# library (50.2 kB installed) — negligible against the 176.9 MB the
# `-scm` re-base saves, and NOT a compiler or dev-header re-add.
# tmux — required by factory-tier acceptance tests that run inside this same
# Fabro sandbox image and drive real private tmux sockets. It is a 468.6 kB
# package (1,160.0 kB installed on noble amd64) with no daemon, and keeps
# CI-vs-sandbox parity for tmux-dependent verifiers without adding a compiler
# or dev headers back to base.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libatomic1 tmux \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------------------
# Tool pins — ARG form so `just check-fabro-image-pin-lockstep` can
# parse them mechanically across the layer Dockerfiles. JUST_VERSION /
# LEFTHOOK_VERSION MUST match this repo's .mise.toml `[tools]` pins (the
# check fails the build pipeline on drift). MISE_VERSION / NODE_VERSION
# have no repo-side pin source — they mirror the host toolchain and are
# tracked only here. GH_VERSION is the supported GitHub CLI pin enforced
# by the repo-private lockstep check. The ACP adapter pins
# (CLAUDE_AGENT_ACP_VERSION / CODEX_ACP_VERSION) live in the `agent`
# layer alongside the adapters they pin; keep each ARG in exactly one
# layer Dockerfile.
# ---------------------------------------------------------------
ARG MISE_VERSION=v2026.2.7
ARG JUST_VERSION=1.36.0
ARG LEFTHOOK_VERSION=1.13.6
ARG NODE_VERSION=26.3.0
ARG GH_VERSION=2.96.0

# The mise.run installer reads MISE_VERSION from the environment.
ENV MISE_VERSION=${MISE_VERSION}
RUN curl -fsSL https://mise.run | sh
ENV PATH=/root/.local/share/mise/shims:/root/.local/bin:$PATH

RUN mise use -g just@${JUST_VERSION} lefthook@${LEFTHOOK_VERSION} \
        node@${NODE_VERSION} gh@${GH_VERSION} \
    && mise reshim

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
