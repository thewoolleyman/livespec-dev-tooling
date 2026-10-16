"""ONE renderer writes an agent's node-status kubeconfig — not two that disagree.

Two renderers used to write the same file in two shapes. The control-plane
node's boot converge (`ci-runner/k3s/phase2/reconstruct/converge-ci-stack.sh`
step 10d) calls `render-sa-kubeconfig.sh`, which writes cluster name `k3s`,
contexts before users and unindented lists. The `node_status_credential` role
carried its OWN `set_fact` template of the same credential, writing cluster name
`ci-runner`, users before contexts, indented lists — and, because its
`--server` came from the agent profile's `CLUSTER_JOIN_ADDRESS` rather than from
the converge's `NODE_STATUS_SERVER`, a different API-server address as well.

THE COST WAS A DRIFT REPORT THAT COULD NEVER READ CLEAN. After every
poweredge-xubuntu reboot the agent's five-minute timer pulls the SERVER's
rendering (`refresh-node-status-kubeconfig`), so the agent holds the converge's
bytes. The role's delivery task is `ansible.builtin.copy`, idempotent by
CONTENT, so it then reported a change on every run although the credential it
would have replaced was the same credential. Measured 2026-10-12 after the
11:58Z reboot: `/etc/rancher/k3s/node-status-kubeconfig` on gmktec-xubuntu and
`/etc/ci-runner/node-status-gmktec-xubuntu.kubeconfig` on poweredge-xubuntu had
the SAME sha256 (root:root 0600, 2200 bytes) and
`just ansible-drift ansible/ci-pool.yml` still reported `gmktec-xubuntu
changed=1` on that one task. The plan's zero-drift assertion cannot pass while
that holds.

WHY THE RENDERER IS RUN RATHER THAN READ. The claim is a claim about BYTES —
every field, every ordering, every indent of two renderings of one credential —
and no reading of a shell heredoc beside a Jinja block establishes it. So the
committed `render-sa-kubeconfig.sh` is EXECUTED twice, once with each caller's
own invocation, against a stand-in `kubectl` that serves one token and one
cluster CA to both. No cluster is reached, no credential exists, and every path
either run writes stays inside `tmp_path`.

AND THE INVOCATIONS ARE TAKEN FROM THE CALLERS, not restated here. The
converge's own variable assignments and its own renderer invocation are
extracted from the committed script and executed by bash, so the server address,
the namespace and the ServiceAccount name are the converge's. The role's are
extracted from its committed task and resolved against its committed defaults.
A test that restated either side would compare two copies of its own opinion and
pass over a role that had drifted back to a second template.

Work-item: livespec-dev-tooling-psqaav. Plan: livespec
`k3s-on-gmktec-for-vps-usage` (epic livespec-sab5gn), assertion 6 (zero drift on
ci-pool and gates-kubeconfig).
"""

from __future__ import annotations

import base64
import os
import re
import subprocess
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_K3S = _REPO_ROOT / "ci-runner" / "k3s"
_PHASE2 = _K3S / "phase2"
_RENDERER = _PHASE2 / "reconstruct" / "render-sa-kubeconfig.sh"
_BOOT_CONVERGE = _PHASE2 / "reconstruct" / "converge-ci-stack.sh"
_ROLE = _REPO_ROOT / "ansible" / "roles" / "node_status_credential"
_ROLE_TASKS = _ROLE / "tasks" / "main.yml"
_ROLE_DEFAULTS = _ROLE / "defaults" / "main.yml"

# The COMMITTED agent profile, so the node name both sides compose their
# ServiceAccount and their destination filename from is the pool's real one.
_AGENT_PROFILE = _K3S / "phase0-bare-metal" / "profiles" / "gmktec-xubuntu.env"

# The stand-in cluster's two secrets. They authenticate nothing; what matters is
# that BOTH renderings are served the SAME token and the SAME CA, which is what
# makes a byte difference attributable to the renderer rather than to its input.
_TOKEN = "stand-in.node-status.token.not-a-credential"
_CA_PEM = "-----BEGIN CERTIFICATE-----\nc3RhbmQtaW4tY2x1c3Rlci1jYQ==\n-----END CERTIFICATE-----\n"

# `render-sa-kubeconfig.sh` reads the token as base64 and decodes it, and reads
# `ca.crt` as base64 and writes it through unchanged (that is the form
# `certificate-authority-data` wants).
_TOKEN_B64 = base64.b64encode(_TOKEN.encode("utf-8")).decode("ascii")
_CA_B64 = base64.b64encode(_CA_PEM.encode("utf-8")).decode("ascii")

