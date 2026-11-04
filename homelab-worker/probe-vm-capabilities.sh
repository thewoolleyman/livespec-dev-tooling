#!/usr/bin/env bash
# probe-vm-capabilities.sh [<data-mount>] — run INSIDE a homelab worker's Linux
# VM (as root) before the worker container starts.
#
# Governed by SPECIFICATION/non-functional-requirements.md, "Homelab worker
# nodes": "Capability probe before admission". It reports each capability the
# worker's pods need on its own line,
#
#   PRESENT <capability>
#   MISSING <capability>: <actionable remedy>
#
# and exits non-zero when any is missing. It only observes: it never loads a
# module, relaxes a sysctl or changes a mount to make itself pass.
#
# PROBE_ROOT (default empty) prefixes every kernel-interface path, so the probe
# can be exercised against a fixture tree; the commands it runs are found on
# PATH for the same reason.
set -uo pipefail

root="${PROBE_ROOT:-}"
data_mount="${1:-/mnt/homelab-worker-data}"
missing=0

present() {
  printf 'PRESENT %s\n' "$1"
}

absent() {
  printf 'MISSING %s: %s\n' "$1" "$2"
  missing=1
}

# version_ge A B over the leading numeric MAJOR.MINOR of a kernel release.
kernel_at_least() {
  local rel="$1" want_major="$2" want_minor="$3" major minor
  major="${rel%%.*}"
  minor="${rel#*.}"
  minor="${minor%%[!0-9]*}"
  [ "${major:-0}" -gt "$want_major" ] && return 0
  [ "${major:-0}" -eq "$want_major" ] && [ "${minor:-0}" -ge "$want_minor" ]
}

# 1. AppArmor loaded and enforcing.
if [ "$(cat "$root/sys/module/apparmor/parameters/enabled" 2>/dev/null)" = "Y" ] &&
  [ -e "$root/sys/kernel/security/apparmor/profiles" ]; then
  present apparmor
else
  absent apparmor "the VM kernel does not have AppArmor enabled; boot it with 'apparmor=1 security=apparmor' and install the apparmor package, or choose a guest image whose kernel enables it"
fi

# 2. Pod user namespaces with idmapped mounts (Linux >= 6.3 for tmpfs idmap).
release="$(uname -r)"
userns_max="$(cat "$root/proc/sys/user/max_user_namespaces" 2>/dev/null || echo 0)"
if ! kernel_at_least "$release" 6 3; then
  absent userns-idmap "kernel $release is older than 6.3, which pod user namespaces need for idmapped tmpfs mounts; use a guest image with Linux 6.3 or newer"
elif [ "${userns_max:-0}" -le 0 ]; then
  absent userns-idmap "user.max_user_namespaces is ${userns_max:-0}; set it above 0 in the guest image's sysctl configuration"
elif ! idmap_dir="$(mktemp -d)" || ! mkdir -p "$idmap_dir/src" "$idmap_dir/dst" ||
  ! mount --bind -o X-mount.idmap=b:0:100000:65536 "$idmap_dir/src" "$idmap_dir/dst" 2>/dev/null; then
  absent userns-idmap "an idmapped bind mount failed; the guest needs util-linux 2.39 or newer and a filesystem that supports idmapped mounts"
else
  umount "$idmap_dir/dst" 2>/dev/null || true
  present userns-idmap
fi

# 3. TUN device for the worker's kernel-mode Tailscale.
if [ -c "$root/dev/net/tun" ]; then
  present tun
else
  absent tun "/dev/net/tun is absent; load the tun module in the guest (modprobe tun) through its image configuration"
fi

# 4. cgroup v2 with the kubelet's controllers delegated.
controllers="$(cat "$root/sys/fs/cgroup/cgroup.controllers" 2>/dev/null || true)"
subtree="$(cat "$root/sys/fs/cgroup/cgroup.subtree_control" 2>/dev/null || true)"
cg_missing=""
for c in cpu memory pids io; do
  case " $controllers " in *" $c "*) ;; *) cg_missing="$cg_missing $c" ;; esac
  case " $subtree " in *" $c "*) ;; *) cg_missing="$cg_missing $c(not-delegated)" ;; esac
done
if [ -z "$controllers" ]; then
  absent cgroup-v2 "the unified cgroup v2 hierarchy is not mounted at /sys/fs/cgroup; boot the guest with systemd.unified_cgroup_hierarchy=1"
elif [ -n "$cg_missing" ]; then
  absent cgroup-v2 "controllers missing or not delegated at the root:$cg_missing; enable them in the guest's systemd delegation"
else
  present cgroup-v2
fi

# 5. Shared mount propagation on /.
case "$(findmnt -n -o PROPAGATION / 2>/dev/null)" in
  *shared*) present mount-propagation ;;
  *) absent mount-propagation "/ is not a shared mount; the guest's systemd must keep / shared (do not mount it private)" ;;
esac

# 6. A nested container runtime that can start a container.
if docker run --rm --pull=missing public.ecr.aws/docker/library/busybox:1.37 true >/dev/null 2>&1; then
  present nested-containerd
else
  absent nested-containerd "rootful Docker in the VM could not start a container; check 'systemctl status docker containerd' in the VM"
fi

# 7. Reflink-capable local storage for the worker's containerd store and caches.
if [ ! -d "$root$data_mount" ]; then
  absent reflink-storage "the worker data disk is not mounted at $data_mount; the start task attaches it as an XFS Lima disk"
elif ! rf_dir="$(mktemp -d "$root$data_mount/.reflink-probe.XXXXXX")" ||
  ! printf 'probe\n' >"$rf_dir/a" || ! cp --reflink=always "$rf_dir/a" "$rf_dir/b" 2>/dev/null; then
  absent reflink-storage "$data_mount does not support reflink copies; format it XFS with reflink=1 or btrfs"
else
  rm -rf "$rf_dir"
  present reflink-storage
fi

exit "$missing"
