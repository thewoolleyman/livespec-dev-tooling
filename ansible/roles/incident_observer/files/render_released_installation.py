#!/usr/bin/env python3
"""Render the released-installation manifest the independent incident observer verifies.

Work-item livespec-dev-tooling-w7n3ad (plan expedited-incident-response-flag).

Run with the INSTALLATION's own interpreter, isolated:

    /opt/livespec-incident/venv/bin/python -I render_released_installation.py \\
        --release v1.178.0 --revision <40-hex> --reader-release v0.290.0 \\
        --reader-script /opt/livespec-incident/reader/<plugin>/bin/incident_authority.py \\
        --config /etc/livespec-incident/controller.json --required-job ci-green

It prints the manifest JSON on stdout and writes nothing: the role installs the
output at the manifest path with the ownership and mode the service demands.

WHY THIS IS NOT A HAND-WRITTEN FILE. `incident_controller_installation.py`
authenticates the installation at every start by recomputing a digest over every
`.py` of the installed package in `sorted(root.rglob("*.py"))` order, and by
hashing every executable the reader and principal argv name plus the resolved
serving interpreter. Those are facts of the host (the interpreter's version
selects the site-packages path; `Path` ordering is Python's, not the shell's),
so the manifest is rendered on the host by the interpreter that will serve it.
`package_digest` below is byte-for-byte the service's algorithm; the repository's
test holds the two together.

The argv it renders:

  reader     [<interpreter>, <reader script>] -- the orchestrator plugin's
             canonical `incident_authority.py`; `read-current` and its flags are
             appended by the service. It is a shebang wrapper that needs its own
             directory on sys.path (`from _bootstrap import bootstrap`), so it
             is deliberately NOT given -I; the unit clears PYTHONPATH and every
             other injection variable instead.
  principal  [<interpreter>, -I, <installed incident_recovery_principal_service.py>,
             <controller.json>] -- the live recovery principal
             (docs/incident-recovery-principal.md). It acts on the forge only
             as the dedicated recovery App, whose credential it reads from the
             protected `recovery-app.json` beside controller.json; without that
             file every forge operation refuses by name.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path

__all__: list[str] = ["ManifestInputs", "package_digest", "render_manifest"]

_PRINCIPAL_MODULE = "incident_recovery_principal_service.py"
_ARGV_SEPARATORS = frozenset({"-I", "--"})


@dataclass(frozen=True, kw_only=True)
class ManifestInputs:
    """Everything the manifest carries that is not computed from the installation."""

    release: str
    revision: str
    reader_release: str
    reader_script: Path
    config: Path
    required_jobs: tuple[str, ...]
    interpreter: Path


def package_digest(*, root: Path) -> str:
    """Digest every `.py` under the package root exactly as the service does."""
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*.py")):
        digest.update(str(path.relative_to(root)).encode() + b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()


def render_manifest(*, inputs: ManifestInputs, package_root: Path) -> dict[str, object]:
    """Render the eight-key manifest; every executable path is hashed as found."""
    interpreter = str(inputs.interpreter)
    reader = [interpreter, str(inputs.reader_script)]
    principal = [interpreter, "-I", str(package_root / _PRINCIPAL_MODULE), str(inputs.config)]
    files: dict[str, str] = {}
    for value in (*reader, *principal, str(inputs.interpreter.resolve())):
        if value not in _ARGV_SEPARATORS:
            files[value] = hashlib.sha256(Path(value).read_bytes()).hexdigest()
    return {
        "release": inputs.release,
        "revision": inputs.revision,
        "package_sha256": package_digest(root=package_root),
        "reader": reader,
        "reader_release": inputs.reader_release,
        "principal": principal,
        "files": files,
        "required_jobs": list(inputs.required_jobs),
    }


def _parse(argv: list[str]) -> ManifestInputs:
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.add_argument("--release", required=True)
    _ = parser.add_argument("--revision", required=True)
    _ = parser.add_argument("--reader-release", required=True)
    _ = parser.add_argument("--reader-script", required=True, type=Path)
    _ = parser.add_argument("--config", required=True, type=Path)
    _ = parser.add_argument("--required-job", action="append", required=True)
    _ = parser.add_argument("--interpreter", type=Path, default=Path(sys.executable))
    args = parser.parse_args(argv)
    return ManifestInputs(
        release=args.release,
        revision=args.revision,
        reader_release=args.reader_release,
        reader_script=args.reader_script,
        config=args.config,
        required_jobs=tuple(args.required_job),
        interpreter=args.interpreter,
    )


def main(argv: list[str] | None = None) -> int:
    """Refuse a release that is not the installed distribution; otherwise print JSON."""
    inputs = _parse(sys.argv[1:] if argv is None else argv)
    installed = "v" + importlib.metadata.version("livespec-dev-tooling")
    if installed != inputs.release:
        _ = sys.stderr.write(
            f"refused: --release {inputs.release} but the interpreter's installed "
            f"livespec-dev-tooling is {installed}; install the release first\n"
        )
        return 2
    spec = importlib.util.find_spec("livespec_dev_tooling")
    if spec is None or spec.origin is None:
        _ = sys.stderr.write("refused: livespec_dev_tooling is not importable here\n")
        return 2
    manifest = render_manifest(inputs=inputs, package_root=Path(spec.origin).resolve().parent)
    _ = sys.stdout.write(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
