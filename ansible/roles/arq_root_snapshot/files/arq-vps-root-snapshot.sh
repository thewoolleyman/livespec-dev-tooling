#!/usr/bin/env bash
set -euo pipefail

BASE="/srv/arq-vps-root-snapshot"
DEST="${BASE}/current"
META="${DEST}/.arq-vps-root-snapshot"
LOCK="/run/lock/arq-vps-root-snapshot.lock"

RSYNC_FILTERS=(
    "--filter=- **/.bun/install/***"
    "--filter=- **/.cache/***"
    "--filter=- **/.cargo/***"
    "--filter=- **/.claude-flow/***"
    "--filter=- **/.claude/plugins/***"
    "--filter=- **/.claude/worktrees/***"
    "--filter=- **/.codex/.tmp/***"
    "--filter=- **/.codex/plugins/***"
    "--filter=- **/.git/***"
    "--filter=- **/.gradle/caches/***"
    "--filter=- **/.local/share/mise/installs/***"
    "--filter=- **/.local/share/mise/downloads/***"
    "--filter=- **/.local/share/claude/versions/***"
    "--filter=- **/.local/share/containers/***"
    "--filter=- **/.local/share/JetBrains/Daemon/***"
    "--filter=- **/.local/share/pnpm/***"
    "--filter=- **/.local/share/uv/***"
    "--filter=- **/.mypy_cache/***"
    "--filter=- **/.npm/***"
    "--filter=- **/.pnpm-store/***"
    "--filter=- **/.ruff_cache/***"
    "--filter=- **/.rustup/***"
    "--filter=- **/.venv/***"
    "--filter=- **/.vscode-server/extensions/***"
    "--filter=- **/.vscode/cli/***"
    "--filter=- **/.vscode/extensions/***"
    "--filter=- **/.worktrees/***"
    "--filter=- **/build/***"
    "--filter=- **/dist/***"
    "--filter=- **/go/pkg/***"
    "--filter=- **/node_modules/***"
    "--filter=- **/site-packages/***"
    "--filter=- **/target/***"
    "--filter=- **/__pycache__/***"
    "--filter=- **/venv/***"
    "--filter=- /ci-runner/_work/***"
    "--filter=- /ci-runner/cache/***"
    "--filter=- /ci-runner/runners/***"
    "--filter=- /ubuntu/gate-runner/_work/***"
    "--filter=- arq-vps-root-snapshot/***"
    "--filter=- *.pyc"
    "--filter=- .DS_Store"
)

mkdir -p "${DEST}"

exec 9>"${LOCK}"
if ! flock -n 9; then
    echo "Root snapshot already running; exiting."
    exit 0
fi

rsync_common=(
    -a
    --numeric-ids
    --delete
    --delete-delay
    --delete-excluded
    --one-file-system
    --partial-dir=.rsync-partial
    "${RSYNC_FILTERS[@]}"
)

sync_dir() {
    local src="$1"
    local dest_rel="$2"

    if [[ ! -e "${src}" ]]; then
        return 0
    fi

    mkdir -p "${DEST}/${dest_rel}"
    rsync "${rsync_common[@]}" "${src%/}/" "${DEST}/${dest_rel%/}/"
}

sync_var_lib() {
    mkdir -p "${DEST}/var/lib"
    rsync "${rsync_common[@]}" \
        "--filter=- docker/***" \
        "--filter=- containerd/***" \
        "--filter=- apt/lists/***" \
        "--filter=- apt/periodic/***" \
        "--filter=- dpkg/info/***" \
        "--filter=- snapd/cache/***" \
        "--filter=- snapd/snaps/***" \
        "--filter=- systemd/coredump/***" \
        /var/lib/ "${DEST}/var/lib/"
}

sync_var_log() {
    mkdir -p "${DEST}/var/log"
    rsync "${rsync_common[@]}" \
        --max-size=50M \
        --exclude=journal/** \
        --exclude=*.gz \
        --exclude=*.xz \
        --exclude=*.zst \
        /var/log/ "${DEST}/var/log/"
}

main() {
    set +e
    sync_dir /etc etc
    status_etc=$?
    sync_dir /home home
    status_home=$?
    sync_dir /data data
    status_data=$?
    sync_dir /root root
    status_root=$?
    sync_dir /opt opt
    status_opt=$?
    sync_dir /srv srv
    status_srv=$?
    sync_dir /usr/local usr/local
    status_usr_local=$?
    sync_var_lib
    status_var_lib=$?
    sync_var_log
    status_var_log=$?
    set -e

    local statuses=(
        "${status_etc}" "${status_home}" "${status_data}" "${status_root}"
        "${status_opt}" "${status_srv}" "${status_usr_local}"
        "${status_var_lib}" "${status_var_log}"
    )

    local status
    for status in "${statuses[@]}"; do
        if [[ "${status}" -ne 0 && "${status}" -ne 24 ]]; then
            echo "ERROR: rsync failed with status ${status}" >&2
            exit "${status}"
        fi
    done

    mkdir -p "${META}"
    {
        echo "created_at=$(date --iso-8601=seconds)"
        echo "source_host=$(hostname -f 2>/dev/null || hostname)"
        echo "included_paths=/etc /home /data /root /opt /srv /usr/local /var/lib /var/log"
        echo "excluded_paths=/dev /proc /sys /run /tmp /var/tmp /var/cache /var/lib/docker /var/lib/containerd /var/lib/dpkg/info /mnt /media /lost+found /snap"
        echo "dependency_excludes=go/pkg .rustup .cargo .npm .gradle/caches .bun/install .local/share/mise/installs .local/share/mise/downloads .local/share/claude/versions .local/share/containers .local/share/JetBrains/Daemon .local/share/pnpm .local/share/uv .venv venv site-packages __pycache__ node_modules .pnpm-store .cache .claude/plugins .claude/worktrees .codex/plugins .codex/.tmp .vscode-server/extensions .vscode/extensions .worktrees .git build dist target ci-runner/_work ci-runner/cache ci-runner/runners ubuntu/gate-runner/_work"
        echo "self_excludes=/srv/arq-vps-root-snapshot"
        printf 'rsync_statuses='
        printf '%s ' "${statuses[@]}"
        printf '\n'
        du -sh "${DEST}" 2>/dev/null || true
        find "${DEST}" -xdev -type f 2>/dev/null | wc -l | awk '{print "file_count=" $1}'
    } > "${META}/manifest.txt"

    cp "${META}/manifest.txt" "${BASE}/last-success.txt"
}

main "$@"
