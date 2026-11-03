#!/usr/bin/env bash
# Start one named interactive Claude seat from its committed class profile.
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly script_dir
readonly profile_path="${script_dir}/../config/interactive-fleet-seat-profile.tsv"

usage() {
    printf 'usage: %s <seat-class> <seat-name> [claude arguments...]\n' "$0" >&2
    exit 2
}

if (( $# < 2 )); then
    usage
fi

readonly seat_class="$1"
readonly seat_name="$2"
shift 2

if [[ ! -f "$profile_path" ]]; then
    printf 'interactive fleet seat profile is missing: %s\n' "$profile_path" >&2
    exit 2
fi

matches="$(awk -F $'\t' -v requested_class="$seat_class" '
    NR > 1 && $1 == requested_class { print }
' "$profile_path")"
match_count="$(printf '%s\n' "$matches" | awk 'NF { count += 1 } END { print count + 0 }')"
if [[ "$match_count" != 1 ]]; then
    printf 'interactive fleet seat class is not defined exactly once: %s\n' "$seat_class" >&2
    exit 2
fi

IFS=$'\t' read -r configured_class model effort auto_compact_threshold model_context_ceiling lifetime_seconds <<< "$matches"
if [[ "$configured_class" != "$seat_class" || -z "$model" || -z "$effort" ]]; then
    printf 'interactive fleet seat profile is invalid for class: %s\n' "$seat_class" >&2
    exit 2
fi
if ! [[ "$auto_compact_threshold" =~ ^[0-9]+$ && "$model_context_ceiling" =~ ^[0-9]+$ && "$lifetime_seconds" =~ ^[0-9]+$ ]]; then
    printf 'interactive fleet seat profile has non-numeric limits for class: %s\n' "$seat_class" >&2
    exit 2
fi
if (( auto_compact_threshold >= model_context_ceiling || lifetime_seconds == 0 )); then
    printf 'interactive fleet seat profile has invalid limits for class: %s\n' "$seat_class" >&2
    exit 2
fi

export CLAUDE_CODE_AUTO_COMPACT_WINDOW="$auto_compact_threshold"
export LIVESPEC_INTERACTIVE_SEAT_LIFETIME_SECONDS="$lifetime_seconds"
exec claude \
    --model "$model" \
    --effort "$effort" \
    --dangerously-skip-permissions \
    -n "$seat_name" \
    "$@"