# The two jsonpath reads the renderer makes, quoted as kubectl receives them.
# The `ca.crt` one carries the ESCAPED dot: the key is `ca.crt`, so an
# unescaped `{.data.ca.crt}` would name key `crt` under key `ca` and read as
# empty — the defect f7dc420f fixed on the role's own copy of this read, and the
# reason this stand-in matches the escaped spelling rather than a loose `*ca*`.
_TOKEN_JSONPATH = "{.data.token}"
_CA_JSONPATH = "{.data.ca\\.crt}"

# The stand-in `kubectl`. It answers the renderer's two reads and EXITS NON-ZERO
# on anything else rather than returning a plausible empty string, so an
# invocation this fixture was not written for breaks the test instead of quietly
# satisfying a guard.
_KUBECTL_STAND_IN = f"""#!/bin/sh
case "$*" in
  *'{_TOKEN_JSONPATH}'*)
    printf '%s' '{_TOKEN_B64}'
    exit 0 ;;
  *'{_CA_JSONPATH}'*)
    printf '%s' '{_CA_B64}'
    exit 0 ;;
esac
printf 'stand-in kubectl: unexpected invocation: %s\\n' "$*" >&2
exit 1
"""

# A stand-in `chown`, because the renderer gives the credential to `root:root`
# and only root can give a file away — this suite runs as whoever invoked
# pytest. It LOGS the ownership asked for rather than merely succeeding, so the
# ownership intent is still observable, and the bytes under test are the
# kubeconfig's, not its inode's.
_CHOWN_STAND_IN = """#!/bin/sh
printf 'chown %s\\n' "$*" >> "$CHOWN_LOG"
exit 0
"""

# The ownership both callers must ask for. The credential is a bearer token, and
# its only consumer is a root systemd unit on the agent.
_EXPECTED_OWNERSHIP = "chown root:root"

# A hand-written kubeconfig's own marker, and the one the role must no longer
# carry. `kind: Config` cannot serve: the role's refusal of a non-kubeconfig
# fetch quotes it, so matching on it would convict the guard that replaced the
# template.
_TEMPLATE_MARKER = "current-context:"

# A bounded wait. Two renderer runs against a stand-in `kubectl` answer
# immediately; the renderer's own token wait is 60 s, and a fixture that fell
# into it must fail this test rather than the suite's whole budget.
_RENDER_TIMEOUT_SECONDS = 180


