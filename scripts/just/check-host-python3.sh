#!/usr/bin/env bash
# check-host-python3.sh <checkout> — refuse a developer host whose first
# `python3` on PATH is older than the checkout's `requires-python` floor.
#
# Governed by SPECIFICATION/non-functional-requirements.md, "Developer host
# platforms" (scenario "bootstrap names a bare python3 that does not satisfy
# requires-python"). `just bootstrap` runs this FIRST, before `uv run`, because
# `uv run` resolves its own interpreter and may download one, and the scenario
# forbids installing or replacing any interpreter on the host. The fleet's hook
# and helper scripts invoke the bare `python3`, which is why the host's own one
# must satisfy the floor even though `uv` would not use it (macOS ships 3.9).
#
# Only the `>=X.Y[.Z]` form of `requires-python` is read; any other form is
# refused by name rather than guessed at. Nothing is installed or changed.
set -euo pipefail

prog="check-host-python3"
checkout="${1:-.}"

die() {
  printf '%s: %s\n' "$prog" "$*" >&2
  exit 1
}

floor="$(sed -n 's/^requires-python = ">=\([0-9][0-9.]*\)"$/\1/p' "$checkout/pyproject.toml" | head -n 1)"
[ -n "$floor" ] ||
  die "could not read a '>=X.Y.Z' requires-python from $checkout/pyproject.toml"

command -v python3 >/dev/null 2>&1 ||
  die "no python3 on PATH; requires-python needs >=$floor — install one on the host (this check installs nothing)"

found="$(python3 --version 2>&1 | sed -n 's/^Python \([0-9][0-9.]*\).*/\1/p' | head -n 1)"
[ -n "$found" ] || die "could not read the version of $(command -v python3); requires-python needs >=$floor"

# version_ge A B: true when dotted version A >= B (numeric fields, missing = 0).
version_ge() {
  local a="$1" b="$2" i x y
  local IFS=.
  # shellcheck disable=SC2206  # deliberate field split on '.'
  local av=($a) bv=($b)
  for i in 0 1 2; do
    x="${av[$i]:-0}"
    y="${bv[$i]:-0}"
    if [ "$x" -gt "$y" ]; then return 0; fi
    if [ "$x" -lt "$y" ]; then return 1; fi
  done
  return 0
}

version_ge "$found" "$floor" ||
  die "python3 $found ($(command -v python3)) does not satisfy requires-python >=$floor; put a python3 >=$floor first on PATH (this check installs nothing)"
printf '%s: python3 %s satisfies requires-python >=%s\n' "$prog" "$found" "$floor"
