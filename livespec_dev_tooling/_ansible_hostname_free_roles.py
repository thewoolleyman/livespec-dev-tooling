"""The role-tree half of `ansible_hostname_free`: a role's VALUES name no machine.

A machine is bound ONLY through the inventory's host groups and host variables
(the maintainer's 2026-10-15 ruling, livespec-dev-tooling-prdxxe). The parent
module owns the INVENTORY's host names, the play scan and the report; this one
owns every read of a value out of `ansible/roles`:

- **YAML.** A role's defaults, vars, tasks, handlers and meta must not carry a
  machine name as a VALUE. A line fails when it contains an inventory host's
  tailnet name (`<host>.<tailnet>.ts.net`, alone or inside a URL), or when it
  assigns a value that equals an inventory host name (`key: host`, `- host`).
- **Templates.** The same two rules over a `.j2`, against its assignments.
- **Executables.** The files a role INSTALLS and a host then RUNS — by mode bit
  or by shebang, because the tree carries both. This is the rule the check
  lacked, and it is where the names it missed actually lived: a
  `${GATES_REMOTE_HOST:-poweredge-xubuntu}` default in a shipped refresh tool, a
  host as an ssh `ProxyJump` target, a host as a directory component of a
  key path, a `restic --host vps` argument (livespec-dev-tooling-mavj5i,
  measured 2026-10-19 on master cc607f3e with the check passing).

WHAT "AS A VALUE" MEANS IN A SHELL LINE, and why it cannot be the YAML rule. A
YAML value is the whole scalar, so `key: host` is an assignment and prose
mentioning a host inside a longer sentence is not. A shell line has no such
shape: the name arrives as a path component, after an `@`, inside a `${VAR:-…}`
default, or as the bare word after an option. So a shell line is read as FIELDS —
split on whitespace and on the punctuation that separates a value from its
surroundings, with `:-` flattened first because it is the default-expansion
separator, and a leading `-` stripped so an option's own argument is reached —
and a field EQUAL to an inventory host name is that host named as a value.

Flattening `:-` is load-bearing for the TAILNET rule too, not only for the field
split: that pattern refuses a `-` immediately before the name so a hyphenated
word ending in a host name is not a match, and inside `${VAR:-vps.…}` that `-`
is exactly the character before it. Un-flattened, the one shipped script that
carried a tailnet address was invisible to the pattern meant to find it.

Comments are provenance, not placement, and are skipped: YAML `#` comments,
Jinja `{# … #}` comments plus `#`/`;` comment lines in templates, and `#`
comment lines in executables. `measured on vps:` survives the field split as
`vps:`, which is not a host name, so a provenance sentence inside a refusal
message passes; `vps-restic-backup` and `arq-vps-backup` survive as themselves,
so a path the installers created and a service account do too.

Private sibling module (the leading underscore marks it), imported by
`ansible_hostname_free`. Only the three names in `__all__` cross that boundary:
pyright strict (`reportPrivateUsage`) and `check-private-calls` both refuse an
import of a `_`-prefixed name defined in another module.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import NamedTuple

__all__: list[str] = [
    "Finding",
    "role_findings",
    "strip_quotes",
]


_ROLES_DIR = Path("ansible") / "roles"
_YAML_SUFFIXES = (".yml", ".yaml")
_TEMPLATE_SUFFIX = ".j2"

_YAML_VALUE = re.compile(r"^\s*(?:-\s+)?(?:[\w.-]+:\s+)?(\S.*)$")
_TEMPLATE_ASSIGNMENT = re.compile(r"^\s*[\w.-]+\s*[:=]\s*(\S.*)$")
_JINJA_COMMENT = re.compile(r"\{#.*?#\}", re.DOTALL)
_TRAILING_YAML_COMMENT = re.compile(r"\s+#.*$")
# The punctuation that separates a shell value from its surroundings. A bare `:`
# is deliberately absent: `vps:` ending a sentence must stay one field, or every
# provenance line that names a host becomes a finding.
_SHELL_FIELD_SPLIT = re.compile(r"""[\s=@/,${}"'()\[\]|&;<>]""")
_SHELL_DEFAULT_EXPANSION = re.compile(r":-")
_SHEBANG = "#!"
_EXECUTABLE_BITS = 0o111


class Finding(NamedTuple):
    path: str
    line: int
    kind: str
    token: str


def strip_quotes(*, value: str) -> str:
    return value.strip().strip("'\"").strip()


