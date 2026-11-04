#!/usr/bin/env node
'use strict'
// git-seed-hook.js -- the pool's runner container hook entry point. It names
// the job's own repository's git object seed to the job container, then runs
// the fleet-patched ARC hook (../container-hook/) UNCHANGED.
//
// The runner runs ACTIONS_RUNNER_CONTAINER_HOOKS as `node <this file>` and
// writes one JSON line to stdin: {command, responseFile, args, state}. For
// `prepare_job` -- the one command that creates the job container -- this file
// adds GIT_ALTERNATE_OBJECT_DIRECTORIES to args.container.environmentVariables
// and hands the line to the real hook, which turns that map into the job
// container's env. Every other command, and every prepare_job this file
// declines to touch, reaches the real hook byte for byte.
//
// WHY A HOOK AND NOT THE POD TEMPLATE. The template's env is static, and
// SPECIFICATION "Runner-pool build cache tiers" requires the variable to be
// set ONLY when the seed directory exists in the job's work volume and not at
// all under the fleet kill switch or the cold canary. git also prints
// "unable to normalize alternate object path" for every command when a named
// directory is absent (git 2.43, measured 2026-11-04), so a static value would
// turn every unseeded job's git output noisy. No workflow step is involved:
// actions/checkout deletes the work tree and runs `git init` before it
// fetches, so the container's own env is the only seam.
//
// THE REPOSITORY IS NOT A WORKFLOW'S TO CHOOSE. It is the last path segment of
// RUNNER_WORKSPACE, which the runner derives from the job's repository. The
// seed lives at <work volume>/_warm/git/<repo>/objects (the local-path
// provisioner's setup script puts only that repository's store there), and the
// job container sees the work volume at /__w.
//
// FAIL-SOFT. Any condition this file cannot establish -- an unset or odd
// RUNNER_WORKSPACE, a missing or unreadable seed, an unreadable template -- is
// "do not set the variable". The line is then forwarded as received.
//
// The kill switch and the canary are read from the SAME hook pod template the
// postStart script reads, by the same rule, so one ConfigMap converge moves
// every tier together: CI_CACHE_KILL_SWITCH non-empty turns the tier off, and
// so does the pod whose cksum is 0 mod CI_CACHE_CANARY_N.

const fs = require('fs')
const path = require('path')
const { spawn } = require('child_process')

const ALTERNATES_VARIABLE = 'GIT_ALTERNATE_OBJECT_DIRECTORIES'
const JOB_WORK_ROOT = '/__w'
const MAX_POD_NAME_LENGTH = 63
const REPOSITORY_NAME = /^[A-Za-z0-9._-]+$/

function templateValue(template, name) {
  const found = new RegExp(
    `name:\\s*${name}\\s*\\n\\s*value:\\s*(?:"([^"\\n]*)"|'([^'\\n]*)'|([^\\s#"'\\n]*))`
  ).exec(template)
  if (found === null) {
    return ''
  }
  return found[1] ?? found[2] ?? found[3] ?? ''
}

// The POSIX cksum of a string: the number `cksum | cut -d' ' -f1` prints, which
// the hook pod template's postStart script reduces mod CI_CACHE_CANARY_N.
function cksum(text) {
  const bytes = Buffer.from(text, 'utf8')
  let crc = 0
  const feed = byte => {
    crc = (crc ^ (byte << 24)) >>> 0
    for (let bit = 0; bit < 8; bit += 1) {
      crc = (crc & 0x80000000 ? (crc << 1) ^ 0x04c11db7 : crc << 1) >>> 0
    }
  }
  for (const byte of bytes) {
    feed(byte)
  }
  let length = bytes.length
  while (length > 0) {
    feed(length & 0xff)
    length = Math.floor(length / 256)
  }
  return ~crc >>> 0
}

function jobPodName(runnerPodName) {
  return `${runnerPodName.substring(0, MAX_POD_NAME_LENGTH - '-workflow'.length)}-workflow`
}

// '' when the cache tiers are on for this job; otherwise the switch's name.
function coldReason(env, template) {
  if (templateValue(template, 'CI_CACHE_KILL_SWITCH') !== '') {
    return 'operator'
  }
  const canary = templateValue(template, 'CI_CACHE_CANARY_N')
  const runnerPodName = env.ACTIONS_RUNNER_POD_NAME
  if (/^[0-9]+$/.test(canary) && Number(canary) > 0 && runnerPodName) {
    if (cksum(jobPodName(runnerPodName)) % Number(canary) === 0) {
      return 'canary'
    }
  }
  return ''
}

function seedDirectory(workspace) {
  if (!workspace || !path.isAbsolute(workspace)) {
    return null
  }
  const repository = path.basename(workspace)
  if (!REPOSITORY_NAME.test(repository) || repository === '.' || repository === '..') {
    return null
  }
  const objects = path.join(path.dirname(workspace), '_warm', 'git', repository, 'objects')
  try {
    fs.accessSync(objects, fs.constants.R_OK | fs.constants.X_OK)
    if (!fs.statSync(objects).isDirectory()) {
      return null
    }
    fs.readdirSync(objects)
    const packs = path.join(objects, 'pack')
    if (fs.existsSync(packs)) {
      fs.readdirSync(packs)
    }
  } catch {
    return null
  }
  return path.posix.join(JOB_WORK_ROOT, '_warm', 'git', repository, 'objects')
}

function readTemplate(env) {
  const templatePath = env.ACTIONS_RUNNER_CONTAINER_HOOK_TEMPLATE
  if (!templatePath) {
    return null
  }
  try {
    return fs.readFileSync(templatePath, 'utf8')
  } catch {
    return null
  }
}

// The stdin line to hand the real hook: the input unchanged unless every
// condition for naming the seed holds.
function rewriteInput(raw, env) {
  let payload
  try {
    const lines = raw.toString('utf8').split('\n').filter(line => line.trim() !== '')
    payload = JSON.parse(lines[lines.length - 1])
  } catch {
    return raw
  }
  const container = payload?.args?.container
  if (payload?.command !== 'prepare_job' || !container || typeof container.environmentVariables !== 'object' || container.environmentVariables === null) {
    return raw
  }
  const template = readTemplate(env)
  if (template === null || coldReason(env, template) !== '') {
    return raw
  }
  const seed = seedDirectory(env.RUNNER_WORKSPACE)
  if (seed === null) {
    return raw
  }
  container.environmentVariables[ALTERNATES_VARIABLE] = seed
  return Buffer.from(`${JSON.stringify(payload)}\n`, 'utf8')
}

function run() {
  const realHook = process.env.FLEET_REAL_CONTAINER_HOOK || '/home/runner/fleet-hook/index.js'
  const input = rewriteInput(fs.readFileSync(0), process.env)
  const child = spawn(process.execPath, [realHook], { stdio: ['pipe', 'inherit', 'inherit'], env: process.env })
  for (const signal of ['SIGINT', 'SIGTERM']) {
    process.on(signal, () => child.kill(signal))
  }
  child.on('error', error => {
    process.stderr.write(`git-seed-hook: cannot run ${realHook}: ${error.message}\n`)
    process.exit(1)
  })
  child.on('close', (code, signal) => {
    process.exit(signal ? 1 : code)
  })
  child.stdin.on('error', () => undefined)
  child.stdin.end(input)
}

if (require.main === module) {
  run()
} else {
  module.exports = { cksum, coldReason, jobPodName, rewriteInput, seedDirectory, templateValue }
}
