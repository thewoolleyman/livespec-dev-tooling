#!/usr/bin/env node
// sanitize-hook.js — Phase 0 containment shim for ACTIONS_RUNNER_CONTAINER_HOOKS
// + T10 trust-tiered dependency-cache tiering.
//
// PHASE 0 CONTAINMENT (unchanged behaviour):
// The stock GitHub Actions runner unconditionally mounts the host docker socket
// (-v /var/run/docker.sock:/var/run/docker.sock) into `container:` jobs and can
// pass through create-options a workflow requests. This wrapper enforces the
// Phase 0 runner-containment invariants (plan/fabro-ci-image-factoring/
// phase0-runner-containment-design.md) at the hook boundary — independent of what
// the runner emits — before delegating to the real container hook:
//
//   * strip any host-socket bind (/var/run/docker.sock, /run/docker.sock, and the
//     rootless podman socket) from system/user mount volumes (test 4);
//   * strip host-namespace / privilege escalations from createOptions
//     (--privileged, --pid=host, --network=host, --ipc=host, --userns=host, …);
//   * pass everything else through untouched (run_script_step / cleanup_job etc.).
//
// T10 CACHE-TIERING (livespec-dev-tooling-9mp):
// On `prepare_job`, mount a per-repo warm dependency cache into the job container
// via a THROWAWAY fuse-overlayfs overlay — lowerdir = the persistent warm cache
// (READ-ONLY), upperdir = a per-job throwaway. Every job (trusted OR fork PR)
// reads the warm cache and can only write to its own upper, so a fork PR job
// PHYSICALLY CANNOT mutate the shared cache feeding master builds. There is no
// trust decision at container-create time, hence no forgeable signal anywhere in
// the path — trust-tiering holds BY CONSTRUCTION, not by policy. Proven on the
// live host 2026-07-16 (the 9mp probe) and again with the real console image.
// The hook also STRIPS any workflow-declared mount of the host cache tree, so a
// fork PR cannot bind the raw lower read-write itself.
//
// This whole T10 layer is a NO-OP when CACHE_ROOT does not exist (the natural
// kill switch: provisioning creates it; remove it to disable), and every step is
// wrapped so ANY failure falls through to the plain Phase-0 sanitize + delegate —
// caching never fails a job.
//
// The real hook (hooklib getInputFromStdin) reads only the LAST line of stdin, so
// the payload is single-line JSON; we parse it, sanitize, and re-emit one line.
'use strict';
const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const REAL_HOOK = '/home/ci-runner/actions-runner/container-hooks/index.js';
const BAD_SOURCES = new Set([
  '/var/run/docker.sock',
  '/run/docker.sock',
  '/run/user/1001/podman/podman.sock',
]);
const BAD_OPTS = [
  '--privileged',
  '--pid=host', '--pid host',
  '--network=host', '--net=host',
  '--ipc=host',
  '--userns=host',
  '--security-opt=label=disable', '--security-opt label=disable',
  '--cap-add=all', '--cap-add=ALL',
];

// --- T10 cache-tiering config ---------------------------------------------
// TEST_MODE: emit the transformed payload to stdout (no delegate) and skip the
// real fuse mount (assume success). Set ONLY by the isolation/unit tests; never
// in production. CACHE_ROOT can be overridden for tests to a temp tree.
const TEST_MODE = process.env.LIVESPEC_HOOK_TEST_MODE === '1';
const CACHE_ROOT = process.env.LIVESPEC_HOOK_CACHE_ROOT || '/home/ci-runner/cache';
const OVERLAY_ROOT = path.join(CACHE_ROOT, '.overlay');
// Each warm-cache subdir maps to a container mount target + the env var that
// points the toolchain at it. Set the env EXPLICITLY (not via ~ expansion) —
// container-hook steps run with HOME=/github/home while the image bakes tools
// under /root, so ~ would resolve to the wrong place.
const CACHE_SPECS = [
  { sub: 'cargo', target: '/opt/ci-cache/cargo', env: 'CARGO_HOME' },
  { sub: 'target', target: '/opt/ci-cache/target', env: 'CARGO_TARGET_DIR' },
  { sub: 'uv', target: '/opt/ci-cache/uv', env: 'UV_CACHE_DIR' },
];

function isForbiddenSource(src) {
  if (!src) return false;
  const s = String(src);
  if (BAD_SOURCES.has(s)) return true;
  // Anti-forge: a fork PR must not bind the raw host cache tree itself. Our own
  // injected overlay mounts are added AFTER this filter runs, so they survive.
  if (s === CACHE_ROOT || s.startsWith(CACHE_ROOT + '/')) return true;
  return false;
}

function sanitizeContainer(c) {
  if (!c || typeof c !== 'object') return;
  for (const key of ['systemMountVolumes', 'userMountVolumes']) {
    if (Array.isArray(c[key])) {
      c[key] = c[key].filter((v) => !(v && isForbiddenSource(v.sourceVolumePath)));
    }
  }
  if (typeof c.createOptions === 'string') {
    let opts = c.createOptions;
    for (const bad of BAD_OPTS) opts = opts.split(bad).join('');
    c.createOptions = opts.replace(/\s+/g, ' ').trim();
  }
}

function dirExists(p) {
  try { return fs.statSync(p).isDirectory(); } catch (e) { return false; }
}

