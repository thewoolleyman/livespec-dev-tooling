#!/bin/sh
# RELOCATED 2026-09-06 from hp-xubuntu's untracked /usr/local/sbin/disk-guard.sh
# (live sha256 65e4ff71ba61bf4c369e26166956813e0f86e5e12de28cbd4bd0c5bf9e6ec2cb)
# under livespec plan `k3s-on-gmktec-for-vps-usage`, work-item `livespec-cy2syw`.
# The reclamation LOGIC below is byte-faithful to that file; the only additions
# are this header, the host env read that replaces the hardcoded THRESHOLD_GB,
# and the --dry-run flag install.sh uses to verify the installed copy without
# pruning. Installed by install.sh to the SAME path, so the live timer keeps
# executing the same name and nothing on the host changes but the bytes.
#
#   /usr/local/sbin/disk-guard.sh                        # the timer's form
#   /usr/local/sbin/disk-guard.sh --dry-run              # report only, exit 0
#   ./disk-guard.sh hosts/hp-xubuntu.env --dry-run       # from a checkout
#
# Emergency reclamation guard for hp-xubuntu.
#
# WHY THIS EXISTS: on 2026-08-22 / filled to 0 bytes available. The visible
# symptom was NOT a disk alarm -- it was fabro dispatches failing per-item with
# "Failed to persist run state: ... No space left on device (os error 28)",
# which reads as a work-item fault rather than a host condition. The consumer
# was the containerd image store (Docker 29 keeps images in /var/lib/containerd,
# NOT /var/lib/docker), which had accumulated ~390G of unpruned sandbox images
# and snapshots. Nothing pruned it and nothing watched the disk.
#
# The daily docker-prune.timer is the routine control. This is the backstop for
# when accumulation outruns a day.
set -u

# Host values come from the env file install.sh copies beside the other
# reclaimers' env files. The timer's ExecStart passes no arguments, so the
# installed location is the default; a checkout run names its hosts/<host>.env.
# Any other argument is a flag. A missing env file is a refusal, not a fallback
# to a built-in threshold -- a guard silently running on a number nobody set is
# exactly the untracked state this relocation ends.
ENV_FILE=/usr/local/libexec/disk-guard.env
DRY_RUN=0
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=1 ;;
        --*) echo "ERROR: unknown flag: $arg" >&2; exit 2 ;;
        *) ENV_FILE=$arg ;;
    esac
done
[ -f "$ENV_FILE" ] || { echo "ERROR: no such host env file: $ENV_FILE" >&2; exit 2; }
set -a
# shellcheck source=/dev/null
. "$ENV_FILE"
set +a
: "${DISK_GUARD_THRESHOLD_GB:?host env must set DISK_GUARD_THRESHOLD_GB}"
THRESHOLD_GB=$DISK_GUARD_THRESHOLD_GB
# 2026-09-06 (console plan optimize-console-builds, qxjdan): both docker stores
# (/var/lib/docker AND /var/lib/containerd) moved to the /data volume on
# 2026-08-22, so guarding / alone no longer watches the filesystem the sandbox
# images fill. Derive the store filesystem from the daemon (as
# container-reclaim.sh does) and guard the LOWER of / and the store fs.
STORE_DIR=$(docker info -f "{{.DockerRootDir}}" 2>/dev/null || echo /var/lib/docker)
ROOT_AVAIL_GB=$(df -BG --output=avail / | tail -1 | tr -dc 0-9)
STORE_AVAIL_GB=$(df -BG --output=avail "$STORE_DIR" 2>/dev/null | tail -1 | tr -dc 0-9)
[ -n "$STORE_AVAIL_GB" ] || STORE_AVAIL_GB=$ROOT_AVAIL_GB
AVAIL_GB=$ROOT_AVAIL_GB
WATCHED=/
if [ "$STORE_AVAIL_GB" -lt "$AVAIL_GB" ]; then AVAIL_GB=$STORE_AVAIL_GB; WATCHED="$STORE_DIR"; fi

# --dry-run: the installer's verification. Reports the measurement and the
# decision the live path would take, then exits 0 having pruned nothing.
if [ "$DRY_RUN" = 1 ]; then
    echo "disk-guard DRY RUN: watching ${WATCHED} (store ${STORE_DIR}), ${AVAIL_GB}G available, threshold ${THRESHOLD_GB}G"
    if [ "$AVAIL_GB" -ge "$THRESHOLD_GB" ]; then
        echo "  above threshold: the live run would exit 0 without reclaiming"
    else
        echo "  BELOW threshold: the live run would prune containers, images, builder cache, vacuum the journal to 200M, and apt-get clean"
    fi
    echo "  (dry run -- nothing was pruned)"
    exit 0
fi

[ "$AVAIL_GB" -ge "$THRESHOLD_GB" ] && exit 0

logger -t disk-guard -p daemon.err \
  "LOW DISK: ${WATCHED} has ${AVAIL_GB}G available (threshold ${THRESHOLD_GB}G) - running emergency reclamation"

# Images held by a RUNNING container are never removed, so in-flight fabro
# dispatches survive this.
docker container prune -f          >/dev/null 2>&1
docker image   prune -a -f         >/dev/null 2>&1
docker builder prune -a -f         >/dev/null 2>&1
journalctl --vacuum-size=200M      >/dev/null 2>&1
apt-get clean                      >/dev/null 2>&1

AFTER_GB=$(df -BG --output=avail "$WATCHED" | tail -1 | tr -dc 0-9)
logger -t disk-guard -p daemon.warning \
  "disk-guard reclamation complete: ${AVAIL_GB}G -> ${AFTER_GB}G available on /"
