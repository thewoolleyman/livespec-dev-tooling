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
# @agentclientprotocol/codex-acp ~150 MB) that CI never executes; hoisting
# them out of `base` into this on-top layer cuts CI's pull from 751 MB to
# 435 MB (~42%) while keeping CI and the sandbox on BYTE-IDENTICAL
# toolchain layers — there is no separate slim CI image and therefore no
# CI-vs-sandbox drift.
#
# Contents:
#   - bubblewrap (HARD codex-acp requirement — for BOTH its
#     require_escalated command execution AND its apply_patch edit tool;
#     dropping it silently breaks Codex-driven runs)
#   - a headless browser payload: the Playwright CLI plus the Chromium
#     build that Playwright release pins, with its system libraries.
#     ITS CONSUMER is factory-captured proofs in the
#     livespec-orchestrator-beads-fabro reserved workflow — a dispatched
#     run that has to SHOW a rendered page rather than assert about it.
#     Like the adapters, it lands in this agent layer and NOT in `base`,
#     so CI image pulls are unchanged: a browser is the largest instance
#     yet of payload only Fabro sandboxes execute, and pushing it down to
#     `base` would add every one of those bytes to every CI job's pull
#     for a capability no CI job uses.
#   - BOTH ACP adapters preinstalled: @agentclientprotocol/claude-agent-acp
#     (Claude) as a global so `npx -y <adapter>` resolves locally, and
#     @agentclientprotocol/codex-acp (the orchestrator's Codex adapter) under
#     the dedicated prefix /opt/livespec/codex-acp, invoked at its baked path
#     — baked, never per-run npx-fetched
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
# for the baked @agentclientprotocol/codex-acp adapter version — it does not
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
ARG CODEX_ACP_VERSION=1.10.0

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

# TRANSITIONAL — the PREDECESSOR Codex adapter, kept baked for ONE release.
# @zed-industries/codex-acp is npm-deprecated at its terminal release 0.16.0
# (replaced by @agentclientprotocol/codex-acp, pinned by CODEX_ACP_VERSION).
# This line carries a LITERAL version on purpose: it declares no ARG, the
# pin-autodiscovery walk does not see it, and the freshness scan never bumps
# it (livespec-dev-tooling/SPECIFICATION/contracts.md §"Pin autodiscovery
# rules", package succession). It keeps the GLOBAL install — and therefore
# the `codex-acp` bin link — so every dispatch that still resolves the
# predecessor by name (`npx --no-install @zed-industries/codex-acp`) keeps
# running the last verified adapter while the orchestrator cuts over.
# REMOVE THIS LINE when BOTH hold: the orchestrator invokes the successor at
# its baked path, AND a real Codex-provider factory dispatch has run on the
# successor (§"codex-acp factory gate", equivalent proof part 3; tracker
# livespec-dev-tooling-opdc).
RUN npm install -g --fetch-retries=5 \
        @zed-industries/codex-acp@0.16.0

# The SUCCESSOR Codex adapter, pinned by CODEX_ACP_VERSION, baked under a
# DEDICATED npm prefix — never as a global. Both packages export the bin
# `codex-acp`, and `npx --no-install <package>` runs whichever package owns
# the shared GLOBAL bin link (measured 2026-08-26: with both installed
# globally, BOTH package names ran the link owner), so package-name
# resolution cannot keep the two apart. Consumers invoke the successor at
# its stable path /opt/livespec/codex-acp/bin/codex-acp. This prefix is its
# PERMANENT home: do not add a global copy when the predecessor is removed.
RUN npm install -g --prefix /opt/livespec/codex-acp --fetch-retries=5 \
        @agentclientprotocol/codex-acp@${CODEX_ACP_VERSION}

