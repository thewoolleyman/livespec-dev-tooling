# Protected CI invocation identity

`POST /ci/identity` authenticates one supported GitHub Actions invocation. It
accepts the actual OIDC JWT as `Authorization: Bearer <JWT>` and exactly the six
`ObserverArmQuery` body fields: `repository`, `arm_id`, `pr_number`, `base_sha`,
`head_sha` and `receipt_digest`. Query and control secrets cannot authenticate
this route. The exact retained arm must remain unbound and unrevoked before and
after verification. Crypto and network reads run outside the repository effect
lock so already owed recovery can continue.

A successful response has exactly `schema: 1`, `status: "authenticated"`,
`identity`, `policy_sha256`, and four false fields: `authorizes_current_effects`,
`ci_admission`, `authorizes_merge`, `normal_factory_proof`. The identity contains
the signed repository and stable repository/owner IDs, run ID/attempt, check ID,
actual separately resolved job ID, check suite, caller and reusable workflow
ref/SHA, token times, PR ref and synthetic merge SHA, and exact arm/query fields.
No token, signature, secret or session capability is returned. Responses use
`Cache-Control: no-store`; existing current/admitted consumers reject this shape.
Authentication establishes neither command/artifact execution nor complete CI,
current canonical mode, a session, merge permission or factory proof.

## Optional installation policy

`controller.json` is unchanged. The independently protected release manifest may
add one optional member:

```json
"ci_identity_policy": {
  "path": "/etc/livespec-incident/ci-identity.json",
  "sha256": "<SHA256 of exact policy bytes>"
}
```

The policy file must be private, protected against candidate writes, and contain
exactly the following schema (values below illustrate structure only):

```json
{
  "schema": 1,
  "audience": "urn:independently-provisioned-controller",
  "subject": "repo:owner/repository:pull_request",
  "repository": "owner/repository",
  "repository_id": 123,
  "repository_owner_id": 456,
  "approved_reusable_workflows": [
    {
      "ref": "owner/provider/.github/workflows/protected.yml@ffffffffffffffffffffffffffffffffffffffff",
      "sha": "ffffffffffffffffffffffffffffffffffffffff"
    }
  ],
  "issuer_keys": [{"kid": "<independently pinned issuer key ID>", "n": "<RSA JWK modulus>", "e": "AQAB"}],
  "crypto": {"path": "/usr/bin/openssl", "sha256": "<approved executable SHA256>"}
}
```

These example IDs, revision and fixture keys approve no production workflow.
The mutable `reusable-check-matrix` is not implicitly trusted. Provisioning an
approved isolated immutable reusable workflow and obtaining issuer keys through
an independent trust path remain operator obligations. No request or environment
selects policy, audience, keys, issuer endpoint, workflow revision or executable.

The issuer is fixed to `https://token.actions.githubusercontent.com`, with RS256
and JWT headers. Optional bounded `x5t` metadata is accepted and ignored for key
selection. Token-selected key material, key URLs and critical extensions refuse.
Unknown or rotated `kid` values refuse until normal independent policy
reprovisioning updates its digest in the protected manifest and reloads the
controller. There is no request-triggered discovery or key refresh.

The policy and approved executable are rehashed and their lexical/resolved path
ownership and permissions rechecked at invocation and before returning. OpenSSL
runs with fixed arguments, private temporary inputs, a minimal environment,
configuration overrides disabled, output discarded and a timeout. Python only
encodes the pinned public key as DER. The optional executable is deliberately
absent from mandatory manifest `files`: missing, invalid or tampered policy or
crypto makes identity unavailable while preserving existing controller recovery,
query, control and callback routes. Unknown manifest members still refuse startup.

## Supported forge correlation

Only `pull_request` with `refs/pull/<exact PR>/merge` is supported. Let M be the
signed synthetic merge SHA, H the retained arm head, and B its base. The current
PR must be open/unmerged with exact B/H and test `merge_commit_sha=M`; an
independent Git commit read must show exact ordered parents `[B,H]` for M.
Current REST run, job and check `head_sha` must equal H. Provider shapes using M
there are unsupported rather than guessed.

Independently credentialed budgeted forge reads require both the latest run and
the signed attempt to match, including current attempt, repository IDs, event,
workflow path and suite. Complete bounded attempt-job pagination resolves exactly
one canonical `check_run_url` for the signed check ID. Job and check IDs need not
be equal. The independently fetched check must match the suite, head, ID and
GitHub Actions producer. Empty `pull_requests` arrays are supported; they are
not used to infer association. Final latest-attempt, PR, token lifetime, policy,
crypto and arm checks refuse stale or unavailable observations.

This implementation performs no workflow edit, service activation, secret
projection, account creation, policy provisioning or branch-protection change.
Controlled signed fixtures and process/HTTP checks exercise local behavior;
they are not production token, release/adoption or plan completion evidence.
