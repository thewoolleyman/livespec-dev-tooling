#!/usr/bin/env bash
set -euo pipefail

if [[ -z "$(git diff --cached --name-only)" ]]; then
    echo ":: empty commit detected (nothing staged at all): repo-state gates have nothing to gate; exit 0"
    exit 0
fi

staged=$(git diff --cached --name-only --diff-filter=AM)
py_staged=$(echo "$staged" | grep -E '\.py$' || true)
test_staged=$(echo "$staged" | grep -E '^tests/.*\.py$' || true)
impl_staged=$(echo "$staged" | grep -E '^livespec_dev_tooling/.*\.py$' || true)
test_count=0
impl_count=0
[[ -n "$test_staged" ]] && test_count=$(echo "$test_staged" | wc -l)
[[ -n "$impl_staged" ]] && impl_count=$(echo "$impl_staged" | wc -l)

if [[ -z "$py_staged" ]]; then
    echo ":: doc-only mode detected (zero .py files staged): running just check-pre-commit-doc-only"
    echo ":: pre-push + CI keep the full aggregate as the load-bearing safety net"
    just check-pre-commit-doc-only
    exit $?
fi

if [[ "$test_count" -eq 1 ]] && [[ "$impl_count" -eq 0 ]]; then
    echo ":: Red-mode shape detected: $test_staged"
    echo ":: scoping the Red gate by staged-path class (red_leg_scope): coverage gates skip"
    echo ":: (verified at the Green amend) + any orthogonal legs a staged unit test cannot affect"
    just red_staged="$test_staged" check
    exit $?
fi

just check
