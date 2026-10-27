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

# ---------------------------------------------------------------
# Tool pins — ARG form so `just check-fabro-image-pin-lockstep` can
# parse them mechanically across the layer Dockerfiles. JUST_VERSION /
# LEFTHOOK_VERSION / SHELLCHECK_VERSION MUST match this repo's .mise.toml
# `[tools]` pins (the check fails the build pipeline on drift), and each
# must ALSO be installed by the `mise use -g` below — an ARG alone pins a
# version without baking the tool, leaving it to be re-fetched over the
# network by every containerized job. MISE_VERSION / NODE_VERSION
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
ARG SHELLCHECK_VERSION=0.11.0
ARG NODE_VERSION=26.3.0
ARG GH_VERSION=2.102.0
# sha256 of gh_${GH_VERSION}_linux_amd64.tar.gz, from that release's
# gh_${GH_VERSION}_checksums.txt. Bump it WITH GH_VERSION.
ARG GH_SHA256=bb766f710eef8ede859c18578c72c327597cd4c8a85b06001b1f3843c6019386

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
# ---------------------------------------------------------------
# RETRY POLICY — every dependency fetch in this image RETRIES a transient CDN
# failure instead of failing the build.
#
# Baking a tool moves its download out of CI and into THIS build, which
# concentrates the risk rather than removing it: a half-delivered tarball now
# fails an image publish instead of one job. Observed 2026-08-13, when a
# shellcheck tarball arriving as "connection closed before message completed"
# reddened master in two repos at once.
#
# Every fetcher here defaults to NO retries — curl, apt, and mise all ship with
# zero — so each is set explicitly:
#
#   curl  --retry N already backs off EXPONENTIALLY (~1s, doubling, capped at 10
#         minutes). Do NOT add --retry-delay: it REPLACES that backoff with a
#         fixed sleep. --retry-all-errors is required because curl's default
#         "transient error" set is timeouts and a few HTTP codes, which does NOT
#         include a connection dropped mid-stream — precisely our failure.
#   apt   Acquire::Retries defaults to 0.
#   mise  http_retries defaults to 0, i.e. one attempt.
#   uv    already understood this; UV_HTTP_RETRIES is set for `uv python install`
#         in the python layer and for any in-sandbox `uv sync`.
#
# The two ENVs persist into every layer stacked on this one, so the python and
# python-rust layers inherit them without repeating themselves.
# ---------------------------------------------------------------
ENV MISE_HTTP_RETRIES=5
ENV UV_HTTP_RETRIES=5

# gh comes from its pinned GitHub release tarball, verified against GH_SHA256,
# NOT from cli.github.com's apt repo: that repo serves only the current
# version, so an `apt-get install gh=<pin>` stops resolving the day upstream
# releases again ("E: Version '2.102.0' for 'gh' was not found" broke every
# image build on 2026-10-27). A release asset never disappears. The step fails
# fast and loudly if the download or the checksum does not match.
RUN apt-get -o Acquire::Retries=5 update \
    && apt-get -o Acquire::Retries=5 install -y --no-install-recommends \
        libatomic1 tmux \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && set -eux \
    && asset="gh_${GH_VERSION}_linux_amd64" \
    && curl -fsSL --retry 5 --retry-all-errors --retry-connrefused \
        -o /tmp/gh.tgz \
        "https://github.com/cli/cli/releases/download/v${GH_VERSION}/${asset}.tar.gz" \
    && echo "${GH_SHA256}  /tmp/gh.tgz" | sha256sum -c - \
    && tar -xzf /tmp/gh.tgz -C /tmp "${asset}/bin/gh" \
    && install -m 0755 "/tmp/${asset}/bin/gh" /usr/local/bin/gh \
    && rm -rf /tmp/gh.tgz "/tmp/${asset}" \
    && test "$(gh --version | head -1 | cut -d' ' -f3)" = "${GH_VERSION}"

# The mise.run installer reads MISE_VERSION from the environment.
ENV MISE_VERSION=${MISE_VERSION}
RUN curl -fsSL --retry 5 --retry-all-errors --retry-connrefused https://mise.run | sh
ENV PATH=/root/.local/share/mise/shims:/root/.local/bin:$PATH

RUN mise use -g just@${JUST_VERSION} lefthook@${LEFTHOOK_VERSION} \
        shellcheck@${SHELLCHECK_VERSION} node@${NODE_VERSION} \
    && mise reshim

