"""ARC listener pods run only on always-on nodes (work-item livespec-dev-tooling-crvvxt).

THE DEFECT. On 2026-11-12 `gamingpc-xubuntu` was powered off for a RAM upgrade.
Eight ARC AutoscalingListener pods were on it and sat Terminating with no
replacement for about 45 minutes. A scale set with no listener takes no jobs.

THE RULE, AND ITS FIVE PARTS. Each is asserted here from the committed files.

1. Every runner scale set values file gives its listener pod a placement that
   admits only nodes carrying `ci-runner.io/always-on=true`. A values file that
   lacks it fails here, named.
2. The label is a fact of a node's committed phase0 profile (`ALWAYS_ON_NODE`),
   and the three routes that carry it spell it identically: the join-time
   install command, the `node_labels` Ansible role, and the boot converge.
   `gamingpc-xubuntu` and every homelab container worker do not carry it.
3. The boot converge re-asserts it, because the control plane's datastore is a
   tmpfs and a re-registered node carries only what its kubelet started with.
   It runs before the ARC controller, since every listener selects on the label.
4. A read-only read-back lists each scale set's listener pod with its node and
   exits non-zero when one is on a node without the label.

5. Each install route (the boot converge and the first-install script) installs
   no scale set when no node carries the label or when that cannot be read.

The shell scripts are run for real, against a stand-in `kubectl` (and `helm`) on
a scratch PATH. Nothing here contacts a cluster.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ANSIBLE = _REPO_ROOT / "ansible"
_K3S = _REPO_ROOT / "ci-runner" / "k3s"
_PHASE2 = _K3S / "phase2"
_ARC = _PHASE2 / "arc"
_PROFILES = _K3S / "phase0-bare-metal" / "profiles"
_PARSER = _K3S / "phase0-bare-metal" / "profile.sh"
_PROVISION = _K3S / "provision-k3s.sh"
_BOOT_CONVERGE = _PHASE2 / "reconstruct" / "converge-ci-stack.sh"
_LABEL_CONVERGE = _PHASE2 / "reconstruct" / "converge-always-on-node-labels.sh"
_READ_BACK = _ARC / "read-listener-placement.sh"
_ROLE_DEFAULTS = _ANSIBLE / "roles" / "node_labels" / "defaults" / "main.yml"
_ROLE_TASKS = _ANSIBLE / "roles" / "node_labels" / "tasks" / "main.yml"
_CONVERGE_UNIT_DEFAULTS = _ANSIBLE / "roles" / "ci_converge_unit" / "defaults" / "main.yml"
_HOMELAB_WORKER = _REPO_ROOT / "homelab-worker"

_LABEL_KEY = "ci-runner.io/always-on"
_LABEL_VALUE = "true"
_LABEL = f"{_LABEL_KEY}={_LABEL_VALUE}"
_PROFILE_KEY = "ALWAYS_ON_NODE"

# The nodes nobody powers off at will, and the one its owner does. Stated, not
# derived: the Definition of Done names them, and a profile edit that moves a
# node across this line is a decision this file should make somebody restate.
_ALWAYS_ON_NODES = frozenset({"poweredge-xubuntu", "gmktec-xubuntu", "hp-xubuntu"})
_NOT_ALWAYS_ON_NODES = frozenset({"gamingpc-xubuntu"})

# Every scale set values file: the fleet's sets, the template a new set is
# copied from (so a new set is born with the placement), each worker set, and
# the phase-1 file the first-install script still applies before the converge
# supersedes it.
_VALUES = sorted(
    [
        *_ARC.glob("values-*.yaml"),
        *(_ARC / "worker").glob("values-*.yaml"),
        *(_K3S / "arc").glob("values-*.yaml"),
    ]
)


# --- 1. the values files ----------------------------------------------------


def _mapping(*, value: Any) -> dict[str, Any]:
    """A YAML mapping, or `{}` for an absent or empty one."""
    return dict(value) if value else {}


def _sequence(*, value: Any) -> list[Any]:
    """A YAML sequence, or `[]` for an absent or empty one."""
    return list(value) if value else []


def _term_requires_the_label(*, term: dict[str, Any]) -> bool:
    """Whether one node-selector term admits only nodes carrying the label."""
    expressions = _sequence(value=term.get("matchExpressions"))
    return any(
        expression.get("key") == _LABEL_KEY
        and expression.get("operator") == "In"
        and expression.get("values") == [_LABEL_VALUE]
        for expression in expressions
    )


def _listener_placement_defect(*, values: dict[str, Any]) -> str:
    """Why `values` does not keep its listener on always-on nodes, or `""`.

    Either form the Definition of Done allows is accepted: a `nodeSelector`
    entry, or a required node affinity whose EVERY term requires the label.
    Terms are ORed by the scheduler, so one term without the label admits any
    node and the affinity as a whole restricts nothing.
    """
    if "listenerTemplate" not in values:
        return "it declares no `listenerTemplate`"
    spec = _mapping(value=_mapping(value=values["listenerTemplate"]).get("spec"))
    if _mapping(value=spec.get("nodeSelector")).get(_LABEL_KEY) == _LABEL_VALUE:
        return ""
    node_affinity = _mapping(value=_mapping(value=spec.get("affinity")).get("nodeAffinity"))
    required = _mapping(value=node_affinity.get("requiredDuringSchedulingIgnoredDuringExecution"))
    terms = _sequence(value=required.get("nodeSelectorTerms"))
    if terms and all(_term_requires_the_label(term=term) for term in terms):
        return ""
    return (
        f"its `listenerTemplate.spec` has neither `nodeSelector: {{{_LABEL_KEY}: "
        f'"{_LABEL_VALUE}"}}` nor a required nodeAffinity whose every term requires it'
    )


def test_the_values_file_set_is_not_empty_and_includes_the_template_and_a_worker() -> None:
    """The enumeration below must not pass over an empty or partial set."""
    names = {path.relative_to(_K3S).as_posix() for path in _VALUES}
    assert "phase2/arc/values-EXAMPLE-repo.yaml" in names
    assert any(name.startswith("phase2/arc/worker/") for name in names)
    assert any(name.startswith("arc/") for name in names)
    assert len(names) > 2


@pytest.mark.parametrize("path", _VALUES, ids=lambda p: p.relative_to(_K3S).as_posix())
def test_every_scale_set_values_file_keeps_its_listener_on_always_on_nodes(*, path: Path) -> None:
    """The check-suite refusal: a values file without the placement fails, named."""
    values: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    defect = _listener_placement_defect(values=values)
    assert not defect, (
        f"{path.relative_to(_REPO_ROOT)}: {defect}. Every ARC runner scale set's listener pod "
        f"must be placed only on a node carrying {_LABEL} — a listener on a node that is "
        "powered off at will leaves its scale set taking no jobs (livespec-dev-tooling-crvvxt)"
    )
    containers = _sequence(value=values["listenerTemplate"]["spec"].get("containers"))
    assert [container.get("name") for container in containers] == ["listener"], (
        f"{path.relative_to(_REPO_ROOT)}: `listenerTemplate.spec.containers` must be the one "
        "`- name: listener` entry, the same shape in every values file: a pod template with no "
        "containers is not a valid one, and the name is the chart's own listener container"
    )
    assert "tolerations" not in values["listenerTemplate"]["spec"], (
        f"{path.relative_to(_REPO_ROOT)}: the listener must tolerate nothing, so a tainted "
        "worker can never host it"
    )


def test_the_placement_reader_refuses_each_shape_that_does_not_restrict_the_listener() -> None:
    """The control arm: the reader above fails on the shapes it must fail on."""
    selector = {"nodeSelector": {_LABEL_KEY: _LABEL_VALUE}}
    labelled_term = {
        "matchExpressions": [{"key": _LABEL_KEY, "operator": "In", "values": [_LABEL_VALUE]}]
    }
    other_term = {
        "matchExpressions": [{"key": "kubernetes.io/arch", "operator": "In", "values": ["amd64"]}]
    }

    def affinity(*terms: dict[str, Any]) -> dict[str, Any]:
        required = {"nodeSelectorTerms": list(terms)}
        return {
            "affinity": {
                "nodeAffinity": {"requiredDuringSchedulingIgnoredDuringExecution": required}
            }
        }

    assert not _listener_placement_defect(values={"listenerTemplate": {"spec": selector}})
    assert not _listener_placement_defect(
        values={"listenerTemplate": {"spec": affinity(labelled_term)}}
    )
    for refused in (
        {},
        {"template": {"spec": selector}},
        {"listenerTemplate": {"spec": {"nodeSelector": {"kubernetes.io/arch": "amd64"}}}},
        {"listenerTemplate": {"spec": {"nodeSelector": {_LABEL_KEY: "false"}}}},
        {"listenerTemplate": {"spec": affinity(other_term)}},
        {"listenerTemplate": {"spec": affinity(labelled_term, other_term)}},
    ):
        assert _listener_placement_defect(values=refused), refused


# --- 2. the profiles and the three carriers ---------------------------------


def _declared(*, profile: Path) -> str:
    """A profile's `ALWAYS_ON_NODE`, read as the roles read it; `""` when absent."""
    found = re.findall(rf"^{_PROFILE_KEY}=(.*)$", profile.read_text(encoding="utf-8"), re.MULTILINE)
    return found[0].strip() if found else ""


