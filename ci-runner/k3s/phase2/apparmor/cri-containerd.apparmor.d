# cri-containerd.apparmor.d — the NODE-LEVEL copy of containerd's default
# AppArmor profile, with two rules added so a stacked label matches.
#
# WHY THIS FILE EXISTS (livespec-dev-tooling-ddy5xu, measured 2026-11-12)
# ---------------------------------------------------------------------
# Every pod that names no AppArmor profile runs under the profile containerd
# generates and loads itself, `cri-containerd.apparmor.d`. That profile allows
# signal and ptrace only to the BARE peer name `cri-containerd.apparmor.d`.
#
# Ubuntu kernel 7.0.0-43 carries upstream commit 08c2f7c8d4b1 ("apparmor: fix
# unconfined user namespace restriction forced stack", CVE-2026-90231). It moves
# the `kernel.apparmor_restrict_unprivileged_unconfined` check from the moment
# runc requests the profile to the moment the container process is exec'd. By
# then the process holds no CAP_MAC_OVERRIDE, so EVERY non-privileged container
# is labelled
#
#     cri-containerd.apparmor.d//&unconfined
#
# and the bare peer rule no longer matches the container's own processes. On
# gamingpc-xubuntu (the first node booted into 7.0.0-43) a process could not
# signal its own child: 234 `apparmor="DENIED" operation="signal"` lines in a
# day, tests that stop a child waited out their timeout, and gate Jobs hung.
# Older kernels stacked only user-namespaced pods and exec'd processes, which is
# what ./ci-runner-workflow was written for.
#
# HOW IT TAKES EFFECT
# -------------------
# containerd's `LoadDefaultProfile` returns early when a profile of this name is
# already loaded (contrib/apparmor/apparmor.go, `isLoaded`). The apparmor_profile
# Ansible role installs this file in /etc/apparmor.d/ and loads it live with
# `apparmor_parser -r`; the distribution's apparmor unit loads it at every boot,
# before k3s starts. So containerd finds the name present and never generates
# its own. No k3s restart is needed and running containers pick the rules up.
#
# WHERE THE BASE TEXT CAME FROM, so drift can be re-checked
# ---------------------------------------------------------
# Everything below the two marked rules is `defaultTemplate` from
#
#     github.com/k3s-io/containerd  tag v2.3.2-k3s2
#     contrib/apparmor/template.go
#
# (byte-identical to upstream containerd v2.3.2), the containerd that k3s
# v1.36.2+k3s1 ships, rendered the way `loadData` renders it on these nodes:
# `abi/3.0` and `tunables/global` and `abstractions/base` exist, the daemon runs
# unconfined, and no `rootlesskit` is on PATH. WHEN k3s IS UPGRADED, diff that
# file at the new containerd tag against this one and carry any change over;
# this copy shadows the built-in template, so nothing else will.
#
# WHAT IT WIDENS: only the two rules marked STACKED PEER. They let a container's
# processes signal and ptrace peers carrying this same profile stacked with
# `unconfined`. No capability, mount or file rule changes, and the profile stays
# in enforce mode.

abi <abi/3.0>,

#include <tunables/global>

profile cri-containerd.apparmor.d flags=(attach_disconnected,mediate_deleted) {

  #include <abstractions/base>

  network,
  capability,
  file,
  umount,
  # Host (privileged) processes may send signals to container processes.
  signal (receive) peer=unconfined,
  # runc may send signals to container processes.
  signal (receive) peer=runc,
  # crun may send signals to container processes.
  signal (receive) peer=crun,
  # Manager may send signals to container processes.
  signal (receive) peer=unconfined,
  # Container processes may send signals amongst themselves.
  signal (send,receive) peer=cri-containerd.apparmor.d,
  # STACKED PEER (not in containerd's template): the label kernel 7.0.0-43 gives.
  signal (send,receive) peer=cri-containerd.apparmor.d//&unconfined,

  deny @{PROC}/* w,   # deny write for all files directly in /proc (not in a subdir)
  # deny write to files not in /proc/<number>/** or /proc/sys/**
  deny @{PROC}/{[^1-9/],[^1-9/][^0-9/],[^1-9s/][^0-9y/][^0-9s/],[^1-9/][^0-9/][^0-9/][^0-9/]*}/** w,
  deny @{PROC}/sys/[^k]** w,  # deny /proc/sys except /proc/sys/k* (effectively /proc/sys/kernel)
  deny @{PROC}/sys/kernel/{?,??,[^s][^h][^m]**} w,  # deny everything except shm* in /proc/sys/kernel/
  deny @{PROC}/sysrq-trigger rwklx,
  deny @{PROC}/kcore rwklx,

  deny mount,

  deny /sys/[^f]*/** wklx,
  deny /sys/f[^s]*/** wklx,
  deny /sys/fs/[^c]*/** wklx,
  deny /sys/fs/c[^g]*/** wklx,
  deny /sys/fs/cg[^r]*/** wklx,
  deny /sys/firmware/** rwklx,
  deny /sys/devices/virtual/powercap/** rwklx,
  deny /sys/kernel/security/** rwklx,

  # allow processes within the container to trace each other,
  # provided all other LSM and yama setting allow it.
  ptrace (trace,tracedby,read,readby) peer=cri-containerd.apparmor.d,
  # STACKED PEER (not in containerd's template): the label kernel 7.0.0-43 gives.
  ptrace (trace,tracedby,read,readby) peer=cri-containerd.apparmor.d//&unconfined,
}
