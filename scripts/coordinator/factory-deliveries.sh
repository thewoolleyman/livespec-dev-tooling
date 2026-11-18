#!/usr/bin/env bash
# Read-only factory-delivery report for the coordinator's FACTORY-GREEN-WATCH.
#
# Usage: scripts/coordinator/factory-deliveries.sh
#
# GitHub is the source of truth here.  A factory drive can exit after its pull
# request merges, so this deliberately reports merged factory pull requests,
# not a drive or Fabro exit status.  The roster is the committed livespec-core
# fleet manifest that the fleet reconcilers read; a newly registered repository
# therefore appears here without a second list to maintain.
set -euo pipefail

exec python3 -I - <<'PY'
"""Print the latest merged factory delivery and trailing-day count per fleet repo."""

import datetime as dt
import json
import os
import subprocess
import sys

MANIFEST_OWNER = "livespec-ai"
MANIFEST_REPOSITORY = "livespec"
MANIFEST_PATH = ".livespec-fleet-manifest.jsonc"
FACTORY_APP_LOGINS = frozenset(("livespec-ai-factory-bot", "thewoolleyman-factory-bot"))
DELIVERY_PREFIXES = ("feat/", "fix/")


def gh(*args: str) -> str:
    completed = subprocess.run(
        ["gh", "api", *args], capture_output=True, check=False, text=True
    )
    if completed.returncode:
        detail = completed.stderr.strip() or "gh api exited without stderr"
        raise RuntimeError(detail)
    return completed.stdout


def remove_jsonc_comments(source: str) -> str:
    """Remove line and block comments without treating URL text as a comment."""
    output: list[str] = []
    index = 0
    quoted = False
    escaped = False
    while index < len(source):
        character = source[index]
        following = source[index + 1] if index + 1 < len(source) else ""
        if quoted:
            output.append(character)
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                quoted = False
            index += 1
        elif character == '"':
            quoted = True
            output.append(character)
            index += 1
        elif character == "/" and following == "/":
            index = source.find("\n", index)
            if index == -1:
                break
        elif character == "/" and following == "*":
            end = source.find("*/", index + 2)
            if end == -1:
                raise ValueError("unterminated JSONC block comment")
            index = end + 2
        else:
            output.append(character)
            index += 1
    return "".join(output)


def fleet_repositories() -> tuple[str, tuple[str, ...]]:
    source = gh(
        f"repos/{MANIFEST_OWNER}/{MANIFEST_REPOSITORY}/contents/{MANIFEST_PATH}?ref=master",
        "-H",
        "Accept: application/vnd.github.raw",
    )
    manifest = json.loads(remove_jsonc_comments(source))
    owner = manifest.get("owner")
    members = manifest.get("fleet")
    if not isinstance(owner, str) or not isinstance(members, list):
        raise ValueError("fleet manifest has no owner and fleet list")
    repositories = tuple(
        member["repo"]
        for member in members
        if isinstance(member, dict) and isinstance(member.get("repo"), str)
    )
    if not repositories:
        raise ValueError("fleet manifest contains no repositories")
    return owner, repositories


def pull_requests(*, owner: str, repository: str) -> list[dict[str, object]]:
    """Read only the factory apps' merged pull requests, paging to completion.

    Listing all closed PRs per repository used the right data but made a
    delivery report walk years of human PRs.  GitHub's GraphQL search narrows
    each scan to the two factory identities before pagination, while still
    carrying the merge timestamp and head ref that decide eligibility.
    """
    records: list[dict[str, object]] = []
    query = """
query($search: String!, $cursor: String) {
  search(query: $search, type: ISSUE, first: 100, after: $cursor) {
    pageInfo { hasNextPage endCursor }
    nodes {
      ... on PullRequest {
        number
        mergedAt
        headRefName
        title
        author { login }
      }
    }
  }
}
"""
    for login in sorted(FACTORY_APP_LOGINS):
        cursor: str | None = None
        while True:
            arguments = ["graphql", "-f", f"query={query}", "-f", f"search=repo:{owner}/{repository} is:pr is:merged author:app/{login}"]
            if cursor is not None:
                arguments.extend(("-f", f"cursor={cursor}"))
            parsed = json.loads(gh(*arguments))
            search = parsed.get("data", {}).get("search") if isinstance(parsed, dict) else None
            if not isinstance(search, dict):
                raise ValueError(f"{repository}: factory pull-request search is malformed")
            nodes = search.get("nodes")
            page_info = search.get("pageInfo")
            if not isinstance(nodes, list) or any(not isinstance(node, dict) for node in nodes):
                raise ValueError(f"{repository}: factory pull-request search has invalid nodes")
            if not isinstance(page_info, dict) or not isinstance(page_info.get("hasNextPage"), bool):
                raise ValueError(f"{repository}: factory pull-request search has invalid pagination")
            for node in nodes:
                head_ref = node.get("headRefName")
                author = node.get("author")
                records.append(
                    {
                        "number": node.get("number"),
                        "merged_at": node.get("mergedAt"),
                        "head": {"ref": head_ref},
                        "title": node.get("title"),
                        "user": {"login": author.get("login") if isinstance(author, dict) else None},
                    }
                )
            if not page_info["hasNextPage"]:
                break
            cursor = page_info.get("endCursor")
            if not isinstance(cursor, str) or not cursor:
                raise ValueError(f"{repository}: factory pull-request search has no next cursor")
    return records