def test_exactly_the_always_on_nodes_declare_the_label_in_their_profiles() -> None:
    """poweredge, gmktec and hp declare it; gamingpc does not."""
    declared = {
        profile.stem for profile in _PROFILES.glob("*.env") if _declared(profile=profile) == "true"
    }
    assert declared == _ALWAYS_ON_NODES, (
        f"exactly {sorted(_ALWAYS_ON_NODES)} must declare {_PROFILE_KEY}=true; "
        f"declared={sorted(declared)}"
    )
    for node in sorted(_NOT_ALWAYS_ON_NODES):
        value = _declared(profile=_PROFILES / f"{node}.env")
        assert value in {
            "",
            "false",
        }, f"{node} is powered off at will and must not declare {_PROFILE_KEY}=true; got {value!r}"


def test_no_homelab_container_worker_file_names_the_label() -> None:
    """A homelab worker has no phase0 profile and joins by its own script: never labelled."""
    naming = sorted(
        path.relative_to(_REPO_ROOT).as_posix()
        for path in _HOMELAB_WORKER.rglob("*")
        if path.is_file() and _LABEL_KEY.encode() in path.read_bytes()
    )
    assert not naming, (
        f"no file under homelab-worker/ may name {_LABEL_KEY}: a container worker on a laptop "
        f"is powered off at will, so nothing there may set the label; found in {naming}"
    )


def _load_profile(*, tmp_path: Path, always_on_line: str) -> subprocess.CompletedProcess[str]:
    """Run the ONE profile parser over poweredge's profile with its key line replaced."""
    text = (_PROFILES / "poweredge-xubuntu.env").read_text(encoding="utf-8")
    assert f"\n{_PROFILE_KEY}=true\n" in text
    profile = tmp_path / "scratch.env"
    _ = profile.write_text(
        text.replace(f"\n{_PROFILE_KEY}=true\n", f"\n{always_on_line}"), encoding="utf-8"
    )
    script = (
        'die() { printf "FATAL: %s\\n" "$*" >&2; exit 1; }\n'
        f'source "{_PARSER}"\n'
        f'profile_load "{profile}"\n'
        f'printf "%s\\n" "${{CFG[{_PROFILE_KEY}]}}"\n'
    )
    return subprocess.run(
        ["bash", "-c", script], capture_output=True, text=True, check=False, timeout=60
    )


def test_the_parser_defaults_the_key_to_false_and_refuses_any_other_value(
    *, tmp_path: Path
) -> None:
    """An unstated node is never chosen, and a typo is refused rather than read as false."""
    stated = _load_profile(tmp_path=tmp_path, always_on_line=f"{_PROFILE_KEY}=true\n")
    assert (stated.returncode, stated.stdout.strip()) == (0, "true"), stated.stderr
    omitted = _load_profile(tmp_path=tmp_path, always_on_line="")
    assert (omitted.returncode, omitted.stdout.strip()) == (0, "false"), omitted.stderr
    typo = _load_profile(tmp_path=tmp_path, always_on_line=f"{_PROFILE_KEY}=yes\n")
    assert typo.returncode != 0
    assert f"{_PROFILE_KEY} must be 'true' or 'false'" in typo.stderr


