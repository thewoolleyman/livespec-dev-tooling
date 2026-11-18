"""Run the incident-merge principal for ONE expedited repair pull request.

    python -I -m livespec_dev_tooling.incident_merge_runner --pr <number>

This is the production binding of the ratified `Incident-merge principal.` contract
(SPECIFICATION/contracts.md, the expedited incident execution contract): it connects
the principal's injected seams to the host and calls `merge_incident_repair` once.

- The App credential is the root-owned 0600 file the incident_observer role projects; the
  runner REFUSES TO START, naming which condition failed, when it is absent, not owned by
  root, or not mode 0600 (`_incident_merge_credential`).
- The chain, queue and record seams are `_incident_merge_bindings`.
- The pull request number is mandatory: there is no mode that scans for work.

Exit status: 0 merged; 1 the principal refused (the refusal is named on stdout and was
recorded on the incident work item); 2 the runner could not start. Nothing is reported as
merged unless the principal confirmed the merge on the forge.
"""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from livespec_dev_tooling._incident_app_installation import AppRefusal
from livespec_dev_tooling._incident_merge_bindings import (
    ArmIdentity,
    LedgerWriteError,
    TextRunner,
    authority_chain_reader,
    authority_command,
    graphql_queue_reader,
    ledger_recorder,
    read_arm_identity,
    run_text,
    token_forge_reader,
)
from livespec_dev_tooling._incident_merge_credential import (
    DEFAULT_CREDENTIAL_PATH,
    load_merge_credential,
)
from livespec_dev_tooling.checks._effective_required_checks import ForgeReader
from livespec_dev_tooling.config import load_config
from livespec_dev_tooling.incident_merge_app import MergeForge
from livespec_dev_tooling.incident_merge_principal import Merged, merge_incident_repair
from livespec_dev_tooling.incident_protected_path import protected_path

__all__: list[str] = ["main", "run"]

DEFAULT_REPOSITORY = "livespec-ai/livespec-dev-tooling"
DEFAULT_STATE_DIR = Path("/var/lib/livespec-incident/receipts")
_MERGED, _REFUSED, _NOT_STARTED, _UNRECORDED = 0, 1, 2, 3
# The files `bd` and the canonical authority read from the ledger root, relative to it.
_LEDGER_FILES = (".beads/config.yaml", ".beads/metadata.json", ".livespec.jsonc")


def _parse(*, argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="incident_merge_runner")
    _ = parser.add_argument("--pr", required=True, type=int)
    _ = parser.add_argument("--repository", default=DEFAULT_REPOSITORY)
    _ = parser.add_argument("--credential", type=Path, default=DEFAULT_CREDENTIAL_PATH)
    _ = parser.add_argument("--state-dir", type=Path, default=DEFAULT_STATE_DIR)
    _ = parser.add_argument("--project-root", type=Path, default=Path.cwd())
    _ = parser.add_argument("--authority-script", required=True, type=Path)
    _ = parser.add_argument("--ledger-root", type=Path, default=None)
    return parser.parse_args(list(argv))


def _say(*, text: str) -> None:
    _ = sys.stdout.write(f"{text}\n")


def _not_started(*, code: str, detail: str) -> int:
    _say(text=f"incident-merge-runner-refused: {code}: {detail}")
    return _NOT_STARTED


@dataclass(frozen=True, kw_only=True)
class _Ready:
    forge: MergeForge
    identity: ArmIdentity
    command: Sequence[str]
    principal: str
    ledger_root: Path


def _prepare(
    *,
    args: argparse.Namespace,
    owner_uid: int,
    connect: Callable[..., MergeForge | AppRefusal],
    interpreter: Path,
) -> _Ready | int:
    """Everything that must hold before the principal runs, or the exit status for why not."""
    config = load_config(repo_root=args.project_root)
    credential = load_merge_credential(
        path=args.credential,
        owner_uid=owner_uid,
        merge_integration_id=config.incident_merge_integration_id,
        recovery_integration_id=config.recovery_bypass_integration_id,
    )
    if isinstance(credential, AppRefusal):
        return _not_started(code=credential.code, detail=credential.detail)
    forge = connect(repository=args.repository, credential=credential)
    if isinstance(forge, AppRefusal):
        return _not_started(code=forge.code, detail=forge.detail)
    identity = read_arm_identity(
        state_dir=args.state_dir, repository=args.repository, pr_number=args.pr
    )
    if isinstance(identity, str):
        return _not_started(code="incident-merge-runner-no-arm", detail=identity)
    command = _authority_command(script=args.authority_script, interpreter=interpreter)
    if isinstance(command, int):
        return command
    ledger_root = _ledger_root(root=args.ledger_root)
    if isinstance(ledger_root, int):
        return ledger_root
    return _Ready(
        forge=forge,
        identity=identity,
        command=command,
        principal=f"incident-merge-app-{credential.app_id}",
        ledger_root=ledger_root,
    )


