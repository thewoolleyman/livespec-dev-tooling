# livespec fleet Fabro sandbox image — PYTHON-RUST layer.
#
# FROM the python layer + the Rust toolchain baked once, so a Rust
# consumer (livespec-console-beads-fabro) needs NO per-run `rustup`
# install. The console needs Python too (its janitor reuses the Python
# baseline verifiers + commit-refuse installer), so this is python-rust,
# not a Rust-only image.
#
# PYTHON_IMAGE is passed by the build pipeline as the exact python image
# reference just built (digest-pinned; hermetic chain). Its default is the
# documented local-development tag, which keeps standalone Dockerfile
# validation valid; CI always overrides it with the exact python digest.
#
# RUST_VERSION has NO repo-side pin source in livespec-dev-tooling (this
# is not a Rust repo), so it carries NO lockstep obligation here — it
# mirrors livespec-console-beads-fabro/rust-toolchain.toml (channel
# 1.92.0 + clippy + rustfmt). Per the No-Circular-Dependency Directive,
# any check that the baked Rust matches the console's rust-toolchain.toml
# lives on the CONSUMER (console) side reading this image ARG, never in
# dev-tooling.
#
# Build (context = REPO ROOT; the adjacent Dockerfile.dockerignore
# excludes everything — this layer COPYs nothing):
#   docker build -f docker/fabro-sandbox/python-rust/Dockerfile \
#     --build-arg PYTHON_IMAGE=livespec-fabro-sandbox:python-dev \
#     -t livespec-fabro-sandbox:python-rust-dev .
#
# Published as ghcr.io/<owner>/livespec-fabro-sandbox with immutable
# python-rust-sha-<short> / python-rust-v<X.Y.Z> tags.
ARG PYTHON_IMAGE=livespec-fabro-sandbox:python-dev
FROM ${PYTHON_IMAGE}

ARG RUST_VERSION=1.92.0

# Minimal C toolchain re-add — THIS LAYER ONLY. The chain's base is
# buildpack-deps:noble-scm, which ships NO compiler (that is the point:
# it keeps 176.9 MB of dev headers off the CI-facing `python-` tag). But
# on linux-gnu rustc invokes `cc` as its linker driver, so `cargo build`
# fails with "linker `cc` not found" without one (measured; see
# livespec-dev-tooling-oik). gcc + libc6-dev (54.8 MB of archives) is the
# minimal set that restores linking — deliberately NOT the full
# buildpack-deps dev-header library set, and deliberately NOT in `base`,
# so only the Rust consumer pays for it.
RUN apt-get -o Acquire::Retries=5 update \
    && apt-get -o Acquire::Retries=5 install -y --no-install-recommends gcc libc6-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Bake the pinned Rust toolchain (mirrors the console's
# rust-toolchain.toml: channel + clippy + rustfmt). The minimal profile
# keeps the layer lean; rustup lands cargo/rustc under /root/.cargo.
RUN curl --proto '=https' --tlsv1.2 -sSf \
        --retry 5 --retry-all-errors --retry-connrefused https://sh.rustup.rs \
    | sh -s -- -y --default-toolchain ${RUST_VERSION} --profile minimal \
        --component clippy,rustfmt
ENV PATH=/root/.cargo/bin:$PATH

# Pre-warmed cargo REGISTRY (console factory build cache, shape 1 — plan
# console-factory-build-cache, child livespec-dev-tooling-3u3gm2.1; delivers
# livespec-console-beads-fabro-qxjdan). A fabro dispatch of the console runs a
# fully COLD cargo build in a fresh sandbox and re-fetches every crate from
# crates.io on every run (console research/003, research/006 factory §1). The
# fabro 0.254 docker provider exposes NO volume/bind-mount knob, so the registry
# cannot be shared in from the host; it is baked INTO the image instead: shallow-
# clone the console at CONSOLE_REF and `cargo fetch --locked` its lockfile into
# this layer's CARGO_HOME registry (/root/.cargo/registry), then drop the clone.
# Zero runtime coupling; a crate outside the baked set downloads exactly as it
# does today (miss cost unchanged). EVICTION by construction: the generations
# are the image tags, bounded by the fleet's 72 h image-prune — no new service.
# This runs BEFORE the cargo shim swap below, so the real rustup `cargo` does the
# fetch and an image build emits no build.env=factory span. CONSOLE_REF is the
# console branch/ref whose lockfile is baked; the resolved commit is echoed into
# the build log so each image tag records which lockfile it warmed.
ARG CONSOLE_REPO=https://github.com/thewoolleyman/livespec-console-beads-fabro.git
ARG CONSOLE_REF=master
ENV CARGO_NET_RETRY=5
RUN set -eux; \
    git clone --quiet --depth 1 --branch "${CONSOLE_REF}" "${CONSOLE_REPO}" /tmp/console-lockfile \
    && cd /tmp/console-lockfile \
    && echo "pre-warm: console lockfile @ $(git rev-parse HEAD)" \
    && cargo fetch --locked \
    && echo "pre-warm: registry size $(du -sh /root/.cargo/registry | cut -f1)" \
    && cd / \
    && rm -rf /tmp/console-lockfile

# Factory build-telemetry seam (build.env=factory). A fabro dispatch of the
# console runs a fully cold cargo build+test in this sandbox and emitted NOTHING
# about its timing; the console workflow runs cargo via its agent + git hooks,
# not via a wrappable prepare step, so the only console-change-free wrap point is
# HERE, in the image. The `cargo` shim runs the real cargo unchanged and
# best-effort hands each measured phase's timing to livespec-cargo-phase-timer,
# which POSTs one build.env=factory span to the host OTel receiver — routed to
# the `github-ci` Honeycomb dataset by `service.name`, the same keyless seam the
# prepare.* spans use. The stopwatch is strictly non-fatal: a broken/absent
# timer never changes cargo's result.
#
# The shim REPLACES the rustup `cargo` proxy itself (the proxy is renamed to
# `cargo-real` beside it), rather than sitting on a separate earlier PATH entry.
# That earlier-PATH-entry approach is silently bypassed the moment a consumer's
# `.mise.toml` re-prepends `~/.cargo/bin` — livespec-console-beads-fabro does
# exactly this (`_.path = ["~/.cargo/bin"]`), so `mise exec -- just check`
# resolved `cargo` to the rustup proxy and the shim never fired (measured: zero
# build.env=factory spans from a real GREEN dispatch). Being `~/.cargo/bin/cargo`
# itself makes `cargo` resolve to the shim under ANY PATH order. `cargo-real` is
# the rustup proxy, which dispatches on argv[0]; the shim calls it via
# `exec -a cargo` so it still resolves the pinned toolchain. Both files are
# allowlisted into the (repo-root) build context by the adjacent
# Dockerfile.dockerignore.
RUN mv /root/.cargo/bin/cargo /root/.cargo/bin/cargo-real
COPY --chmod=0755 livespec_dev_tooling/otel_cargo_phase.py /usr/local/bin/livespec-cargo-phase-timer
COPY --chmod=0755 docker/fabro-sandbox/python-rust/cargo-phase-shim.sh /root/.cargo/bin/cargo
