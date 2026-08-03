#!/usr/bin/env bash
set -euo pipefail

: "${test_nprocs:?}"

uv run pytest -n "${test_nprocs}" --cov --cov-branch --cov-config=pyproject.toml --cov-report=term-missing
uv run python -m livespec_dev_tooling.checks.per_file_coverage