def _tailnet_pattern(*, hosts: set[str]) -> re.Pattern[str] | None:
    if not hosts:
        return None
    names = "|".join(re.escape(host) for host in sorted(hosts, key=len, reverse=True))
    return re.compile(rf"(?<![\w.-])(?:{names})\.[A-Za-z0-9-]+\.ts\.net(?![\w-])")


def _tailnet_findings(
    *, path: str, number: int, line: str, tailnet: re.Pattern[str] | None
) -> list[Finding]:
    if tailnet is None:
        return []
    return [
        Finding(path=path, line=number, kind="tailnet-name", token=hit.group(0))
        for hit in tailnet.finditer(line)
    ]


def _yaml_line_findings(
    *, path: str, number: int, raw: str, hosts: set[str], tailnet: re.Pattern[str] | None
) -> list[Finding]:
    if raw.lstrip().startswith("#"):
        return []
    line = _TRAILING_YAML_COMMENT.sub("", raw)
    findings = _tailnet_findings(path=path, number=number, line=line, tailnet=tailnet)
    value = _YAML_VALUE.match(line)
    if value is not None and strip_quotes(value=value.group(1)) in hosts:
        findings.append(
            Finding(
                path=path, line=number, kind="host-value", token=strip_quotes(value=value.group(1))
            )
        )
    return findings


def _template_findings(
    *, path: str, source: str, hosts: set[str], tailnet: re.Pattern[str] | None
) -> list[Finding]:
    blanked = _JINJA_COMMENT.sub(lambda hit: "\n" * hit.group(0).count("\n"), source)
    findings: list[Finding] = []
    for number, raw in enumerate(blanked.splitlines(), start=1):
        if raw.lstrip().startswith(("#", ";")):
            continue
        findings.extend(_tailnet_findings(path=path, number=number, line=raw, tailnet=tailnet))
        assignment = _TEMPLATE_ASSIGNMENT.match(raw)
        if assignment is not None and strip_quotes(value=assignment.group(1)) in hosts:
            findings.append(
                Finding(
                    path=path,
                    line=number,
                    kind="host-value",
                    token=strip_quotes(value=assignment.group(1)),
                )
            )
    return findings


def _executable_findings(
    *, path: str, source: str, hosts: set[str], tailnet: re.Pattern[str] | None
) -> list[Finding]:
    findings: list[Finding] = []
    for number, raw in enumerate(source.splitlines(), start=1):
        if raw.lstrip().startswith("#"):
            continue
        flat = _SHELL_DEFAULT_EXPANSION.sub("  ", raw)
        findings.extend(_tailnet_findings(path=path, number=number, line=flat, tailnet=tailnet))
        findings.extend(
            Finding(path=path, line=number, kind="host-value", token=field)
            for field in (part.lstrip("-") for part in _SHELL_FIELD_SPLIT.split(flat))
            if field in hosts
        )
    return findings


def _is_executable(*, path: Path, source: str) -> bool:
    """A mode bit is file hygiene; a shebang is intent. The tree carries both.

    Measured in this repository's own `docker_engine` acceptance tree: of the
    FAULTS case scripts that named a machine, `faults/lib.sh` carried the
    executable bit and NO shebang while `faults/p05_p06.sh` carried a shebang and
    mode 0644. Keying on either alone would read half of them as data.
    """
    return bool(path.stat().st_mode & _EXECUTABLE_BITS) or source.startswith(_SHEBANG)


def role_findings(*, cwd: Path, hosts: set[str]) -> list[Finding]:
    """Every machine name carried as a value under `ansible/roles`."""
    tailnet = _tailnet_pattern(hosts=hosts)
    findings: list[Finding] = []
    for path in sorted((cwd / _ROLES_DIR).rglob("*")):
        if not path.is_file():
            continue
        relative = str(path.relative_to(cwd))
        source = path.read_text(encoding="utf-8")
        if path.suffix in _YAML_SUFFIXES:
            for number, raw in enumerate(source.splitlines(), start=1):
                findings.extend(
                    _yaml_line_findings(
                        path=relative, number=number, raw=raw, hosts=hosts, tailnet=tailnet
                    )
                )
        elif path.suffix == _TEMPLATE_SUFFIX:
            findings.extend(
                _template_findings(path=relative, source=source, hosts=hosts, tailnet=tailnet)
            )
        elif _is_executable(path=path, source=source):
            findings.extend(
                _executable_findings(path=relative, source=source, hosts=hosts, tailnet=tailnet)
            )
    return findings
