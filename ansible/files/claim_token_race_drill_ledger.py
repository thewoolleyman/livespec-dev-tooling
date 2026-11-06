"""The ledger half of `claim_token_race_drill_probe.py`: create, grade, inspect, dispose.

Split from the probe so each file stays under the repository's LLOC ceiling;
the play copies both beside each other and the probe imports this one from its
own directory. Nothing here reads a credential: every function takes the
package's client the probe already opened.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import argparse

__all__: list[str] = [
    "TOKEN_KEY",
    "grade",
    "metadata_of",
    "run_create",
    "run_dispose",
    "run_id_of",
    "run_inspect",
    "write_json",
]

TOKEN_KEY = "dispatch_claim_token"  # noqa: S105 - a metadata key, mirrors the package constant
_TRANSITION_KIND = "claim-token-transition"
_DISCARD_KIND = "claim-token-discard"
_ASSIGNEE = "claim-token-race-drill"


def metadata_of(*, record: dict[str, Any]) -> dict[str, Any]:
    raw = record.get("metadata")
    return dict(raw) if isinstance(raw, dict) else {}


def run_id_of(*, record: dict[str, Any]) -> str | None:
    stamp = metadata_of(record=record).get("dispatch_claim")
    return stamp.get("run_id") if isinstance(stamp, dict) else None


def _parse_reason(*, reason: object) -> dict[str, Any] | None:
    if not isinstance(reason, str):
        return None
    try:
        parsed = json.loads(reason)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def write_json(*, path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_create(
    *, args: argparse.Namespace, plugin: Any, client: Any, prefix: str
) -> dict[str, Any]:
    """Create the probe item as an `active` claim that names its first token."""
    item_id = plugin.new_work_item_id(prefix=prefix)
    item = plugin.work_item(
        id=item_id,
        type="task",
        status="active",
        title=args.title,
        description=args.description,
        origin="freeform",
        gap_id=None,
        rank="zzzz",
        assignee=_ASSIGNEE,
        depends_on=(),
        captured_at=datetime.now(timezone.utc).isoformat(),
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )
    plugin.create_work_item(client=client, item=item, claim_tokens=True)
    record = client.show_issue(issue_id=item_id)
    return {
        "item_id": item_id,
        "token_id": metadata_of(record=record).get(TOKEN_KEY),
        "status": record.get("status"),
    }


def grade(
    *,
    item: dict[str, Any],
    token: dict[str, Any],
    reports: list[dict[str, Any]],
    successors: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """The Definition of Done bullet, graded from server reads and the writers' reports."""
    reason = _parse_reason(reason=token.get("close_reason")) or {}
    attempted = {
        report["writer"]: next(
            (c["reason"] for c in report.get("trace", {}).get("closes", [])), None
        )
        for report in reports
    }
    winners = [w for w, r in attempted.items() if r is not None and r == token.get("close_reason")]
    applied = [r["writer"] for r in reports if r.get("outcome") == "applied"]
    losers = [r for r in reports if r["writer"] not in applied]
    named = metadata_of(record=item).get(TOKEN_KEY)
    winner_report = next((r for r in reports if r["writer"] in winners), None)
    discards_ok = all(
        all(
            successors.get(s, {}).get("status") == "closed"
            and (_parse_reason(reason=successors.get(s, {}).get("close_reason")) or {}).get("kind")
            == _DISCARD_KIND
            for s in r.get("trace", {}).get("successors_created", [])
        )
        for r in losers
    )
    checks = {
        "token_closed_once_with_a_transition_reason": token.get("status") == "closed"
        and reason.get("kind") == _TRANSITION_KIND,
        "exactly_one_writer_reason_on_token": len(winners) == 1,
        "exactly_one_writer_applied": applied == winners,
        "item_names_winner_successor": winner_report is not None
        and named == reason.get("successor") == winner_report.get("successor_token_id"),
        "item_carries_winner_write": winner_report is not None
        and run_id_of(record=item) == winner_report.get("writer_run_id"),
        "losers_stood_down": all(r.get("outcome") == "claim-changed" for r in losers)
        and discards_ok,
    }
    released = [r["trace"]["released_at"] for r in reports if "released_at" in r.get("trace", {})]
    return {
        "item": item.get("id"),
        "contested_token": token.get("id"),
        "release_skew_seconds": max(released) - min(released) if released else None,
        "token_close_reason": reason or token.get("close_reason"),
        "item_names": named,
        "item_run_id": run_id_of(record=item),
        "winner": winners[0] if len(winners) == 1 else None,
        "writers": {r["writer"]: r.get("outcome") for r in reports},
        "attempted_reasons": attempted,
        "checks": checks,
        "ok": all(checks.values()),
    }


def run_inspect(*, args: argparse.Namespace, client: Any) -> dict[str, Any]:
    """Read the item, the contested token and every successor back from the server."""
    reports = [json.loads(Path(p).read_text(encoding="utf-8")) for p in args.reports]
    successors = {
        s: client.show_issue(issue_id=s)
        for r in reports
        for s in r.get("trace", {}).get("successors_created", [])
    }
    return grade(
        item=client.show_issue(issue_id=args.item),
        token=client.show_issue(issue_id=args.token),
        reports=reports,
        successors=successors,
    )


def run_dispose(*, args: argparse.Namespace, plugin: Any, client: Any) -> dict[str, Any]:
    """Win the item's token one last time (the hold), then close the item."""
    result = plugin.change_claim(
        client=client,
        work_item_id=args.item,
        writer=args.writer,
        intent="claim-token-race-drill:dispose",
        claim_tokens=True,
        transition_observations=plugin.transition_observations,
    )
    closed = result.outcome == "applied"
    if closed:
        client.close_issue(issue_id=args.item, reason=args.reason)
    return {"item": args.item, "hold_outcome": result.outcome, "closed": closed}