# sccache for FACTORY sandboxes (console plan optimize-console-builds,
# livespec-console-beads-fabro-di6fn5; dev-tooling 3u3gm2 shape 2). Every
# fabro dispatch of a Rust consumer compiles fully cold in a fresh container
# (console research/003: cargo-build MAX 50 s, cargo-test MAX 62 s per run);
# sccache is built for exactly this — many ephemeral builders sharing one
# content-addressed cache. Two constraints shape the wiring:
#   - fabro's docker provider exposes NO volume mount, so the cache cannot be
#     a host directory; it is a REDIS on the factory host, reached over the
#     docker bridge gateway (172.17.0.1:6379) — the same path the cargo
#     telemetry shim already uses for the OTLP receiver at 172.17.0.1:4318
#     (fabro-hosts services/sccache-redis; 4 GB allkeys-lru, no persistence).
#   - fabro spawns ACP nodes under a fail-closed env allowlist, so SCCACHE_*
#     env cannot be relied on to reach cargo. Everything is therefore a FILE:
#     the redis endpoint in sccache's own config (~/.config/sccache/config)
#     and `rustc-wrapper` in the cargo config the python-rust layer already
#     bakes. No env, no workflow change.
# Only the python-rust-agent build has a cargo home; on python-agent the
# binary lands unused (10 MB) and the cargo stanza is skipped. The wrapper is
# NOT sccache itself but sccache-or-rustc.sh: sccache falls back to a plain
# compile when a cache OPERATION fails, but when its server cannot START (an
# unreachable redis at first use) the client exits non-zero and cargo fails —
# measured 2026-09-06. The wrapper probes once per container and execs plain
# rustc when the cache is unusable, so a host without the redis builds exactly
# as before (di6fn5 bullet 5). The telemetry shim wraps cargo, not rustc, so
# the wrapper is orthogonal to it; its spans carry build.cache.sccache.* from
# the server when one is up.
# The version and checksum are the pool's (ci-runner/k3s/phase2/sccache/
# install-sccache-binary.sh) — bump both together.
ARG SCCACHE_VERSION=0.17.0
ARG SCCACHE_SHA256=67c4a96dd237c1f518f6b36083f270f9976d516f1e57fce891755ea782e50006
ARG SCCACHE_REDIS_ENDPOINT=redis://172.17.0.1:6379
COPY --chmod=0755 docker/fabro-sandbox/agent/sccache-or-rustc.sh /usr/local/bin/sccache-or-rustc
RUN set -eux; \
    asset="sccache-v${SCCACHE_VERSION}-x86_64-unknown-linux-musl"; \
    curl -fsSL --retry 5 --retry-all-errors --retry-connrefused \
        -o /tmp/sccache.tgz \
        "https://github.com/mozilla/sccache/releases/download/v${SCCACHE_VERSION}/${asset}.tar.gz"; \
    echo "${SCCACHE_SHA256}  /tmp/sccache.tgz" | sha256sum -c -; \
    tar -xzf /tmp/sccache.tgz -C /tmp "${asset}/sccache"; \
    install -m 0755 "/tmp/${asset}/sccache" /usr/local/bin/sccache; \
    rm -rf /tmp/sccache.tgz "/tmp/${asset}"; \
    /usr/local/bin/sccache --version; \
    mkdir -p /root/.config/sccache; \
    printf '# Factory compilation cache: the redis on the factory host (fabro-hosts\n# services/sccache-redis). sccache falls back to compiling on any error.\n[cache.redis]\nendpoint = "%s"\n' "${SCCACHE_REDIS_ENDPOINT}" \
        > /root/.config/sccache/config; \
    if [ -d /root/.cargo ]; then \
        printf '\n# Dependency compiles served from the factory host sccache when it answers,\n# plain rustc otherwise (agent layer; sccache-or-rustc probes once per container).\n[build]\nrustc-wrapper = "/usr/local/bin/sccache-or-rustc"\nincremental = false\n' \
            >> /root/.cargo/config.toml; \
    fi

# ---------------------------------------------------------------
# Headless browser payload — Playwright plus the Chromium build this
# Playwright release pins. ARG form so `just check-fabro-image-pin-lockstep`
# can parse the pin mechanically; declared in THIS layer only, because that
# check MERGES the ARG lines across the layer tree and a second copy would
# drift silently rather than fail. PLAYWRIGHT_VERSION has no `.mise.toml`
# counterpart (Playwright is not a host toolchain pin), so it carries no
# lockstep obligation — the two ACP adapter ARGs above are the precedent.
# ---------------------------------------------------------------
ARG PLAYWRIGHT_VERSION=1.63.0

RUN npm install -g --fetch-retries=5 \
        playwright@${PLAYWRIGHT_VERSION}

