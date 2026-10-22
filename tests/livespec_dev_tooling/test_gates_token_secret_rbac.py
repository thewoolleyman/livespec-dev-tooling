"""The gate credential may CREATE the per-run token Secret, and do nothing else with it.

`SPECIFICATION/contracts.md` says, of the delegated pre-push gate and its
cross-repository siblings, that the installation token a private sibling is
cloned with "MUST NOT be stored as a long-lived Secret or under any new standing
credential name". Work-item livespec-dev-tooling-7kvh2d.

WHY A PYTEST BESIDE THE SHELL SUITE. `ci-runner/k3s/phase2/gates/`'s convention
is a `*-exit-tests.sh` beside each artifact, and `gates-credential-exit-tests.sh`
is where this scope is asserted end to end against the real renderer. But
NOTHING IN `just check` RUNS THOSE SUITES — they are driven by the boot converge
and by hand — so a Role that drifted would be caught only on the node. This file
is the gated half: it asserts the manifest's scope directly, and asserts that
the shell suite still asserts it, so the shell arms cannot be quietly dropped
without a red tree here.

NOTHING HERE REACHES A CLUSTER. Every assertion is a read of committed source:
the RBAC manifest, the exit-test suite beside it, and the minter the pushing
host runs.
"""

from __future__ import annotations

import re
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GATES = _REPO_ROOT / "ci-runner" / "k3s" / "phase2" / "gates"
_RBAC = _GATES / "gates-rbac.yaml"
_EXIT_TESTS = _GATES / "gates-credential-exit-tests.sh"
_MINTER = _GATES / "mint-private-sibling-token.sh"

# Where the fleet's GitHub App credentials are already named, as the control for
# "no NEW standing credential name": the minter must reach for the two the fleet
# wiring already projects and invent none of its own.
_EXISTING_CREDENTIAL_SOURCE = _REPO_ROOT / "livespec_dev_tooling" / "fleet" / "_reconcile.py"
_APP_CREDENTIAL_NAMES = ("GITHUB_APP_ID", "GITHUB_PRIVATE_KEY")

# Every verb that would turn the one write this design needs into something
# else. `get`/`list`/`watch` would let one gate run read another's token;
# `delete` is unnecessary because garbage collection removes an owned Secret;
# `update`/`patch` have no caller because the Secret is per run.
_FORBIDDEN_SECRETS_VERBS = (
    "delete",
    "deletecollection",
    "get",
    "list",
    "patch",
    "update",
    "watch",
)

# A YAML rule's own lines, from its `- apiGroups:` to the next one or the end of
# the `rules:` block. Sliced by the `- ` marker rather than by a line count so a
# reordered or reformatted rule is still read whole.
_RULE = re.compile(r"^  - apiGroups:.*?(?=^  - apiGroups:|^\S|\Z)", re.MULTILINE | re.DOTALL)


def _rules() -> list[str]:
    """Every rule in the gates Role, as text."""
    manifest = _RBAC.read_text(encoding="utf-8")
    role = manifest[manifest.index("\nkind: Role\n") :]
    role = role[: role.index("\n---\n")]
    found = _RULE.findall(role)
    assert found, f"{_RBAC.name} declares a Role with no readable rules"
    return found


def _declared_yaml() -> str:
    """The manifest with comment lines stripped.

    The header explains the App token at length, and a prose mention is the
    opposite of a credential in source — so every "is it in the manifest"
    assertion reads the DECLARED yaml, never the commentary about it.
    """
    return "\n".join(
        line
        for line in _RBAC.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    )


def test_the_gate_submitter_may_create_secrets_and_do_nothing_else_with_them() -> None:
    """One verb, on one resource, in one namespaced Role.

    The grant exists so the private-sibling installation token can reach ONE
    gate Job without entering the rendered manifest, which the API server stores
    and hands back to any reader. `create` is the whole of it: the Secret is
    owner-referenced to its Job, so garbage collection — not this credential —
    removes it, and the client writes a token without ever reading one back.
    """
    secrets_rules = [rule for rule in _rules() if '"secrets"' in rule]

    assert len(secrets_rules) == 1, (
        f"{_RBAC.name} must carry exactly one secrets rule so there is one place to read "
        f"the scope off; found {len(secrets_rules)}"
    )
    rule = secrets_rules[0]
    assert 'verbs: ["create"]' in rule, (
        f"the gates Role must grant `create` and only `create` on secrets — the gate client "
        f"creates one per-run token Secret per delegated push and never reads one; got: {rule}"
    )
    for verb in _FORBIDDEN_SECRETS_VERBS:
        assert f'"{verb}"' not in rule, (
            f"the gates Role grants `{verb}` on secrets. A read verb would let any gate run "
            f"read every other run's installation token, and a delete verb is unnecessary: "
            f"the Secret's ownerReference makes garbage collection remove it"
        )
    assert '"*"' not in rule


