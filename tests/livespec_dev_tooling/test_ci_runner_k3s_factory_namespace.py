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
_BOOT_CONVERGE = _PHASE2 / "reconstruct" / "converge-ci-stack.sh"
# The role that installs the boot tree onto the host; the boot converge can
# only apply what this role has already put there.
_ROLE_DEFAULTS = _REPO_ROOT / "ansible" / "roles" / "ci_converge_unit" / "defaults" / "main.yml"

# The objects the work-items' Definitions of Done name, as KINDS: the names are
# this repository's to choose, the kinds are not. The two cluster-scoped kinds
# arrived with the nodes read `livespec-dev-tooling-pvykv7` widened the
# credential by; everything else is `livespec-dev-tooling-f5e6vl`'s original
# seven.
_EXPECTED_KINDS = (
    "ClusterRole",
    "ClusterRoleBinding",
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
    # `patch` relabels a live sandbox pod (bd-ib-ad6dby).
    ("", "pods"): frozenset({"create", "get", "list", "watch", "delete", "patch"}),
    ("", "pods/log"): frozenset({"get"}),
    # `get` because a WebSocket exec upgrade is an HTTP GET (bd-ib-ad6dby).
    ("", "pods/exec"): frozenset({"create", "get"}),
}
_JOBS_RULE_KEY = ("batch", "jobs")
_CLUSTER_SCOPED_KINDS = frozenset({"ClusterRole", "ClusterRoleBinding"})
# The grants `livespec-dev-tooling-pvykv7` widened the launcher credential by,
# each the item's own wording, and each the WHOLE rule rather than a floor: the
# assertions below compare for EQUALITY, so an extra verb fails exactly as a
# missing one does.
#
# The nodes read is the only cluster-scoped grant, and it HAS to be one —
# `nodes` is a cluster-scoped resource, so a namespaced Role cannot name it at
# all. The plugin uses it to tell a NotReady node from a lost pod; without it
# every node-loss check answers 403.
_EXPECTED_CLUSTER_RULES: dict[tuple[str, str], frozenset[str]] = {
    ("", "nodes"): frozenset({"get", "list"}),
}
# In the namespaced Role: the per-pod egress policies that open holes in the
# `factory-egress` baseline, and the Events that tell pending-on-quota from
# pending-on-scheduling.
_EXPECTED_WIDENED_ROLE_VERBS: dict[tuple[str, str], frozenset[str]] = {
    ("networking.k8s.io", "networkpolicies"): frozenset({"create", "get", "list", "delete"}),
    ("", "events"): frozenset({"list", "watch"}),
}
# What the derivation note must NAME, so the widening carries its reason beside
# the manifest the way every other number in this directory does.
_WIDENING_DERIVATION_TERMS = (
    "nodes",
    "networkpolicies",
    "events",
    "pvykv7",
)
# The live node capacities the quota must be sized against, each as the plan's
# own research note spells it, plus the pod-allocatable figure hp is left with
# while the Docker sandbox slice runs. A quota derived without naming these is
# a number somebody picked.
_NODE_CAPACITY_FACTS = (
    "poweredge-xubuntu",
    "72 CPUs",
    "377 GB",
    "gmktec-xubuntu",
    "32 threads",
    "62 GB",
    "hp-xubuntu",
    "16 CPUs",
    "30 GB",
    "3 GiB",
)
# Where each egress target was READ, never recalled: the Fabro instance
# configuration on hp for the sandbox image and the telemetry receiver, and the
# committed beads pointer for the Dolt tenant.
_ENDPOINT_SOURCES = (
    "ansible/inventory/host_vars/hp-xubuntu.yml",
    "LIVESPEC_SANDBOX_OTEL_ENDPOINT",
    ".beads/config.yaml",
)
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


def _binding_subject(*, document: str) -> tuple[str, str, str]:
    """A binding's SINGLE subject as `(kind, name, namespace)`.

    Asserted to be single rather than searched for a match: a binding's power
    is the UNION of its subjects, so "the launcher is in there somewhere" is not
    the question — an extra subject is itself the widening, and a reader that
    looked for one entry would never see it.
    """
    subjects = re.findall(
        r"-\s*kind:\s*(?P<kind>\S+)\s*\n\s*name:\s*(?P<name>\S+)\s*\n\s*namespace:\s*(?P<ns>\S+)",
        document,
    )
    assert len(subjects) == 1, (
        f"the binding must carry exactly ONE subject; found {len(subjects)}, and a binding's "
        "grant is the union of all of them"
    )
    kind, name, namespace = subjects[0]
    return (kind, name, namespace)


