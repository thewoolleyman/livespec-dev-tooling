"""hp-xubuntu's coexistence budget: the kubelet reservations, and the record beside them.

WHAT THIS FILE GRADES (work-item livespec-dev-tooling-7we6po, Definition of Done
assertion 4). hp-xubuntu runs a k3s agent, the Docker sandbox slice every Fabro
sandbox container joins, two Fabro server instances and the page cache, all on
one 16-CPU / 30 GB machine. The kubelet must hold capacity back from the pods it
would otherwise schedule, or the first node-pressure eviction takes a running
factory dispatch with it. Two things are therefore required: the reservations
themselves on this node's k3s agent configuration, and the BUDGET — the
arithmetic, the resulting pod-allocatable figures and the condition under which
they are revisited — recorded beside the values it derives from.

WHERE THE RECORD LIVES, AND WHY THERE. Beside the slice limits, in
`ansible/roles/docker_sandbox_slice/HOST_VARS.md`. That file already carries
`MemoryHigh 22G`, `MemoryMax 24G` and `CPUQuota 1400%`, their derivation, and an
Expiry condition that IS this budget's revisit condition — the Kubernetes
sandbox backend cutover steps the slice budget down, and the reservations move
with it. The slice ceiling is the dominant term in every line of the arithmetic,
so recording the budget anywhere else would be recording it away from the numbers
it is computed from. hp's profile points at it rather than restating it, because
two copies of one budget is two budgets.

WHERE THE VALUES LIVE. In hp's own committed phase0 profile, as `KUBELET_ARGS` —
the per-node key, because a reservation is measured against the OTHER workloads
on that one machine and so belongs to no other node. The `k3s_config` role
renders them into a per-node drop-in under `/etc/rancher/k3s/config.yaml.d/`,
which k3s merges over the shared `config.yaml` on every start.

THE APPEND FORM IS LOAD-BEARING AND IS ASSERTED AS SUCH. The fleet's shared
`config.agent.yaml` already declares `kubelet-arg: ["max-pods=200"]`, a per-node
pod bound with its own derivation. A drop-in declaring the same key would
REPLACE that list; k3s's own multi-file merge appends only when the key carries a
`+` suffix. So the template must emit `kubelet-arg+`, and
`test_the_rendered_drop_in_appends_*` fails if it ever emits the plain key — a
regression that would silently drop `max-pods` on exactly the node whose kubelet
is most constrained.

THE RENDERER IS A SUBSTITUTION RENDERER, AND ONE TEST KEEPS IT HONEST. Neither
Ansible nor Jinja is importable in this suite (`ansible-lint` and
`ansible-playbook` are resolved through `uvx` against their own interpreter — see
the justfile), so `_render` substitutes `{{ name }}` from a mapping and nothing
else, exactly as the sibling `test_ci_runner_k3s_agent_node_taint` does, and
`test_the_templates_stay_inside_the_vocabulary_this_test_can_render` fails the
moment a template grows a filter, a conditional or a loop.
"""

from __future__ import annotations

import json
import re
from itertools import pairwise
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ANSIBLE = _REPO_ROOT / "ansible"
_K3S_CONFIG = _ANSIBLE / "roles" / "k3s_config"
_K3S_TASKS = _K3S_CONFIG / "tasks" / "main.yml"
_K3S_DEFAULTS = _K3S_CONFIG / "defaults" / "main.yml"
_KUBELET_TEMPLATE = _K3S_CONFIG / "templates" / "kubelet-args.yaml.j2"
_MOUNT_TEMPLATE = _K3S_CONFIG / "templates" / "data-dir-mount.conf.j2"
_SHARED_AGENT_CONFIG = (
    _REPO_ROOT / "ci-runner" / "k3s" / "phase2" / "k3s-config" / "config.agent.yaml"
)
_HP_PROFILE = _REPO_ROOT / "ci-runner" / "k3s" / "phase0-bare-metal" / "profiles" / "hp-xubuntu.env"
_SLICE_DEFAULTS = _ANSIBLE / "roles" / "docker_sandbox_slice" / "defaults" / "main.yml"
_BUDGET_RECORD = _ANSIBLE / "roles" / "docker_sandbox_slice" / "HOST_VARS.md"

