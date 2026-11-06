"""One claim writer of `ansible/claim-token-race-drill.yml`, and its read-back.

The drill proves orchestrator work item bd-ib-4eeefv's host-captured bullet:
two claim writers on different hosts, sharing only the Beads server, race to
change one active claim, and exactly one close reason lands on the contested
token while exactly one writer writes the item. This script is that writer. It
is copied to each host by the play and runs there against the released
orchestrator plugin the play cloned beside it, so the write it makes is the
package's own `change_claim` — the primitive every Dispatcher, valve and
recovery write goes through — and never a hand-rolled `bd close`.

THE PROBE ADDS ONE THING TO THE PACKAGE'S WRITE: A PAUSE. `BarrierClient`
delegates every ledger verb to the package's own client and, at the first
conditional close, waits for the drill's go signal (a line on a FIFO naming an
instant, or `now`). Both writers have then read the item, created their
successor tokens and reached the compare-and-swap, so the close is what races.
The sequential case gates the START instead: the second writer decides on a
read taken before the first writer wrote, and is released only after that
writer has finished, so its stand-down is the `still_as_decided` predicate
answering `False` on the fresh read, which the package reports `claim-changed`.

THE CREDENTIAL NEVER TOUCHES ARGV OR A FILE. A remote writer reads it from a
FIFO the play feeds over a pipelined task and sets it in its own process
environment, which is where the package's `bd` children read it; the control
node's writer inherits it from the environment the credential wrapper gave the
play. Nothing this script prints or writes carries the value.

Four verbs, all JSON on stdout or in the report file: `create` makes the probe
item (an `active` claim naming its first token, through the package's own
creation seam), `writer` is one racer, `inspect` reads the token chain back
from the server and grades the Definition of Done bullet, `dispose` wins the
item's token one last time and closes it. Exit 0 means the verb ran; a
writer's OUTCOME is data in its report, not its exit code.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import socket
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# The ledger half lives beside this file; `python -I` leaves the script's own
# directory off `sys.path`, so it is added here before the import.
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from claim_token_race_drill_barrier import BarrierClient, BarrierMissedError, wait_for_go
from claim_token_race_drill_ledger import (
    TOKEN_KEY,
    metadata_of,
    run_create,
    run_dispose,
    run_id_of,
    run_inspect,
    write_json,
)

__all__: list[str] = []

CREDENTIAL_ENV = "BEADS_DOLT_PASSWORD"  # the variable's NAME, never a value
_SERVER_HOST = "127.0.0.1"
_SERVER_PORT = 3307


@dataclass(frozen=True, kw_only=True)
class Plugin:
    """The handles this probe takes from the released package, by name."""

    store_config: Any
    make_client: Callable[..., Any]
    change_claim: Callable[..., Any]
    claim_row_from_record: Callable[..., Any]
    same_claim_row: Callable[..., Any]
    claim_stamp: Any
    claim_stamp_metadata: Callable[..., dict[str, Any]]
    transition_observations: dict[Any, float]
    work_item: Any
    create_work_item: Callable[..., None]
    new_work_item_id: Callable[..., str]


def load_plugin(*, scripts_root: Path) -> Plugin:
    """Import the released package from the clone's scripts tree and its vendor dir."""
    for entry in (scripts_root, scripts_root / "_vendor"):
        if str(entry) not in sys.path:
            sys.path.insert(0, str(entry))
    package = "livespec_orchestrator_beads_fabro"
    types = importlib.import_module(f"{package}.types")
    client = importlib.import_module(f"{package}._beads_client")
    tokens = importlib.import_module(f"{package}._store_claim_tokens")
    claim = importlib.import_module(f"{package}._store_dispatch_claim")
    guard = importlib.import_module(f"{package}.commands._dispatcher_claim_guard")
    mutations = importlib.import_module(f"{package}._store_mutations")
    ids = importlib.import_module(f"{package}._ids")
    if tokens.CLAIM_TOKEN_METADATA_KEY != TOKEN_KEY:
        msg = f"the released package names its token key {tokens.CLAIM_TOKEN_METADATA_KEY!r}"
        raise RuntimeError(msg)
    return Plugin(
        store_config=types.StoreConfig,
        make_client=client.make_beads_client,
        change_claim=tokens.change_claim,
        claim_row_from_record=claim.claim_row_from_record,
        same_claim_row=guard.same_claim_row,
        claim_stamp=claim.ClaimStamp,
        claim_stamp_metadata=claim.claim_stamp_metadata,
        transition_observations=guard.TRANSITION_OBSERVATIONS,
        work_item=types.WorkItem,
        create_work_item=mutations.create_work_item,
        new_work_item_id=ids.new_work_item_id,
    )


