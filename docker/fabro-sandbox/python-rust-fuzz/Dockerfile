# syntax=docker/dockerfile:1
#
# livespec-fabro-sandbox: python-rust-fuzz layer
#
# FROM the python-rust layer + the fuzzing toolchain baked once, so the
# console's `check-fuzz` job (and the warm-cache populator that will build
# its warmed ASAN generation) needs NO per-run install of a C++ compiler,
# a nightly toolchain, or cargo-fuzz.
#
# Why a SEPARATE leaf and not python-rust itself (console plan
# optimize-console-builds, research/010; livespec-dev-tooling-3u3gm2.2):
# the console's check-fuzz job is the longest job in its matrix (323–337 s
# vs 220 s next) and `ci-green` needs it, so it is every PR's critical
# path — and it spends 40–48 s of every run installing exactly this
# payload (g++ via apt 13–16 s; nightly + cargo-fuzz 26–32 s, measured
# 2026-09-06). But a minimal nightly toolchain is 598 MB installed /
# ~200 MB as a compressed layer, and the hosted lane pulls the image per
# job (livespec-dev-tooling-a46: pull dominates short jobs). Baked into
# python-rust that would tax all ten console jobs to save one; as its own
# leaf only the fuzz job pulls it, and the shared tags gain zero bytes.
#
# Contents, and why each:
#   g++            libfuzzer-sys compiles libFuzzer FROM SOURCE in its build
#                  script (cc-rs, `c++`); python-rust ships gcc + libc6-dev
#                  for linking but no C++ compiler (measured: cc-rs
#                  `ToolNotFound "c++"` on the job's first run).
#   nightly        `cargo fuzz` needs `-Zsanitizer=address`, which stable
#                  refuses. Installed as the UNDATED `nightly` channel name
#                  because the console's dev-tooling/ensure-rust-quality-tools.sh
#                  and `cargo +nightly` both address it by that name; the
#                  image tag pins the date it resolved to (echoed below).
#   cargo-fuzz     pinned; installed via `rustup run <stable> cargo install`,
#                  not the telemetry shim python-rust installs at
#                  /root/.cargo/bin/cargo, so an image build never runs the shim.
#
# The `agent` leaf is NOT built atop this layer: fuzzing is a CI-job
# concern, the factory's ACP sandboxes do not fuzz.

ARG PYTHON_RUST_IMAGE=livespec-fabro-sandbox:python-rust-dev
FROM ${PYTHON_RUST_IMAGE}

ARG CARGO_FUZZ_VERSION=0.13.2

# C++ compiler for libfuzzer-sys — g++ only, no extra dev-header library set.
RUN apt-get -o Acquire::Retries=5 update \
    && apt-get -o Acquire::Retries=5 install -y --no-install-recommends g++ \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Nightly toolchain (minimal profile: rustc + cargo + std) beside the pinned
# stable one; the default toolchain stays the console's pinned stable.
RUN rustup toolchain install nightly --profile minimal --no-self-update \
    && echo "python-rust-fuzz: nightly resolved to $(rustc +nightly --version)"

# cargo-fuzz, built with the pinned stable toolchain through `rustup run`,
# which executes that toolchain's own cargo with RUSTUP_TOOLCHAIN set for
# every child process — so neither the cargo telemetry shim python-rust
# installs at /root/.cargo/bin/cargo nor a racing `rustc` proxy resolution
# (measured: two proxies fetching a component concurrently fail the build)
# is involved. The binary lands in /root/.cargo/bin like every rustup tool.
RUN STABLE="$(rustup show active-toolchain | cut -d' ' -f1)" \
    && rustup run "${STABLE}" cargo install --locked cargo-fuzz --version "${CARGO_FUZZ_VERSION}" \
    && rm -rf /root/.cargo/registry/src /root/.cargo/git \
    && rustup run "${STABLE}" cargo fuzz --version