# The heading the record lives under, and the figures the Definition of Done
# names. Stated because the item states them: the reservations, the eviction
# thresholds, the slice limits and hp's resulting pod-allocatable CPU and memory.
_BUDGET_HEADING = "## Coexistence with the k3s agent"
_EXPECTED_RESERVED = (
    "system-reserved=cpu=14500m,memory=25088Mi",
    "kube-reserved=cpu=1000m,memory=1024Mi",
    "eviction-hard=memory.available<512Mi,nodefs.available<10%,imagefs.available<10%",
)
# The arithmetic's own answers, which the record must state so a reader is not
# left to do the subtraction: 16000m - 14500m - 1000m, and (about) 29Gi -
# 25088Mi - 1024Mi - 512Mi.
_ALLOCATABLE_CPU = "500m"
_ALLOCATABLE_MEMORY = "3Gi"

_PLACEHOLDER = re.compile(r"\{\{ (?P<name>[a-z0-9_]+) \}\}")
_ROLE_DEFAULT = re.compile(r"^(?P<name>k3s_config_[a-z_]+): (?P<value>\S.*)$", re.MULTILINE)
_SLICE_DEFAULT = re.compile(
    r"^(?P<name>docker_sandbox_slice_[a-z_]+): (?P<value>\S.*)$", re.MULTILINE
)
_KUBELET_ARG_LIST = re.compile(r"^kubelet-arg(?P<append>\+?): (?P<records>\[.*\])$", re.MULTILINE)
_PROFILE_LINE = re.compile(r"^KUBELET_ARGS=(?P<value>.*)$", re.MULTILINE)


def _unquote(*, value: str) -> str:
    """One committed scalar, with the quoting the YAML author chose removed."""
    stripped = value.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in "\"'":
        return stripped[1:-1]
    return stripped


def _declared(*, pattern: re.Pattern[str], source: Path) -> dict[str, str]:
    """Every scalar one `defaults/main.yml` declares."""
    declared = {
        match["name"]: _unquote(value=match["value"])
        for match in pattern.finditer(source.read_text(encoding="utf-8"))
    }
    assert declared, (
        f"{source.relative_to(_REPO_ROOT)} must declare its variables as scalars: a value "
        f"spelled inline in a task is one no host can redirect and no test can read"
    )
    return declared


def _scalar(*, declared: dict[str, str], name: str, source: Path, why: str) -> str:
    """One declared scalar, refusing by NAME a role that does not declare it.

    Asked through a helper rather than by subscript so an absent variable is an
    ASSERTION about the role — "this converge has no such knob" — rather than a
    `KeyError` whose message names only the key.
    """
    assert name in declared, (
        f"{source.relative_to(_REPO_ROOT)} must declare `{name}`: {why}. It declares "
        f"{sorted(declared)}"
    )
    return declared[name]


def _template(*, path: Path, why: str) -> str:
    """One committed template, as Jinja receives it."""
    assert path.is_file(), f"the role must carry {path.relative_to(_REPO_ROOT)}: {why}"
    return path.read_text(encoding="utf-8")


def _render(*, body: str, variables: dict[str, str]) -> str:
    """`body` with every `{{ name }}` substituted, refusing a name it was not given."""
    unknown = sorted(set(_PLACEHOLDER.findall(body)) - set(variables))
    assert not unknown, (
        f"the template names {unknown}, which the role's facts do not carry; Ansible would "
        f"refuse the render on the first unset name"
    )
    return _PLACEHOLDER.sub(lambda match: variables[match["name"]], body)


def _profile_kubelet_args(*, text: str) -> str:
    """A profile's declared `KUBELET_ARGS`, as the role's `regex_findall` reads it."""
    found = _PROFILE_LINE.findall(text)
    return found[0] if found else ""