// The runner materializes each ephemeral runner under a STABLE per-(repo,slot)
// instance dir /home/ci-runner/runners/<reposlug>-<slot>/, set by the supervisor
// (NOT by any workflow), so it is a non-forgeable identity. Because the overlay
// makes every write throwaway, this is only ever a CACHE KEY — forging it can at
// worst read another repo's public dependency cache read-only, which is harmless;
// it can never poison anything. Derive it (in order): cwd, then the payload's own
// mount paths, then the minted RUNNER_NAME (ci-<reposlug>-<slot>-<pid>-<rand>).
function deriveInst(raw) {
  const RUN_DIR_RE = /\/home\/ci-runner\/runners\/([A-Za-z0-9._]+(?:-[A-Za-z0-9._]+)*-\d+)(?:\/|$)/;
  let cwd = '';
  try { cwd = process.cwd(); } catch (e) { cwd = ''; }
  let m = cwd.match(RUN_DIR_RE);
  if (m) return m[1];
  m = String(raw || '').match(RUN_DIR_RE);
  if (m) return m[1];
  const rn = process.env.RUNNER_NAME || '';
  const mm = rn.match(/^ci-(.+-\d+)-\d+-\d+$/);
  if (mm) return mm[1];
  return null;
}

function reposlugFromInst(inst) {
  return inst.replace(/-\d+$/, '');
}

// Unmount + discard any overlay left under this instance's scratch from a prior
// job (ephemeral runners reuse a stable instance dir, so a missed cleanup_job is
// reclaimed here at the next prepare_job — this is the leak backstop, so cleanup
// need not depend on the label-pruning real cleanupJob or on state-passing).
function cleanupOverlaysForInst(instDir) {
  for (const spec of CACHE_SPECS) {
    const merged = path.join(instDir, spec.sub, 'merged');
    spawnSync('fusermount3', ['-u', merged], { stdio: 'ignore' });
  }
  spawnSync('rm', ['-rf', instDir], { stdio: 'ignore' });
}

// Mount a throwaway overlay per warm-cache subdir that exists (i.e. has been
// provisioned/warmed for this repo). Returns the list of successful injections.
function mountCaches(inst, reposlug) {
  const injected = [];
  const instDir = path.join(OVERLAY_ROOT, inst);
  cleanupOverlaysForInst(instDir);
  for (const spec of CACHE_SPECS) {
    const lower = path.join(CACHE_ROOT, reposlug, spec.sub);
    if (!dirExists(lower)) continue; // only mount caches that are provisioned/warm
    const base = path.join(instDir, spec.sub);
    const upper = path.join(base, 'upper');
    const work = path.join(base, 'work');
    const merged = path.join(base, 'merged');
    try {
      fs.mkdirSync(upper, { recursive: true });
      fs.mkdirSync(work, { recursive: true });
      fs.mkdirSync(merged, { recursive: true });
    } catch (e) { continue; }
    if (TEST_MODE) {
      injected.push({ merged, target: spec.target, env: spec.env });
      continue;
    }
    const r = spawnSync(
      'fuse-overlayfs',
      ['-o', `lowerdir=${lower},upperdir=${upper},workdir=${work}`, merged],
      { stdio: ['ignore', 'ignore', 'inherit'] },
    );
    if (r.status === 0) {
      injected.push({ merged, target: spec.target, env: spec.env });
    } else {
      process.stderr.write(`sanitize-hook: T10 overlay mount failed for ${spec.sub} (status ${r.status})\n`);
    }
  }
  return injected;
}

function injectCaches(c, injected) {
  if (!c || typeof c !== 'object' || !injected.length) return;
  if (!Array.isArray(c.userMountVolumes)) c.userMountVolumes = [];
  if (!c.environmentVariables || typeof c.environmentVariables !== 'object') c.environmentVariables = {};
  for (const inj of injected) {
    c.userMountVolumes.push({ sourceVolumePath: inj.merged, targetVolumePath: inj.target, readOnly: false });
    c.environmentVariables[inj.env] = inj.target;
  }
}

function delegate(inputText) {
  const r = spawnSync(process.execPath, [REAL_HOOK], {
    input: inputText,
    stdio: ['pipe', 'inherit', 'inherit'],
  });
  process.exit(r.status == null ? 1 : r.status);
}

function emitOrDelegate(data) {
  const out = JSON.stringify(data) + '\n';
  if (TEST_MODE) { process.stdout.write(out); process.exit(0); }
  delegate(out);
}

const raw = fs.readFileSync(0, 'utf8');
const line = raw.split('\n').filter((s) => s.trim().length).pop() || '';
let data;
try {
  data = JSON.parse(line);
} catch (e) {
  // Not parseable here — let the real hook produce the canonical error.
  if (TEST_MODE) { process.stdout.write(raw); process.exit(0); }
  delegate(raw);
}
const args = (data && data.args) || {};

// Phase 0 containment — every command that carries a container/service spec.
if (args.container && typeof args.container === 'object') sanitizeContainer(args.container);
if (Array.isArray(args.services)) args.services.forEach(sanitizeContainer);

// T10 cache-tiering — prepare_job only, best-effort, NEVER fatal to the job.
if (data && data.command === 'prepare_job' && dirExists(CACHE_ROOT)) {
  try {
    const inst = deriveInst(raw);
    if (inst && args.container && typeof args.container === 'object') {
      const reposlug = reposlugFromInst(inst);
      const injected = mountCaches(inst, reposlug);
      injectCaches(args.container, injected);
      if (injected.length) {
        // Surfaces in the runner's job-setup log — confirms caching is live and
        // which instance/reposlug the derivation resolved to.
        process.stderr.write(`sanitize-hook: T10 mounted ${injected.map((i) => i.env).join(',')} for ${reposlug} (inst ${inst})\n`);
      }
    }
  } catch (e) {
    process.stderr.write(`sanitize-hook: T10 cache-tiering skipped (${e})\n`);
  }
}

emitOrDelegate(data);
