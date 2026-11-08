---
topic: k3s-control-plane-emitter-sends
author: claude-opus-5-5
created_at: 2026-11-07T20:40:04Z
---

## Proposal: The control-plane emitter sends API-server request latency and 504 counts by verb and resource

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Extend §"Runner-pool workload and control-plane telemetry" so the control-plane emitter also sends the API server's request latency histogram and its count of HTTP 504 responses, each aggregated to `verb` and `resource`. The latency of a lease PUT can then be read apart from every other request, and a handler timeout appears in Honeycomb rather than only in the k3s journal.

### Motivation

The `ci-runner-scheduler` lost its leader lease twice on 2026-11-05, at 14:39:33Z and 20:45:11Z. In the second loss the API server on `poweredge-xubuntu` logged `http: Handler timeout` on the lease PUT at 20:44:27Z and 20:44:46Z. The emitter's data showed neither loss, because it reads only `/readyz`, `apiserver_storage_size_bytes` and `etcd_request_duration_seconds`. The cause was CPU queueing on the control-plane node, measured at 0.2 percent idle with no queue backlog, and the datastore paragraph's latency series does not separate a slow lease PUT from any other API-server request. Plan kubernetes-observability owns watching API-server latency and lease renewal at the coordinator's 2026-11-05 ask, and livespec-dev-tooling-f5qjzn carries the work. Its spec-change-tier judgement reported `unstated` against this section, and no proposal for its linked topic was filed at the time, so the pre-dispatch wall refuses it with `unratified-topic`. This proposal is that topic.

Measured against the live API server's `/metrics` on 2026-11-07: `apiserver_request_duration_seconds` carries `component`, `dry_run`, `group`, `le`, `resource`, `scope`, `subresource`, `verb` and `version`. Aggregated to `verb` and `resource` it yields 302 series of 24 buckets each from 9672 raw lines, so the series count stays bounded. A lease PUT reads as `verb=PUT`, `resource=leases`.

What is not yet observed: `apiserver_request_total` held no `code="504"` row at that read. That is not evidence the metric misses handler timeouts. The k3s journal holds 120 `Handler timeout` lines since 2026-11-01, all before the running process started at 2026-11-06T00:55:59Z and none after it, so the counter has had nothing to count. Whether a handler timeout increments the `code="504"` row has therefore not been seen on this server. The clause states the emitter's behaviour against whatever the API server reports, which a fixture can prove, and it does not require a natural 504 as proof. A counter with no events has no series at all, so the clause also states that the emitter sends nothing in that case rather than inventing a zero.

### Proposed Changes

In `SPECIFICATION/non-functional-requirements.md` §"Runner-pool workload and control-plane telemetry", insert this paragraph directly after the paragraph headed "Datastore health.":

**API server request latency and handler timeouts.** The control-plane emitter MUST send the API server's `apiserver_request_duration_seconds` histogram with its data points aggregated to the `verb` and `resource` attributes only, summing away `subresource`, `scope`, `group`, `version`, `component` and `dry_run`, so the latency of a `leases` PUT can be read apart from every other request and the series count stays bounded. The emitter MUST also send the API server's count of HTTP 504 responses as `apiserver_request_total` data points with `code` = `504`, aggregated to `verb` and `resource` in the same way. It MUST NOT send any other response code in that metric. When the API server reports no 504 response, the emitter MUST NOT send a data point for it, because a counter with no events has no series and an invented zero would claim a reading the server did not give. These series MUST be read from the same `/metrics` response, with the same read-only cluster identity, as the datastore series, and stamped `host.name` equal to the server node's name.

In `SPECIFICATION/scenarios.md`, insert these three scenarios directly after `## Scenario: an unready API server or a failing datastore fires its trigger`:

## Scenario: a lease PUT's latency is readable apart from every other API-server request

Given the control-plane emitter is converged on `poweredge-xubuntu`

When 15 minutes pass with the API server serving lease renewals

Then the `livespec` environment's metrics dataset MUST hold `apiserver_request_duration_seconds` rows with `verb` = `PUT`, `resource` = `leases` and `host.name` = `poweredge-xubuntu` within that window

And those rows MUST NOT carry a `subresource`, `scope`, `group`, `version`, `component` or `dry_run` attribute

## Scenario: API-server 504 responses are counted by verb and resource

Given the API server's `/metrics` reports `apiserver_request_total` rows with `code` = `504` for `verb` = `PUT`, `resource` = `leases` under two different `scope` values, beside rows with other codes

When the control-plane emitter runs

Then it MUST send one `apiserver_request_total` data point for `verb` = `PUT`, `resource` = `leases`, `code` = `504` whose value is the sum of those rows

And it MUST NOT send an `apiserver_request_total` data point for any other code

## Scenario: an API server with no 504 responses gets no invented zero

Given the API server's `/metrics` reports no `apiserver_request_total` row with `code` = `504`

When the control-plane emitter runs

Then it MUST NOT send any `apiserver_request_total` data point

The co-edit for these three headings belongs to the revise commit, not to this file: `tests/heading-coverage.json` gains one row for each, naming livespec-dev-tooling-f5qjzn as the owning work item, and `tests/heading-coverage-debt.json` is regenerated.
