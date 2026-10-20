#!/usr/bin/env bash
set -euo pipefail

mapfile -t targets < <(
    sed -E 's/[[:space:]]*#.*$//; s/^[[:space:]]+//; s/[[:space:]]+$//' check-targets.txt \
        | grep -E '^check-' || true
)
literal_targets=("$@")

if [[ ${#targets[@]} -ne ${#literal_targets[@]} ]]; then
    printf 'ERROR: literal check target mirror drift: inventory has %d entries, justfile has %d\n' \
        "${#targets[@]}" "${#literal_targets[@]}" >&2
    exit 1
fi
for index in "${!targets[@]}"; do
    if [[ "${targets[$index]}" != "${literal_targets[$index]}" ]]; then
        printf 'ERROR: literal check target mirror drift at entry %d: inventory=%s justfile=%s\n' \
            "$index" "${targets[$index]}" "${literal_targets[$index]}" >&2
        exit 1
    fi
done

if ! uv sync --all-groups; then
    echo "ERROR: up-front 'uv sync --all-groups' failed; aborting the check aggregate" >&2
    exit 1
fi

export UV_NO_SYNC=1

# Populate pyright's bundled node runtime + typeshed ONCE, serially, before
# the dispatcher fans out — the justfile's `warm-typecheck` recipe, run here
# for the LOCAL and CI aggregate the way the delegated gate pod already runs
# it before `just hook_gate=1 check`.
#
# The `pyright==<pin>` PyPI wrapper fetches the node-based pyright (typeshed
# bundled inside) on its FIRST invocation. Two members invoke it —
# check-types and check-no-shadow-ledger-body-typechecks — and the dispatcher
# starts them concurrently, so on a COLD cache they can race that first fetch
# and read it half-written, which surfaces as pyright's "Stub file not found
# for 'typing'" against an otherwise-green tree (livespec-dev-tooling-v572ul's
# hp run 01M5C054VFF7: 24,727 missing-stub errors on a markdown-only change).
# One serial invocation up front makes the fetch happen completely, before any
# target can start a second one. On a warm cache it is a sub-second no-op.
#
# Fail-closed like the sync above: a warm-up that cannot complete leaves every
# pyright member to cold-start, which is the state this exists to prevent
# (work-item livespec-dev-tooling-tqloqv).
if ! uv run pyright --version; then
    echo "ERROR: up-front pyright warm-up ('uv run pyright --version') failed; aborting the check aggregate before any target starts" >&2
    exit 1
fi

# Members the two LOCAL git-hook gates do NOT run. Consulted only when the
# caller sets `hook_gate` (check-pre-commit.sh, check-pre-push.sh); a bare
# `just check` sets nothing and still runs every member, so this omits a
# target from a CALLER rather than demoting it in the recipe.
#
# check-fleet-conformance-admin is the sole member. It is a WORLD GATE: it
# reads the live admin-scoped state of nine OTHER repositories, so its verdict
# is a fact about the fleet at this instant, not about the commit being made.
# At 2026-09-06 06:35Z one sibling's branch-protection state
# (livespec-console-beads-fabro, required check `upstream-dep-gate-wired`)
# made it exit 4 and refuse a hand push HERE, and would have refused every
# later push until that sibling's own repair landed — a member's state
# blocking an unrelated commit, which is what a per-commit gate must never do
# (work-item livespec-dev-tooling-mmqe, absorbing tkzf). Its enforcement home
# is the operator's deliberate `just check`; the per-PR CI matrix cannot host
# it, because CI authenticates with the fleet App installation token, which
# deliberately lacks admin scope and makes the lane classify itself
# out-of-vantage at zero API reads.
hook_gate_skips="check-fleet-conformance-admin"

effective_skip="${skip:-}"
if [[ -n "${hook_gate:-}" ]]; then
    effective_skip="${effective_skip} ${hook_gate_skips}"
fi
if [[ -n "${red_staged:-}" ]]; then
    red_skip=$(uv run python -m livespec_dev_tooling.red_leg_scope \
        --staged "${red_staged}" --targets "${targets[@]}") || {
        echo "ERROR: red_leg_scope fail-fast; the Red selection would be empty - run the full aggregate instead" >&2
        exit 1
    }
    effective_skip="${effective_skip} ${red_skip}"
fi

uv run python -m livespec_dev_tooling.parallel_check_dispatcher --skip "${effective_skip}" -- "${targets[@]}" || exit 1

# `hook_gate` is deliberately NOT disqualifying here, unlike `skip` and
# `red_staged`. The token's ONLY consumer is check-pre-push.sh, which is
# itself a hook gate and therefore omits exactly the same members: the token
# means "this tree passed the gate the hooks run", and it is read by the
# gate the hooks run. Disqualifying it would leave the token never written
# from either hook, so every push would re-run the whole aggregate that
# pre-commit had just run.
if [[ -z "${skip:-}" && -z "${red_staged:-}" ]]; then
    uv run python -m livespec_dev_tooling.green_token write || true
fi
