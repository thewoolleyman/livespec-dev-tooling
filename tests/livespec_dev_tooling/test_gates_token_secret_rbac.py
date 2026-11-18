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
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

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

_EXPECTED_SUBMITTER_RULES = [
    {
        "apiGroups": ["batch"],
        "resources": ["jobs"],
        "verbs": ["create", "delete", "get", "list", "watch"],
    },
    {
        "apiGroups": [""],
        "resources": ["pods"],
        "verbs": ["create", "get", "list", "watch"],
    },
    {
        "apiGroups": [""],
        "resources": ["pods/log"],
        "verbs": ["get"],
    },
    {
        "apiGroups": [""],
        "resources": ["secrets"],
        "verbs": ["create"],
    },
]

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


def _documents(path: Path = _RBAC) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    for document in yaml.safe_load_all(path.read_text(encoding="utf-8")):
        if document is None:
            continue
        assert isinstance(document, dict), f"{path.name} contains a non-mapping YAML document"
        documents.append(document)
    return documents


def _named_document(documents: list[dict[str, Any]], *, kind: str, name: str) -> dict[str, Any]:
    matches = [
        document
        for document in documents
        if document.get("kind") == kind
        and isinstance(document.get("metadata"), dict)
        and document["metadata"].get("name") == name
    ]
    assert len(matches) == 1, f"expected exactly one {kind} named {name}; found {len(matches)}"
    return matches[0]


def _role(path: Path, name: str) -> dict[str, Any]:
    return _named_document(_documents(path), kind="Role", name=name)


def _role_binding(path: Path, name: str) -> dict[str, Any]:
    return _named_document(_documents(path), kind="RoleBinding", name=name)


def _assert_factory_role_scope(path: Path = _RBAC) -> None:
    vps_role = _role(path, "gate-submitter")
    factory_role = _role(path, "gate-submitter-factory")

    assert vps_role["rules"] == _EXPECTED_SUBMITTER_RULES
    assert factory_role["rules"] == vps_role["rules"] == _EXPECTED_SUBMITTER_RULES


def _assert_role_binding_isolation(path: Path = _RBAC) -> None:
    vps_binding = _role_binding(path, "gate-submitter")
    factory_binding = _role_binding(path, "gate-submitter-factory")

    assert vps_binding["roleRef"] == {
        "apiGroup": "rbac.authorization.k8s.io",
        "kind": "Role",
        "name": "gate-submitter",
    }
    assert vps_binding["subjects"] == [
        {"kind": "ServiceAccount", "name": "gate-submitter", "namespace": "gates"}
    ]
    assert factory_binding["roleRef"] == {
        "apiGroup": "rbac.authorization.k8s.io",
        "kind": "Role",
        "name": "gate-submitter-factory",
    }
    assert factory_binding["subjects"] == [
        {
            "kind": "ServiceAccount",
            "name": "gate-submitter-factory",
            "namespace": "gates",
        }
    ]


def _mutated_manifest(tmp_path: Path, mutation: Callable[[list[dict[str, Any]]], None]) -> Path:
    documents = _documents()
    mutation(documents)
    path = tmp_path / _RBAC.name
    path.write_text(yaml.safe_dump_all(documents, sort_keys=False), encoding="utf-8")
    return path


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


def test_the_gate_submitter_may_delete_jobs_and_nothing_else() -> None:
    """Job deletion reaps an abandoned suspended gate and its owned Secret.

    A Job that has not started cannot reach its TTL terminal state, so the
    submitter needs the narrow namespaced power to delete that Job. The owned
    per-run token Secret is then garbage-collected with it; no Secret delete
    grant is necessary or allowed.
    """
    rules = _rules()
    jobs_rules = [rule for rule in rules if '"jobs"' in rule]

    assert len(jobs_rules) == 1
    assert 'verbs: ["create", "delete", "get", "list", "watch"]' in jobs_rules[0]
    for rule in rules:
        if rule != jobs_rules[0]:
            assert '"delete"' not in rule
    declared = _declared_yaml()
    assert "kind: ClusterRole" not in declared
    assert "kind: ClusterRoleBinding" not in declared

    suite = _EXIT_TESTS.read_text(encoding="utf-8")
    assert 'verbs:["create","delete","get","list","watch"]' in suite
    assert "only jobs may be deleted" in suite


def test_the_factory_role_has_the_exact_gate_submitter_scope() -> None:
    """The factory receives the same narrow scope as the VPS submitter."""
    _assert_factory_role_scope()


def test_factory_and_vps_bindings_keep_their_roles_and_service_accounts_separate() -> None:
    """Each consumer must remain bound only to its own Role and ServiceAccount."""
    _assert_role_binding_isolation()


def test_factory_role_scope_rejects_a_missing_secrets_rule(tmp_path: Path) -> None:
    """A factory credential without its per-run Secret write cannot submit a gate."""

    def delete_secrets_rule(documents: list[dict[str, Any]]) -> None:
        factory_role = _named_document(documents, kind="Role", name="gate-submitter-factory")
        factory_role["rules"] = [
            rule for rule in factory_role["rules"] if rule["resources"] != ["secrets"]
        ]

    mutated = _mutated_manifest(tmp_path, delete_secrets_rule)

    with pytest.raises(AssertionError):
        _assert_factory_role_scope(mutated)


def test_factory_role_scope_rejects_a_widened_verb(tmp_path: Path) -> None:
    """A factory credential must not gain a Secret read verb."""

    def add_secret_read(documents: list[dict[str, Any]]) -> None:
        factory_role = _named_document(documents, kind="Role", name="gate-submitter-factory")
        secrets_rule = next(
            rule for rule in factory_role["rules"] if rule["resources"] == ["secrets"]
        )
        secrets_rule["verbs"].append("get")

    mutated = _mutated_manifest(tmp_path, add_secret_read)

    with pytest.raises(AssertionError):
        _assert_factory_role_scope(mutated)


def test_factory_binding_rejects_the_vps_service_account(tmp_path: Path) -> None:
    """The VPS identity must never receive the factory Role."""

    def bind_vps_service_account(documents: list[dict[str, Any]]) -> None:
        factory_binding = _named_document(
            documents, kind="RoleBinding", name="gate-submitter-factory"
        )
        factory_binding["subjects"][0]["name"] = "gate-submitter"

    mutated = _mutated_manifest(tmp_path, bind_vps_service_account)

    with pytest.raises(AssertionError):
        _assert_role_binding_isolation(mutated)


def test_the_rbac_manifest_declares_no_secret_holding_a_github_credential() -> None:
    """The per-run token Secret is created at submit time and exists in no source.

    THE CONVERGE IS WHY THIS MATTERS. `reconstruct/converge-ci-stack.sh` applies
    this manifest on every boot, so a Secret declared here persists for as long
    as the node does — which is exactly the long-lived credential the contract
    forbids. The two declared Secrets are the independently revocable
    ServiceAccount tokens that render the VPS and factory kubeconfigs; neither
    holds a GitHub credential.
    """
    declared = _declared_yaml()

    assert declared.count("\nkind: Secret\n") == 2, (
        f"{_RBAC.name} must declare exactly two Secrets — the VPS and factory "
        f"ServiceAccount tokens — so the private-sibling installation token has nowhere "
        f"standing to live"
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
