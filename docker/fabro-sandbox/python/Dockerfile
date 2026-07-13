# livespec fleet Fabro sandbox image — PYTHON layer.
#
# FROM the base layer + uv and a uv-managed CPython. This is the image
# the Python-only consumers pull (e.g. livespec-orchestrator-beads-fabro).
#
# BASE_IMAGE is passed by the build pipeline as the exact base image
# reference just built (digest-pinned, not a floating tag, so the chain
# is hermetic). It carries NO default: a value-less `ARG` is invisible to
# `check-fabro-image-pin-lockstep` (which only parses `ARG NAME=value`),
# and a local `docker build` must pass `--build-arg BASE_IMAGE=...`.
#
# NO uv package-cache pre-warm: the previous single-image pre-warm read
# THIS repo's own lockfile (not each consumer's) and its `paths:` trigger
# never rebuilt on consumer-lockfile changes, so the warm layer silently
# rotted. Per-repo dep caching is a persistent local-disk `~/.cache/uv`
# concern, not an image layer.
#
# Build (context = REPO ROOT; the adjacent Dockerfile.dockerignore
# excludes everything — this layer COPYs nothing):
#   docker build -f docker/fabro-sandbox/python/Dockerfile \
#     --build-arg BASE_IMAGE=livespec-fabro-sandbox:base-dev \
#     -t livespec-fabro-sandbox:python-dev .
#
# Published as ghcr.io/<owner>/livespec-fabro-sandbox with immutable
# python-sha-<short> / python-v<X.Y.Z> tags.
ARG BASE_IMAGE
FROM ${BASE_IMAGE}

# ---------------------------------------------------------------
# Tool pins — UV_VERSION MUST match this repo's .mise.toml `[tools]` uv
# pin and PYTHON_VERSION MUST match .python-version (the
# check-fabro-image-pin-lockstep gate fails the build on drift). Each ARG
# lives in exactly one layer Dockerfile.
# ---------------------------------------------------------------
ARG UV_VERSION=0.9.26
ARG PYTHON_VERSION=3.10.16

RUN mise use -g uv@${UV_VERSION} \
    && mise reshim

RUN uv python install ${PYTHON_VERSION}
