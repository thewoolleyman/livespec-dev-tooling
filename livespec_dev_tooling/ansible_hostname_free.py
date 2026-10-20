"""ansible_hostname_free — no playbook or role under `ansible/` names a machine.

The maintainer ruled on 2026-10-15 (livespec-dev-tooling-prdxxe, plan
`petri-factory-on-gmktec`) that a machine is bound ONLY through the
inventory's host groups and host variables, because the factory moves onto
Kubernetes later and a hostname baked into a play or a role default is a
second, silent place that binding lives. This check refuses a regression:

- **Plays.** Every `hosts:` field in a playbook at `ansible/*.yml` must name
  inventory groups only. A pattern token that equals an inventory HOST name
  fails, whatever operators surround it (`a:b`, `a:&b`, `a:!b`, `a,b`).
- **Roles.** A role's defaults, vars, tasks, handlers, meta, templates and the
  EXECUTABLES it installs must not carry a machine name as a VALUE. That half
  lives in `_ansible_hostname_free_roles`, which also carries why a shell line
  is read as FIELDS rather than as a whole scalar.

Comments are provenance, not placement, and are skipped. Prose that merely
mentions a host inside a longer value (`server string = vps Arq backup source`)
is not an assignment of that host and passes.

Inventory host names are read from the committed inventory itself: every key
directly under a `hosts:` mapping in `ansible/inventory/*.yml`, plus every
`ansible/inventory/host_vars/<host>.yml` stem. The scan covers `ansible/`
only; the repository's `tests/` tree is out of scope by design, because it
keeps playbook fixtures that name hosts on purpose.

Repo-private check: the module lives OUTSIDE `livespec_dev_tooling/checks/`
so it stays out of the canonical (fleet-universal) slug set. Wired into this
repo's justfile `check:` aggregate (repo-private block).

Output discipline: structlog JSON to stderr; no `print`, no
`sys.stderr.write`.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

from livespec_dev_tooling._ansible_hostname_free_roles import (  # noqa: E402
    Finding,
    role_findings,
    strip_quotes,
)

__all__: list[str] = []


_ANSIBLE_DIR = Path("ansible")
_INVENTORY_DIR = _ANSIBLE_DIR / "inventory"

_HOSTS_BLOCK = re.compile(r"^(\s*)hosts:\s*$")
_MAPPING_KEY = re.compile(r"^(\s*)([A-Za-z0-9_.-]+):")
_PLAY_HOSTS = re.compile(r"^\s*(?:-\s+)?hosts:\s*(\S.*)$")
_PATTERN_SPLIT = re.compile(r"[:,]")
_TRAILING_YAML_COMMENT = re.compile(r"\s+#.*$")

_REMEDIATION = (
    "bind the machine through the inventory instead: target an inventory group "
    "in a play's hosts field, and read a host-specific value from host_vars or "
    "resolve it from an inventory group (for the k3s server, the ci_pool member "
    "whose cluster_role is server). A shipped executable takes the value from a "
    "variable the role renders, and REFUSES when it is unset rather than "
    "defaulting to a machine name"
)


def _hosts_in_inventory_source(*, source: str) -> set[str]:
    """Return every key directly under a `hosts:` mapping in one inventory file."""
    hosts: set[str] = set()
    block_indent: int | None = None
    child_indent: int | None = None
    for raw in source.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        opener = _HOSTS_BLOCK.match(raw)
        indent = len(raw) - len(raw.lstrip())
        if block_indent is not None and indent <= block_indent:
            block_indent = None
        if opener is not None:
            block_indent = len(opener.group(1))
            child_indent = None
            continue
        if block_indent is None:
            continue
        if child_indent is None:
            child_indent = indent
        key = _MAPPING_KEY.match(raw)
        if key is not None and len(key.group(1)) == child_indent:
            hosts.add(key.group(2))
    return hosts


def _inventory_hosts(*, cwd: Path) -> set[str]:
    inventory = cwd / _INVENTORY_DIR
    hosts: set[str] = set()
    for path in sorted(inventory.glob("*.yml")) + sorted(inventory.glob("*.yaml")):
        hosts |= _hosts_in_inventory_source(source=path.read_text(encoding="utf-8"))
    host_vars = inventory / "host_vars"
    for path in sorted(host_vars.glob("*.yml")) + sorted(host_vars.glob("*.yaml")):
        hosts.add(path.stem)
    return hosts


def _play_findings(*, path: str, source: str, hosts: set[str]) -> list[Finding]:
    findings: list[Finding] = []
    for number, raw in enumerate(source.splitlines(), start=1):
        match = _PLAY_HOSTS.match(_TRAILING_YAML_COMMENT.sub("", raw))
        if match is None:
            continue
        pattern = strip_quotes(value=match.group(1))
        for token in _PATTERN_SPLIT.split(pattern):
            name = token.strip().lstrip("!&")
            if name in hosts:
                findings.append(Finding(path=path, line=number, kind="play-hosts", token=name))
    return findings


def _findings(*, cwd: Path) -> list[Finding]:
    hosts = _inventory_hosts(cwd=cwd)
    findings: list[Finding] = []
    playbooks = sorted((cwd / _ANSIBLE_DIR).glob("*.yml")) + sorted(
        (cwd / _ANSIBLE_DIR).glob("*.yaml")
    )
    for path in playbooks:
        findings.extend(
            _play_findings(
                path=str(path.relative_to(cwd)),
                source=path.read_text(encoding="utf-8"),
                hosts=hosts,
            )
        )
    findings.extend(role_findings(cwd=cwd, hosts=hosts))
    return findings


def main() -> int:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    log = structlog.get_logger("ansible_hostname_free")
    findings = _findings(cwd=Path.cwd())
    for finding in findings:
        log.error(
            "ansible tree names a machine outside the inventory",
            path=finding.path,
            line=finding.line,
            kind=finding.kind,
            token=finding.token,
            remediation=_REMEDIATION,
        )
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
