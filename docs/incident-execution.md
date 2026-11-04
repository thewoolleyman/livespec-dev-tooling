# Incident execution context

The public `livespec_dev_tooling.incident_execution` API resolves a context
before a caller selects checks, reads cached evidence, or delegates work.
`incident_transport` carries that context across a process or credential-wrapper
boundary. These primitives do not authorize an incident, look up a ledger
record, verify a forge event, or enable incident execution in a repository.
The receiving caller must establish those facts through its trusted receipt
and event boundary before granting an exception.

<!-- EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-sh3vz3 -->

## Resolve before selecting work

Call `resolve_execution_context(environ=..., invocation=..., identity=...)`.
All arguments are keyword-only. It returns `IncidentResolution`: inspect
`is_successful`, then use `unwrap()` or `failure()`. A refusal has a stable
`code` and a diagnostic `detail`; it must terminate selection rather than
fall through to normal execution.

Use an `Invocation` constant supplied by the trusted caller:

- `ORDINARY` parses invocation-scoped incident flags.
- `NORMAL_MASTER` and `NORMAL_FACTORY_FOLLOW_UP` select normal mode before
  parsing inherited values, including malformed incident flags.

`EXPEDITED_INCIDENT_RESPONSE` selects repair;
`EXPEDITED_INCIDENT_RESPONSE_REVERT` takes precedence when both are true.
The shared parser accepts `1`, `true`, `yes`, and `on`, or the false values
unset, empty, `0`, `false`, `no`, and `off`, ignoring surrounding whitespace
and letter case. Other ordinary values produce a named refusal.

An incident requires an immutable `OperationIdentity` naming the incident item,
attempt, phase, repository, base SHA, head SHA, and operation. Repository syntax
is `owner/name`; SHAs are full lowercase hexadecimal object identifiers
(40 or 64 characters). Scalar identities must be nonblank, trimmed, and free
of control characters. Repair phases are `repair` or `expedited-repair`;
revert phases are `reverting` or `emergency-revert`. A revert additionally
requires `recorded_incident_merge_sha` from the authorized incident receipt.
Syntax validation does not prove that the named merge exists or belongs to
the incident; the caller that supplies the receipt must verify that relation.

`validate_execution_context(context=...)` revalidates a context constructed by
a caller. A normal result has no incident identity. Do not construct an
incident context directly from an untrusted environment and treat successful
syntax validation as authorization.

## Carry context explicitly

`encode_execution_context(context=...)` returns a `Result` containing canonical
JSON or an `IncidentConfigurationRefusal`. Its versioned schema contains
`schema_version`, `mode`, `invocation`, and the complete `identity` (or null
for normal execution). `CONTEXT_ENV` names the transport variable,
`LIVESPEC_INCIDENT_CONTEXT`.

At the receiving boundary, independently resolve a trusted context from the
authenticated event and authorized receipt. Then call
`decode_execution_context(payload=..., trusted_context=...)`. The decoder
checks the complete schema and compares the payload to that trusted context.
It returns the trusted context, never an authority inferred from the payload.
Trusted master and factory-follow-up contexts retain normal precedence even
when inherited transport is malformed. Never derive `trusted_context` from
the same payload being checked.

`child_environment(context=..., environ=...)` returns a `Result` containing
the explicit environment for a child performing the same operation. It removes
old incident flags and transport before projecting the validated context.
`normal_child_environment(environ=...)` always removes both flags and the
context carrier. Neither function mutates the supplied mapping or the parent's
process environment. Use normal cleanup deliberately when spawning ordinary
work from an incident-aware process.

Credential wrappers may filter environment variables. Project the generated
values through the wrapper's supported inner boundary, for example an explicit
`env` argument vector after the wrapper, and measure propagation with a
nonsecret probe. Do not persist incident variables in host configuration,
repository settings, images, or shell startup files.

Omitting a key from an environment overlay does not delete an inherited key.
Use the returned mapping as the complete `env=` of a subprocess. When using an
inner `env` command after a wrapper that preserves caller variables, first
unset `EXPEDITED_INCIDENT_RESPONSE`, `EXPEDITED_INCIDENT_RESPONSE_REVERT`, and
`LIVESPEC_INCIDENT_CONTEXT` with `env -u` for each name, then apply the generated
assignments. Normal projection supplies no replacement incident assignments.
The installed wrapper's propagation behavior must be measured; it must not be
assumed to scrub those variables.

## Caller obligations

Normal mode continues the caller's existing policy. Incident callers pass the
resolved context to their selectors and record deferred work under the same
operation identity. The resolver does not run gates, mint green tokens, create
normal TDD evidence, or satisfy deferred factory proof. Hook, CI, recovery,
and lifecycle integrations must preserve those separate obligations.

These modules expose Python APIs. Importing a module with `python -m` is not
a gate selector or an incident authorization command. Use an actual supported
caller integration before enabling incident execution.