def _render_kubelet_drop_in(*, kubelet_args: str) -> str:
    """The committed kubelet-args drop-in, rendered for a profile declaring `kubelet_args`.

    Ansible's `to_json` is `json.dumps` with its own defaults, and Jinja's
    `.split()` with no argument splits on runs of whitespace and drops empties
    exactly as Python's does — so the records are the profile's space-separated
    list and nothing else.
    """
    body = _template(
        path=_KUBELET_TEMPLATE,
        why=(
            "a node's kubelet reservations are a per-node fact, and a fact rendered from the "
            "profile is the only one a reboot cannot make stale"
        ),
    )
    named = sorted(set(_PLACEHOLDER.findall(body)))
    assert len(named) == 1, (
        f"the template must substitute exactly ONE fact — the profile's records; it names "
        f"{named}. A second name is a second thing this renderer would have to guess"
    )
    return _render(body=body, variables={named[0]: json.dumps(kubelet_args.split())})


# --- the control on the renderer -------------------------------------------


def test_the_templates_stay_inside_the_vocabulary_this_test_can_render() -> None:
    """No filter, no conditional, no loop — a template expression is a bare variable."""
    for path, why in (
        (_KUBELET_TEMPLATE, "the kubelet reservations"),
        (_MOUNT_TEMPLATE, "the data directory's mount ordering"),
    ):
        body = _template(path=path, why=f"it renders {why} from the node's profile")
        assert "{%" not in body and "{#" not in body, (
            f"{path.name} renders by substituting `{{{{ name }}}}` and nothing else, because "
            f"neither Ansible nor Jinja is importable in this suite. A template carrying a "
            f"statement would be rendered WRONG here and right on the host, which is worse "
            f"than not rendering it at all;\nbody={body!r}"
        )
        unsupported = sorted(
            expression
            for expression in re.findall(r"\{\{[^}]*\}\}", body)
            if not _PLACEHOLDER.fullmatch(expression)
        )
        assert not unsupported, (
            f"every expression in {path.name} must be a bare variable for the renderer above "
            f"to be faithful; unsupported={unsupported}"
        )


# --- the reservations, on the node's k3s agent configuration ----------------


def test_hp_declares_the_reservations_the_coexistence_budget_derives() -> None:
    """The three records, in hp's own profile, because they belong to no other node."""
    declared = _profile_kubelet_args(text=_HP_PROFILE.read_text(encoding="utf-8"))
    assert declared.split() == list(_EXPECTED_RESERVED), (
        f"hp's profile must declare exactly the three records the budget derives — the two "
        f"reservations and the eviction thresholds — as KUBELET_ARGS. They are per-node "
        f"because each is measured against the OTHER workloads on this one machine;\n"
        f"declared={declared!r}"
    )


def test_the_rendered_drop_in_appends_to_the_fleets_shared_kubelet_arg_list() -> None:
    """The `+` suffix, and what it protects: `max-pods=200` on the fleet's shared config.

    The shared `config.agent.yaml` every agent receives declares `kubelet-arg`
    with its own derivation. A drop-in declaring the plain key REPLACES that
    list; k3s appends only when the key carries `+`. Dropping `max-pods` on the
    node whose kubelet is most constrained is exactly the regression this
    asserts away.
    """
    shared = _SHARED_AGENT_CONFIG.read_text(encoding="utf-8")
    assert "kubelet-arg:" in shared and "max-pods=200" in shared, (
        "the fleet's shared agent config must still declare `kubelet-arg` with "
        "`max-pods=200`; this assertion is the premise the `+` suffix below exists for"
    )
    rendered = _render_kubelet_drop_in(kubelet_args=" ".join(_EXPECTED_RESERVED))
    match = _KUBELET_ARG_LIST.search(rendered)
    assert match is not None, (
        f"the rendered drop-in must declare `kubelet-arg+: [...]` on one line — the form k3s "
        f"merges over /etc/rancher/k3s/config.yaml and the only one this test can read;\n"
        f"rendered={rendered!r}"
    )
    assert match["append"] == "+", (
        f"the key must be `kubelet-arg+`, not `kubelet-arg`: without the suffix k3s REPLACES "
        f"the shared list and this node silently loses `max-pods=200`;\nrendered={rendered!r}"
    )
    assert json.loads(match["records"]) == list(
        _EXPECTED_RESERVED
    ), f"and the records must be exactly the profile's, in its order;\nrendered={rendered!r}"


