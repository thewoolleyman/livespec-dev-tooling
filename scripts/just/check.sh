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

effective_skip="${skip:-}"
if [[ -n "${red_staged:-}" ]]; then
    red_skip=$(uv run python -m livespec_dev_tooling.red_leg_scope \
        --staged "${red_staged}" --targets "${targets[@]}") || {
        echo "ERROR: red_leg_scope fail-fast; the Red selection would be empty - run the full aggregate instead" >&2
        exit 1
    }
    effective_skip="${skip:-} ${red_skip}"
fi

uv run python -m livespec_dev_tooling.parallel_check_dispatcher --skip "${effective_skip}" -- "${targets[@]}" || exit 1

if [[ -z "${skip:-}" && -z "${red_staged:-}" ]]; then
    uv run python -m livespec_dev_tooling.green_token write || true
fi
