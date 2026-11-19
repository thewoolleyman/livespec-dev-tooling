"use strict";

const fs = require("fs");

const DEFAULT_BAND = "low";
const HIGH_BAND = "high";
const MAX_RECORD_AGE_MILLISECONDS = 72 * 60 * 60 * 1000;
const BAND_ORDER = Object.freeze({ low: 0, medium: 1, high: 2 });
const ITEM_ID_PATTERN = /\b[a-z0-9]+(?:-[a-z0-9]+){2,}\b/g;

function writeOutput(name, value) {
  if (process.env.GITHUB_OUTPUT) {
    fs.appendFileSync(process.env.GITHUB_OUTPUT, `${name}=${value}\n`, {
      encoding: "utf-8",
    });
  }
}

function writeSummary(reason) {
  if (process.env.GITHUB_STEP_SUMMARY) {
    fs.appendFileSync(
      process.env.GITHUB_STEP_SUMMARY,
      `CI priority route: ${reason}\n`,
      { encoding: "utf-8" },
    );
  }
}

function validTimestamp(value) {
  if (typeof value !== "string") {
    return false;
  }
  const timestamp = Date.parse(value);
  return Number.isFinite(timestamp) && Date.now() - timestamp <= MAX_RECORD_AGE_MILLISECONDS;
}

function parseRecord(text) {
  try {
    const record = JSON.parse(text);
    if (
      !record ||
      record.schema !== 1 ||
      !validTimestamp(record.generated_at) ||
      typeof record.radar_commit !== "string" ||
      !record.radar_commit ||
      !record.items ||
      Array.isArray(record.items) ||
      typeof record.items !== "object" ||
      !Object.hasOwn(BAND_ORDER, record.default)
    ) {
      return null;
    }
    for (const band of Object.values(record.items)) {
      if (!Object.hasOwn(BAND_ORDER, band)) {
        return null;
      }
    }
    return record;
  } catch {
    return null;
  }
}

function itemIds(text) {
  return [...new Set((text || "").match(ITEM_ID_PATTERN) || [])];
}

function eventItemIds(eventName, event) {
  if (eventName === "pull_request") {
    const pullRequest = event.pull_request || {};
    return itemIds(`${pullRequest.head?.ref || ""}\n${pullRequest.title || ""}`);
  }
  if (eventName === "push") {
    return itemIds(
      (event.commits || [])
        .map((commit) => commit.message || "")
        .join("\n"),
    );
  }
  return [];
}

function bestBand(record, ids) {
  const bands = ids.map((id) => record.items[id] || record.default);
  return bands.reduce(
    (best, band) => (BAND_ORDER[band] > BAND_ORDER[best] ? band : best),
    record.default,
  );
}

function readEvent() {
  if (!process.env.GITHUB_EVENT_PATH) {
    return null;
  }
  try {
    return JSON.parse(fs.readFileSync(process.env.GITHUB_EVENT_PATH, "utf-8"));
  } catch {
    return null;
  }
}

function route({ env = process.env, now = Date.now } = {}) {
  const record = parseRecord(env.INPUT_CI_PRIORITY_RECORD || "");
  if (!record) {
    return { band: DEFAULT_BAND, reason: "normal lane selected: priority record is missing or unreadable" };
  }
  const event = readEvent();
  if (!event) {
    return { band: DEFAULT_BAND, reason: "normal lane selected: event payload is unreadable" };
  }
  const ids = eventItemIds(env.GITHUB_EVENT_NAME || "", event);
  if (ids.length === 0) {
    return { band: DEFAULT_BAND, reason: "normal lane selected: run names no work item" };
  }
  const band = bestBand(record, ids);
  if (band !== HIGH_BAND) {
    return { band: DEFAULT_BAND, reason: "normal lane selected: run names no high-band work item" };
  }
  return { band, reason: `priority lane selected: high-band work item ${ids.find((id) => record.items[id] === HIGH_BAND)}` };
}

function main() {
  const result = route();
  writeOutput("band", result.band);
  writeSummary(result.reason);
}

if (require.main === module) {
  main();
}

module.exports = { bestBand, eventItemIds, parseRecord, route };
