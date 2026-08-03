"use strict";

const crypto = require("crypto");

const INVALID_INPUT = "rate-budget-invalid-input";
const MALFORMED = "rate-budget-malformed";
const NOT_RESTORED = "rate-budget-not-restored";
const PROBE_UNUSABLE = "probe-unusable";

function deterministicJitterSeconds(seed) {
  const digest = crypto.createHash("sha256").update(seed).digest("hex");
  return Number.parseInt(digest.slice(0, 8), 16) % 31;
}

function parseNonNegativeInteger(value) {
  if (!/^\d+$/.test(value || "")) {
    throw new Error(INVALID_INPUT);
  }
  const parsed = Number.parseInt(value, 10);
  if (!Number.isSafeInteger(parsed) || parsed < 0) {
    throw new Error(INVALID_INPUT);
  }
  return parsed;
}

function inputValue(env, name, fallback) {
  return Object.prototype.hasOwnProperty.call(env, name) ? env[name] : fallback;
}

function parseInputs(env) {
  const minCoreRemaining = parseNonNegativeInteger(
    inputValue(env, "INPUT_MIN_CORE_REMAINING", "500"),
  );
  const minGraphqlRemaining = parseNonNegativeInteger(
    inputValue(env, "INPUT_MIN_GRAPHQL_REMAINING", "1"),
  );
  const cushionSeconds = parseNonNegativeInteger(
    inputValue(env, "INPUT_CUSHION_SECONDS", "30"),
  );
  const maxWaitSeconds = parseNonNegativeInteger(
    inputValue(env, "INPUT_MAX_WAIT_SECONDS", "3900"),
  );
  if (minCoreRemaining === 0 || minGraphqlRemaining === 0) {
    throw new Error(INVALID_INPUT);
  }
  const seed = env.INPUT_JITTER_SEED || env.GITHUB_SHA || "";
  return {
    apiUrl: (env.GITHUB_API_URL || "https://api.github.com").replace(/\/+$/, ""),
    probeToken: env.PROBE_TOKEN || "",
    minCoreRemaining,
    minGraphqlRemaining,
    cushionSeconds,
    maxWaitSeconds,
    jitterSeconds: deterministicJitterSeconds(seed),
  };
}

function resourceBudget(payload, name) {
  const resource = payload && payload.resources && payload.resources[name];
  if (
    !resource ||
    !Number.isSafeInteger(resource.remaining) ||
    !Number.isSafeInteger(resource.reset)
  ) {
    throw new Error(MALFORMED);
  }
  return resource;
}

function deficientResources(payload, config) {
  const core = resourceBudget(payload, "core");
  const graphql = resourceBudget(payload, "graphql");
  const deficient = [];
  if (core.remaining < config.minCoreRemaining) {
    deficient.push(core);
  }
  if (graphql.remaining < config.minGraphqlRemaining) {
    deficient.push(graphql);
  }
  return deficient;
}

async function defaultSleepSeconds(seconds) {
  await new Promise((resolve) => {
    setTimeout(resolve, seconds * 1000);
  });
}

async function fetchRateLimit(config, fetchImpl, sleepSeconds) {
  const url = `${config.apiUrl}/rate_limit`;
  for (const attempt of [1, 2, 3]) {
    try {
      const response = await fetchImpl(url, {
        method: "GET",
        headers: {
          accept: "application/vnd.github+json",
          authorization: `Bearer ${config.probeToken}`,
          "x-github-api-version": "2022-11-28",
        },
      });
      if (response.ok) {
        try {
          return await response.json();
        } catch (error) {
          throw new Error(MALFORMED);
        }
      }
    } catch (error) {
      if (error.message === MALFORMED) {
        throw error;
      }
    }
    if (attempt < 3) {
      await sleepSeconds(attempt === 1 ? 2 : 4);
    }
  }
  throw new Error(PROBE_UNUSABLE);
}

function waitSecondsFor(deficient, config, nowSeconds) {
  const laterReset = Math.max(...deficient.map((resource) => resource.reset));
  const resetWait = Math.max(0, laterReset - nowSeconds);
  return resetWait + config.cushionSeconds + config.jitterSeconds;
}

async function runGate(options = {}) {
  const env = options.env || process.env;
  const fetchImpl = options.fetchImpl || globalThis.fetch;
  const sleepSeconds = options.sleepSeconds || defaultSleepSeconds;
  const nowSeconds =
    options.nowSeconds || (() => Math.floor(Date.now() / 1000));
  const log = options.log || ((message) => console.log(message));
  const config = parseInputs(env);
  if (!config.probeToken) {
    throw new Error(PROBE_UNUSABLE);
  }

  let sleptSeconds = 0;
  while (true) {
    const payload = await fetchRateLimit(config, fetchImpl, sleepSeconds);
    const deficient = deficientResources(payload, config);
    if (deficient.length === 0) {
      log(`rate budget healthy after ${sleptSeconds}s of budget waiting`);
      return { status: "healthy", sleptSeconds };
    }
    const waitSeconds = waitSecondsFor(deficient, config, nowSeconds());
    const remainingWait = config.maxWaitSeconds - sleptSeconds;
    if (remainingWait <= 0 || waitSeconds > remainingWait) {
      throw new Error(NOT_RESTORED);
    }
    log(`rate budget deficient; sleeping ${waitSeconds}s before re-probe`);
    await sleepSeconds(waitSeconds);
    sleptSeconds += waitSeconds;
  }
}

async function main() {
  try {
    await runGate();
  } catch (error) {
    const marker = String(error.message || error).split(":")[0];
    console.error(`::error::${marker}`);
    process.exitCode = 1;
  }
}

if (require.main === module) {
  void main();
}

module.exports = {
  deterministicJitterSeconds,
  runGate,
};