def _authority_command(*, script: Path, interpreter: Path) -> list[str] | int:
    """The authority command, only when the script and interpreter are protected; else why not.

    The runner is root, so it executes only a root-owned build: the script and the serving
    interpreter, with every ancestor directory and each resolved target, must be owned by root
    (or the running account) and writable by neither group nor other, the rule the observer's
    loader applies to its own reader.
    """
    if not script.exists():
        return _not_started(
            code="incident-merge-runner-no-authority",
            detail=f"no canonical incident authority script at {script}",
        )
    unprotected = [str(path) for path in (script, interpreter) if not protected_path(path=path)]
    if unprotected:
        return _not_started(
            code="incident-merge-runner-authority-unprotected",
            detail=f"not root-owned and unwritable by group and other: {', '.join(unprotected)}",
        )
    return authority_command(interpreter=interpreter, script=script)


def _ledger_root(*, root: Path | None) -> Path | int:
    """The root-owned ledger tree, only when every file `bd` and the authority read is protected.

    `bd` takes its tenant and Dolt host from the working directory's `.beads` pointer, and the
    authority takes its store configuration from `--repo`, so a tree an unprivileged account
    can write would let it choose where root's ledger credential goes.
    """
    if root is None:
        return _not_started(
            code="incident-merge-runner-no-ledger-root", detail="no --ledger-root was given"
        )
    files = [root / name for name in _LEDGER_FILES]
    absent = [str(path) for path in (root, *files) if not path.exists()]
    if absent:
        return _not_started(
            code="incident-merge-runner-no-ledger-root",
            detail=f"missing from the ledger root: {', '.join(absent)}",
        )
    unprotected = [str(path) for path in (root, *files) if not protected_path(path=path)]
    if unprotected:
        return _not_started(
            code="incident-merge-runner-ledger-root-unprotected",
            detail=f"not root-owned and unwritable by group and other: {', '.join(unprotected)}",
        )
    return root


def run(  # noqa: PLR0913 — every host dependency is an injected seam.
    *,
    argv: Sequence[str],
    owner_uid: int = 0,
    interpreter: Path = Path(sys.executable),
    run_text_command: TextRunner = run_text,
    make_reader: Callable[..., ForgeReader] = token_forge_reader,
    connect: Callable[..., MergeForge | AppRefusal] = MergeForge.connect,
    clock: Callable[[], datetime] = lambda: datetime.now(tz=timezone.utc),
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """Merge one pull request or say, by name, why not; see the module docstring."""
    args = _parse(argv=argv)
    ready = _prepare(args=args, owner_uid=owner_uid, connect=connect, interpreter=interpreter)
    if isinstance(ready, int):
        return ready
    gating = make_reader(token=ready.forge.token)
    ledger = ledger_recorder(run=run_text_command)
    written: list[str] = []

    def record(*, incident_id: str, text: str) -> None:
        written.append(text)
        ledger(incident_id=incident_id, text=text)

    try:
        outcome = merge_incident_repair(
            repo=args.repository,
            incident_id=ready.identity.incident_id,
            pr_number=args.pr,
            principal=ready.principal,
            forge=ready.forge,
            check_reader=gating,
            chain=authority_chain_reader(
                command=ready.command,
                repository=args.repository,
                repo=ready.ledger_root,
                identity=ready.identity,
            ),
            queue=graphql_queue_reader(read=gating),
            record=record,
            clock=clock,
            sleep=sleep,
        )
    except LedgerWriteError as unrecorded:
        _say(text=f"incident-merge-runner-record-failed: {unrecorded}")
        for text in written[-1:]:
            for line in text.splitlines():
                _say(text=line)
        _say(text="the pull request may already be merged: read the forge")
        return _UNRECORDED
    if isinstance(outcome, Merged):
        _say(text=f"incident-merge-runner-merged: pr {args.pr} master {outcome.master_sha}")
        return _MERGED
    _say(text=f"incident-merge-runner-refused: {outcome.reason}: {outcome.detail}")
    return _REFUSED


def main() -> int:
    """Entry point: the pull request number comes only from the command line."""
    return run(argv=sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
