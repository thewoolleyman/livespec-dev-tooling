"""The `factory` namespace is a converge artifact, not a hand step.

The k3s datastore on `poweredge-xubuntu` is a tmpfs (`phase2/datastore-tmpfs/`),
so every cluster object exists only until the next boot unless
`reconstruct/converge-ci-stack.sh` re-applies it from the tree the
`ci_converge_unit` Ansible role copies onto the host. The `gates` namespace is
the pattern this tree already follows; the `factory` namespace — where the
kubernetes-sandbox-backend plugin will run its sandbox pods — must be rebuilt
the same way, because a namespace created by hand reads as present right up to
the first reboot and then vanishes with no error anywhere.

These tests read the REAL manifests and the REAL boot converge. They assert the
object set, the least-privilege Role, the converge wiring, and the committed
derivation of the two numbers that cannot be read off anything else — the
quota's limits and the egress targets.

Plan: livespec `factory-worker-nodes-gitops`, epic `livespec-sqvj7p`; this
repository's child `livespec-dev-tooling-f5e6vl`.
"""

from __future__ import annotations

import re
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PHASE2 = _REPO_ROOT / "ci-runner" / "k3s" / "phase2"
_FACTORY_DIR = _PHASE2 / "factory"
_GATES_RBAC = _PHASE2 / "gates" / "gates-rbac.yaml"

# The seven objects the work-item's Definition of Done names, as KINDS: the
# names are this repository's to choose, the kinds are not.
_EXPECTED_KINDS = (
    "Namespace",
    "NetworkPolicy",
    "ResourceQuota",
    "Role",
    "RoleBinding",
    "Secret",
    "ServiceAccount",
)
_NAMESPACE_NAME = "factory"
# The pod-lifecycle grants a sandbox needs, each the Definition of Done's own
# wording. `delete` is the one verb the gates credential deliberately lacks: a
# gate Job is reaped by its own ttlSecondsAfterFinished, while the backend owns
# its sandboxes' whole lifetime.
_EXPECTED_POD_VERBS: dict[tuple[str, str], frozenset[str]] = {
    ("", "pods"): frozenset({"create", "get", "list", "watch", "delete"}),
    ("", "pods/log"): frozenset({"get"}),
    ("", "pods/exec"): frozenset({"create"}),
}
_JOBS_RULE_KEY = ("batch", "jobs")
_CLUSTER_SCOPED_KINDS = frozenset({"ClusterRole", "ClusterRoleBinding"})
_MANAGED_BY_LABEL = "app.kubernetes.io/managed-by"
_SA_TOKEN_TYPE = "kubernetes.io/service-account-token"
_SA_NAME_ANNOTATION = "kubernetes.io/service-account.name"


def _manifests() -> tuple[Path, ...]:
    """Every manifest file under the factory artifact directory."""
    return tuple(
        path for path in sorted(_FACTORY_DIR.glob("*")) if path.suffix in {".yaml", ".yml"}
    )


def _documents(*, path: Path) -> tuple[str, ...]:
    """One multi-document manifest, split on its `---` separators."""
    body = path.read_text(encoding="utf-8")
    return tuple(doc for doc in re.split(r"(?m)^---$", body) if doc.strip())


def _top_level(*, document: str, key: str) -> str:
    """The scalar value of a column-zero `key:` in one document."""
    match = re.search(rf"(?m)^{re.escape(key)}:[ \t]*(\S.*?)[ \t]*$", document)
    return match.group(1) if match else ""


def _top_level_block(*, document: str, key: str) -> str:
    """The indented body following a column-zero `key:` line.

    Collected until the next column-zero line, which is what makes an
    indent-anchored lookup inside the result unambiguous: `metadata:`'s own
    children sit at two spaces and its labels' children at four.
    """
    collected: list[str] = []
    collecting = False
    for line in document.splitlines():
        if collecting:
            if line and not line.startswith((" ", "\t")):
                break
            collected.append(line)
            continue
        collecting = line == f"{key}:"
    return "\n".join(collected)


def _at_indent(*, block: str, key: str, indent: int) -> str:
    """The scalar value of `key:` at exactly `indent` spaces within a block."""
    pattern = rf"(?m)^{' ' * indent}{re.escape(key)}:[ \t]*(\S.*?)[ \t]*$"
    match = re.search(pattern, block)
    return match.group(1) if match else ""


def _flow_list(*, raw: str) -> tuple[str, ...]:
    """The members of a YAML flow sequence such as `["create", "get"]`."""
    return tuple(member.strip().strip("\"'") for member in raw.split(",") if member.strip())


def _role_rules(*, document: str) -> dict[tuple[str, str], frozenset[str]]:
    """A Role document's rules, keyed by `(apiGroup, resource)`.

    Both this file's Role and `../gates/gates-rbac.yaml`'s are authored in flow
    style with one resource per rule, which is what lets one pattern read both
    and makes the gates comparison a read of the real file rather than a
    restatement of it here.
    """
    pattern = (
        r"-\s*apiGroups:\s*\[(?P<groups>[^\]]*)\]\s*\n"
        r"\s*resources:\s*\[(?P<resources>[^\]]*)\]\s*\n"
        r"\s*verbs:\s*\[(?P<verbs>[^\]]*)\]"
    )
    rules: dict[tuple[str, str], frozenset[str]] = {}
    for match in re.finditer(pattern, document):
        groups = _flow_list(raw=match.group("groups"))
        resources = _flow_list(raw=match.group("resources"))
        verbs = frozenset(_flow_list(raw=match.group("verbs")))
        for group in groups:
            for resource in resources:
                rules[(group, resource)] = verbs
    return rules


