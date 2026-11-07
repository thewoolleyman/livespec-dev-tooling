"""Authenticate current PR/head labels; a master push never reads incident payloads."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, cast

from livespec_dev_tooling.budgeted_gh import gh_read
from livespec_dev_tooling.incident_ci_payload import strict_json
from livespec_dev_tooling.incident_ci_policy import CiEvent

__all__: list[str] = ["incident_block", "observe_event"]
# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-egy3ri
_BEGIN = "<!-- livespec-incident-ci\n"
_END = "\n-->"
_MAX_PAYLOAD = 16384
_SHA = re.compile(r"[0-9a-f]{40}")


def _map(*, value: object) -> dict[str, Any]:
    return cast("dict[str, Any]", value) if isinstance(value, dict) else {}


def _pull_request(
    *, environ: Mapping[str, str], repository: str
) -> tuple[CiEvent, dict[str, Any]] | None:
    number = int(environ["GITHUB_PR_NUMBER"])
    if number <= 0:
        return None
    reply = gh_read(args=["api", f"repos/{repository}/pulls/{number}"], timeout=10)
    data = _map(value=strict_json(text=reply.stdout, limit=1048576))
    source, base = _map(value=data.get("head")), _map(value=data.get("base"))
    head_sha, base_sha = source.get("sha"), base.get("sha")
    raw_labels = data.get("labels")
    labels = cast("list[Any]", raw_labels) if isinstance(raw_labels, list) else None
    if (
        reply.returncode != 0
        or data.get("state") != "open"
        or type(data.get("number")) is not int
        or data.get("number") != number
        or head_sha != environ["GITHUB_PR_HEAD_SHA"]
        or not isinstance(head_sha, str)
        or not isinstance(base_sha, str)
        or _SHA.fullmatch(head_sha) is None
        or _SHA.fullmatch(base_sha) is None
        or _map(value=base.get("repo")).get("full_name") != repository
        or labels is None
        or any(not isinstance(_map(value=label).get("name"), str) for label in labels)
    ):
        return None
    names = tuple(cast("str", label["name"]) for label in labels)
    if len(set(names)) != len(names):
        return None
    return CiEvent(
        kind="pull_request",
        repository=repository,
        base_sha=base_sha,
        head_sha=head_sha,
        pr_number=number,
        labels=names,
    ), data


def incident_block(*, body: str) -> str | None:
    """The body's one bounded `livespec-incident-ci` payload, or None. A locator, not authority."""
    if body.count(_BEGIN) != 1 or body.count(_END) != 1:
        return None
    payload = body.split(_BEGIN, maxsplit=1)[1].split(_END, maxsplit=1)[0]
    return payload if len(payload.encode("utf-8", "surrogatepass")) <= _MAX_PAYLOAD else None


def _incident_payload(*, event: CiEvent, data: dict[str, Any]) -> tuple[CiEvent, str] | None:
    if "expedited-incident-response" not in event.labels:
        return event, ""
    body = data.get("body")
    payload = incident_block(body=body) if isinstance(body, str) else None
    if (
        payload is None
        or _map(value=_map(value=data.get("head")).get("repo")).get("full_name") != event.repository
    ):
        return None
    return event, payload


def _observe(*, environ: Mapping[str, str]) -> tuple[CiEvent, str] | None:
    kind, repository = environ["GITHUB_EVENT_NAME"], environ["GITHUB_REPOSITORY"]
    if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) is None:
        return None
    if kind == "push":
        head = environ["GITHUB_SHA"]
        base = environ.get("GITHUB_BEFORE_SHA", head)
        return (
            (CiEvent(kind="push", repository=repository, base_sha=base, head_sha=head), "")
            if _SHA.fullmatch(head) and _SHA.fullmatch(base)
            else None
        )
    if kind != "pull_request":
        return None
    observed = _pull_request(environ=environ, repository=repository)
    return None if observed is None else _incident_payload(event=observed[0], data=observed[1])


def observe_event(*, environ: Mapping[str, str]) -> tuple[CiEvent, str] | None:
    """Bind a protected event to a fresh forge read, never candidate event JSON."""
    try:
        observed = _observe(environ=environ)
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        return None
    else:
        return observed
