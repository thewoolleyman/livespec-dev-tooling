"""A refresh tool accepts a valid kubeconfig whatever its size, and never because of timing.

The three credential refresh tools (`refresh-gates-kubeconfig`,
`refresh-node-status-kubeconfig`, `refresh-factory-kubeconfig`) fetch a rendered
kubeconfig into a shell variable, then check it for two markers before they
overwrite anything. Each runs under `set -o pipefail`, and each checked the
markers as `printf '%s' "$rendered" | grep -q PATTERN`. `grep -q` exits on its
first match. Once it has, any further write from `printf` gets SIGPIPE, the
pipeline's status becomes 141, and `pipefail` turns a MATCH into a failure.
The tool then refused a valid kubeconfig as "NOT A KUBECONFIG" and left the
stale credential in place.

Whether `printf` still had bytes to write when `grep` exited is a matter of
scheduling. On a small answer the refusal was intermittent: about 1 run in 200
under load on the dev host, and it reddened livespec-dev-tooling master CI on
2026-11-02 (run 41407935442, test_the_refresh_tool_fetches_from_the_host_the_pool_supplies).
On an answer larger than a pipe buffer it is CERTAIN, because the reader exits
long before the writer finishes. A real kubeconfig carrying
`certificate-authority-data` gets closer to that than the small fixture does.

So this suite feeds each tool an answer far larger than a pipe buffer, with
both markers near the top. That makes the timing race deterministic. A tool
that reads the whole answer before judging it accepts the kubeconfig; a tool
that races its own reader refuses it on every run.

`ssh` and `id` are faked on a scratch PATH exactly as
`test_gates_kubeconfig_remote_host_required.py` fakes them, so no host is
contacted. The non-root `id -u` keeps each tool on its fetch-as-self branch.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ROLES = _REPO_ROOT / "ansible" / "roles"

# Far larger than a Linux pipe buffer (64 KiB), so `grep -q` always exits before
# the writer has finished.
_PADDING_BYTES = 512 * 1024

_LARGE_KUBECONFIG = (
    "apiVersion: v1\nkind: Config\nclusters:\n  - name: ci-runner\n"
    "    cluster:\n      server: https://an-answering-host.example.ts.net:6443\n"
    f"      certificate-authority-data: {'Q' * _PADDING_BYTES}\n"
    "users:\n  - name: submitter\n    user:\n      token: fixture\n"
)

_SSH_SHIM = """\
printf 'ssh %s\\n' "$*" >> "$ARGV_LOG"
cat "$FIXTURE_FILE"
exit 0
"""
_ID_SHIM = '[ "${1:-}" = -u ] && printf \'%s\\n\' 1000 && exit 0\nexec /usr/bin/id "$@"\n'


@dataclass(frozen=True, kw_only=True)
class _Tool:
    """One shipped refresh tool and the environment that points it at a scratch tree."""

    name: str
    script: Path
    dest_var: str
    env_file_var: str
    pool_facts: dict[str, str]


_TOOLS = (
    _Tool(
        name="refresh-gates-kubeconfig",
        script=_ROLES / "gates_kubeconfig" / "files" / "refresh-gates-kubeconfig",
        dest_var="GATES_KUBECONFIG",
        env_file_var="GATES_SSH_ENV",
        pool_facts={"GATES_REMOTE_HOST": "an-answering-host"},
    ),
    _Tool(
        name="refresh-node-status-kubeconfig",
        script=_ROLES / "node_status_credential" / "files" / "refresh-node-status-kubeconfig",
        dest_var="NODE_STATUS_KUBECONFIG",
        env_file_var="NODE_STATUS_REFRESH_ENV",
        pool_facts={
            "NODE_STATUS_REMOTE_HOST": "an-answering-host",
            "NODE_STATUS_NODE_NAME": "a-node",
        },
    ),
    _Tool(
        name="refresh-factory-kubeconfig",
        script=_ROLES / "factory_kubeconfig" / "files" / "refresh-factory-kubeconfig",
        dest_var="FACTORY_KUBECONFIG",
        env_file_var="FACTORY_REFRESH_ENV",
        pool_facts={
            "FACTORY_REMOTE_HOST": "an-answering-host",
            "FACTORY_SSH_USER": "a-login-user",
            "FACTORY_GROUP": "a-group",
        },
    ),
)


def _shim(*, bin_dir: Path, name: str, body: str) -> None:
    path = bin_dir / name
    _ = path.write_text(f"#!/usr/bin/env bash\n{body}", encoding="utf-8")
    path.chmod(0o755)


@pytest.mark.parametrize("tool", _TOOLS, ids=[tool.name for tool in _TOOLS])
def test_a_refresh_tool_accepts_a_valid_kubeconfig_larger_than_a_pipe_buffer(
    *, tool: _Tool, tmp_path: Path
) -> None:
    """The fetched kubeconfig is written to the destination, byte for byte."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    dest = tmp_path / "etc" / "ci-runner" / "fetched.kubeconfig"
    dest.parent.mkdir(parents=True)
    _shim(bin_dir=bin_dir, name="ssh", body=_SSH_SHIM)
    _shim(bin_dir=bin_dir, name="id", body=_ID_SHIM)
    # Through a file, not the environment: one environment string is capped at
    # 128 KiB by execve, well under the size this suite needs.
    fixture = tmp_path / "answer.kubeconfig"
    _ = fixture.write_text(_LARGE_KUBECONFIG, encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if not k.startswith(("COVERAGE_", "COV_CORE_"))}
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    env.update(
        {
            "ARGV_LOG": str(tmp_path / "argv.log"),
            "FIXTURE_FILE": str(fixture),
            tool.dest_var: str(dest),
            tool.env_file_var: str(tmp_path / "no-such-env-file"),
            **tool.pool_facts,
        }
    )

    completed = subprocess.run(
        ["bash", str(tool.script)],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    # Compared as a flag, not with `==` inside the assert: on a mismatch pytest
    # would diff two half-megabyte strings, which takes minutes.
    written = dest.read_text(encoding="utf-8")
    identical = written == _LARGE_KUBECONFIG
    assert identical, f"wrote {len(written)} bytes; the fetched answer was {len(_LARGE_KUBECONFIG)}"
