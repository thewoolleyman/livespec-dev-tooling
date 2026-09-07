# container-hook/ — the fleet-patched ARC container hook and the externals pre-seed

Work-item `livespec-wm7c` (decision `livespec-b1c6`, 2026-09-04), carrier F5
of livespec plan `ci-runner-pod-lifecycle-reliability`, research/005 ("What
one job start writes"). This directory carries the FIRST half of that item:
the build pipeline for the patched hook, the host-side extraction of the
runner image's externals, the node-local installer, and the upstream proposal.
The second half — selecting the hook from the scale-set values and seeding
the externals from the local-path provisioner — landed after `livespec-lvtu`
and is described at the end; the two are one mechanism and are read together.

## What the problem is

In ARC's `containerMode: kubernetes`, the runner's container hook
(`/home/runner/k8s/index.js`, compiled from actions/runner-container-hooks
`packages/k8s`) prepares every job. Its `copyExternalsToRoot()` copies
`/home/runner/externals` — the runner's bundled Node runtimes: `node24`
202 MB, `node20` 167 MB, `node24_alpine` 125 MB, `node20_alpine` 100 MB;
595 MB and 9,028 files in all — into `<work volume>/externals` on every job
start, unconditionally, ~14 s on the pool's array. Verified 2026-09-04 by
mounting the pinned image read-only on `poweredge-xubuntu` (`livespec-b1c6`):
line 541 of the bundle, called from `prepareJob` at line 419, with
`{ force: true, recursive: true }`. The measurement is research/005 §2; with
the warm-cache copy it was 21 of a lint job's 56-second pod lifetime.

The maintainer's decision (`livespec-b1c6`, ~10:35Z): a fleet-built PATCHED
hook that skips the copy when the volume was pre-seeded, selected through
the runner's `ACTIONS_RUNNER_CONTAINER_HOOKS` setting; externals pre-seeded
by hardlink from a host copy extracted from the pinned image; and the skip
proposed upstream so the fleet patch can be dropped when accepted.

## Files

| File | Role |
|---|---|
| `externals-skip.patch` | The ONE change against upstream: `git diff` output against tag `v0.7.0`, with a header saying why. Skips the copy only when `ACTIONS_RUNNER_PRESEEDED_EXTERNALS_VERSION` names a runner version AND `<work volume>/externals/.externals-seeded-<that version>` exists with that version as its content; otherwise the copy runs exactly as upstream's. 23 lines added, 1 changed. |
| `build-patched-hook.sh` | Developer-host build (Node via mise, network to GitHub and npm). Derives the hook version the pinned image bundles, proves it against the image's bytes and a reproducible unpatched rebuild, applies the patch, rebuilds, checks the result, writes `bundle/<runner-version>/`. Fails loudly at every step — see "Failure modes". |
| `runner-image.sh` | Sourced by the three scripts: reads the image pin from `../arc/values-livespec.yaml` (the reference values file; every values file carries the same line) and derives the runner version and containerd's digest name from it, so the three cannot disagree. Also carries `assert_values_pins_agree`, which requires EVERY `../arc/values-*.yaml` to state the same image pin, the same fleet-hook hostPath version and the same `ACTIONS_RUNNER_PRESEEDED_EXTERNALS_VERSION` — the notice that reading one reference file is safe. It compares the files against each other, never against a caller's `--image`, so the bump order below still passes. |
| `bundle/<runner-version>/index.js` + `index.js.sha256` + `BUILD-INFO` | The COMMITTED build output (8.9 MB, an ncc bundle; `dist/` is gitignored in this repo, hence the name). The node needs no Node toolchain: the installer copies from the checkout. `BUILD-INFO` records the image, the derived hook version and its source, the tag commit, the upstream asset's sha256, the image cross-check result, the patch's sha256, the patched bundle's sha256 and size, the line delta, and the Node/npm versions. |
| `extract-externals.sh` | Node-local (root): mounts the pinned image read-only through containerd (`ctr -n k8s.io images mount --rw=false`; pulls it first only if this node never ran a runner pod), cross-checks the runner version inside (`bin/Runner.Listener.deps.json`) and optionally the bundled hook's sha256, copies `/home/runner/externals` to `/var/lib/rancher/k3s/storage/.externals/<runner-version>/` with the marker file, verifies a per-file sha256 manifest, moves it into place atomically, and LAST publishes `.externals/current` — a relative symlink to that version directory, by one atomic rename — because the provisioner's setup script cannot know the runner version and seeds from that one name. Idempotent on the manifest, and republishes the pointer even when it copies nothing. `--dry-run` prints the plan without root. |
| `install-container-hook.sh` | Node-local (root), run by `../install-node.sh` step 7c: verifies the committed bundle's manifest and that it was built for the pinned image, installs it to `/usr/local/lib/ci-runner-k3s/hooks/<runner-version>/index.js` (0644 root), then runs `extract-externals.sh` with the hook cross-check. |

## How the pieces fit

```
developer host                          CI node (poweredge-xubuntu)
--------------                          ---------------------------
build-patched-hook.sh                   install-node.sh 7c -> install-container-hook.sh
  derive hook version (Dockerfile ARG)    verify bundle/<v>/index.js.sha256 + BUILD-INFO
  image bytes == release asset            install /usr/local/lib/ci-runner-k3s/hooks/<v>/index.js
  unpatched rebuild == release asset      extract-externals.sh
  apply externals-skip.patch, rebuild       ctr images mount --rw=false <image>
  write bundle/<v>/ (committed)             cp -a /home/runner/externals -> storage/.externals/<v>/
                                            write .externals-seeded-<v> (content: <v>)

                                            publish storage/.externals/current -> <v>

                                        SECOND HALF (landed after livespec-lvtu):
                                        values-*.yaml: hostPath hooks/<v>/index.js (ro, type: File),
                                          ACTIONS_RUNNER_CONTAINER_HOOKS=/home/runner/fleet-hook/index.js,
                                          ACTIONS_RUNNER_PRESEEDED_EXTERNALS_VERSION=<v>
                                        provisioner setup:
                                          cp -a --reflink=always storage/.externals/current/. ${VOL_DIR}/externals
```

At job start the patched hook reads the env, looks for the marker under
`<work volume>/externals`, and on a match logs `externals pre-seeded at …;
skipping the copy` and returns; the job container mounts the volume at
`/__e` exactly as before and finds the same bytes, now as hardlinks into the
host copy (metadata writes only; research/005 §6, lever L3).

### Why the version comes from the environment

The marker check needs to know which runner version's externals to expect,
and the runner exports nothing a hook could read it from: no `RUNNER_VERSION`
in the hook's environment (the runner's `ContainerHookManager` passes the
process environment through unchanged), no version file or label in the
image, and `/home/runner/bin/Runner.Listener.deps.json` is the only place
that names it (checked 2026-09-04 against the runner source at v2.336.0 and
the image). So the scale-set values declare it beside the image pin. An unset
env is the upstream behaviour: the copy runs. That is also what makes the
patch safe to run against an unseeded volume.

