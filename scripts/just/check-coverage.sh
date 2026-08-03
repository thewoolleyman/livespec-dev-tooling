#!/usr/bin/env bash
set -euo pipefail

: "${test_nprocs:?}"

echo ":: check-coverage: clean standalone suite (COVERAGE_FILE unset) - strict, matches CI"
env -u COVERAGE_FILE uv run pytest -n "${test_nprocs}" --cov --cov-branch --cov-config=pyproject.toml --cov-report=term-missing
