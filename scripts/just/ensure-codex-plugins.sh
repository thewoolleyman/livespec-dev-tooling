#!/usr/bin/env bash
set -euo pipefail

if ! command -v codex >/dev/null 2>&1; then
    echo "codex CLI not found; skipping host-wide Codex plugin install." >&2
    exit 0
fi

codex plugin marketplace add thewoolleyman/livespec --ref release
codex plugin marketplace add thewoolleyman/livespec-driver-codex --ref release
codex plugin marketplace add thewoolleyman/livespec-orchestrator-beads-fabro --ref release
codex plugin marketplace upgrade livespec
codex plugin marketplace upgrade livespec-driver-codex
codex plugin marketplace upgrade livespec-orchestrator-beads-fabro
codex plugin add livespec@livespec
codex plugin add livespec@livespec-driver-codex
codex plugin add livespec-orchestrator-beads-fabro@livespec-orchestrator-beads-fabro