# The Chromium build this Playwright release pins, plus its system libraries.
# `--with-deps` shells out to apt on this Ubuntu 24.04 chain, and those apt
# calls are Playwright's own children, so the retry posture is installed as an
# apt.conf.d drop-in (a `-o` flag would reach only OUR apt invocation) and
# removed again in the same step, leaving no config residue. Lists are cleaned
# in the layer that populated them, matching the bubblewrap step above.
#
# NO `PLAYWRIGHT_BROWSERS_PATH`: the install is left at Playwright's DEFAULT
# destination, which for uid 0 with HOME=/root is /root/.cache/ms-playwright.
# Fabro spawns ACP nodes under a fail-closed env allowlist, so a browser that
# can only be located through an environment variable is a browser the sandbox
# cannot find at runtime. The `test -d` proves the default root really is where
# the bytes landed rather than leaving it to assumption.
RUN set -eux; \
    printf 'Acquire::Retries "5";\n' > /etc/apt/apt.conf.d/99livespec-acquire-retries; \
    apt-get -o Acquire::Retries=5 update; \
    playwright install --with-deps chromium; \
    rm -f /etc/apt/apt.conf.d/99livespec-acquire-retries; \
    apt-get clean; \
    rm -rf /var/lib/apt/lists/*; \
    test -d /root/.cache/ms-playwright

# What the image actually carries, recorded for the sandbox to read and printed
# so the build log carries it too. Both numbers are READ BACK from the install
# rather than written down: Playwright's pin already determines which Chromium
# build lands, so a literal here would be a second copy free to drift, and a
# drifted versions file reports a browser the image does not have. The binary is
# found by globbing the default browsers root (`chromium-*` does not match the
# sibling `chromium_headless_shell-*` directory), and the glob is required to
# resolve — an unmatched glob would otherwise leave the loop variable holding the
# pattern itself and record a nonsense version. The binary's directory is
# `chrome-linux64` for the Chrome for Testing builds Playwright has shipped
# since the CfT cutover (measured on the pinned release: "Chrome for Testing
# ... chrome-linux64.zip") and `chrome-linux` for the older layout; the glob
# accepts both so a Playwright bump cannot silently break this step again.
RUN set -eux; \
    chromium_bin=""; \
    for candidate in /root/.cache/ms-playwright/chromium-*/chrome-linux*/chrome; do \
        if [ -x "${candidate}" ]; then chromium_bin="${candidate}"; fi; \
    done; \
    test -n "${chromium_bin}"; \
    playwright_version="$(playwright --version | awk '{print $NF}')"; \
    chromium_version="$("${chromium_bin}" --version | awk '{print $NF}')"; \
    test -n "${playwright_version}"; \
    test -n "${chromium_version}"; \
    mkdir -p /etc/livespec; \
    printf 'playwright %s\nchromium %s\n' "${playwright_version}" "${chromium_version}" \
        > /etc/livespec/sandbox-browser-versions; \
    cat /etc/livespec/sandbox-browser-versions