### The coupling rule

The three second-half edits MUST be applied together: the provisioner
seed, the hook selection, and the version env. A seed with NO env (or with
the image's own hook) means the upstream copy runs over seeded files it
cannot write — the runner is uid 1000 and the files are the image's
1001:123 — and the job fails at prepare. An env with NO seed is harmless (no
marker, so the copy runs). A seed with the env but the wrong version is
harmless the same way. The reflink seed does not relax this: a reflink copy
gives the volume its own inodes, which is what keeps a job's writes out of the
host copy, but the files still carry the image's `1001:123` ownership, so a
uid-1000 runner still cannot write them.

## The derivation, and the proof it is right

Runner image `ghcr.io/actions/actions-runner:2.336.0@sha256:0cfdcc70…`
bundles runner-container-hooks **v0.7.0** at `/home/runner/k8s/index.js`
(and, separately, v0.8.1 at `/home/runner/k8s-novolume/index.js`, the
"novolume" variant the fleet does not select). Derived from `ARG
RUNNER_CONTAINER_HOOKS_VERSION=0.7.0` in actions/runner `images/Dockerfile`
at tag `v2.336.0`; the runner's publish workflow passes no override for that
argument, and the runner release notes do not name the hook version at all.

The build does not trust the Dockerfile alone:

- the image's `/home/runner/k8s/index.js` is byte-identical to the v0.7.0
  release asset `actions-runner-hooks-k8s-0.7.0.zip`'s `index.js`
  (sha256 `ab92729b095f5fdb8b51b8a6f8cfc2f1647617e0e12c17f2ff39feea686a1966`,
  8,945,722 bytes), read out of the image with `docker create` + `docker cp`,
  never running it;
- an UNPATCHED rebuild of tag v0.7.0 (commit `7da5474`) with Node 20.19.5
  (and, separately, 22.22.0) is byte-identical to that asset — so the
  toolchain reproduces upstream, and the patched bundle is provably
  "upstream plus the patch".

The first build (2026-09-04): patched `index.js` sha256
`6a91cc4882c0d6ec97c687add2a6d13609b08856d598972c0d66c807f650919a`,
8,946,760 bytes, 27 lines differing from upstream's bundle — the compiled
patch and nothing else (`diff` of the two bundles shows exactly the `fs`
import, the `destination`/marker check in `copyExternalsToRoot`, and the
`externalsPreseeded` function). The compiled check was exercised locally in
seven states (env unset/set, marker absent/mismatched/matching/for another
version, destination missing); only env-set-and-marker-matching returns
true.

## Runner-image bump procedure

A runner-image bump is ALSO a hook rebuild and a re-extraction. In this
order:

1. On a developer host, with the NEW reference: `./build-patched-hook.sh
   --image ghcr.io/actions/actions-runner:<new>@sha256:<new digest>`. It
   derives the hook version the new image bundles and either produces
   `bundle/<new version>/` or fails (below). Commit the new bundle directory
   and delete the previous version's in the same change.
2. Change tag and digest together in every `../arc/values-*.yaml` (the k3s
   README "Pinned versions" procedure), and in the SAME change point that
   file's `fleet-container-hook` hostPath at
   `/usr/local/lib/ci-runner-k3s/hooks/<new version>/index.js` and set
   `ACTIONS_RUNNER_PRESEEDED_EXTERNALS_VERSION=<new version>`. Each file
   states the version three times and no file can inherit it from another —
   Helm applies each on its own with `-f`, merging no shared base — so this
   is a rewrite of every file, and `assert_values_pins_agree` (run by both
   `build-patched-hook.sh` and `install-container-hook.sh`) refuses a
   half-rewritten set. The provisioner's setup script needs no edit at all:
   it seeds from `.externals/current`, which step 3 republishes.
3. On the node: `sudo ../install-node.sh ../../phase0-bare-metal/profiles/<node>.env`
   (step 7c installs the
   new hook beside the old one, extracts the new image's externals under their
   own version directory, and moves `.externals/current` onto it; nothing
   running changes yet, because volumes already provisioned keep the seed they
   were born with and the next volume is the first to get the new one).
4. Apply the values (`helm upgrade` per release) and recycle idle runners
   (`../arc/recycle-scale-set-runners.sh`), exactly as for any values change.
5. Verify with research/005's single-start watcher: externals present at
   +0 s, `externals pre-seeded` in the runner's hook log, no externals bytes
   in the per-start writes. Then remove the old `hooks/<old>/` and
   `.externals/<old>/` on the node — check first that `.externals/current`
   does not name the one being removed (a live volume's reflink copies are its
   own inodes and stay valid regardless; the directories are only the seed
   source, and the pointer is the only thing that must never dangle).

## Failure modes

- **The patch does not apply** (a bump moved the bundled hook to a tag whose
  `prepare-job.ts` differs — upstream's v0.8.x has already removed
  `copyExternalsToRoot` in favour of an init-container move, so any bump
  onto a 0.8-bundling image WILL fail here). `build-patched-hook.sh` stops at
  `git apply --check`; no bundle is written; the bump is blocked until the
  patch is re-derived against the new tag (or the upstream proposal below is
  released and the fleet patch is dropped). This block is the design, not a
  bug: shipping an image whose hook the fleet has not patched would silently
  reinstate the 595 MB copy on every start.
- **The unpatched rebuild does not reproduce the release bytes.** Toolchain
  drift (a different Node major, an npm that resolves the lockfile
  differently). The build refuses; try `NODE_VERSION=22.22.0` (both 20 and
  22 reproduced v0.7.0), then investigate before overriding anything.
- **The image's hook is not the release asset for the derived version.** The
  Dockerfile default was overridden at image build. Derive the version from
  the bytes instead (compare the image's `index.js` against release assets)
  and pass the finding on; the script has no override flag on purpose.
- **`install-container-hook.sh`: no bundle for this runner version**, or the
  bundle's `BUILD-INFO` names a different digest. Step 1 of the bump was
  skipped; nothing is installed.
- **`extract-externals.sh`: the image's runner is not the tag's version**, or
  the bundled hook's sha256 is not what the bundle patched. A mismatched
  image or a stale bundle; nothing is extracted.
- **A marker for the wrong version on a volume.** The hook copies (the env
  names the current version, the marker another); the job runs, only slower.
  Nothing corrupts: the copy writes new files beside the old hardlinks.

## The alpine variants

`node20_alpine` and `node24_alpine` (225 MB of the 595) are extracted and
seeded with the rest. They can never be used by the fleet's glibc sandbox
image, but excluding them is allowed only once verified unused by EVERY
routed workflow (the decision record's condition), and the hook selects the
alpine runtime per job container (`isPodContainerAlpine`), so a routed job
with an alpine `container:` would break without them. Not verified in this
half; a follow-up may exclude them from the seed (never from the extraction).

## Upstream proposal

Fork: `thewoolleyman/runner-container-hooks`. Pull request:
https://github.com/actions/runner-container-hooks/pull/434 (draft) — the same opt-in written against upstream
`main`, where the copy is now the `fs-init` init container's `mv` into an
`emptyDir` (v0.8.x, PR #244): the platform may supply the `externals` volume
through the hook-template extension and declare
`ACTIONS_RUNNER_PRESEEDED_EXTERNALS_VERSION`; `fs-init` skips the move when
the marker matches. Default behaviour is unchanged. Context upstream: issue
#168 (open since 2024, asking for exactly this skip) and PR #399 (open;
mounts externals from a Kubernetes image volume instead, which needs the
`ImageVolume` feature gate, Kubernetes 1.35+) — the proposal complements
#399 for platforms that pre-seed rather than image-mount.

## Second half — what the seed and the selection actually do

Landed after `livespec-lvtu`, in the files this half deliberately did not
touch while that item was editing them:

- `../local-path-provisioner/local-path-provisioner.yaml` `setup`: after the
  warm-cache seeds,
  `cp -a --reflink=always "${VOL_DIR%/*}/.externals/current/." "${VOL_DIR}/externals"`.
  A REFLINK copy, not the `cp -al` this half first planned, for the reason
  research/006 forced on the warm seed: hardlinked inodes ARE the host copy's
  and are writable from every job, while a reflink gives the volume its own
  inodes sharing the host copy's extents copy-on-write. It reads
  `.externals/current` rather than a version, because the setup script gets
  only `VOL_DIR`, `VOL_MODE` and `VOL_SIZE_BYTES` and never reads the values
  files. The marker rides along inside the tree. A missing pointer, a missing
  generation or any failure leaves NO `externals` at all — with the marker
  removed BEFORE the tree, so an interrupted removal can only leave a tree the
  hook overwrites, never a partial tree carrying a marker the hook would trust.
  Ownership and modes stay the image's, with no `0777` directory pass like the
  warm seed's: nothing adds entries here, and the hook's own copy is skipped.
- every `../arc/values-*.yaml`: a `hostPath` volume named
  `fleet-container-hook` for
  `/usr/local/lib/ci-runner-k3s/hooks/<v>/index.js` (`type: File`, so a node
  that has not installed the hook fails the pod loudly rather than presenting
  an empty directory) mounted read-only at `/home/runner/fleet-hook/index.js`,
  `ACTIONS_RUNNER_CONTAINER_HOOKS` pointing at that same path (the chart
  yields to a user-supplied value of that env), and
  `ACTIONS_RUNNER_PRESEEDED_EXTERNALS_VERSION: "<v>"` beside the image pin.
  Every file states the version three times because Helm applies each one on
  its own; `assert_values_pins_agree` is what makes that safe.
- `../arc/hook-pod-template.yaml`: unchanged, as expected; the workflow pod
  keeps mounting the work volume, and `/__e` is the same path.
- Acceptance is `livespec-wm7c` criterion 2, and is NOT discharged by this
  repository change alone: the single-start watcher must show externals
  present at +0 s, no copy in the hook log, per-start writes under 100 MB, a
  real node20 and a real node24 action green on the pool, and one clean reboot
  survived — all of which need the host apply (`install-node.sh` step 7c, then
  the values applied per release and idle runners recycled).
