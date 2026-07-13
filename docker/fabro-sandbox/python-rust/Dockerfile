# livespec fleet Fabro sandbox image — PYTHON-RUST layer.
#
# FROM the python layer + the Rust toolchain baked once, so a Rust
# consumer (livespec-console-beads-fabro) needs NO per-run `rustup`
# install. The console needs Python too (its janitor reuses the Python
# baseline verifiers + commit-refuse installer), so this is python-rust,
# not a Rust-only image.
#
# PYTHON_IMAGE is passed by the build pipeline as the exact python image
# reference just built (digest-pinned; hermetic chain). Value-less `ARG`
# so it is invisible to check-fabro-image-pin-lockstep; a local build
# must pass `--build-arg PYTHON_IMAGE=...`.
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
ARG PYTHON_IMAGE
FROM ${PYTHON_IMAGE}

ARG RUST_VERSION=1.92.0

# Bake the pinned Rust toolchain (mirrors the console's
# rust-toolchain.toml: channel + clippy + rustfmt). The minimal profile
# keeps the layer lean; rustup lands cargo/rustc under /root/.cargo.
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \
    | sh -s -- -y --default-toolchain ${RUST_VERSION} --profile minimal \
        --component clippy,rustfmt
ENV PATH=/root/.cargo/bin:$PATH
