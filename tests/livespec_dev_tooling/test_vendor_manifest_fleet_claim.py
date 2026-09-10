"""Repo-conformance test: `.vendor.jsonc`'s `returns` annotation claims nothing fleet-wide.

The manifest used to assert, in the comment block annotating the `returns`
entry, that pinning `0.25.0` kept "one railway version across the fleet".
Measured 2026-08-03 on fresh clones that was FALSE: the fleet carried THREE
distinct `returns` provenances — `0.25.0` in this repo and in `livespec`,
`0.26.0` in `livespec-orchestrator-git-jsonl`, and a commit-pin
copy-of-a-copy (`e2cdeea:.claude-plugin/scripts/_vendor/returns`) in
`livespec-orchestrator-beads-fabro`, which is not an upstream ref at all.
Removing the clause is work-item livespec-dev-tooling-yteb; this file is
what keeps it removed.

Why the defect could not have been caught where it lived:
`check-vendor-manifest` validates each entry's SHAPE — non-empty
`upstream_url`, non-empty `upstream_ref`, parseable-ISO `vendored_at` — and
never compares refs ACROSS repos. A cross-repo `upstream_ref` comparison is
the natural home for a convergence check and is EXPLICITLY DEFERRED by the
item; nothing here reaches another repo, reads another manifest, or
proposes a re-vendor. The scope is exactly one thing: an annotation in THIS
file must not assert a property no machinery in this file can compute.

Three properties are pinned, none a literal-string match for its own sake:

1. The `returns` annotation — and, so the claim cannot simply migrate to
   another paragraph, the WHOLE raw manifest text — carries no fleet-wide
   single-railway-version assertion. The detector is a small family of
   phrasings (`one railway version across the fleet`, `a single version
   fleet-wide`, `fleet-wide, one railway version`, ...), not the one
   sentence that happened to be there.
2. The detector is proven NON-VACUOUS by a NEGATIVE CONTROL: it is run
   against the verbatim pre-fix annotation this repo carried at
   `0d37ea6f`, and MUST flag it. A guard that passes because it detects
   nothing is the failure mode this control exists to exclude.
3. The retained text is coherent with the entry it annotates: the version
   the prose names is the version `upstream_ref` actually pins. That is the
   measurably-true residue the item allows to stay — a pairwise statement
   about this repo and `livespec`, and nothing wider.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[2]
_VENDOR_MANIFEST = _REPO_ROOT / ".vendor.jsonc"

# The paragraph of the leading comment block that annotates the `returns`
# entry is the one naming the library; paragraphs are separated by bare `//`
# lines and the block ends at the manifest's opening brace.
_RETURNS_ANCHOR = "`returns` is vendored"

# The annotation VERBATIM as it stood before livespec-dev-tooling-yteb (repo
# HEAD `0d37ea6f`). It is the negative control's input: the detector below
# must flag this, or it is not detecting anything. Kept as a literal rather
# than read from git history, so the control survives the merge that removes
# the string from every reachable tree.
_PRE_FIX_ANNOTATION = (
    "// `returns` is vendored to satisfy livespec\n"
    '// `SPECIFICATION/non-functional-requirements.md` §"Shared content\n'
    '// provenance": every governed repo carrying first-party Python "MUST put\n'
    "// its product logic on the `Result` / `IOResult` railway ...\n"
    '// `dry-python/returns` is vendored under `_vendor/`". This repo — the\n'
    "// enforcement suite itself — carried no copy, so it could not compose on\n"
    "// the railway even in principle. Version 0.25.0 matches the copy\n"
    "// `livespec` vendors, keeping one railway version across the fleet.\n"
    "// Landed as step 1 of livespec-dev-tooling-8o8e.\n"
)

# Equivalent spellings of the SAME false claim, each exercising a different
# word order. They ride beside the verbatim control so the guard is a claim
# detector rather than a checksum of one deleted sentence.
_EQUIVALENT_CLAIMS = [
    "keeping one railway version across the fleet",
    "the same railway version across the fleet",
    "pinned to a single version fleet-wide",
    "fleet-wide, one railway version everywhere",
    "one fleet-wide railway version",
]

_SINGLETON = r"(?:one|a\s+single|single|the\s+same|same|unified|identical)"
_VERSION = r"(?:railway\s+version|version\s+of\s+the\s+railway|railway|version)"
_FLEET = r"(?:across\s+the\s+fleet|throughout\s+the\s+fleet|fleet[\s-]*wide|the\s+fleet|fleet)"
_GAP = r"[\s,]+"

_CLAIM_PATTERNS = (
    # "one railway version across the fleet"
    re.compile(_SINGLETON + _GAP + _VERSION + _GAP + _FLEET, re.IGNORECASE),
    # "fleet-wide, one railway version"
    re.compile(_FLEET + _GAP + _SINGLETON + _GAP + _VERSION, re.IGNORECASE),
    # "one fleet-wide railway version"
    re.compile(_SINGLETON + _GAP + _FLEET + _GAP + _VERSION, re.IGNORECASE),
)

# One `returns` entry object, read out of the RAW text rather than parsed:
# the entries carry no nesting, and staying on the raw bytes keeps this file
# free of the vendored-JSONC import dance the check module needs.
_RETURNS_ENTRY = re.compile(r'\{[^{}]*"name":\s*"returns"[^{}]*\}', re.DOTALL)
_UPSTREAM_REF = re.compile(r'"upstream_ref":\s*"([^"]+)"')


def _manifest_text() -> str:
    """The raw `.vendor.jsonc` bytes, comments and all."""
    return _VENDOR_MANIFEST.read_text(encoding="utf-8")


def _normalize(*, text: str) -> str:
    """Strip `//` comment markers and collapse whitespace onto one line.

    Line wrapping is an artifact of the 79-column comment style, so a claim
    split across two `//` lines must read the same to the detector as one
    written inline. Without this the guard would be defeated by a newline.
    """
    unmarked = [line.lstrip().removeprefix("//") for line in text.splitlines()]
    return re.sub(r"\s+", " ", " ".join(unmarked)).strip()


def _fleet_wide_claims(*, text: str) -> list[str]:
    """Every substring of `text` asserting one railway version across the fleet."""
    normalized = _normalize(text=text)
    return [match.group(0) for pattern in _CLAIM_PATTERNS for match in pattern.finditer(normalized)]


def _returns_annotation(*, text: str) -> str:
    """The comment paragraph annotating the `returns` entry."""
    header = text[: text.index("{")]
    owning = [para for para in header.split("\n//\n") if _RETURNS_ANCHOR in para]
    assert len(owning) == 1, (
        f"expected exactly one comment paragraph containing {_RETURNS_ANCHOR!r}; "
        f"found {len(owning)} — the guard's scope has drifted from the file"
    )
    return owning[0]


def _returns_upstream_ref(*, text: str) -> str:
    """The `upstream_ref` the `returns` entry actually pins."""
    entry = _RETURNS_ENTRY.search(text)
    assert entry is not None, "the .vendor.jsonc `returns` entry must exist"
    ref = _UPSTREAM_REF.search(entry.group(0))
    assert ref is not None, "the .vendor.jsonc `returns` entry must carry an `upstream_ref`"
    return ref.group(1)


@pytest.mark.parametrize("claim", [_PRE_FIX_ANNOTATION, *_EQUIVALENT_CLAIMS])
def test_the_detector_flags_a_fleet_wide_single_version_claim(*, claim: str) -> None:
    """NEGATIVE CONTROL: the pre-fix annotation, and its rephrasings, MUST be flagged.

    Run against the annotation this repo carried before the fix, the
    detector has to fire. A guard whose only evidence is a green run on the
    corrected file cannot distinguish "no claim present" from "no claim
    detectable", and this test is the difference.
    """
    assert _fleet_wide_claims(text=claim) != [], (
        "the detector missed a fleet-wide single-railway-version claim, so a green "
        f"result on the real manifest would prove nothing; missed text: {claim!r}"
    )


def test_returns_annotation_makes_no_fleet_wide_single_version_claim() -> None:
    """POSITIVE CONTROL: the corrected `returns` annotation is clean."""
    annotation = _returns_annotation(text=_manifest_text())

    assert _fleet_wide_claims(text=annotation) == [], (
        "the .vendor.jsonc `returns` annotation must not assert that one railway "
        "version is kept across the fleet — measured 2026-08-03 the fleet carried "
        "three distinct provenances (0.25.0, 0.26.0, and a beads-fabro commit-pin "
        "copy-of-a-copy), and nothing in this repo computes a cross-repo comparison"
    )


def test_no_paragraph_of_the_manifest_asserts_a_fleet_wide_single_version() -> None:
    """The claim must not migrate: the WHOLE raw manifest text is clean, not just one paragraph."""
    assert _fleet_wide_claims(text=_manifest_text()) == [], (
        "no comment anywhere in .vendor.jsonc may assert a fleet-wide single railway "
        "version; moving the claim to another paragraph does not make it true"
    )


def test_returns_annotation_still_records_the_measurably_true_pairwise_match() -> None:
    """What the item allows to stay: this repo pins 0.25.0, matching the copy `livespec` vendors."""
    text = _manifest_text()
    annotation = _normalize(text=_returns_annotation(text=text))
    pinned = _returns_upstream_ref(text=text)

    assert f"Version {pinned} matches the copy `livespec` vendors" in annotation, (
        f"the annotation must name the version the entry actually pins ({pinned}) and "
        "the one repo the match was measured against; it is a PAIRWISE statement"
    )


def test_returns_annotation_records_the_measured_plurality() -> None:
    """Deleting the false clause is not enough — the measurement that refutes it is recorded.

    A bare deletion leaves the next author free to re-derive the same wrong
    conclusion from the same two matching pins. Naming the other two
    provenances is what makes the correction durable.
    """
    annotation = _normalize(text=_returns_annotation(text=_manifest_text()))

    assert "2026-08-03" in annotation, "the measurement date must be recorded"
    assert "0.26.0" in annotation, "the divergent git-jsonl provenance must be named"
    assert "e2cdeea" in annotation, "the beads-fabro commit-pin copy-of-a-copy must be named"
