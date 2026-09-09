#!/usr/bin/env bash
#
# vps-restic-backup.sh — back up this VPS's live filesystem to S3 with restic.
#
# The independent, VPS-native counterpart to the Arq Premium backup. Where Arq
# needs the Mac to pull a pre-pruned SMB snapshot, restic backs up the LIVE
# paths directly here, on a systemd timer, and restore also runs here.
#
# Runs as ROOT (a host backup must read /etc/shadow, /root, ssh host keys,
# /etc/credstore, ...). Secrets come from the 1Password "homelab" Environment
# via with-homelab-env.sh, invoked with OPENV_KEEP_PRIVILEGES=1 so the payload
# stays root. Secrets live only in env — never argv, disk, or logs.
#
# Usage (interactively, wrap in `/usr/bin/sg`-free — this uses sudo, not group):
#   vps-restic-backup.sh backup            # init-if-needed + backup + prune
#   vps-restic-backup.sh doctor            # tooling + secrets + repo reachability
#   vps-restic-backup.sh snapshots [args]
#   vps-restic-backup.sh restore <id> --target <DIR>   # NEVER restore over live
#   vps-restic-backup.sh check | unlock | forget | exec -- <restic args>
#
set -euo pipefail

SELF="$(readlink -f "$0")"
ONEPASSWORD_WRAPPER="${ONEPASSWORD_WRAPPER:-/usr/local/bin/with-homelab-env.sh}"
ENV_MARKER="__vps_restic_env_loaded__"
EXCLUDE_FILE="${VPS_RESTIC_EXCLUDE_FILE:-/etc/vps-restic-backup/excludes.txt}"

# Live paths to back up. Explicit list (matches arq-vps-root-snapshot's
# included_paths); --one-file-system keeps each within its own filesystem.
BACKUP_PATHS=(/etc /home /data /root /opt /usr/local /srv /var/lib /var/log)
RETENTION=(--keep-last 8 --keep-daily 7 --keep-weekly 5 --keep-monthly 12)

# --- stage 1: re-exec as root WITH the homelab env -------------------------
# Positional-arg marker (survives sudo, unlike an env var). sudo sets SUDO_UID
# so the loader reaches stage 1; OPENV_KEEP_PRIVILEGES=1 keeps it root.
if [[ "${1:-}" != "${ENV_MARKER}" ]]; then
    [[ -e "${ONEPASSWORD_WRAPPER}" ]] || { echo "ERROR: missing loader ${ONEPASSWORD_WRAPPER}" >&2; exit 127; }
    exec sudo -n OPENV_KEEP_PRIVILEGES=1 "${ONEPASSWORD_WRAPPER}" "${SELF}" "${ENV_MARKER}" "$@"
fi
shift  # drop the marker

# --- stage 2: root + homelab secrets present -------------------------------
die() { echo "ERROR: $*" >&2; exit 1; }

map_env() {
    : "${VPS_RESTIC_REPOSITORY:?not set — import the .env into the 1Password homelab Environment}"
    : "${VPS_RESTIC_PASSWORD:?not set — import the .env into the 1Password homelab Environment}"
    : "${VPS_RESTIC_AWS_ACCESS_KEY_ID:?not set — import the .env into the 1Password homelab Environment}"
    : "${VPS_RESTIC_AWS_SECRET_ACCESS_KEY:?not set — import the .env into the 1Password homelab Environment}"
    export RESTIC_REPOSITORY="${VPS_RESTIC_REPOSITORY}"
    export RESTIC_PASSWORD="${VPS_RESTIC_PASSWORD}"
    export AWS_ACCESS_KEY_ID="${VPS_RESTIC_AWS_ACCESS_KEY_ID}"
    export AWS_SECRET_ACCESS_KEY="${VPS_RESTIC_AWS_SECRET_ACCESS_KEY}"
    export AWS_DEFAULT_REGION="${VPS_RESTIC_S3_REGION:-us-east-1}"
    export RESTIC_CACHE_DIR="${RESTIC_CACHE_DIR:-/var/cache/restic}"
}

cmd_backup() {
    [[ -f "${EXCLUDE_FILE}" ]] || die "exclude file not found: ${EXCLUDE_FILE} (run install.sh)"
    restic snapshots >/dev/null 2>&1 || restic init
    # NO --exclude-caches: it drops any dir containing CACHEDIR.TAG (Rust target/,
    # .venv/, .mypy_cache/, .ruff_cache/, .pytest_cache/, ...) and is NOT overridden
    # by the "!/data" re-include, so it would silently break verbatim /data.
    # Cache dirs are excluded by name in the exclude-file instead.
    restic backup "${BACKUP_PATHS[@]}" \
        --one-file-system \
        --exclude-file "${EXCLUDE_FILE}" \
        --host vps --tag scheduled
    # Retention applies only to this host's scheduled snapshots.
    restic forget --host vps --tag scheduled "${RETENTION[@]}" --prune
}

cmd_doctor() {
    local ok=1
    echo "== identity =="; echo "  uid=$(id -u) (expect 0)"
    echo "== tooling =="
    # shellcheck disable=SC2043  # One tool today; the loop is the list's shape,
    # matching the six-variable loop below, so adding a second tool is one word.
    for b in restic; do command -v "$b" >/dev/null 2>&1 && printf '  %-8s %s\n' "$b" "$(command -v "$b")" || { printf '  %-8s MISSING\n' "$b"; ok=0; }; done
    echo "== secrets (homelab Environment; values not shown) =="
    for v in VPS_RESTIC_REPOSITORY VPS_RESTIC_PASSWORD VPS_RESTIC_AWS_ACCESS_KEY_ID VPS_RESTIC_AWS_SECRET_ACCESS_KEY VPS_RESTIC_S3_BUCKET VPS_RESTIC_S3_REGION; do
        [[ -n "${!v:-}" ]] && printf '  %-34s set\n' "$v" || { printf '  %-34s MISSING\n' "$v"; ok=0; }
    done
    echo "== exclude file =="; [[ -f "${EXCLUDE_FILE}" ]] && echo "  ${EXCLUDE_FILE}" || { echo "  MISSING: ${EXCLUDE_FILE}"; ok=0; }
    [[ "${ok}" -eq 1 ]] || die "doctor found problems (see above)"
    map_env
    echo "== repository =="
    if restic snapshots >/dev/null 2>&1; then echo "  reachable: ${RESTIC_REPOSITORY}"; else echo "  NOT reachable / not initialized: ${RESTIC_REPOSITORY}"; ok=0; fi
    [[ "${ok}" -eq 1 ]] && echo "OK" || die "repository not reachable"
}

case "${1:-backup}" in
    backup)          map_env; cmd_backup ;;
    doctor)          cmd_doctor ;;
    snapshots)       map_env; shift; restic snapshots "$@" ;;
    restore)         map_env; shift; restic restore "$@" ;;
    check)           map_env; shift; restic check "$@" ;;
    unlock)          map_env; shift; restic unlock "$@" ;;
    forget)          map_env; shift; restic forget "$@" ;;
    exec)            map_env; shift; [[ "${1:-}" == "--" ]] && shift; exec restic "$@" ;;
    help|-h|--help)  sed -n '2,32p' "${SELF}" | sed 's/^# \{0,1\}//' ;;
    *) echo "unknown command: ${1}" >&2; exit 2 ;;
esac
