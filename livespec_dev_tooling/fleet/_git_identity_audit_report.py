"""Evidence validation and report metadata for the Git identity audit."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import cast

__all__: list[str] = []

CANONICAL_NAME = "Chad Woolley"
CANONICAL_EMAIL = "thewoolleyman@gmail.com"
FORBIDDEN_EMAILS = ("chad@thewoolleyman.com",)
OWNER = "thewoolleyman"
EXPECTED_SANDBOX_DIGESTS = frozenset(
    {
        "sha256:83e0bec519eb412d82a1136627193564e356bfa8091f2b9171597141c9d3ed33",
        "sha256:9331287cce9edfb82e143e87072e12774ef7c5f635a6d7d0aa6dd4b8732c7a7c",
    }
)
_COMMIT = re.compile(r"[0-9a-f]{40}")
_RUN_ID = re.compile(r"[0-9A-HJKMNP-TV-Z]{26}")


def valid_evidence(*, evidence: dict[str, object] | None) -> bool:
    if evidence is None or evidence.get("schema_version") != 1:
        return False
    required = ("repository", "orchestrator_version", "sandbox_image_version")
    digests = evidence.get("sandbox_image_digests")
    if not isinstance(digests, list):
        return False
    digest_items = cast("list[object]", digests)
    if not all(isinstance(item, str) for item in digest_items):
        return False
    digest_values = cast("list[str]", digest_items)
    return (
        all(isinstance(evidence.get(key), str) and evidence[key] for key in required)
        and isinstance(evidence.get("run_id"), str)
        and _RUN_ID.fullmatch(cast("str", evidence["run_id"])) is not None
        and isinstance(evidence.get("commit"), str)
        and _COMMIT.fullmatch(cast("str", evidence["commit"])) is not None
        and evidence.get("orchestrator_version") == "0.148.2"
        and evidence.get("sandbox_image_version") == "1.85.3"
        and set(digest_values) == set(EXPECTED_SANDBOX_DIGESTS)
        and isinstance(evidence.get("negative_ci_run_id"), str)
        and cast("str", evidence["negative_ci_run_id"]).isdigit()
        and evidence.get("missing_identity_rejected") is True
        and evidence.get("canonical_identity_accepted") is True
    )


def base_report(*, inventory_path: Path, findings: list[str]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "generated_at": datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z"),
        "overall": "fail",
        "expected_identity": {"name": CANONICAL_NAME, "email": CANONICAL_EMAIL},
        "forbidden_author_emails": list(FORBIDDEN_EMAILS),
        "scope": {
            "history_scanned": False,
            "hosts": ["gmktec-xubuntu", "hp-xubuntu", "poweredge-xubuntu", "vps"],
            "inventory": str(inventory_path),
            "owned_github_origin": OWNER,
        },
        "findings": findings,
    }


def observed_dispositions(
    *, host_reports: list[dict[str, object]], findings: list[str]
) -> dict[str, str]:
    poweredge_seen = False
    homelab_seen = False
    for report in host_reports:
        owned = report.get("owned_repositories")
        if isinstance(owned, list):
            for item in cast("list[object]", owned):
                row = cast("dict[str, object]", item) if isinstance(item, dict) else {}
                poweredge_seen |= row.get("repo") == "poweredge-xubuntu-info"
        excluded = report.get("excluded_repositories")
        if isinstance(excluded, list):
            for item in cast("list[object]", excluded):
                row = cast("dict[str, object]", item) if isinstance(item, dict) else {}
                homelab_seen |= _github_slug(origin=row.get("origin")) == "mi-homelab/homelab"
    if not poweredge_seen:
        findings.append("poweredge-xubuntu-info: required owned repository was not observed")
    if not homelab_seen:
        findings.append("mi-homelab/homelab: required excluded repository was not observed")
    return {
        "poweredge-xubuntu-info": (
            "owned; audited" if poweredge_seen else "owned; not observed; audit incomplete"
        ),
        "mi-homelab/homelab": (
            "not owned by thewoolleyman; excluded and unmodified"
            if homelab_seen
            else "not owned by thewoolleyman; not observed; audit incomplete"
        ),
    }


def _github_slug(*, origin: object) -> str | None:
    if not isinstance(origin, str):
        return None
    matched = re.search(r"github\.com(?::|/)([^/]+)/([^/]+?)(?:\.git)?$", origin)
    return f"{matched.group(1)}/{matched.group(2)}" if matched else None