def test_the_label_is_spelled_once_per_carrier_and_the_carriers_agree() -> None:
    """Join, apply, boot and the read-back: one fact, four spellings held to agreement."""
    assert _PROVISION.read_text(encoding="utf-8").count(_LABEL) == 1, (
        f"provision-k3s.sh must spell {_LABEL!r} exactly once, as the constant both roles' "
        "install commands read"
    )
    defaults = _ROLE_DEFAULTS.read_text(encoding="utf-8")
    assert f"node_labels_always_on_key: {_LABEL_KEY}\n" in defaults
    # QUOTED: a bare `true` is a YAML boolean and would render `...=True`.
    assert f'node_labels_always_on_value: "{_LABEL_VALUE}"\n' in defaults
    converge = _LABEL_CONVERGE.read_text(encoding="utf-8")
    assert f'ALWAYS_ON_LABEL_KEY="{_LABEL_KEY}"\n' in converge
    assert f'ALWAYS_ON_LABEL_VALUE="{_LABEL_VALUE}"\n' in converge
    assert f'ALWAYS_ON_LABEL="{_LABEL}"\n' in _READ_BACK.read_text(encoding="utf-8")


# Every tool the real provisioning run would reach for. On the scratch PATH each
# one records its call and does nothing, so a `--dry-run` that executed anything
# is caught rather than performed.
_TRIPWIRE_TOOLS = ("curl", "k3s", "kubectl", "helm", "install", "chmod", "tar", "findmnt")
_TOKEN_FILE_LINE = re.compile(r"^CLUSTER_TOKEN_FILE=.+$", re.MULTILINE)