def store_config(*, plugin: Plugin, repo_root: Path, bd_path: str) -> Any:
    """The tenant descriptor, read from the clone's own `.beads/config.yaml`.

    No credential wrapper: the password is already in this process's
    environment, and the wrapper exists on the control node alone.
    """
    keys: dict[str, str] = {}
    for line in (repo_root / ".beads" / "config.yaml").read_text(encoding="utf-8").splitlines():
        name, separator, value = line.partition(":")
        if separator and not name.startswith("#"):
            keys[name.strip()] = value.strip()
    return plugin.store_config(
        tenant=keys["dolt.database"],
        prefix=keys["dolt.prefix"],
        server_user=keys["dolt.server-user"],
        database=keys["dolt.database"],
        bd_path=bd_path,
        server_host=keys.get("dolt.server-host", _SERVER_HOST),
        server_port=int(keys.get("dolt.server-port", _SERVER_PORT)),
        socket=None,
        fake=False,
        repo_root=repo_root,
        credential_wrapper=(),
    )


def take_credential(*, fifo: Path | None, environ: dict[str, str]) -> None:
    """Put the tenant password in this process's environment, from the FIFO if given."""
    if fifo is not None:
        environ[CREDENTIAL_ENV] = fifo.read_text(encoding="utf-8").rstrip("\n")
    if not environ.get(CREDENTIAL_ENV):
        msg = f"{CREDENTIAL_ENV} is not set and no credential FIFO was given"
        raise SystemExit(msg)


def run_writer(*, args: argparse.Namespace, plugin: Plugin, client: Any) -> dict[str, Any]:
    """Decide on one read, wait for the go signal, make the package's claim write."""
    record = client.show_issue(issue_id=args.item)
    row = plugin.claim_row_from_record(record=record)
    decided = {
        "writer": args.writer,
        "token": metadata_of(record=record).get(TOKEN_KEY),
        "status": record.get("status"),
        "assignee": record.get("assignee"),
        "run_id": run_id_of(record=record),
        "read_at": time.time(),
    }
    write_json(path=args.decided, payload=decided)
    stamp = plugin.claim_stamp(
        dispatch_id=f"claim-token-race-drill:{args.case}",
        dispatching_host=args.host,
        run_id=args.run_id,
        factory_name=None,
        factory_server=None,
    )
    trace: dict[str, Any] = {}

    def go() -> float:
        return wait_for_go(fifo=args.go_fifo)

    if args.barrier_point == "start":
        trace["released_at"] = go()
    racer = BarrierClient(
        inner=client, barrier=go if args.barrier_point == "close" else None, trace=trace
    )
    report: dict[str, Any] = {
        **decided,
        "case": args.case,
        "host": args.host,
        "item": args.item,
        "writer_run_id": args.run_id,
    }
    try:
        result = plugin.change_claim(
            client=racer,
            work_item_id=args.item,
            writer=args.writer,
            intent=f"claim-token-race-drill:{args.case}",
            claim_tokens=True,
            metadata=plugin.claim_stamp_metadata(stamp=stamp),
            transition_observations=plugin.transition_observations,
            still_as_decided=plugin.same_claim_row(row=row),
        )
    except BarrierMissedError as missed:
        report.update(outcome="barrier-missed", detail=str(missed))
    else:
        report.update(outcome=result.outcome, successor_token_id=result.successor_token_id)
    report.update(trace=trace, finished_at=time.time())
    write_json(path=args.report, payload=report)
    return report


def parse_args(*, argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="claim_token_race_drill_probe")
    parser.add_argument("--scripts-root", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--bd-path", required=True)
    parser.add_argument("--host", default=socket.gethostname())
    parser.add_argument("--credential-fifo", type=Path, default=None)
    verbs = parser.add_subparsers(dest="verb", required=True)
    create = verbs.add_parser("create")
    create.add_argument("--title", required=True)
    create.add_argument("--description", required=True)
    writer = verbs.add_parser("writer")
    writer.add_argument("--item", required=True)
    writer.add_argument("--writer", required=True)
    writer.add_argument("--case", required=True)
    writer.add_argument("--run-id", required=True)
    writer.add_argument("--go-fifo", type=Path, required=True)
    writer.add_argument("--barrier-point", choices=("start", "close"), required=True)
    writer.add_argument("--decided", type=Path, required=True)
    writer.add_argument("--report", type=Path, required=True)
    inspect = verbs.add_parser("inspect")
    inspect.add_argument("--item", required=True)
    inspect.add_argument("--token", required=True)
    inspect.add_argument("--reports", nargs="+", required=True)
    dispose = verbs.add_parser("dispose")
    dispose.add_argument("--item", required=True)
    dispose.add_argument("--writer", required=True)
    dispose.add_argument("--reason", required=True)
    return parser.parse_args(argv)


def main(*, argv: list[str] | None = None) -> int:
    args = parse_args(argv=sys.argv[1:] if argv is None else argv)
    take_credential(fifo=args.credential_fifo, environ=os.environ)
    plugin = load_plugin(scripts_root=args.scripts_root)
    config = store_config(plugin=plugin, repo_root=args.repo_root, bd_path=args.bd_path)
    client = plugin.make_client(config=config)
    if args.verb == "writer":
        payload = run_writer(args=args, plugin=plugin, client=client)
    elif args.verb == "create":
        payload = run_create(args=args, plugin=plugin, client=client, prefix=config.prefix)
    elif args.verb == "inspect":
        payload = run_inspect(args=args, client=client)
    else:
        payload = run_dispose(args=args, plugin=plugin, client=client)
    _ = sys.stdout.write(json.dumps(payload, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