def instant(value: object) -> dt.datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(dt.timezone.utc)


def is_delivery(*, pull: dict[str, object]) -> bool:
    head = pull.get("head")
    user = pull.get("user")
    head_ref = head.get("ref") if isinstance(head, dict) else None
    login = user.get("login") if isinstance(user, dict) else None
    title = pull.get("title")
    if not isinstance(head_ref, str) or not isinstance(login, str) or not isinstance(title, str):
        return False
    lowered_title = title.lower()
    is_release = head_ref.startswith("release-please--") or lowered_title.startswith(
        "chore(master): release"
    )
    is_bump = head_ref.startswith("chore/bump") or lowered_title.startswith(
        ("chore: bump", "chore(deps): bump")
    )
    return (
        not is_release
        and not is_bump
        and login in FACTORY_APP_LOGINS
        and head_ref.startswith(DELIVERY_PREFIXES)
        and instant(pull.get("merged_at")) is not None
    )


def age_text(*, merged_at: dt.datetime, now: dt.datetime) -> str:
    seconds = max(0, int((now - merged_at).total_seconds()))
    days, seconds = divmod(seconds, 24 * 60 * 60)
    hours, seconds = divmod(seconds, 60 * 60)
    minutes = seconds // 60
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def now_utc() -> dt.datetime:
    override = os.environ.get("FACTORY_DELIVERY_NOW")
    if override:
        parsed = instant(override)
        if parsed is None:
            raise ValueError("FACTORY_DELIVERY_NOW must be an ISO-8601 UTC instant")
        return parsed
    return dt.datetime.now(dt.timezone.utc)


def report() -> list[str]:
    owner, repositories = fleet_repositories()
    now = now_utc()
    cutoff = now - dt.timedelta(hours=24)
    lines: list[str] = []
    for repository in repositories:
        deliveries = [pull for pull in pull_requests(owner=owner, repository=repository) if is_delivery(pull=pull)]
        deliveries.sort(key=lambda pull: instant(pull["merged_at"]) or dt.datetime.min.replace(tzinfo=dt.timezone.utc), reverse=True)
        trailing = sum(1 for pull in deliveries if (merged_at := instant(pull["merged_at"])) and merged_at >= cutoff)
        if not deliveries:
            lines.append(f"{repository}: newest none; deliveries-24h 0")
            continue
        newest = deliveries[0]
        merged_at = instant(newest["merged_at"])
        number = newest.get("number")
        if merged_at is None or not isinstance(number, int):
            raise ValueError(f"{repository}: eligible pull request has invalid number or merge instant")
        rendered_instant = merged_at.isoformat().replace("+00:00", "Z")
        lines.append(
            f"{repository}: newest #{number} merged {rendered_instant}; "
            f"age {age_text(merged_at=merged_at, now=now)}; deliveries-24h {trailing}"
        )
    return lines


try:
    for line in report():
        print(line, flush=True)
except (RuntimeError, ValueError, json.JSONDecodeError) as failure:
    print(f"factory-deliveries: cannot report: {failure}", file=sys.stderr)
    raise SystemExit(2) from failure
PY
