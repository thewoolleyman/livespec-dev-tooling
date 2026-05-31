"""Consumer-tier: a check attempts forbidden network I/O.

Covers the `SPECIFICATION/scenarios.md` scenario "a check attempts
forbidden network I/O" — the `no-network-io` gate that asserts every
check stays within the local-filesystem + project-local-subprocess
envelope (per `SPECIFICATION/constraints.md` §"No network I/O").

The scenario notes the gate is "sketch only — the gate may itself be
tested by a sandboxed firewall fixture or by AST inspection." This test
takes the AST-inspection path:

- The consumer-observable invariant: EVERY shipped check module under
  `livespec_dev_tooling/checks/` is free of network-library imports, so a
  consumer's `just check` is deterministic against the working tree alone
  regardless of network availability.
- The gate's detection logic: a fixture check module that imports a
  forbidden network library IS detected by the same AST scan — proving
  the gate would fail the build for a network-touching check.

AST inspection (never executing the modules) keeps this deterministic
and offline, consistent with the constraint it guards.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CHECKS_DIR = _REPO_ROOT / "livespec_dev_tooling" / "checks"

# Top-level package names whose import implies network I/O (sockets,
# HTTP(S) clients, mail/FTP/telnet, async network stacks). Reaching a
# remote endpoint or opening a socket is forbidden in check modules per
# `constraints.md` §"No network I/O".
_FORBIDDEN_NETWORK_ROOTS: frozenset[str] = frozenset(
    {
        "socket",
        "ssl",
        "urllib",
        "http",
        "ftplib",
        "telnetlib",
        "smtplib",
        "poplib",
        "imaplib",
        "requests",
        "httpx",
        "aiohttp",
        "websockets",
        "xmlrpc",
    }
)


def _imported_roots(*, source: str) -> set[str]:
    """The set of top-level module roots imported by `source` (via AST)."""
    tree = ast.parse(source)
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".", 1)[0])
        elif isinstance(node, ast.ImportFrom) and node.module is not None and node.level == 0:
            roots.add(node.module.split(".", 1)[0])
    return roots


def _network_imports(*, source: str) -> set[str]:
    return _imported_roots(source=source) & _FORBIDDEN_NETWORK_ROOTS


def test_no_shipped_check_imports_a_network_library() -> None:
    """Every shipped check module is free of forbidden network-library imports.

    The consumer-observable determinism guarantee: a consumer's `just check`
    never depends on network availability.
    """
    # Map each shipped module to its set of forbidden network-library roots
    # (almost always empty). Asserting the union across all modules is empty
    # avoids a conditionally-dead `if found:` branch while still surfacing the
    # full per-module mapping in the failure message when the invariant breaks.
    per_module = {
        module_path.name: _network_imports(source=module_path.read_text(encoding="utf-8"))
        for module_path in sorted(_CHECKS_DIR.glob("*.py"))
    }
    all_network_roots: set[str] = set().union(*per_module.values())

    assert not all_network_roots, (
        f"no check module may import a network library "
        f'(constraints.md §"No network I/O"); per-module imports={per_module}'
    )


def test_gate_detects_a_network_touching_fixture_check(*, tmp_path: Path) -> None:
    """A fixture check that imports a network library IS caught by the gate's scan.

    Proves the gate would fail the build for a network-touching check — the
    scenario's "the gate fails the build" outcome.
    """
    fixture = tmp_path / "naughty_check.py"
    fixture.write_text(
        "from __future__ import annotations\n"
        "\n"
        "import urllib.request\n"
        "\n"
        "\n"
        "def main() -> int:\n"
        '    urllib.request.urlopen("https://example.com")\n'
        "    return 0\n",
        encoding="utf-8",
    )

    found = _network_imports(source=fixture.read_text(encoding="utf-8"))

    assert "urllib" in found, (
        f"the no-network-io scan must catch a check importing `urllib`; " f"found={found}"
    )