def test_a_profile_declaring_no_kubelet_args_renders_no_drop_in_at_all() -> None:
    """The control arm: poweredge and gmktec must be untouched by this mechanism.

    Both declare an empty `KUBELET_ARGS`, and a drop-in carrying an EMPTY
    `kubelet-arg+` list would be a file that says nothing and a converge that
    reports a change on a node with no second workload to reserve against. So
    the render is GATED on the key being non-empty, not merely rendered empty —
    which is the opposite of the node-taint drop-in beside it, where an empty
    list positively states "this node is open".
    """
    body = _task_whose_body_names(needle="k3s_config_kubelet_args_drop_in")
    assert (
        "k3s_config_kubelet_args | length > 0" in body
    ), f"the render must be gated on a non-empty KUBELET_ARGS;\nbody={body!r}"
    for profile in ("poweredge-xubuntu", "gmktec-xubuntu"):
        text = (_HP_PROFILE.parent / f"{profile}.env").read_text(encoding="utf-8")
        assert _profile_kubelet_args(text=text) == "", (
            f"{profile} must declare an empty KUBELET_ARGS: it runs the pool's CI work and "
            f"nothing else, so there is no second workload for the kubelet to hold capacity "
            f"back from"
        )


def _task_whose_body_names(*, needle: str) -> str:
    """The one `k3s_config` task whose body names `needle`."""
    text = _K3S_TASKS.read_text(encoding="utf-8")
    openings = [match.start() for match in re.finditer(r"^- name: ", text, re.MULTILINE)]
    assert openings, (
        f"{_K3S_TASKS.name} must declare its tasks as column-zero `- name:` entries; this "
        f"reader cannot see a task it cannot find, and an unseen task is a converge nothing "
        f"here checks"
    )
    matching = [
        text[start:stop]
        for start, stop in pairwise([*openings, len(text)])
        if needle in text[start:stop]
    ]
    assert len(matching) == 1, (
        f"{_K3S_TASKS.name} must carry exactly one task naming {needle!r}; found "
        f"{len(matching)}. This test reads the role's own converge out of it rather than "
        f"restating it, so a second one is a second answer"
    )
    return matching[0]


def test_the_role_renders_both_per_node_drop_ins_only_on_an_agent() -> None:
    """The wiring, and the mount ordering that makes the moved data directory safe."""
    defaults = _declared(pattern=_ROLE_DEFAULT, source=_K3S_DEFAULTS)
    drop_in = _scalar(
        declared=defaults,
        name="k3s_config_kubelet_args_drop_in",
        source=_K3S_DEFAULTS,
        why="it is the per-node file this node's kubelet reservations are rendered into",
    )
    assert drop_in.startswith("/etc/rancher/k3s/config.yaml.d/"), (
        f"the per-node reservations must be rendered into k3s's drop-in directory, which k3s "
        f"merges over /etc/rancher/k3s/config.yaml; got {drop_in!r}. They may NOT be written "
        f"into the committed config.agent.yaml, which every agent receives"
    )
    body = _task_whose_body_names(needle="k3s_config_kubelet_args_drop_in")
    assert "ansible.builtin.template" in body and _KUBELET_TEMPLATE.name in body, (
        f"the drop-in must be RENDERED by the template module from {_KUBELET_TEMPLATE.name} — "
        f"that is what makes the apply converge it and `just ansible-drift` show it;\n"
        f"body={body!r}"
    )
    assert "k3s_config_cluster_role == 'agent'" in body, (
        f"only an agent takes these: a server's kubelet arguments are the fleet's shared "
        f"config.yaml;\nbody={body!r}"
    )

    # THE HAZARD THE MOUNT DROP-IN EXISTS FOR. hp's NODE_DATA_DIR puts k3s's data
    # directory on the sandbox-stores volume. k3s starting before that volume is
    # mounted would create the directory on the ROOT filesystem, and the mount
    # would then HIDE it — the same shape as the 2026-09-07 incident in which a
    # freshly formatted tier was laid over gmktec's running containerd store.
    mount_unit_dir = _scalar(
        declared=defaults,
        name="k3s_config_agent_unit_drop_in_dir",
        source=_K3S_DEFAULTS,
        why="it is where the agent unit's mount-ordering drop-in is installed",
    )
    assert mount_unit_dir == "/etc/systemd/system/k3s-agent.service.d", (
        f"the mount-ordering drop-in belongs under the AGENT unit's drop-in directory — the "
        f"unit an agent actually runs; got {mount_unit_dir!r}"
    )
    mount_body = _task_whose_body_names(needle="k3s_config_data_dir_drop_in")
    assert "k3s_config_node_data_dir | length > 0" in mount_body, (
        f"and it is rendered only for a node whose profile names a data directory — a node "
        f"on k3s's default needs no ordering it does not already have;\nbody={mount_body!r}"
    )
    rendered = _render(
        body=_template(path=_MOUNT_TEMPLATE, why="it orders the agent after its data volume"),
        variables={"k3s_config_node_data_dir": "/srv/sandbox-storage/k3s"},
    )
    assert "RequiresMountsFor=/srv/sandbox-storage/k3s" in rendered, (
        f"the drop-in must declare `RequiresMountsFor=` on the data directory, which is what "
        f"makes k3s starting before the volume is mounted impossible rather than unlikely;\n"
        f"rendered={rendered!r}"
    )


