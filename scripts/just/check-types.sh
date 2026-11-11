#!/usr/bin/env bash
set -euo pipefail
uv run pyright --pythonplatform Linux
uv run pyright --pythonplatform Darwin
