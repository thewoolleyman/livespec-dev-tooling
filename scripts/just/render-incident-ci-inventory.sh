#!/usr/bin/env bash
# Render one adopting repository's released incident CI inventory into
# livespec_dev_tooling/data/incident-ci-inventory/<owner>/<repo>.json.
#
# The entrance (`incident_ci_process`) looks an inventory up by the repository
# its authenticated pull-request read names and never reads the candidate tree,
# so an adopter's members are fixed here, at build time, from that adopter's own
# normal workflow and check-targets.txt AT A COMMIT OF ITS DEFAULT BRANCH, read
# from a local clone with git. The commit is recorded in the file as its
# `source`, so the render is deterministic and auditable. Rerun it on a newer
# default-branch commit whenever the adopter adds, removes or renames a target
# or changes an `# incident-timing:` annotation.
#
# Usage: render-incident-ci-inventory.sh <owner/repo> <clone-path> <commit-sha>
set -euo pipefail
repository="$1" clone="$2" commit="$3"
if [[ ! "$repository" =~ ^[A-Za-z0-9_-][A-Za-z0-9_.-]*/[A-Za-z0-9_.-]+$ ]]; then
  echo "render-incident-ci-inventory: '$repository' is not an owner/repo name" >&2
  exit 2
fi
if [[ ! "$commit" =~ ^[0-9a-f]{40}$ ]]; then
  echo "render-incident-ci-inventory: the commit must be a full 40-hex sha" >&2
  exit 2
fi
git -C "$clone" fetch --quiet origin
default="$(git -C "$clone" symbolic-ref --short refs/remotes/origin/HEAD)"
if ! git -C "$clone" merge-base --is-ancestor "$commit" "$default"; then
  echo "render-incident-ci-inventory: $commit is not on $repository's default branch ($default)" >&2
  exit 2
fi
destination="livespec_dev_tooling/data/incident-ci-inventory/${repository}.json"
mkdir -p "$(dirname "$destination")"
# Both inputs are required: an adopter that commits no check-targets.txt has no
# inventory, and the entrance refuses it as incident-inventory-undeclared.
workflow="$(git -C "$clone" show "${commit}:.github/workflows/ci.yml")"
inventory="$(git -C "$clone" show "${commit}:check-targets.txt")"
WORKFLOW="$workflow" INVENTORY="$inventory" REPOSITORY="$repository" COMMIT="$commit" \
  uv run python -c '
import os, sys
from livespec_dev_tooling.incident_ci_inventory import (
    InventorySource, decode_inventory, render_inventory,
)
text = render_inventory(
    workflow=os.environ["WORKFLOW"],
    inventory=os.environ["INVENTORY"],
    source=InventorySource(repository=os.environ["REPOSITORY"], commit=os.environ["COMMIT"]),
)
decode_inventory(text=text)
sys.stdout.write(text)
' >"$destination"
echo "rendered $destination from $repository@$commit"