def test_the_rbac_manifest_declares_no_secret_holding_a_github_credential() -> None:
    """The per-run token Secret is created at submit time and exists in no source.

    THE CONVERGE IS WHY THIS MATTERS. `reconstruct/converge-ci-stack.sh` applies
    this manifest on every boot, so a Secret declared here persists for as long
    as the node does — which is exactly the long-lived credential the contract
    forbids. The one Secret this file has always carried is the ServiceAccount
    token that renders the kubeconfig, and it holds no GitHub credential.
    """
    declared = _declared_yaml()

    assert declared.count("\nkind: Secret\n") == 1, (
        f"{_RBAC.name} must declare exactly one Secret — the ServiceAccount token — so the "
        f"private-sibling installation token has nowhere standing to live"
    )
    assert "type: kubernetes.io/service-account-token" in declared
    assert "github" not in declared.lower(), (
        "the declared RBAC yaml names GitHub, so it may be carrying a credential the "
        "contract requires to exist only for one gate run"
    )
    for field in ("data:", "stringData:"):
        assert not any(line.strip().startswith(field) for line in declared.splitlines()), (
            f"the declared RBAC yaml carries a `{field}` block, which is where Secret "
            f"material lives; the ServiceAccount token's bytes are populated by the "
            f"token controller and are deliberately absent from source"
        )


def test_the_committed_exit_tests_still_assert_that_exact_secrets_scope() -> None:
    """The shell suite is the node-side gate, and it must not quietly stop checking.

    Nothing in `just check` runs `gates-credential-exit-tests.sh`, so its arms
    are the one assertion an edit could remove without reddening a tree. This
    test reads them: the suite must compare the Role's verb sequence against an
    expectation that ENDS in the bare `create`, and must assert the secrets rule
    is create-only on its own.
    """
    suite = _EXIT_TESTS.read_text(encoding="utf-8")

    assert "want_verbs=" in suite and 'verbs:["create"]\'' in suite, (
        f"{_EXIT_TESTS.name} must compare the Role's verbs against a full expected sequence "
        f"ending in the secrets rule's bare `create`; without it an added verb passes"
    )
    assert 'resources:["secrets"]' in suite, (
        f"{_EXIT_TESTS.name} must name secrets in its expected resource sequence, so an "
        f"added rule fails there rather than only here"
    )
    assert "create-only" in suite, (
        f"{_EXIT_TESTS.name} must carry the arm that pairs the secrets resource with its "
        f"verb list; matching two sequences separately cannot catch a mispaired rule"
    )
    assert "kind: Secret" in suite, (
        f"{_EXIT_TESTS.name} must assert how many Secret documents the manifest declares — "
        f"the `create` grant is only safe while no standing Secret exists beside it"
    )


def test_the_minter_uses_the_app_credential_names_the_fleet_already_projects() -> None:
    """No NEW standing credential name — the two that exist, and nothing else.

    The minter runs under `with-livespec-env.sh`, which projects the fleet
    GitHub App's id and private key from 1Password under names this repository
    ALREADY consumes elsewhere. Those names are read off that existing consumer
    rather than restated, so a rename reaches this assertion.

    The negative half is the claim: the minter reads no other credential-shaped
    environment variable. A new name would be a new standing credential — one
    more thing to provision, rotate and leak — which is precisely what the
    contract's "no new standing credential name" forbids.
    """
    minter = _MINTER.read_text(encoding="utf-8")
    existing = _EXISTING_CREDENTIAL_SOURCE.read_text(encoding="utf-8")

    for name in _APP_CREDENTIAL_NAMES:
        assert name in existing, (
            f"{name} is no longer named in {_EXISTING_CREDENTIAL_SOURCE.name}, so it is not "
            f"an already-projected fleet credential and the minter must not assume it is"
        )
        assert name in minter, f"{_MINTER.name} must read the projected {name}"
    referenced = set(re.findall(r"\$\{?([A-Z][A-Z0-9_]{3,})\}?", minter))
    credential_shaped = {
        name
        for name in referenced
        if any(word in name for word in ("TOKEN", "KEY", "SECRET", "PASSWORD", "APP_ID"))
    }
    assert credential_shaped == set(_APP_CREDENTIAL_NAMES), (
        f"{_MINTER.name} reaches for credential-shaped environment variables beyond the two "
        f"the fleet already projects: {sorted(credential_shaped - set(_APP_CREDENTIAL_NAMES))}. "
        f"Each would be a NEW standing credential name to provision and rotate"
    )