def _gates_role_rules() -> dict[tuple[str, str], frozenset[str]]:
    """The gates Role's rules, read from the gates manifest itself."""
    roles = [
        _role_rules(document=document)
        for document in _documents(path=_GATES_RBAC)
        if _top_level(document=document, key="kind") == "Role"
    ]
    assert len(roles) == 1, (
        f"{_GATES_RBAC.name} must declare exactly ONE Role for the factory Role's batch-jobs "
        f"verbs to be compared against the real file rather than a restatement; found {len(roles)}"
    )
    return roles[0]


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


def test_the_factory_manifests_declare_exactly_the_nine_labelled_objects() -> None:
    assert _FACTORY_DIR.is_dir(), (
        f"{_FACTORY_DIR.relative_to(_REPO_ROOT)} does not exist, so the factory namespace is "
        "whatever somebody last typed at a cluster whose datastore is wiped at every boot"
    )
    declared = _objects()
    assert tuple(sorted(kind for kind, _, _ in declared)) == _EXPECTED_KINDS, (
        "the factory artifact directory must declare EXACTLY the objects the two Definitions of "
        f"Done name, one each; found {sorted(kind for kind, _, _ in declared)}"
    )
    by_kind = {kind: (name, document) for kind, name, document in declared}
    assert (
        by_kind["Namespace"][0] == _NAMESPACE_NAME
    ), f"the Namespace must be named {_NAMESPACE_NAME!r}, not {by_kind['Namespace'][0]!r}"
    for kind, name, document in declared:
        if kind == "Namespace" or kind in _CLUSTER_SCOPED_KINDS:
            # The Namespace is not in itself, and a cluster-scoped object is in
            # no namespace at all — a `namespace:` on either is silently
            # ignored by the API server, so requiring one would require a lie.
            continue
        metadata = _top_level_block(document=document, key="metadata")
        namespace = _at_indent(block=metadata, key="namespace", indent=2)
        assert namespace == _NAMESPACE_NAME, (
            f"{kind} {name!r} declares namespace {namespace!r}; every namespaced object must be "
            f"IN {_NAMESPACE_NAME!r}, or the apply lands it somewhere else"
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
    # What may be cluster-scoped is asserted in
    # `test_the_widened_launcher_grant_reads_nodes_through_one_cluster_role_and_nothing_else`
    # — the nodes READ and its binding, and nothing else.
    role_binding = by_kind["RoleBinding"]
    role_ref = _top_level_block(document=role_binding, key="roleRef")
    assert _at_indent(block=role_ref, key="kind", indent=2) == "Role", (
        "the RoleBinding's roleRef must name a Role; a RoleBinding to a ClusterRole grants that "
        "ClusterRole's rules in this namespace, which is the cluster-scoped grant this item "
        "forbids wearing a namespaced hat"
    )


def test_the_widened_launcher_grant_reads_nodes_through_one_cluster_role_and_nothing_else() -> None:
    """`livespec-dev-tooling-pvykv7`: the ONE cluster-scoped grant, read-only on nodes.

    The sandbox backend needs it to tell a NotReady NODE from a lost POD — two
    observations that look identical from inside the namespace, and without this
    read every node-loss check answers 403 instead. `nodes` is cluster-scoped,
    so a namespaced Role cannot name it; the narrowing is the VERB SET, asserted
    for equality so `patch`, `delete` or a wildcard fails here rather than on a
    cluster where the credential could then drain or evict a CI node.
    """
    declared = _objects()
    by_kind = {kind: (name, document) for kind, name, document in declared}
    cluster_kinds = sorted(kind for kind, _, _ in declared if kind in _CLUSTER_SCOPED_KINDS)
    assert cluster_kinds == ["ClusterRole", "ClusterRoleBinding"], (
        "the factory artifacts must declare EXACTLY one ClusterRole and one ClusterRoleBinding — "
        "the nodes read and the binding that delivers it — and no other cluster-scoped object; "
        f"found {cluster_kinds}"
    )
    cluster_role_name, cluster_role = by_kind["ClusterRole"]
    granted = _role_rules(document=cluster_role)
    assert granted == _EXPECTED_CLUSTER_RULES, (
        f"ClusterRole {cluster_role_name!r} grants "
        f"{ {key: sorted(verbs) for key, verbs in granted.items()} }; the only cluster-scoped "
        "power this credential may hold is "
        f"{ {key: sorted(verbs) for key, verbs in _EXPECTED_CLUSTER_RULES.items()} }"
    )
    binding_name, binding = by_kind["ClusterRoleBinding"]
    role_ref = _top_level_block(document=binding, key="roleRef")
    assert _at_indent(block=role_ref, key="kind", indent=2) == "ClusterRole"
    assert _at_indent(block=role_ref, key="name", indent=2) == cluster_role_name, (
        f"ClusterRoleBinding {binding_name!r} names a roleRef that is not the declared "
        f"ClusterRole {cluster_role_name!r}, so the nodes read is bound to something else — or to "
        "nothing, which fails as a 403 at the first node-loss check and nowhere else"
    )
    assert _binding_subject(document=binding) == (
        "ServiceAccount",
        by_kind["ServiceAccount"][0],
        _NAMESPACE_NAME,
    ), (
        f"ClusterRoleBinding {binding_name!r} must bind EXACTLY the declared ServiceAccount in "
        f"{_NAMESPACE_NAME!r}; a Group or an extra subject hands a cluster-wide node read to "
        "identities this item never authorized"
    )


def test_the_widened_launcher_role_adds_networkpolicies_and_events_in_the_factory_namespace() -> (
    None
):
    """`livespec-dev-tooling-pvykv7`: the two namespaced widenings, and still no Secrets.

    NetworkPolicies because a sandbox's egress is a per-pod policy punching a
    hole in the `factory-egress` baseline, and Events because `Pending` means
    two different things — out of quota, or unschedulable — that only the
    namespace's Events distinguish. `update` and `patch` are deliberately NOT
    granted on networkpolicies: RBAC cannot express "every NetworkPolicy except
    `factory-egress`", so withholding the in-place-modify verbs is what keeps
    the baseline out of the plugin's reach, and the boot converge re-applies it
    regardless. The derivation note is asserted to carry the reason, because a
    widening whose rationale lives only in a ledger comment is a grant the next
    reader cannot audit.
    """
    by_kind = {kind: document for kind, _, document in _objects()}
    role_rules = _role_rules(document=by_kind["Role"])
    for key, expected in _EXPECTED_WIDENED_ROLE_VERBS.items():
        granted = role_rules.get(key)
        assert granted == expected, (
            f"the factory Role grants {sorted(granted) if granted else None} on {key[1]!r} in "
            f"apiGroup {key[0]!r}; this widening is exactly {sorted(expected)}"
        )
    for scope in ("Role", "ClusterRole"):
        on_secrets = sorted(
            key for key in _role_rules(document=by_kind[scope]) if key[1].split("/")[0] == "secrets"
        )
        assert not on_secrets, (
            f"the factory {scope} grants {on_secrets} — nothing on secrets, ever, at either "
            "scope: the dispatcher projects a sandbox's credentials into it, so a grant here "
            "only widens what a leaked token reaches"
        )
    notes = sorted(_FACTORY_DIR.glob("*.md"))
    derivation = notes[0].read_text(encoding="utf-8")
    unrecorded = [term for term in _WIDENING_DERIVATION_TERMS if term not in derivation]
    assert not unrecorded, (
        f"{notes[0].name} does not record the widening: these terms are absent {unrecorded}. The "
        "manifest says WHAT the credential may now do; only the note can say why, and an "
        "unexplained grant is the one a later reader cannot safely narrow again"
    )


def test_the_boot_converge_applies_the_factory_directory_after_kueue_and_gates() -> None:
    body = _BOOT_CONVERGE.read_text(encoding="utf-8")
    # Resolved in BOTH layouts the way the gates step is: the installed tree
    # (/usr/local/lib/ci-runner-k3s, artifacts beside the script) and the repo
    # checkout (phase2/, artifacts one level up).
    assert '[ -d "${ARTIFACT_DIR}/factory" ]' in body, (
        "converge-ci-stack.sh must resolve FACTORY_DIR for the INSTALLED layout, the branch "
        "GATES_DIR already carries; without it a boot converge on the host finds nothing to apply"
    )
    assert '"${ARTIFACT_DIR}/../factory"' in body, (
        "converge-ci-stack.sh must resolve FACTORY_DIR for the REPO layout too, so one script "
        "works from the checkout and from the install location"
    )
    apply_at = body.find('kubectl apply -f "${FACTORY_DIR}"')
    assert apply_at != -1, (
        "converge-ci-stack.sh must apply the whole factory DIRECTORY — the namespace and its "
        "bounds, the identity and its token request, in filename order — or the objects are "
        "gone at the next boot of the tmpfs datastore"
    )
    step_log = re.search(r'(?m)^log "(?P<step>10e\.[^"]*)"$', body)
    assert step_log is not None, (
        "the factory apply must be a NUMBERED converge step (10e), so the boot journal names it "
        "like every other step rather than hiding it inside another one"
    )
    assert step_log.start() < apply_at, "step 10e's log line must precede its own apply"
    # Step 5's own first apply. The per-repo queues after it are reached by a
    # glob rather than by name, so this is the step's only stable anchor.
    kueue_at = body.find('kubectl apply -f "${KUEUE_DIR}/resource-flavor.yaml"')
    gates_at = body.find('kubectl apply -f "${GATES_DIR}/gates-rbac.yaml"')
    assert -1 < kueue_at < apply_at, (
        "the factory step must come after the Kueue step; a converge ordered before it would "
        "race the queues the rest of the pool is denominated in"
    )
    assert -1 < gates_at < apply_at, (
        "the factory step must come after the gates step, which is where everything namespaced "
        "and credential-shaped already lives"
    )


def test_the_ci_converge_unit_role_installs_the_factory_manifests() -> None:
    text = _ROLE_DEFAULTS.read_text(encoding="utf-8")
    sources = set(re.findall(r"^\s*- src:\s*(\S+)\s*$", text, re.MULTILINE))
    missing = [
        path.relative_to(_PHASE2).as_posix()
        for path in _manifests()
        if path.relative_to(_PHASE2).as_posix() not in sources
    ]
    assert not missing, (
        "the ci_converge_unit role does not install these factory manifests onto the host, so "
        "the boot converge's step 10e would find an absent directory and the namespace would be "
        f"lost at every reboot — silently, exactly as the ghcr mirror was on 2026-09-09: {missing}"
    )
    directories = set(re.findall(r"^\s*- (\S+)\s*$", text, re.MULTILINE))
    assert "factory" in directories, (
        "the role must create the installed `factory` directory in ci_converge_unit_directories; "
        "--check cannot see past a missing parent, so a drift read would pass and the apply fail"
    )


def _quota_hard_values(*, document: str) -> tuple[str, ...]:
    """Every value of the ResourceQuota's `hard:` map, as written."""
    hard = re.search(r"(?ms)^  hard:\n(?P<body>(?:^    \S.*\n?)+)", document)
    assert hard is not None, "the ResourceQuota declares no `hard:` map"
    return tuple(
        match.group(1).strip("\"'")
        for match in re.finditer(r"(?m)^    \S+:[ \t]*(\S+)[ \t]*$", hard.group("body"))
    )


def _egress_targets(*, document: str) -> tuple[str, ...]:
    """Every CIDR and port the NetworkPolicy's egress rules name."""
    cidrs = re.findall(r"(?m)^\s*(?:cidr:|- )(\d+\.\d+\.\d+\.\d+/\d+)\s*$", document)
    ports = re.findall(r"(?m)^\s*port:\s*(\S+)\s*$", document)
    return tuple(cidrs) + tuple(ports)


def test_the_quota_limits_and_egress_targets_are_derived_in_a_committed_note() -> None:
    notes = sorted(_FACTORY_DIR.glob("*.md"))
    assert len(notes) == 1, (
        "the factory artifact directory must carry exactly ONE committed derivation note beside "
        f"the manifests, the way ../kueue/DERIVATION.md sits beside the queues; found {notes}"
    )
    derivation = notes[0].read_text(encoding="utf-8")
    by_kind = {kind: document for kind, _, document in _objects()}
    undrilled = [
        value
        for value in _quota_hard_values(document=by_kind["ResourceQuota"])
        if value not in derivation
    ]
    assert not undrilled, (
        f"{notes[0].name} does not derive these ResourceQuota values: {undrilled}. The quota is "
        "the ONLY bound on what factory runs take from the CI pool on poweredge, so an "
        "underived number is the whole safety story resting on a guess"
    )
    unexplained = [
        target
        for target in _egress_targets(document=by_kind["NetworkPolicy"])
        if target not in derivation
    ]
    assert (
        not unexplained
    ), f"{notes[0].name} does not name these NetworkPolicy egress targets: {unexplained}"
    missing_capacities = [fact for fact in _NODE_CAPACITY_FACTS if fact not in derivation]
    assert not missing_capacities, (
        f"{notes[0].name} must size the quota against the LIVE node capacities and name them; "
        f"these are absent: {missing_capacities}"
    )
    missing_sources = [source for source in _ENDPOINT_SOURCES if source not in derivation]
    assert not missing_sources, (
        f"{notes[0].name} must name where each egress endpoint was READ — the brief requires the "
        "Fabro instance configuration on hp rather than a value recalled from memory; these "
        f"sources are absent: {missing_sources}"
    )
