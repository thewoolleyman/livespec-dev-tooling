#!/usr/bin/env bash
# Compare every released adopter inventory with the adopter's current default branch.
set -euo pipefail

workspace="$(mktemp -d)"
trap 'rm -rf "$workspace"' EXIT
status=0
while IFS= read -r entry; do
  repository="$(uv run python -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["source"]["repository"])' "$entry")"
  clone="$workspace/${repository//\//_}"
  if ! git clone --quiet --depth 1 "https://github.com/${repository}.git" "$clone"; then
    printf 'unreadable\t%s\n' "$repository" >&2
    status=1
    continue
  fi
  head="$(git -C "$clone" rev-parse HEAD)"
  workflow="$workspace/${repository//\//_}.ci.yml"
  inventory="$workspace/${repository//\//_}.check-targets.txt"
  if ! git -C "$clone" show "${head}:.github/workflows/ci.yml" >"$workflow" || ! git -C "$clone" show "${head}:check-targets.txt" >"$inventory"; then
    printf 'unreadable\t%s\t%s\n' "$repository" "$head" >&2
    status=1
    continue
  fi
  if ! uv run python -m livespec_dev_tooling.incident_ci_inventory_freshness "$entry" "$repository" "$head" "$workflow" "$inventory"; then
    status=1
  fi
done < <(find livespec_dev_tooling/data/incident-ci-inventory -type f -name '*.json' | sort)
exit "$status"