def _scratch_bin(*, tmp_path: Path) -> Path:
    """A private bin dir holding the stand-in `kubectl` and `chown`."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (("kubectl", _KUBECTL_STAND_IN), ("chown", _CHOWN_STAND_IN)):
        stand_in = bin_dir / name
        stand_in.write_text(body, encoding="utf-8")
        stand_in.chmod(0o755)
    return bin_dir


def _render_environment(*, bin_dir: Path, tmp_path: Path, render_dir: Path) -> dict[str, str]:
    """The child's environment: the stand-ins first on PATH, nothing real reachable.

    `KUBECONFIG` is set because the renderer REFUSES to run without one — it
    reads the token Secret as the cluster's admin — and the path it names is
    never opened, because the only `kubectl` on this PATH is the stand-in.
    `CI_NODE_STATUS_RENDER_DIR` is the converge's own override for its render
    directory, which is how this fixture redirects the converge's destination
    into `tmp_path` without editing the line under test.
    """
    env = dict(os.environ)
    env.update(
        {
            "PATH": f"{bin_dir}{os.pathsep}{env['PATH']}",
            "KUBECONFIG": str(tmp_path / "admin.kubeconfig"),
            "CHOWN_LOG": str(tmp_path / "chown.log"),
            "CI_NODE_STATUS_RENDER_DIR": str(render_dir),
        }
    )
    return env


def _profile_value(*, key: str) -> str:
    """One scalar out of the committed agent profile."""
    found = re.search(
        rf"^{re.escape(key)}=(?P<value>.*)$",
        _AGENT_PROFILE.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    assert found is not None, (
        f"{_AGENT_PROFILE} must declare {key} — it is the agent fact both the "
        f"role and the boot converge compose this credential's names from"
    )
    return found["value"].strip()


def _role_defaults() -> dict[str, str]:
    """The role's committed defaults, as a flat scalar map.

    Folded (`>-`) values are read through their first continuation line, which
    is every one this resolver needs; a value it cannot resolve leaves its
    placeholder behind and the expansion below refuses it by name.
    """
    return {
        found["key"]: found["value"].strip()
        for found in re.finditer(
            r"^(?P<key>node_status_credential_[a-z0-9_]+): (?:>-\n\s+)?(?P<value>.+)$",
            _ROLE_DEFAULTS.read_text(encoding="utf-8"),
            re.MULTILINE,
        )
    }


def _inventory_k3s_server() -> str:
    """The `ci_pool` member whose `cluster_role` is `server`, read from the inventory."""
    inventory = (_REPO_ROOT / "ansible" / "inventory" / "legacy.yml").read_text(encoding="utf-8")
    pool = inventory.split("        ci_pool:\n", 1)[1]
    server = re.search(
        r"^ {12}(?P<host>[\w.-]+):\n(?: {14}.*\n)*? {14}cluster_role: server$",
        pool,
        re.MULTILINE,
    )
    assert server is not None, "the inventory's ci_pool must name one server"
    return server["host"]


def _role_variables(*, render_dir: Path) -> dict[str, str]:
    """Every role variable the render invocation can name, fully expanded.

    The three the role derives at run time are derived here the way the role
    derives them: the node name comes from the agent's own profile, the
    ServiceAccount is the role's prefix and that node, and the k3s server is the
    inventory's `ci_pool` member whose `cluster_role` is `server`
    (livespec-dev-tooling-prdxxe). `phase2_dir` is resolved
    to the repository's own tree (the committed default spells it relative to
    `role_path`), and `render_dir` is redirected into `tmp_path`.
    """
    variables = _role_defaults()
    node = _profile_value(key="NODE_NAME")
    variables.update(
        {
            "node_status_credential_phase2_dir": str(_PHASE2),
            "node_status_credential_render_dir": str(render_dir),
            "node_status_credential_node": node,
            "node_status_credential_sa": (
                f"{variables.get('node_status_credential_sa_prefix', '')}{node}"
            ),
            "node_status_credential_server_host": _inventory_k3s_server(),
        }
    )
    for _ in range(len(variables)):
        variables = {
            key: _expand(text=value, variables=variables) for key, value in variables.items()
        }
    return variables


_PLACEHOLDER = re.compile(r"\{\{\s*(?P<name>[a-z0-9_]+)\s*\}\}")


def _expand(*, text: str, variables: dict[str, str]) -> str:
    """Substitute every `{{ name }}` this map knows, leaving the rest in place."""
    return _PLACEHOLDER.sub(
        lambda match: variables.get(match["name"], match[0]),
        text,
    )


def _role_render_command(*, render_dir: Path) -> list[str]:
    """The renderer invocation the role's own task makes, resolved to an argv.

    Extracted from the committed task rather than restated: the whole point of
    the fix is that the role no longer renders this credential itself, and a
    test that carried its own copy of the invocation would pass over a role that
    had drifted back to a second template.
    """
    task = re.search(
        r"ansible\.builtin\.script:\n\s+cmd: >-\n(?P<body>(?: {10}\S.*\n)+)",
        _ROLE_TASKS.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    assert task is not None, (
        f"{_ROLE_TASKS} must render this credential by RUNNING the committed "
        f"{_RENDERER.name} through `ansible.builtin.script`, so the role and the "
        f"boot converge share one renderer; no such task was found"
    )
    resolved = _expand(
        text=" ".join(task["body"].split()),
        variables=_role_variables(render_dir=render_dir),
    )
    assert "{{" not in resolved, (
        f"the role's render invocation still carries an unresolved variable, so "
        f"this test cannot run what the role runs: {resolved}"
    )
    argv = resolved.split()
    assert Path(argv[0]) == _RENDERER, (
        f"the role must render through the committed {_RENDERER}, which is the "
        f"renderer the boot converge calls; it names {argv[0]}"
    )
    return argv


def _converge_render_script(*, render_dir: Path) -> str:
    """A bash script that runs the CONVERGE's own renderer invocation.

    The converge's `NODE_STATUS_*` and `GATES_SERVER` assignments and its
    renderer invocation are lifted verbatim out of the committed script and
    executed, so the namespace, the ServiceAccount prefix and — the field this
    bug turned on — the API-server address are the converge's own rather than
    this test's idea of them. Only the agent node name and the renderer's path
    are supplied, because step 10d reads the first from the live cluster and
    resolves the second against its own directory.
    """
    converge = _BOOT_CONVERGE.read_text(encoding="utf-8")
    assignments = re.findall(r"^(?:NODE_STATUS_[A-Z_]+|GATES_SERVER)=.*$", converge, re.MULTILINE)
    assert assignments, (
        f"{_BOOT_CONVERGE} must declare the NODE_STATUS_* facts step 10d renders "
        f"each agent's credential from; none were found"
    )
    invocation = re.search(
        r'"\$\{RENDER_SA_KUBECONFIG\}"(?P<args>(?:\s*\\\n\s+.*)+?); then',
        converge,
    )
    assert invocation is not None, (
        f"{_BOOT_CONVERGE} must call the renderer for each agent node; no "
        f"invocation of RENDER_SA_KUBECONFIG was found"
    )
    body = " ".join(invocation["args"].replace("\\\n", " ").split())
    return (
        "set -euo pipefail\n"
        f'node="{_profile_value(key="NODE_NAME")}"\n'
        f'RENDER_SA_KUBECONFIG="{_RENDERER}"\n' + "\n".join(assignments) + "\n"
        f'install -d -m 0755 "{render_dir}"\n'
        f'"${{RENDER_SA_KUBECONFIG}}" {body}\n'
    )


def _run(*, argv: list[str], env: dict[str, str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run one rendering, failing the test with the renderer's own words."""
    completed = subprocess.run(
        argv,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=_RENDER_TIMEOUT_SECONDS,
        check=False,
    )
    assert completed.returncode == 0, (
        f"the rendering `{' '.join(argv)}` failed; a rendering that does not "
        f"complete cannot be compared:\n{completed.stdout}{completed.stderr}"
    )
    return completed