# Pre-trust every job / sandbox workspace root so a fresh container can run a
# checkout's mise-driven recipe with NO per-job `mise trust` step. mise refuses
# an untrusted `.mise.toml` ("Config files in .../.mise.toml are not trusted"),
# and every tenant's ci.yml worked around that with one `mise trust` step per
# job — about 160 copies fleet-wide (livespec-dev-tooling-tyug). The value is a
# colon-separated list of ANCESTOR directories: any config beneath one of them
# is trusted (verified on this mise pin). Trusting the checkout's own config
# adds no attack surface — the job already executes that repository's code.
#   /__w        ARC and hosted GitHub Actions container jobs check out under
#               /__w/<repo>/<repo> (GITHUB_WORKSPACE).
#   /workspace  the Fabro sandbox clone root (siblings under
#               /workspace/siblings).
# An explicit `mise trust` in a job stays a harmless no-op, so tenants can drop
# their trust steps at their own pace (keep `mise install`).
ENV MISE_TRUSTED_CONFIG_PATHS=/__w:/workspace

# A Fabro sandbox has no real terminal, so lefthook's per-command pty is 0x0.
# CPython 3.10 (the fleet pin) then reports `shutil.get_terminal_size()`
# columns=0 (3.11+ falls back to 80), and pytest-icdiff, a dev dependency in
# every fleet repo, derives its diff width from that at import time; on ANY
# failing `==` assertion its `_split_line` then loops forever. A failing
# assertion inside a pre-commit hook therefore HANGS instead of failing.
# `get_terminal_size()` consults COLUMNS/LINES before it queries the fd, so
# pinning them here makes every layer stacked on this one fail normally
# (measured: rc=124 after a 20s timeout without them, rc=1 in 1s with them).
# The python layer's build-time probe proves it under a real 0x0 pty.
ENV COLUMNS=200 LINES=50

# A reusable sandbox has no author fallback: each workflow must inject and
# validate its operator identity explicitly. `user.useConfigOnly` also keeps
# Git from inventing an address from the container hostname when injection is
# absent. The build-time probe exercises both sides against the image's real
# Git/config stack: no identity fails actionably, while an explicitly injected
# canonical fleet operator is recorded byte-for-byte.
RUN git config --system user.useConfigOnly true \
    && git config --system init.defaultBranch master \
    && identity_probe="$(mktemp -d)" \
    && trap 'rm -rf "$identity_probe"' EXIT \
    && cd "$identity_probe" \
    && git init \
    && touch payload \
    && git add payload \
    && if missing_output="$(git commit -m "identity-negative-control" 2>&1)"; then \
        echo "Git commit unexpectedly accepted a missing sandbox author" >&2; \
        exit 1; \
    fi \
    && printf '%s\n' "$missing_output" | grep -F "Author identity unknown" >/dev/null \
    && git config --local user.name "Chad Woolley" \
    && git config --local user.email "thewoolleyman@gmail.com" \
    && resolved_author="$(git var GIT_AUTHOR_IDENT)" \
    && case "$resolved_author" in \
        "Chad Woolley <thewoolleyman@gmail.com> "*) ;; \
        *) echo "Injected sandbox author did not resolve canonically: $resolved_author" >&2; exit 1 ;; \
    esac \
    && git commit -m "identity-positive-control" >/dev/null \
    && [ "$(git log -1 --format="%an <%ae>")" = "Chad Woolley <thewoolleyman@gmail.com>" ]

# Bake the sandbox prepare-step timing wrapper onto PATH. It is
# stdlib-only so it resolves via the base image's python3 BEFORE the
# first `uv sync` in the python layer. The adjacent
# Dockerfile.dockerignore allowlists this one file into the (repo-root)
# build context.
COPY --chmod=0755 livespec_dev_tooling/otel_step_timer.py /usr/local/bin/livespec-step-timer

# WHAT THIS IMAGE CAN DO, published for the sandbox to read.
#
# ITS CONSUMER is the Definition-of-Done gate in
# livespec-orchestrator-beads-fabro, which checks each factory-captured
# assertion against the capabilities the running sandbox image PUBLISHES here.
# That makes this file an assertion the gate BELIEVES — there is no second
# source to catch it with — so every name is probed in this same step before it
# is written, and a layer that failed to install what it declares fails the
# build instead of publishing a capability the image does not carry.
#
# Format: one lowercase snake_case name per line, no comments. The file is
# parsed, not read.
#   terminal  the pty + terminfo stack a dispatched run needs to drive an
#             interactive terminal at all. It has no binary of its own; tmux
#             is its consumer here, and the agent layer's herdr smoke step is
#             where the round trip is exercised end to end.
#   tmux      the multiplexer the apt step above bakes for factory-tier
#             acceptance tests that drive real private tmux sockets.
#
# The AGENT layer REWRITES this file with its own, longer list rather than
# appending to it, so each published image in the chain states exactly what IT
# carries. The python and python-rust layers add toolchain, not capabilities,
# and inherit this file unchanged.
RUN set -eux; \
    tmux -V; \
    mkdir -p /etc/livespec; \
    printf '%s\n' terminal tmux > /etc/livespec/sandbox-capabilities; \
    cat /etc/livespec/sandbox-capabilities