# BUILD-TIME SMOKE CHECK — an end-to-end capture, not a version probe.
# `playwright --version` and a present binary prove nothing about whether this
# browser can actually render: the ways a containerized headless Chromium fails
# are missing shared libraries, no usable sandbox for uid 0, and a missing font
# stack, and every one of them passes a version probe and then fails on the
# first real navigation. So this step IS the whole round trip: it writes a page,
# serves that page itself over the loopback interface (hermetic — no internet,
# no third-party URL that can change under the build), drives the installed
# Chromium at it through the Playwright CLI, and keeps the PNG only long enough
# to check it. `playwright screenshot` forces headless, and Playwright's
# `chromiumSandbox` default of false is what lets Chromium run as uid 0 here.
RUN set -eux; \
    smoke_port=45231; \
    smoke_dir="$(mktemp -d)"; \
    printf '%s\n' \
        '<!doctype html><html><head><meta charset="utf-8">' \
        '<title>livespec fabro-sandbox headless browser smoke</title></head>' \
        '<body style="margin:0;background:#0b2545">' \
        '<h1 style="color:#ffffff;font:700 56px/1.4 sans-serif;padding:64px">' \
        'livespec fabro-sandbox: headless Chromium rendered this page over loopback.' \
        '</h1></body></html>' \
        > "${smoke_dir}/page.html"; \
    printf '%s\n' \
        'const http = require("http");' \
        'const fs = require("fs");' \
        'const body = fs.readFileSync(process.argv[2]);' \
        'http.createServer(function (_req, res) {' \
        '  res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });' \
        '  res.end(body);' \
        '}).listen(Number(process.argv[3]), "127.0.0.1");' \
        > "${smoke_dir}/serve.js"; \
    node "${smoke_dir}/serve.js" "${smoke_dir}/page.html" "${smoke_port}" & \
    smoke_server="$!"; \
    smoke_ready=""; \
    for _attempt in 1 2 3 4 5 6 7 8 9 10; do \
        if node -e 'require("http").get({host:"127.0.0.1",port:Number(process.argv[1]),path:"/page.html"},function(res){process.exit(res.statusCode===200?0:1);}).on("error",function(){process.exit(1);});' "${smoke_port}"; then \
            smoke_ready=1; \
            break; \
        fi; \
        sleep 1; \
    done; \
    test -n "${smoke_ready}"; \
    playwright screenshot --browser chromium --viewport-size "1280,720" \
        "http://127.0.0.1:${smoke_port}/page.html" "${smoke_dir}/smoke.png"; \
    smoke_signature="$(od -An -N8 -tx1 < "${smoke_dir}/smoke.png" | tr -d ' \n')"; \
    test "${smoke_signature}" = "89504e470d0a1a0a"; \
    smoke_bytes="$(wc -c < "${smoke_dir}/smoke.png")"; \
    test "${smoke_bytes}" -gt 1024; \
    echo "sandbox browser smoke: ${smoke_bytes} PNG bytes, signature ${smoke_signature}"; \
    kill "${smoke_server}"; \
    rm -rf "${smoke_dir}"

# ---------------------------------------------------------------
# herdr — the terminal workspace manager a dispatched run drives to create,
# split, write to and read back real panes. ARG form so
# `just check-fabro-image-pin-lockstep` can parse the pins mechanically;
# declared in THIS layer only, because that check MERGES the ARG lines across
# the layer tree and a second copy would drift silently rather than fail.
# Neither ARG has a `.mise.toml` counterpart — herdr is not a host toolchain
# pin — so neither carries a lockstep obligation, exactly as PLAYWRIGHT_VERSION
# and the SCCACHE_* pair above.
#
# HERDR_SHA256 is a SECOND pin, not a convenience. A release asset URL is
# mutable, so the version alone does not make the download reproducible; the
# digest does. ORDER IS LOAD-BEARING: `curl -o` writes a NON-executable file
# and `install -m 0755` is the moment the payload becomes runnable, so the
# `sha256sum -c` sits strictly between them and an unverified binary is never
# executable in this layer.
#
# The asset is a static-pie x86-64 binary with no runtime library dependency,
# so there is no apt step here and nothing to clean up after one. It lands in
# /usr/local/bin, which is on a non-root sandbox shell's default PATH — a
# payload reachable only by sourcing something is a payload the sandbox cannot
# find, the same constraint that keeps the browser at its default root.
#
# The version is READ BACK from the installed binary and held to the ARG. A
# release asset that quietly carried a different build would otherwise install
# silently, and every assertion downstream would be about a herdr nobody pinned.
# ---------------------------------------------------------------
ARG HERDR_VERSION=0.9.3
ARG HERDR_SHA256=18a8dc65f1c2fa485884344356dea1cfd911c6f06cf46fa78e193f4087f4dba7

RUN set -eux; \
    curl -fsSL --retry 5 --retry-all-errors --retry-connrefused \
        -o /tmp/herdr-linux-x86_64 \
        "https://github.com/herdrdev/herdr/releases/download/v${HERDR_VERSION}/herdr-linux-x86_64"; \
    echo "${HERDR_SHA256}  /tmp/herdr-linux-x86_64" | sha256sum -c -; \
    install -m 0755 /tmp/herdr-linux-x86_64 /usr/local/bin/herdr; \
    rm -f /tmp/herdr-linux-x86_64; \
    test "$(herdr --version | awk '{print $NF}')" = "${HERDR_VERSION}"; \
    herdr --version