def test_the_install_command_plans_the_label_exactly_when_the_profile_declares_it(
    *, tmp_path: Path
) -> None:
    """The join-time carrier, run as `--dry-run` over every committed profile."""
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir()
    tripwire = tmp_path / "tripwire.log"
    for tool in _TRIPWIRE_TOOLS:
        fake = bin_dir / tool
        _ = fake.write_text(
            f'#!/bin/sh\nprintf "{tool} %s\\n" "$*" >> "{tripwire}"\nexit 0\n', encoding="utf-8"
        )
        fake.chmod(0o755)
    token = tmp_path / "join-token"
    _ = token.write_text("K10fixture::server:notasecret\n", encoding="utf-8")
    token.chmod(0o600)
    planned: set[str] = set()
    for profile in sorted(_PROFILES.glob("*.env")):
        # An agent profile names the join token's path ON THE NODE; only that
        # one line is redirected at a scratch file, as the factory-label suite does.
        runnable = tmp_path / profile.name
        _ = runnable.write_text(
            _TOKEN_FILE_LINE.sub(
                f"CLUSTER_TOKEN_FILE={token}", profile.read_text(encoding="utf-8"), count=1
            ),
            encoding="utf-8",
        )
        completed = subprocess.run(
            ["bash", str(_PROVISION), "--dry-run", str(runnable)],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
            env={**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"},
        )
        output = completed.stdout + completed.stderr
        assert completed.returncode == 0, f"{profile.name}:\n{output}"
        declares = _declared(profile=profile) == "true"
        assert (f"--node-label {_LABEL}" in output) == declares, (
            f"{profile.stem} declares {_PROFILE_KEY}={_declared(profile=profile) or '<unset>'}, "
            f"so its install plan must {'register' if declares else 'not register'} {_LABEL}:"
            f"\n{output}"
        )
        planned |= {profile.stem} if declares else set()
    assert planned == _ALWAYS_ON_NODES
    assert not tripwire.exists(), tripwire.read_text(encoding="utf-8")


def test_the_node_labels_role_reconciles_the_label_from_the_profile_key() -> None:
    """The apply-time carrier: read the key, assert its enum, add and remove."""
    tasks = _ROLE_TASKS.read_text(encoding="utf-8")
    assert f"regex_findall('^{_PROFILE_KEY}=(.*)$', multiline=True) | first | default('false')" in (
        tasks
    ), f"the role must read {_PROFILE_KEY} from the profile, defaulting to the parser's `false`"
    assert "node_labels_always_on_declared in ['true', 'false']" in tasks
    pair = "{{ node_labels_always_on_key }}={{ node_labels_always_on_value }}"
    assert f"kubectl label --overwrite node {{{{ inventory_hostname }}}}\n      {pair}\n" in tasks
    assert "kubectl label node {{ inventory_hostname }} {{ node_labels_always_on_key }}-\n" in tasks


# --- 3. the boot converge ---------------------------------------------------

# `kubectl`, faked: logs its argv and answers the reads from the environment.
_LABEL_KUBECTL = """\
printf 'kubectl %s\\n' "$*" >> "$ARGV_LOG"
if [ "$1" = "label" ]; then exit 0; fi
if [ "$1" = "get" ] && [ "$2" = "node" ]; then
  case " ${REGISTERED:-} " in
    *" $3 "*) printf 'node/%s\\n' "$3"; exit 0 ;;
  esac
  printf 'Error from server (NotFound): nodes "%s" not found\\n' "$3" >&2
  exit 1
fi
if [ "$1" = "get" ] && [ "$2" = "nodes" ]; then
  case " $* " in
    *" -l "*)
      [ -z "${SELECTOR_FAILS:-}" ] || { echo 'Unable to connect to the server' >&2; exit 1; }
      for n in ${LABELLED:-}; do printf 'node/%s\\n' "$n"; done ;;
  esac
  exit 0
fi
exit 0
"""
_SLEEP_SHIM = 'printf \'sleep %s\\n\' "$*" >> "$ARGV_LOG"\n'


_HELM_SHIM = 'printf \'helm %s\\n\' "$*" >> "$ARGV_LOG"\n'


def _scratch_path(
    *, tmp_path: Path, kubectl: str, helm: bool = False
) -> tuple[dict[str, str], Path]:
    """An environment whose PATH resolves `kubectl` and `sleep` (and `helm`) to stand-ins."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    shims = [("kubectl", kubectl), ("sleep", _SLEEP_SHIM)]
    if helm:
        shims.append(("helm", _HELM_SHIM))
    for name, body in shims:
        shim = bin_dir / name
        _ = shim.write_text(f"#!/usr/bin/env bash\n{body}", encoding="utf-8")
        shim.chmod(0o755)
    log = tmp_path / "argv.log"
    env = {k: v for k, v in os.environ.items() if not k.startswith(("COVERAGE_", "COV_CORE_"))}
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    env["ARGV_LOG"] = str(log)
    return env, log


def _run_label_converge(
    *,
    tmp_path: Path,
    profiles_dir: Path,
    registered: tuple[str, ...],
    labelled: tuple[str, ...] = (),
    wait_seconds: int = 2,
    selector_fails: bool = False,
) -> tuple[int, str, list[str]]:
    """Run the shipped converge against a faked cluster; return code, output, argv."""
    env, log = _scratch_path(tmp_path=tmp_path, kubectl=_LABEL_KUBECTL)
    env.update(
        {
            "REGISTERED": " ".join(registered),
            "LABELLED": " ".join(labelled),
            "SELECTOR_FAILS": "1" if selector_fails else "",
            "CI_ALWAYS_ON_LABEL_PROFILES_DIR": str(profiles_dir),
            "CI_ALWAYS_ON_LABEL_WAIT_SECONDS": str(wait_seconds),
            "CI_ALWAYS_ON_LABEL_POLL_SECONDS": "1",
        }
    )
    completed = subprocess.run(
        ["bash", str(_LABEL_CONVERGE)],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    invoked = log.read_text(encoding="utf-8").splitlines() if log.is_file() else []
    return completed.returncode, completed.stdout + completed.stderr, invoked


def _asserted(*, invoked: list[str]) -> set[str]:
    """Every node the run asserted the label on."""
    prefix, suffix = "kubectl label --overwrite node ", f" {_LABEL}"
    return {
        line.removeprefix(prefix).removesuffix(suffix)
        for line in invoked
        if line.startswith(prefix) and line.endswith(suffix)
    }


def _removed(*, invoked: list[str]) -> set[str]:
    """Every node the run removed the label from."""
    prefix, suffix = "kubectl label node ", f" {_LABEL_KEY}-"
    return {
        line.removeprefix(prefix).removesuffix(suffix)
        for line in invoked
        if line.startswith(prefix) and line.endswith(suffix)
    }


def _scratch_profiles(*, tmp_path: Path, declared: dict[str, str]) -> Path:
    """A profiles directory in the committed `KEY=value` shape, for the control arms."""
    directory = tmp_path / "profiles"
    directory.mkdir()
    for node, value in declared.items():
        body = f"NODE_NAME={node}\n" + (f"{_PROFILE_KEY}={value}\n" if value else "")
        _ = (directory / f"{node}.env").write_text(body, encoding="utf-8")
    return directory


def test_the_boot_converge_labels_the_committed_always_on_nodes_and_unlabels_the_rest(
    *, tmp_path: Path
) -> None:
    """Against the committed profiles: three nodes asserted, gamingpc's stale label removed."""
    everyone = tuple(sorted(_ALWAYS_ON_NODES | _NOT_ALWAYS_ON_NODES))
    code, output, invoked = _run_label_converge(
        tmp_path=tmp_path, profiles_dir=_PROFILES, registered=everyone, labelled=everyone
    )
    assert code == 0, output
    assert _asserted(invoked=invoked) == _ALWAYS_ON_NODES, output
    assert _removed(invoked=invoked) == _NOT_ALWAYS_ON_NODES, output


def test_a_profile_without_the_key_is_never_labelled_and_a_typo_is_skipped_not_unlabelled(
    *, tmp_path: Path
) -> None:
    """The default is the safe side, and a typo must not remove a live label."""
    profiles = _scratch_profiles(
        tmp_path=tmp_path, declared={"on": "true", "silent": "", "typo": "ture"}
    )
    nodes = ("on", "silent", "typo")
    code, output, invoked = _run_label_converge(
        tmp_path=tmp_path, profiles_dir=profiles, registered=nodes, labelled=nodes
    )
    assert code != 0, f"an unreadable posture must fail the step:\n{output}"
    assert _asserted(invoked=invoked) == {"on"}
    assert _removed(invoked=invoked) == {"silent"}
    assert "ALWAYS_ON_NODE='ture'" in output


def test_the_boot_converge_unlabels_a_labelled_node_that_has_no_profile(*, tmp_path: Path) -> None:
    """Every other node must not carry it: a homelab worker labelled by hand is unlabelled."""
    profiles = _scratch_profiles(
        tmp_path=tmp_path, declared={"on": "true", "off": "false", "typo": "ture"}
    )
    code, output, invoked = _run_label_converge(
        tmp_path=tmp_path,
        profiles_dir=profiles,
        registered=("on", "off", "typo"),
        labelled=("on", "off", "typo", "homelab-worker"),
    )
    assert _asserted(invoked=invoked) == {"on"}
    # `typo` is skipped, not unlabelled: its profile could not be read.
    assert _removed(invoked=invoked) == {"off", "homelab-worker"}, output
    assert f"homelab-worker: {_LABEL_KEY} removed (it has no committed profile)" in output
    assert f"typo: {_LABEL_KEY} left as it is" in output
    assert code != 0, f"the unreadable profile must still fail the step:\n{output}"


def test_a_node_with_no_profile_is_unlabelled_and_the_step_passes_when_every_profile_reads(
    *, tmp_path: Path
) -> None:
    """The removal alone is not a failure: with readable profiles the reconcile exits 0."""
    profiles = _scratch_profiles(tmp_path=tmp_path, declared={"on": "true"})
    code, output, invoked = _run_label_converge(
        tmp_path=tmp_path,
        profiles_dir=profiles,
        registered=("on",),
        labelled=("on", "homelab-worker"),
    )
    assert code == 0, output
    assert _removed(invoked=invoked) == {"homelab-worker"}


def test_a_profile_that_names_no_node_stops_the_removal_from_nodes_no_profile_names(
    *, tmp_path: Path
) -> None:
    """The nameless profile may be that node's, so its label is not removed on a guess."""
    profiles = _scratch_profiles(tmp_path=tmp_path, declared={"on": "true", "off": "false"})
    _ = (profiles / "nameless.env").write_text(f"{_PROFILE_KEY}=true\n", encoding="utf-8")
    code, output, invoked = _run_label_converge(
        tmp_path=tmp_path,
        profiles_dir=profiles,
        registered=("on", "off"),
        labelled=("on", "off", "unnamed-node"),
    )
    assert code != 0, output
    assert _removed(invoked=invoked) == {"off"}, output
    assert f"WARN: unnamed-node carries {_LABEL_KEY} and no readable profile names it" in output


def test_the_early_pass_labels_what_is_registered_without_waiting(*, tmp_path: Path) -> None:
    """`CI_ALWAYS_ON_LABEL_WAIT_SECONDS=0`: one probe per node, no sleep, and it says so."""
    profiles = _scratch_profiles(tmp_path=tmp_path, declared={"server": "true", "agent": "true"})
    code, output, invoked = _run_label_converge(
        tmp_path=tmp_path, profiles_dir=profiles, registered=("server",), wait_seconds=0
    )
    assert code != 0, f"an always-on node left unlabelled must be reported:\n{output}"
    assert _asserted(invoked=invoked) == {"server"}
    assert not [line for line in invoked if line.startswith("sleep ")], invoked
    assert invoked.count("kubectl get node agent -o name") == 1
    assert "agent is not registered" in output


def test_a_failed_selector_read_is_not_read_as_no_node_carrying_the_label(
    *, tmp_path: Path
) -> None:
    """A kubectl failure must fail the step, never pass as 'nothing to remove'."""
    profiles = _scratch_profiles(tmp_path=tmp_path, declared={"on": "true", "off": "false"})
    code, output, invoked = _run_label_converge(
        tmp_path=tmp_path,
        profiles_dir=profiles,
        registered=("on", "off"),
        labelled=("on", "off"),
        selector_fails=True,
    )
    assert code != 0, output
    assert not _removed(invoked=invoked)
    assert "could not read which nodes carry" in output


def test_the_boot_converge_asserts_the_label_before_arc_and_reconciles_it_again_at_the_end() -> (
    None
):
    """Every listener selects on the label, so it must exist before a listener does."""
    body = _BOOT_CONVERGE.read_text(encoding="utf-8")
    assignment = re.search(
        rf'(?m)^(?P<var>[A-Z_]+)="\$\{{SCRIPT_DIR\}}/{re.escape(_LABEL_CONVERGE.name)}"$', body
    )
    assert (
        assignment is not None
    ), f"converge-ci-stack.sh must resolve {_LABEL_CONVERGE.name} beside itself"
    invocation = f'"${{{assignment["var"]}}}"; then'
    early = body.find(f"CI_ALWAYS_ON_LABEL_WAIT_SECONDS=0 {invocation}")
    late = body.find(f"elif ! {invocation}")
    controller = body.find('log "6. Install/upgrade the ARC controller')
    verify = body.find('log "11. Verify')
    assert -1 < early < controller, (
        "the first pass must run BEFORE the ARC controller and with no registration wait: "
        "after a reboot no node carries the label, and a listener created before it is set "
        "stays Pending"
    )
    assert controller < late < verify, (
        "the second pass, with the bounded registration wait, must run after the cluster "
        "stack so its wait sits in front of nothing"
    )


def test_the_ci_converge_unit_role_installs_the_boot_converge_script() -> None:
    """The host has no checkout: the boot converge runs only what the role installed."""
    sources = set(
        re.findall(
            r"^\s*- src:\s*(\S+)\s*$",
            _CONVERGE_UNIT_DEFAULTS.read_text(encoding="utf-8"),
            re.MULTILINE,
        )
    )
    assert _LABEL_CONVERGE.relative_to(_PHASE2).as_posix() in sources


# --- 4. the read-back -------------------------------------------------------

# `kubectl`, faked for the read-back: any verb but `get` is a recorded WRITE and
# fails; the four reads are answered from files, and FAIL_READ names one to fail.
_READ_BACK_KUBECTL = """\
printf 'kubectl %s\\n' "$*" >> "$ARGV_LOG"
case " $* " in
  *" get "*) ;;
  *) exit 97 ;;
esac
fail() { echo 'Unable to connect to the server: dial tcp: i/o timeout' >&2; exit 1; }
case " $* " in
  *" autoscalingrunnersets.actions.github.com "*)
    [ "${FAIL_READ:-}" != runner_sets ] || fail
    cat "$RUNNER_SETS_FILE" ;;
  *" autoscalinglisteners.actions.github.com "*)
    [ "${FAIL_READ:-}" != listeners ] || fail
    cat "$LISTENERS_FILE" ;;
  *" get pods "*)
    [ "${FAIL_READ:-}" != pods ] || fail
    cat "$PODS_FILE" ;;
  *" get nodes "*)
    [ "${FAIL_READ:-}" != nodes ] || fail
    cat "$NODES_FILE" ;;
  *) exit 98 ;;
esac
"""

_LISTENERS = (
    ("livespec-k3s-listener", "livespec-local-ci-k3s"),
    ("overseer-k3s-listener", "livespec-overseer-k3s"),
)


def _pod(*, listener: str, node: str, phase: str = "Running", deleting: str = "") -> str:
    """One pod row in the read-back's own jsonpath shape."""
    return f"{listener}|AutoscalingListener|{listener}|{node}|{phase}|{deleting}"


def _run_read_back(
    *,
    tmp_path: Path,
    pods: tuple[str, ...],
    listeners: tuple[tuple[str, str], ...] = _LISTENERS,
    labelled: tuple[str, ...] = ("poweredge-xubuntu", "hp-xubuntu"),
    fail_read: str = "",
    runner_sets: tuple[str, ...] | None = None,
) -> tuple[int, str, list[str]]:
    """Run the shipped read-back against a faked cluster; return code, output, argv."""
    env, log = _scratch_path(tmp_path=tmp_path, kubectl=_READ_BACK_KUBECTL)
    installed = (
        tuple(scale_set for _, scale_set in listeners) if runner_sets is None else runner_sets
    )
    files = {
        "RUNNER_SETS_FILE": "".join(f"{scale_set}\n" for scale_set in installed),
        "LISTENERS_FILE": "".join(f"{name}|{scale_set}\n" for name, scale_set in listeners),
        # The controller's own pod shares the namespace and is owned by a
        # ReplicaSet on a node without the label: it must be ignored.
        "PODS_FILE": "arc-gha-rs-controller-0|ReplicaSet|arc-rs|gamingpc-xubuntu|Running|\n"
        + "".join(f"{row}\n" for row in pods),
        "NODES_FILE": "".join(f"node/{node}\n" for node in labelled),
    }
    for variable, content in files.items():
        path = tmp_path / variable.lower()
        _ = path.write_text(content, encoding="utf-8")
        env[variable] = str(path)
    env["FAIL_READ"] = fail_read
    completed = subprocess.run(
        ["bash", str(_READ_BACK)],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    invoked = log.read_text(encoding="utf-8").splitlines() if log.is_file() else []
    return completed.returncode, completed.stdout + completed.stderr, invoked


def test_the_read_back_lists_each_listener_with_its_node_and_passes_when_all_are_placed(
    *, tmp_path: Path
) -> None:
    """Exit 0, one line per scale set naming pod and node, and not one write."""
    code, output, invoked = _run_read_back(
        tmp_path=tmp_path,
        pods=(
            _pod(listener="livespec-k3s-listener", node="poweredge-xubuntu"),
            _pod(listener="overseer-k3s-listener", node="hp-xubuntu"),
        ),
    )
    assert code == 0, output
    for listener, scale_set in _LISTENERS:
        row = next(line for line in output.splitlines() if line.startswith(scale_set))
        assert listener in row and row.rstrip().endswith("ok"), row
    assert re.search(
        r"(?m)^livespec-local-ci-k3s\s+\S+\s+poweredge-xubuntu\s+Running\s+ok$", output
    )
    assert len(invoked) == 4 and all(" get " in f" {line} " for line in invoked), invoked
    assert sum("autoscalingrunnersets.actions.github.com" in line for line in invoked) == 1
    assert any(
        line.startswith("kubectl -n arc-runners get autoscalingrunnersets") for line in invoked
    )


def test_the_read_back_fails_naming_a_listener_on_a_node_without_the_label(
    *, tmp_path: Path
) -> None:
    """The Definition of Done's refusal: non-zero, and the scale set and node are named."""
    code, output, _ = _run_read_back(
        tmp_path=tmp_path,
        pods=(
            _pod(listener="livespec-k3s-listener", node="poweredge-xubuntu"),
            _pod(listener="overseer-k3s-listener", node="gamingpc-xubuntu"),
        ),
    )
    assert code == 1, output
    row = next(line for line in output.splitlines() if line.startswith("livespec-overseer-k3s"))
    assert "gamingpc-xubuntu" in row and f"FAIL: node does not carry {_LABEL}" in row, row
    assert "1 of 2 scale set listener(s)" in output


@pytest.mark.parametrize(
    ("pods", "reason"),
    [
        ((), "no listener pod"),
        ((_pod(listener="overseer-k3s-listener", node=""),), "not scheduled on any node"),
        (
            (_pod(listener="overseer-k3s-listener", node="hp-xubuntu", phase="Pending"),),
            "is Pending, not Running",
        ),
        (
            (
                _pod(
                    listener="overseer-k3s-listener",
                    node="hp-xubuntu",
                    deleting="2026-11-12T21:28:00Z",
                ),
            ),
            "is Terminating, not Running",
        ),
    ],
    ids=["no-pod", "unscheduled", "pending", "terminating"],
)
def test_the_read_back_fails_when_a_scale_set_has_no_running_listener(
    *, tmp_path: Path, pods: tuple[str, ...], reason: str
) -> None:
    """A stranded listener is the outage itself; it must not read as correctly placed."""
    healthy = _pod(listener="livespec-k3s-listener", node="poweredge-xubuntu")
    code, output, _ = _run_read_back(tmp_path=tmp_path, pods=(healthy, *pods))
    assert code == 1, output
    row = next(line for line in output.splitlines() if line.startswith("livespec-overseer-k3s"))
    assert reason in row, row


def test_the_read_back_prefers_a_listeners_live_pod_over_its_terminating_predecessor(
    *, tmp_path: Path
) -> None:
    """A listener being replaced owns two pods for a moment; the live one is the answer."""
    old = _pod(
        listener="overseer-k3s-listener", node="gamingpc-xubuntu", deleting="2026-11-12T21:28:00Z"
    )
    new = _pod(listener="overseer-k3s-listener", node="hp-xubuntu")
    healthy = _pod(listener="livespec-k3s-listener", node="poweredge-xubuntu")
    for order in ((old, new), (new, old)):
        scratch = tmp_path / f"order-{order.index(old)}"
        scratch.mkdir()
        code, output, _ = _run_read_back(tmp_path=scratch, pods=(healthy, *order))
        assert code == 0, output


def test_the_read_back_fails_when_the_cluster_has_no_listener_at_all(*, tmp_path: Path) -> None:
    """Zero listeners is zero scale sets taking jobs, not a clean placement."""
    code, output, _ = _run_read_back(
        tmp_path=tmp_path, pods=(), listeners=(), runner_sets=("livespec-overseer-k3s",)
    )
    assert code == 1, output
    assert "holds no AutoscalingListener" in output


def test_the_read_back_fails_when_no_scale_set_is_installed(*, tmp_path: Path) -> None:
    """Zero AutoscalingRunnerSets is no CI at all, not a clean placement."""
    code, output, _ = _run_read_back(tmp_path=tmp_path, pods=(), listeners=(), runner_sets=())
    assert code == 1, output
    assert "holds no AutoscalingRunnerSet" in output
    assert "OK:" not in output


def test_the_read_back_fails_naming_a_scale_set_that_has_no_listener_object(
    *, tmp_path: Path
) -> None:
    """The 2026-11-05 shape: a scale set is installed and no AutoscalingListener exists for it."""
    code, output, _ = _run_read_back(
        tmp_path=tmp_path,
        pods=(
            _pod(listener="livespec-k3s-listener", node="poweredge-xubuntu"),
            _pod(listener="overseer-k3s-listener", node="hp-xubuntu"),
        ),
        runner_sets=("livespec-local-ci-k3s", "livespec-overseer-k3s", "livespec-runtime-k3s"),
    )
    assert code == 1, output
    row = next(line for line in output.splitlines() if line.startswith("livespec-runtime-k3s"))
    assert "FAIL: the scale set has no AutoscalingListener" in row, row
    for healthy in ("livespec-local-ci-k3s", "livespec-overseer-k3s"):
        ok_row = next(line for line in output.splitlines() if line.startswith(healthy))
        assert ok_row.rstrip().endswith("ok"), ok_row
    assert "OK:" not in output


@pytest.mark.parametrize("read", ["listeners", "pods", "nodes", "runner_sets"])
def test_the_read_back_fails_loudly_when_a_kubectl_read_fails(*, tmp_path: Path, read: str) -> None:
    """A failed read is never an empty list: exit 2, FATAL, and no verdict line."""
    code, output, _ = _run_read_back(
        tmp_path=tmp_path,
        pods=(
            _pod(listener="livespec-k3s-listener", node="poweredge-xubuntu"),
            _pod(listener="overseer-k3s-listener", node="hp-xubuntu"),
        ),
        fail_read=read,
    )
    assert code == 2, output
    assert "FATAL: could not read" in output
    assert "OK:" not in output


# --- 5. the install routes refuse when no node can host a listener -----------

_DECISION_START = "arc_listeners_placeable=true"
_STEP_5B = 'log "5b. Assert the ALWAYS-ON label'
_STEP_6 = 'log "6. Install/upgrade the ARC controller'
_END_START = 'if [ "${arc_listeners_placeable}" != true ]; then'
_DONE = 'log "DONE. CI cluster stack converged:'
_BETWEEN = "BETWEEN: the steps after the decision still run"
_BOOT_SCALE_SETS = ("alpha-k3s", "beta-homelab-worker-k3s", "gamma-k3s")


def _line_index(*, lines: list[str], wanted: str, exact: bool = False) -> int:
    """The index of the ONE line that is (or starts with) `wanted`."""
    found = [
        index
        for index, line in enumerate(lines)
        if (line == wanted if exact else line.startswith(wanted))
    ]
    assert len(found) == 1, f"expected exactly one line for {wanted!r}, found {found}"
    return found[0]


def _boot_converge_blocks() -> tuple[str, str]:
    """Step 5b's decision block and the converge's end block, cut out by their own words."""
    lines = _BOOT_CONVERGE.read_text(encoding="utf-8").splitlines()
    step_5b = _line_index(lines=lines, wanted=_STEP_5B)
    decided = _line_index(lines=lines, wanted=_DECISION_START, exact=True)
    step_6 = _line_index(lines=lines, wanted=_STEP_6)
    # Unindented: the same test inside step 7's loop is indented and is not this line.
    end = _line_index(lines=lines, wanted=_END_START, exact=True)
    done = _line_index(lines=lines, wanted=_DONE)
    assert step_5b < decided < step_6 < end < done
    # The steps the stop must NOT skip sit between the decision and the end block.
    for step in (
        "log \"10d. Re-mint every AGENT node's node-status credential",
        'log "10e. Re-apply the factory namespace',
        "log \"10h. Reconcile every ci_pool node's ALWAYS-ON label",
    ):
        assert step_6 < _line_index(lines=lines, wanted=step) < end, step
    return "\n".join(lines[decided:step_6]), "\n".join(lines[end : done + 1])


def _run_boot_decision(
    *, tmp_path: Path, labelled: tuple[str, ...] = (), selector_fails: bool = False
) -> tuple[int, str, str]:
    """RUN the decision block, a marker, then the end block; return code, stdout, stderr."""
    decision, end = _boot_converge_blocks()
    env, _ = _scratch_path(tmp_path=tmp_path, kubectl=_LABEL_KUBECTL)
    env.update({"LABELLED": " ".join(labelled), "SELECTOR_FAILS": "1" if selector_fails else ""})
    declared = " ".join(f"[{name}]=values.yaml" for name in _BOOT_SCALE_SETS)
    program = "\n".join(
        [
            "set -euo pipefail",
            "log() { printf '== %s ==\\n' \"$*\"; }",
            f"declare -A SCALE_SETS=({declared})",
            decision,
            "printf 'PLACEABLE=%s\\n' \"${arc_listeners_placeable}\"",
            "printf 'REFUSAL=%s\\n' \"${arc_listeners_refusal}\"",
            f"echo '{_BETWEEN}'",
            end,
        ]
    )
    completed = subprocess.run(
        ["bash", "-c", program],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    return completed.returncode, completed.stdout, completed.stderr


_NO_NODE = "no node carries ci-runner.io/always-on=true"
_FAILED_READ = "could not read which nodes carry ci-runner.io/always-on=true"


@pytest.mark.parametrize(
    ("selector_fails", "refusal"),
    [(False, _NO_NODE), (True, _FAILED_READ)],
    ids=["empty-read", "failed-read"],
)
def test_the_boot_converge_decides_no_scale_set_runs_the_rest_and_exits_one_naming_the_sets(
    *, tmp_path: Path, selector_fails: bool, refusal: str
) -> None:
    """Run for real: not placeable, the later steps still run, exit 1 naming every scale set."""
    code, stdout, stderr = _run_boot_decision(tmp_path=tmp_path, selector_fails=selector_fails)
    assert "PLACEABLE=false" in stdout, stdout + stderr
    refusal_line = next(line for line in stdout.splitlines() if line.startswith("REFUSAL="))
    assert refusal_line.startswith(f"REFUSAL={refusal}"), refusal_line
    # A failed read is not an empty answer: each case carries its own refusal.
    other = _FAILED_READ if refusal == _NO_NODE else _NO_NODE
    assert other not in stdout + stderr
    deferred = next(line for line in stderr.splitlines() if line.startswith("FATAL (deferred): "))
    assert refusal in deferred
    assert "Step 7 will NOT install or upgrade any runner scale set" in deferred
    # The decision block did not exit: what follows it ran.
    assert _BETWEEN in stdout
    assert code == 1, stdout + stderr
    final = next(
        line
        for line in stderr.splitlines()
        if line.startswith("FATAL: the runner scale sets were NOT installed or upgraded: ")
    )
    assert refusal in final
    assert f"The {len(_BOOT_SCALE_SETS)} scale sets not installed or upgraded: " in final
    assert " ".join(sorted(_BOOT_SCALE_SETS)) + "." in final, final
    assert "Every other step of this converge ran." in final
    assert "DONE. CI cluster stack converged" not in stdout


def test_the_boot_converge_decides_the_scale_sets_install_when_a_node_carries_the_label(
    *, tmp_path: Path
) -> None:
    """The control arm, run for real: placeable, the nodes are printed, and the converge ends 0."""
    code, stdout, stderr = _run_boot_decision(
        tmp_path=tmp_path, labelled=("poweredge-xubuntu", "hp-xubuntu")
    )
    assert code == 0, stdout + stderr
    assert "PLACEABLE=true" in stdout
    assert "REFUSAL=\n" in stdout
    assert (
        "nodes that can host an ARC listener pod: node/poweredge-xubuntu node/hp-xubuntu" in stdout
    )
    assert "FATAL" not in stderr
    assert _BETWEEN in stdout
    assert "DONE. CI cluster stack converged: " in stdout
    assert f"{len(_BOOT_SCALE_SETS)} scale sets" in stdout


_INSTALL_ARC = _K3S / "install-arc.sh"
_SCALE_SET_HELM_CALL = "helm upgrade --install poweredge-xubuntu-k3s "
_CONTROLLER_HELM_CALL = "helm upgrade --install arc "


def _run_install_arc(
    *, tmp_path: Path, labelled: tuple[str, ...] = (), selector_fails: bool = False
) -> tuple[int, str, list[str]]:
    """Run the shipped install-arc.sh against stand-in `kubectl` and `helm`."""
    env, log = _scratch_path(tmp_path=tmp_path, kubectl=_LABEL_KUBECTL, helm=True)
    env.update(
        {
            "LABELLED": " ".join(labelled),
            "SELECTOR_FAILS": "1" if selector_fails else "",
            "KUBECONFIG": str(tmp_path / "no-such-kubeconfig"),
        }
    )
    completed = subprocess.run(
        ["bash", str(_INSTALL_ARC)],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    invoked = log.read_text(encoding="utf-8").splitlines() if log.is_file() else []
    return completed.returncode, completed.stdout + completed.stderr, invoked


@pytest.mark.parametrize(
    ("selector_fails", "refusal"),
    [(False, f"FATAL: {_NO_NODE}"), (True, f"FATAL: {_FAILED_READ}")],
    ids=["empty-read", "failed-read"],
)
def test_the_first_install_script_makes_no_scale_set_helm_call_when_no_node_can_host_a_listener(
    *, tmp_path: Path, selector_fails: bool, refusal: str
) -> None:
    """Run for real: the controller installs, the read is made, and the scale set never is."""
    code, output, invoked = _run_install_arc(tmp_path=tmp_path, selector_fails=selector_fails)
    assert code == 1, output
    assert refusal in output
    assert "Not installing the scale set." in output
    assert f"kubectl get nodes -l {_LABEL} -o name" in invoked
    helm_calls = [line for line in invoked if line.startswith("helm ")]
    # The script got as far as the guard: the controller call before it was made.
    assert [line for line in helm_calls if line.startswith(_CONTROLLER_HELM_CALL)], invoked
    assert not [line for line in helm_calls if "poweredge-xubuntu-k3s" in line], helm_calls
    assert not [line for line in helm_calls if "gha-runner-scale-set " in f"{line} "], helm_calls


def test_the_first_install_script_installs_the_scale_set_when_a_node_carries_the_label(
    *, tmp_path: Path
) -> None:
    """The control arm: the same run with a labelled node reaches the scale set's helm call."""
    code, output, invoked = _run_install_arc(tmp_path=tmp_path, labelled=("poweredge-xubuntu",))
    assert code == 0, output
    read = invoked.index(f"kubectl get nodes -l {_LABEL} -o name")
    install = next(
        index for index, line in enumerate(invoked) if line.startswith(_SCALE_SET_HELM_CALL)
    )
    assert read < install, invoked


# --- 6. the read-back scenario, whole ---------------------------------------


def test_the_read_back_names_a_misplaced_listener_and_a_scale_set_with_no_listener_in_one_run(
    *, tmp_path: Path
) -> None:
    """Scenario "the listener read-back fails when a listener is on a node that is not always on".

    Its whole setup in ONE run: a scale set's listener pod on a node without the
    label, AND another installed scale set with no listener at all. The read-back
    names the first set with its listener pod and node, names the second as having
    no listener, and exits 1.
    """
    misplaced_pod = "overseer-k3s-listener-7c9d4"
    code, output, invoked = _run_read_back(
        tmp_path=tmp_path,
        pods=(
            _pod(listener="livespec-k3s-listener", node="poweredge-xubuntu"),
            f"{misplaced_pod}|AutoscalingListener|overseer-k3s-listener|gamingpc-xubuntu|Running|",
        ),
        runner_sets=("livespec-local-ci-k3s", "livespec-overseer-k3s", "livespec-runtime-k3s"),
    )
    assert code == 1, output
    rows = output.splitlines()
    first = next(line for line in rows if line.startswith("livespec-overseer-k3s"))
    assert first.split()[:4] == [
        "livespec-overseer-k3s",
        misplaced_pod,
        "gamingpc-xubuntu",
        "Running",
    ], first
    assert first.endswith(f"FAIL: node does not carry {_LABEL}"), first
    second = next(line for line in rows if line.startswith("livespec-runtime-k3s"))
    assert second.endswith("FAIL: the scale set has no AutoscalingListener"), second
    healthy = next(line for line in rows if line.startswith("livespec-local-ci-k3s"))
    assert healthy.rstrip().endswith("ok"), healthy
    assert "FAIL: 2 of 2 scale set listener(s)" in output
    assert "OK:" not in output
    assert all(" get " in f" {line} " for line in invoked), invoked
