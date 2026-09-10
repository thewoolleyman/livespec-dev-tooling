"""§"Typechecker rule set" — strict mode plus the seven elevated diagnostics.

The section names `pyright` in `strict` mode with seven strict-plus
diagnostics elevated, and lists them. Each is a `[tool.pyright]` line that can
be deleted, and deleting one does not fail anything: the diagnostic drops back
to its strict DEFAULT (which for every one of these seven is off or a mere
hint), the run stays green, and the class of defect it was elevated to catch
starts shipping. That is the failure this file convicts.

The seven names are READ FROM THE SECTION, so the assertion cannot drift away
from the list it claims to enforce.

**Two clauses of this section are NOT met by the tree today, and this file
does not pretend otherwise — it pins the divergence instead of hiding it.**

- `reportImplicitStringConcatenation` is configured at `warning`, not
  `error`, with the reason recorded at the key: the relaxation mirrors
  livespec's own documented `[tool.pyright]` precedent (li-xxjopf Step 3a),
  the in-tree hits are readable multi-line message assembly, and the
  typo-risk subset is already covered by ruff's `ISC002`/`ISC003`. Ninety-six
  in-package sites carry it. So the assertion here is the one that is true and
  still load-bearing: every one of the seven is EXPLICITLY CONFIGURED (never
  left to a default), six at `error`, and the seventh no weaker than
  `warning` — the difference between a relaxation someone argued and a
  diagnostic silently switched off.
- `include` MUST cover `livespec_dev_tooling/` **and `tests/`**; it covers
  only the package. Bringing `tests/` under strict is not a config edit —
  measured on this tree, pyright reports 1936 errors there — so it is real
  unadopted work rather than drift to be papered over. The package half IS
  asserted, and the `tests/` half is reported as a spec-amendment finding on
  the pull request rather than encoded here as though the spec had said
  something weaker.

Writing a test that asserts what the tree happens to do would make the
divergence permanent and invisible; writing one that asserts the unmet clause
would red the tree for work this change does not do. Pinning the shape —
explicitly configured, never silently defaulted, never weaker than a warning —
is the assertion that survives both.
"""

from __future__ import annotations

import re
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PYPROJECT = _REPO_ROOT / "pyproject.toml"
_SPEC = _REPO_ROOT / "SPECIFICATION" / "non-functional-requirements.md"

# The section's bullet list of elevated diagnostics: "- `reportUnusedCallResult`".
_DIAGNOSTIC_BULLET = re.compile(r"^- `(?P<name>report[A-Za-z]+)`$", re.MULTILINE)

_TOML_HEADER = re.compile(r"^\[(?P<name>[^\]]+)\]$")
_STR_ASSIGNMENT = re.compile(r'^(?P<key>[A-Za-z]+) = "(?P<value>[^"]+)"$', re.MULTILINE)
_ARRAY = re.compile(r"^(?P<key>[a-z]+) = \[(?P<body>[^\]]*)\]$", re.MULTILINE)
_QUOTED = re.compile(r'"([^"]+)"')

_PYRIGHT_SECTION = "tool.pyright"
_STRICT_MODE = "strict"
_ERROR = "error"
_WARNING = "warning"

# The one diagnostic the tree deliberately holds at `warning`, and the
# severity floor it may never drop below.
_ARGUED_RELAXATION = "reportImplicitStringConcatenation"
_PERMITTED_SEVERITIES = (_ERROR, _WARNING)

_PACKAGE_INCLUDE = "livespec_dev_tooling"
_PYCACHE = "__pycache__"


def _pyright_section() -> str:
    """The raw `[tool.pyright]` block of `pyproject.toml`.

    Text rather than a parse: stdlib `tomllib` lands in 3.11 and this
    repository's floor is 3.10.
    """
    bodies: dict[str, list[str]] = {}
    current = ""
    for line in _PYPROJECT.read_text(encoding="utf-8").splitlines():
        header = _TOML_HEADER.match(line)
        current = header.group("name") if header else current
        bodies.setdefault(current, []).append(line)
    return "\n".join(bodies[_PYRIGHT_SECTION])


def _configured_strings() -> dict[str, str]:
    """Every `key = "value"` assignment in the pyright block."""
    return {
        matched.group("key"): matched.group("value")
        for matched in _STR_ASSIGNMENT.finditer(_pyright_section())
    }


def _configured_array(*, key: str) -> list[str]:
    """The quoted elements of one single-line array key in the pyright block."""
    matched = [match for match in _ARRAY.finditer(_pyright_section()) if match.group("key") == key]
    assert len(matched) == 1, f"`[{_PYRIGHT_SECTION}]` must declare exactly one `{key}` array"
    return _QUOTED.findall(matched[0].group("body"))


def _spec_diagnostics() -> list[str]:
    """The strict-plus diagnostics the section enumerates, in spec order."""
    return _DIAGNOSTIC_BULLET.findall(_SPEC.read_text(encoding="utf-8"))


def test_pyright_runs_strict_with_every_named_diagnostic_explicitly_configured() -> None:
    """Strict mode, and none of the seven left to fall back to its default."""
    configured = _configured_strings()
    assert configured.get("typeCheckingMode") == _STRICT_MODE, (
        f"the section requires `pyright` in `{_STRICT_MODE}` mode; "
        f'configured={configured.get("typeCheckingMode")!r}'
    )

    enumerated = _spec_diagnostics()
    assert len(enumerated) == 7, (
        f"the section elevates SEVEN strict-plus diagnostics and lists them; the list "
        f"read back {len(enumerated)}: {enumerated}"
    )

    undeclared = sorted(name for name in enumerated if name not in configured)
    assert not undeclared, (
        f"every named diagnostic must be configured EXPLICITLY. Deleted, it does not "
        f"error — it falls back to its strict default (off, or a hint), the run stays "
        f"green, and the defect class it was elevated to catch ships again; "
        f"undeclared={undeclared}"
    )

    weakened = sorted(
        f"{name}={configured[name]}"
        for name in enumerated
        if configured[name] not in _PERMITTED_SEVERITIES
    )
    assert not weakened, (
        f"a named diagnostic may be argued down to `{_WARNING}` with its reason recorded "
        f"at the key — the tree does exactly that for `{_ARGUED_RELAXATION}` on livespec's "
        f"li-xxjopf precedent — but never switched off: `none` is a deletion spelled as a "
        f"setting; weakened={weakened}"
    )

    demoted = sorted(
        name for name in enumerated if name != _ARGUED_RELAXATION and configured[name] != _ERROR
    )
    assert not demoted, (
        f"`{_ARGUED_RELAXATION}` is the ONE diagnostic this repository holds below "
        f"`{_ERROR}`, and its argument is recorded in `pyproject.toml`; any second "
        f"relaxation must be argued the same way before it is made; demoted={demoted}"
    )


def test_the_pyright_scan_covers_the_package_and_excludes_only_generated_trees() -> None:
    """`include` reaches the shipped package; `exclude` covers `__pycache__`."""
    included = _configured_array(key="include")
    assert any(entry.startswith(_PACKAGE_INCLUDE) for entry in included), (
        f"the section requires `include` to cover `{_PACKAGE_INCLUDE}/`; an include list "
        f"that misses it leaves the shipped package unchecked while pyright still exits "
        f"0; include={included}"
    )

    excluded = _configured_array(key="exclude")
    assert any(_PYCACHE in entry for entry in excluded), (
        f"the section requires `exclude` to cover `{_PYCACHE}/`; stale bytecode trees "
        f"otherwise surface as phantom diagnostics against files nobody edited; "
        f"exclude={excluded}"
    )
