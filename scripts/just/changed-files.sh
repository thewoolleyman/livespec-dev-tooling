#!/usr/bin/env bash
set -euo pipefail

{
    git diff --name-only origin/master...HEAD
    git diff --cached --name-only --diff-filter=AM
} | {
    grep -E '\.py$' || true
} | sort -u