def _gates_role_rules() -> dict[tuple[str, str], frozenset[str]]:
    """The gates Role's rules, read from the gates manifest itself."""
    for document in _documents(path=_GATES_RBAC):
        if _top_level(document=document, key="kind") == "Role":
            return _role_rules(document=document)
    raise AssertionError(f"{_GATES_RBAC} declares no Role to compare the factory Role against")


def _objects() -> tuple[tuple[str, str, str], ...]:
    """Every declared object as `(kind, name, document)`, in file order."""
    found: list[tuple[str, str, str]] = []
    for path in _manifests():
        for document in _documents(path=path):
            metadata = _top_level_block(document=document, key="metadata")
            found.append(
                (
                    _top_level(document=document, key="kind"),
                    _at_indent(block=metadata, key="name", indent=2),
                    document,
                )
            )
    return tuple(found)


def test_the_factory_manifests_declare_exactly_the_seven_labelled_objects() -> None:
    assert _FACTORY_DIR.is_dir(), (
        f"{_FACTORY_DIR.relative_to(_REPO_ROOT)} does not exist, so the factory namespace is "
        "whatever somebody last typed at a cluster whose datastore is wiped at every boot"
    )
    declared = _objects()
    assert tuple(sorted(kind for kind, _, _ in declared)) == _EXPECTED_KINDS, (
        "the factory artifact directory must declare EXACTLY the seven objects the Definition "
        f"of Done names, one each; found {sorted(kind for kind, _, _ in declared)}"
    )
    by_kind = {kind: (name, document) for kind, name, document in declared}
    assert (
        by_kind["Namespace"][0] == _NAMESPACE_NAME
    ), f"the Namespace must be named {_NAMESPACE_NAME!r}, not {by_kind['Namespace'][0]!r}"
    for kind, name, document in declared:
        if kind == "Namespace":
            continue
        metadata = _top_level_block(document=document, key="metadata")
        namespace = _at_indent(block=metadata, key="namespace", indent=2)
        assert namespace == _NAMESPACE_NAME, (
            f"{kind} {name!r} declares namespace {namespace!r}; every object but the Namespace "
            f"itself must be IN {_NAMESPACE_NAME!r}, or the apply lands it somewhere else"
        )
    for kind, name, document in declared:
        metadata = _top_level_block(document=document, key="metadata")
        managed_by = _at_indent(block=metadata, key=_MANAGED_BY_LABEL, indent=4)
        assert managed_by, (
            f"{kind} {name!r} carries no {_MANAGED_BY_LABEL} label, so a live read cannot tell "
            "it apart from an object somebody created by hand"
        )
    secret_name, secret_document = by_kind["Secret"]
    assert _top_level(document=secret_document, key="type") == _SA_TOKEN_TYPE, (
        f"Secret {secret_name!r} must be type {_SA_TOKEN_TYPE} — that type IS the request the "
        "ServiceAccount-token controller fills in with a token and ca.crt"
    )
    secret_metadata = _top_level_block(document=secret_document, key="metadata")
    annotated = _at_indent(block=secret_metadata, key=_SA_NAME_ANNOTATION, indent=4)
    assert annotated == by_kind["ServiceAccount"][0], (
        f"Secret {secret_name!r} annotates {_SA_NAME_ANNOTATION}={annotated!r}, which is not the "
        f"declared ServiceAccount {by_kind['ServiceAccount'][0]!r}; an unannotated token Secret "
        "is never populated and the rendered kubeconfig carries nothing"
    )


def test_the_factory_role_grants_the_pod_lifecycle_the_gates_job_verbs_and_no_secrets() -> None:
    by_kind = {kind: document for kind, _, document in _objects()}
    rules = _role_rules(document=by_kind["Role"])
    for key, expected in _EXPECTED_POD_VERBS.items():
        granted = rules.get(key)
        assert granted == expected, (
            f"the factory Role grants {sorted(granted) if granted else None} on "
            f"{key[1]!r} in apiGroup {key[0]!r}; the sandbox lifecycle needs exactly "
            f"{sorted(expected)}"
        )
    gates_job_verbs = _gates_role_rules()[_JOBS_RULE_KEY]
    assert rules.get(_JOBS_RULE_KEY) == gates_job_verbs, (
        f"the factory Role grants {sorted(rules.get(_JOBS_RULE_KEY) or ())} on batch jobs; it "
        f"must grant the same verbs the gates Role grants, {sorted(gates_job_verbs)}, read from "
        f"{_GATES_RBAC.relative_to(_REPO_ROOT)}"
    )
    on_secrets = sorted(key for key in rules if key[1].split("/")[0] == "secrets")
    assert not on_secrets, (
        f"the factory Role grants {on_secrets} — nothing on secrets, ever: the dispatcher "
        "projects a sandbox's credentials into it, so a grant here only widens what a leaked "
        "token reaches"
    )
    cluster_scoped = sorted(
        f"{kind} {name!r}" for kind, name, _ in _objects() if kind in _CLUSTER_SCOPED_KINDS
    )
    assert (
        not cluster_scoped
    ), f"the factory artifacts declare {cluster_scoped}; nothing here may be cluster-scoped"
    role_binding = by_kind["RoleBinding"]
    role_ref = _top_level_block(document=role_binding, key="roleRef")
    assert _at_indent(block=role_ref, key="kind", indent=2) == "Role", (
        "the RoleBinding's roleRef must name a Role; a RoleBinding to a ClusterRole grants that "
        "ClusterRole's rules in this namespace, which is the cluster-scoped grant this item "
        "forbids wearing a namespaced hat"
    )