def test_the_role_and_the_boot_converge_render_byte_identical_agent_kubeconfigs(
    *, tmp_path: Path
) -> None:
    """The Definition-of-Done assertion, run rather than modelled.

    One stand-in `kubectl` serves both renderings the same ServiceAccount token
    and the same cluster CA, and each rendering is driven by its OWN caller's
    invocation — the role's resolved task and the converge's executed lines. The
    comparison is the whole file, so it holds the two to every field, every
    ordering, every indent AND the API-server address each caller passes: a
    difference in any one of them is a drift report that reports a change after
    every reboot.
    """
    bin_dir = _scratch_bin(tmp_path=tmp_path)
    role_dir = tmp_path / "role-render"
    converge_dir = tmp_path / "converge-render"
    node = _profile_value(key="NODE_NAME")

    role_argv = _role_render_command(render_dir=role_dir)
    _run(
        argv=role_argv,
        env=_render_environment(bin_dir=bin_dir, tmp_path=tmp_path, render_dir=role_dir),
        cwd=tmp_path,
    )
    _run(
        argv=["bash", "-c", _converge_render_script(render_dir=converge_dir)],
        env=_render_environment(bin_dir=bin_dir, tmp_path=tmp_path, render_dir=converge_dir),
        cwd=tmp_path,
    )

    by_role = (role_dir / f"node-status-{node}.kubeconfig").read_bytes()
    by_converge = (converge_dir / f"node-status-{node}.kubeconfig").read_bytes()
    chown_log = (tmp_path / "chown.log").read_text(encoding="utf-8")

    assert b"kind: Config" in by_role
    assert by_role == by_converge, (
        "the role and the boot converge render this agent's node-status "
        "credential differently, so the agent's copy and the server's differ "
        "after every reboot and the drift report can never read clean:\n"
        f"--- role ---\n{by_role.decode('utf-8')}\n"
        f"--- boot converge ---\n{by_converge.decode('utf-8')}"
    )
    assert chown_log.count(_EXPECTED_OWNERSHIP) == 2


def test_the_role_carries_no_kubeconfig_template_of_its_own() -> None:
    """The regression this fix forecloses: a SECOND renderer, added back later.

    Byte-identity above is checked against the role's invocation of the shared
    renderer, so it would keep passing if a later pass left that task in place
    and delivered a hand-written template beside it. The marker is
    `current-context:`, which only a kubeconfig written out in full carries —
    `kind: Config` cannot serve, because the role's refusal of a
    non-kubeconfig fetch quotes it.
    """
    tasks = _ROLE_TASKS.read_text(encoding="utf-8")

    assert _TEMPLATE_MARKER not in tasks, (
        f"{_ROLE_TASKS} writes a kubeconfig out in full; the agent credential "
        f"has ONE renderer, {_RENDERER}, and a second template of it is the "
        f"defect this slice removed"
    )