# --- the record, beside the values it derives from -------------------------


def test_the_coexistence_budget_is_recorded_beside_the_slice_limits_it_derives_from() -> None:
    """The arithmetic, the resulting allocatable figures, and the revisit condition.

    Every number is asserted against the file that OWNS it rather than against a
    literal here: the slice limits come out of the `docker_sandbox_slice`
    defaults, the reservations out of hp's profile. A record that quoted a slice
    ceiling the role no longer declares would be a budget computed from a number
    that is not there any more, which is the failure mode of writing the
    arithmetic down at all.
    """
    record = _BUDGET_RECORD.read_text(encoding="utf-8")
    assert _BUDGET_HEADING in record, (
        f"{_BUDGET_RECORD.relative_to(_REPO_ROOT)} must carry a `{_BUDGET_HEADING}` section: "
        f"the slice limits are the dominant term in every line of hp's kubelet budget, so "
        f"the budget belongs beside them and not in a file of its own"
    )
    section = record.split(_BUDGET_HEADING, 1)[1].split("\n## ", 1)[0]

    slice_defaults = _declared(pattern=_SLICE_DEFAULT, source=_SLICE_DEFAULTS)
    for name in (
        "docker_sandbox_slice_memory_high",
        "docker_sandbox_slice_memory_max",
        "docker_sandbox_slice_cpu_quota",
    ):
        limit = _scalar(
            declared=slice_defaults,
            name=name,
            source=_SLICE_DEFAULTS,
            why="it is a term in hp's kubelet reservation budget",
        )
        assert limit in section, (
            f"the budget must state the slice limit `{name}` ({limit}) it is computed from, "
            f"so a reader can check the subtraction without leaving the file"
        )
    for record_line in _EXPECTED_RESERVED:
        assert record_line in section, (
            f"the budget must state the reservation {record_line!r} verbatim, so the record "
            f"and hp's profile cannot disagree about what the kubelet holds back"
        )
    for figure in (_ALLOCATABLE_CPU, _ALLOCATABLE_MEMORY):
        assert figure in section, (
            f"the budget must state hp's resulting pod-allocatable figure {figure!r}: the "
            f"Definition of Done asks for the OUTCOME and not only the inputs, and a reader "
            f"left to subtract four numbers will not"
        )
    assert "revisit" in section.lower(), (
        f"and the condition under which the budget is revisited, which is the one part a "
        f"stale record cannot tell you it is missing;\nsection={section!r}"
    )
    assert "hp-xubuntu" in section, (
        "the budget is hp-xubuntu's, measured against hp-xubuntu's other workloads; naming "
        "the host is what stops the next factory host inheriting it unexamined"
    )
