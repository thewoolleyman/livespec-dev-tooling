"""Forge-authored-revert exemption for the `red_green_replay` commit-range gate.

This module owns ONE decision and the prose that explains it: whether a
commit in `origin/master..HEAD` that carries no TDD trailer evidence is
nonetheless admissible because it is a SERVER-SIDE REVERT authored by the
forge itself. It also carries the range gate's remedy hint, because the
exemption IS the remedy the hint has to name (work-item
livespec-dev-tooling-j2qa).

THE DEADLOCK THIS CLOSES, measured end to end in livespec-overseer on
2026-08-22 rather than constructed:

- 10:29:49Z PR 1626 merged as `f5e1d45`, tripping PLR0915 in
  `overseer/_supervisor_tick.py`; master CI run 32571990095 went red at
  `check-lint` and `ci-green` and the repo went dispatch-dead.
- 11:17:07Z PR 1630 opened a SERVER-SIDE revert of `f5e1d45`, created
  exactly as `livespec/.ai/ci-gate-discipline.md` directs for a gate
  deadlock: "create the revert SERVER-SIDE (a GitHub revert PR via the web
  UI or API), WHICH NO LOCAL HOOK MEDIATES."
- 11:18:01Z `check-red-green-replay` failed that PR with
  `red-green-replay-range-missing-trailers`, `violating_commits:
  ["32c27a244f5ba8035e8c8d3d596305ea8d670f1e"]`.

The two rules were mutually blocking BY CONSTRUCTION. A server-side revert
cannot carry TDD trailers PRECISELY BECAUSE no local hook mediates it —
which is the property the directive requires it to have. Both exits were
closed: the range gate refused the server-side route, and the hint's local
route (re-author through the hook, force-push) is unreachable while master
is red, because `check-master-ci-green` sits inside the same `check:`
aggregate that runs at pre-push. The only remaining move was a
per-occurrence human bypass of a required check.

⛔ WHAT THIS EXEMPTION KEYS ON, AND WHY AN AGENT CANNOT FORGE IT.

It keys on TWO conjoined properties. Both must hold; either alone admits
too much.

1. AUTHORSHIP BY THE FORGE'S OWN SIGNING KEY — the unforgeable half. The
   commit object must carry an OpenPGP signature that verifies against a
   keyring built from the GitHub web-flow public keys PINNED IN THIS FILE,
   and nothing else. GitHub signs every commit its web UI and API create
   with that key; producing such a signature requires GitHub's PRIVATE key,
   which no agent, hook, or contributor holds. This is the property the
   subject line does NOT have: `git commit -m "Revert \"...\""` costs an
   agent one line, and a `committer` of `GitHub <noreply@github.com>` costs
   it one environment variable. Neither produces a signature.

   The trust root is a CONSTANT of this module. There is no environment
   variable, no `[tool.livespec_dev_tooling]` key, no CLI flag and no
   config file that can point it at another key — a lever there would be
   the escape hatch `ci-gate-discipline.md` forbids without exception. The
   keyword-only `trust_root` parameter exists so the boundary can be tested
   in both directions with an ephemeral key; it is reachable only by an
   in-process caller that already has import access to this module, never
   from the check's own CLI entry point, which passes nothing.

2. A VERIFIED PARENT-COMMIT RELATIONSHIP — the narrowness half. The commit
   must have exactly one parent, must name a reverted commit that is an
   ANCESTOR OF `origin/master`, and — the load-bearing part — for every
   product impl `.py` path the commit touches, its blob must be
   BYTE-IDENTICAL to the blob at that path in the reverted commit's own
   first parent. That is a content proof, not a claim: it establishes that
   the commit introduces NO product code that was not already on master
   before the commit being undone. The TDD evidence for that state exists
   — it is on the commit that first introduced it, which passed this same
   gate. So the exemption transfers evidence rather than waiving it.

   The `This reverts commit <sha>.` line is used ONLY as a lookup hint for
   which ancestor to compare against. It carries no authority: forging it
   buys nothing, because the named commit must still be an ancestor of
   `origin/master` AND the byte-identity must still hold AND the signature
   must still verify. A commit that adds so much as one new product line
   fails the identity check even when everything else about it is genuine.

FAIL-CLOSED BY CONSTRUCTION, AND DELIBERATELY WITHOUT AN ERROR TRACK. Every
predicate here collapses its failure track onto `False` — no `gpg` on
PATH, an unreadable object, a git that did not run, a signature by an
unknown key. `False` means "no exemption", which restores the pre-existing
verdict, so a collapse can only ever make the gate STRICTER. That is the
opposite of the fail-WRONG collapse `_red_green_replay_trailers` converted
to the `IOResult` railway (work-item livespec-dev-tooling-qndn), where an
unread git answer chose the wrong LEG and stamped evidence nobody checked.
Here there is no wrong answer to fall into: the conservative answer is the
one the gate already gives.
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from dataclasses import dataclass

__all__: list[str] = [
    "GITHUB_FORGE_TRUST_ROOT",
    "RANGE_MISSING_TRAILERS_HINT",
    "ForgeTrustRoot",
    "is_forge_authored_revert",
]


@dataclass(frozen=True, kw_only=True)
class ForgeTrustRoot:
    """The pinned public keys a forge-authored revert's signature must verify against.

    `public_key_block` is ASCII-armored OpenPGP key material imported into an
    EPHEMERAL keyring per verification, so the ambient `~/.gnupg` — whatever a
    developer or CI runner happens to have in it — can neither admit a key nor
    withhold one. `fingerprints` is checked against gpg's own `VALIDSIG` status
    line as a second, independent assertion: the keyring already contains only
    these keys, so the two must agree.
    """

    fingerprints: tuple[str, ...]
    public_key_block: str


# GitHub's web-flow commit-signing public keys, pinned as MATERIAL rather than
# fetched: a check that downloads its own trust root at verification time is
# trusting the network, which is exactly the thing an attacker sits on. Two
# keys because GitHub rotated on 2024-01-16 — B5690EEEBB952194 (4096-bit) is
# the key in service today and signs every revert a live deadlock produces;
# 4AEE18F83AFDEB23 (2048-bit, expired at the rotation) is retained so the
# gate reads history authored before it the same way it reads history after.
# Refresh both from https://github.com/web-flow.gpg and re-derive the
# fingerprints with `gpg --with-colons --fingerprint` when GitHub rotates
# again; the check refuses an unrecognized signer, so a stale pin fails
# CLOSED — the deadlock returns, nothing is admitted.
_GITHUB_WEB_FLOW_PUBLIC_KEYS = """\
-----BEGIN PGP PUBLIC KEY BLOCK-----

mQINBGWmxXYBEACyN+4viFQM6QQoKr0A2W0rGdMobTJwOZso2QPpewbyBsuL3rNW
5OmHrWwXAhPKNqUIyOzdq8MoSxoTTuqLksoahixEL/X2nyhOBxR9GkYz/oI9R3nY
cLRaFQoSJoVfOt61opkLUzbWAehpbgT8EKln8JsENq0+0nDlWQi0h2Q9oGmqlgVz
skwmVZ8Leyv4Mg7hN6swyZ7moZfkkpD5+U7Z2XVurCzkSSfg4zb2lMRLJos2eCAc
749ECsX0t7OBftF+YqgjIXixXsm2RrUqvU47OkOtZeAhvAYenbC3pr9Fha5NxoBU
Ea+11MK9W6OcRhwvxVCUrMUR6FTSZyC//VpXTTtrRlOqpU5wGMbP3zpn9geqOXCl
8rF7+1gAPG/o+QFQTBsVEruwi4JWogiQuQyOwAIlFe/7dvaxWZGpv/yW2+L3guL7
xaHKFVGsayhlitQQ5Xa+P1iSgKSXDyReCbWotfqAempPySI25LHh3ScXI6NgdHSr
SBaFojwAfgxbPTEQ6adIsKHCQofrnLrNa3UOeGDGiOOK0aYV3jiEDGAouatkNf2q
85Eosj1f9laCqAH3YLJD7dcSne1iChK5qRTByMvIyeSD0NbNnVMFOGpXySyWtKb2
ldpu8AWBQJsJs9FmYBcWAGBA2pp+IxaCn6rBIHIsUVFRN8OVZKsEsBkWywARAQAB
tBtHaXRIdWIgPG5vcmVwbHlAZ2l0aHViLmNvbT6JAk4EEwEKADgWIQSWhHmhr/kn
430aVmu1aQ7uu5UhlAUCZabFdgIbAwULCQgHAgYVCgkICwIEFgIDAQIeAQIXgAAK
CRC1aQ7uu5UhlIMuEAClvVwC+Neoiq0AdixJZsagKHpx1QrMJWrtMRi4eXVTTaeX
+P1unhC/AmSO4Xxd3uRoejHvfWh4F0gitUJ8XKgiejnmuGcq7Dbt5OoO1JuXGlW2
BQ+MiGoYVw2B0sOhWDNrIBWOO/WL4LykcGnAtrRXwoS0Wx4MCydztXQY5lcnCWaW
8rvu7WmduoOikH4HI97rqN5896dc4iBKSx8LZf+46DRCCD/5SfACplBz4hs5zen8
TL8zd+zxjFrXbzota0jSDEGK9WGO4z55S2xScC6zv6v3Bj1OR8Bs5aodGtmamHZ7
sE9w0RJoCfNx+9cR/rE82SrOaBpVU7urLe4lg7zaaNhqDdNV8ymuXGmIJarDgrme
iB5bHS+dLFzLUkTgot4RFlPa9bFiJuJN6Tc9tMu5RJQ9l/zKmxDHIKWsAle5R65u
zEq04LugTQBdEorGxfQCsF2ga9ncKTDMiAThWTvZpOP3NJ/athZRmOBpG4B9iR6r
pRU8F/+MokG4fIMwnvtOhWQFiEzdTkJ7U5JAkPtTAmT3/mznwtPEU7DrFWSGAdqg
IMOlxNCBeGvjwLR0qGH7cB9qHDGNoDLkjaUFpu5tPv4/ivkQaHlHJxjT0ILM6jet
CAzKpKh48rm65tmrJX6KVpj0r2kKMscFf7s7XaPlCNCFds/YA+0puPbzJKWKfA==
=NRlX
-----END PGP PUBLIC KEY BLOCK-----
-----BEGIN PGP PUBLIC KEY BLOCK-----

mQENBFmUaEEBCACzXTDt6ZnyaVtueZASBzgnAmK13q9Urgch+sKYeIhdymjuMQta
x15OklctmrZtqre5kwPUosG3/B2/ikuPYElcHgGPL4uL5Em6S5C/oozfkYzhwRrT
SQzvYjsE4I34To4UdE9KA97wrQjGoz2Bx72WDLyWwctD3DKQtYeHXswXXtXwKfjQ
7Fy4+Bf5IPh76dA8NJ6UtjjLIDlKqdxLW4atHe6xWFaJ+XdLUtsAroZcXBeWDCPa
buXCDscJcLJRKZVc62gOZXXtPfoHqvUPp3nuLA4YjH9bphbrMWMf810Wxz9JTd3v
yWgGqNY0zbBqeZoGv+TuExlRHT8ASGFS9SVDABEBAAG0NUdpdEh1YiAod2ViLWZs
b3cgY29tbWl0IHNpZ25pbmcpIDxub3JlcGx5QGdpdGh1Yi5jb20+iQEoBBMBCAAc
BQJZlGhBCRBK7hj4Ov3rIwIbAwUJDBJ3/wIZAQAA0O4IAJd0k8M+urETyMvTqNTj
/U6nbqyOdKE4V93uUj5G7sNTfno7wod/Qjj6Zv5KodvA93HmEdQqsmVq5YJ5KGiw
cmGCpd/GqJRPaYSY0hSUSBqYHiHLusCJkPBpQTBhcEMtfVCB2J6fVeoX2DV0K1xf
CGblrSVB0viAxUMnmL5C55RuvbYZsTu8szXhkvIR96CtWbJ8QGaEf1/KSpWz8ept
Y/omf3UPfvdOjnsxc8jVEqPNaR9xC6Q6t53rBa/XgMY6IYyesnyYnc5O6JuexUFa
VjykRFtAiYfDaMARpXOmgMm0lhoBRKb/uMUaN3CSYTmE4pZweJcUi7eWgmoQljX2
ut4=
=7ub0
-----END PGP PUBLIC KEY BLOCK-----
"""

GITHUB_FORGE_TRUST_ROOT = ForgeTrustRoot(
    fingerprints=(
        "968479A1AFF927E37D1A566BB5690EEEBB952194",
        "5DE3E0509C47EA3CF04A42D34AEE18F83AFDEB23",
    ),
    public_key_block=_GITHUB_WEB_FLOW_PUBLIC_KEYS,
)

# The range gate's remedy hint. It lives here rather than inline at the reject
# site because criterion 5 of livespec-dev-tooling-j2qa is precisely that the
# hint must stop prescribing an UNREACHABLE route: its old text sent the
# operator to "re-author locally and force-push" with no mention that
# `check-master-ci-green` — inside the same `check:` aggregate that runs at
# pre-push — refuses that push while master is red. The hint now states the
# precondition AND names the reachable path for the case where it does not
# hold.
RANGE_MISSING_TRAILERS_HINT: str = (
    "Every commit touching product impl .py must carry evidence, "
    "regardless of subject prefix: author behavior changes via the "
    "Red->Green ritual (pair shape), or behavior-preserving changes "
    "via the green-verified leg (suite shape). A commit carrying "
    "TDD-Green-* WITHOUT TDD-Red-* is a HALF-PAIR: a message-replacing "
    "`git commit --amend -m` / `-F` destroyed the Red block at the "
    "Green amend. Recover it from the commit named by that commit's "
    "TDD-Green-Parent-Reflog trailer (`git log -1 --format=%B <sha> | "
    "grep '^TDD-Red-'`) and re-amend with the reassembled message. "
    "Remedy otherwise, WHILE MASTER CI IS GREEN: rewrite the unmerged "
    "feature branch (redo each offending change through the hook so it "
    "earns its trailers) and force-push the branch — the 'never "
    "force-push' rule scopes to shared/protected refs, not to an "
    "unmerged feature branch being brought into shape. "
    "PRECONDITION, because that route is NOT always reachable: the "
    "push runs the same `check:` aggregate this reject came from, and "
    "`check-master-ci-green` inside it refuses every push while master "
    "is red — so a red master closes the local route entirely. "
    "WHEN MASTER IS RED the reachable path is the one livespec's "
    "`.ai/ci-gate-discipline.md` mandates: create the revert "
    "SERVER-SIDE, through the forge's own revert API (the GitHub PR "
    "'Revert' button), and merge that. This gate exempts such a commit "
    "on evidence it cannot fabricate — a signature by GitHub's pinned "
    "web-flow key PLUS byte-identity with the reverted commit's parent "
    "at every product impl .py path it touches — never on its subject "
    "line. If a genuine server-side revert is still convicted here, "
    "check that `gpg` is on PATH in this environment and that the "
    "revert restores the pre-revert bytes exactly (a conflict-resolved "
    "revert does not, and is correctly outside the exemption)."
)

# `git revert` and GitHub's revert API both emit this line into the body. It
# is a LOOKUP HINT for which ancestor to compare against, never an authority:
# see this module's docstring, property 2.
_REVERTS_COMMIT_RE = re.compile(r"^This reverts commit ([0-9a-f]{7,40})\.?[ \t]*$", re.MULTILINE)
_VALIDSIG_PREFIX = "[GNUPG:] VALIDSIG "
# `subprocess.run` could not start the binary at all — gpg absent from a CI
# image, say. Distinct from any exit code gpg or git actually produces, and
# treated exactly like every other failure here: no exemption.
_BINARY_UNUSABLE = 127
# `git rev-list --parents -n 1 <sha>` prints the commit followed by its
# parents, so a single-parent commit yields exactly two fields.
_SINGLE_PARENT_FIELDS = 2


def _run(
    *, argv: list[str], env: dict[str, str] | None = None, input_text: str = ""
) -> subprocess.CompletedProcess[str]:
    """Run `argv`, reporting an unstartable binary as an ordinary non-zero result.

    The catch is STRUCTURAL and narrow — `subprocess.run` itself refusing to
    start the child. Every caller here already treats a non-zero exit as "no
    exemption", so folding an unusable binary into that same shape adds no new
    policy: an absent `gpg` and a bad signature are the same answer.
    """
    try:
        return subprocess.run(
            argv,
            capture_output=True,
            text=True,
            check=False,
            env=env,
            input=input_text,
        )
    except OSError as unusable:
        return subprocess.CompletedProcess(
            args=argv, returncode=_BINARY_UNUSABLE, stdout="", stderr=str(unusable)
        )


def _validsig_names_trusted_key(*, line: str, fingerprints: tuple[str, ...]) -> bool:
    """Whether one gpg status line is a `VALIDSIG` naming a pinned fingerprint.

    gpg emits `VALIDSIG` only for a CRYPTOGRAPHICALLY VALID signature; owner
    trust is a separate axis this deliberately does not consult, because the
    ephemeral keyring already contains nothing but the pinned keys. The line
    carries both the signing (sub)key fingerprint and, as its last field, the
    primary key's — matching either is sufficient and, for the web-flow keys
    (which sign with the primary), they are the same value.
    """
    if not line.startswith(_VALIDSIG_PREFIX):
        return False
    return any(field in fingerprints for field in line.removeprefix(_VALIDSIG_PREFIX).split())


def _verifies_against_trust_root(*, sha: str, trust_root: ForgeTrustRoot) -> bool:
    """Whether `sha`'s OpenPGP signature verifies against the pinned keys ALONE.

    The keyring is built fresh in a private temporary `GNUPGHOME` for each
    call and thrown away after. That is the point: the ambient `~/.gnupg` of
    whoever runs the gate — a developer laptop, a shared CI image — cannot add
    a signer the pin does not name, and cannot remove one it does.
    """
    with tempfile.TemporaryDirectory(prefix="rgr-forge-trust-") as home:
        env = {**os.environ, "GNUPGHOME": home}
        imported = _run(
            argv=["gpg", "--batch", "--quiet", "--no-tty", "--import"],
            env=env,
            input_text=trust_root.public_key_block,
        )
        if imported.returncode != 0:
            return False
        verified = _run(argv=["git", "verify-commit", "--raw", sha], env=env)
        return any(
            _validsig_names_trusted_key(line=line, fingerprints=trust_root.fingerprints)
            for line in verified.stderr.splitlines()
        )


def _reverted_shas_from_message(*, sha: str) -> tuple[str, ...]:
    """The commits `sha`'s message names as reverted, in order — empty when none.

    A tuple rather than an optional single value because `git revert A B`
    against one commit legitimately names several, and because an empty tuple
    says "names none" without a sentinel string standing in for it.
    """
    body = _run(argv=["git", "log", "-1", "--format=%B", sha])
    if body.returncode != 0:
        return ()
    return tuple(found.group(1) for found in _REVERTS_COMMIT_RE.finditer(body.stdout))


def _undoes_ancestor(*, sha: str, reverted: str, base_ref: str, product_paths: list[str]) -> bool:
    """Whether `sha` restores `reverted`'s parent bytes at every product path it touches.

    Three conditions, all structural and all checked against git objects
    rather than against message text:

    - `sha` has EXACTLY ONE parent, so it is an ordinary commit whose diff is
      its own rather than a merge whose content came from elsewhere;
    - `reverted` is an ANCESTOR OF `base_ref` (`origin/master`), so the state
      being restored is state this gate already admitted once. A named commit
      that is not on master — one invented on the branch, say — fails here;
    - and the bytes match: `git diff --quiet <reverted>^ <sha> -- <paths>`
      exits 0 only when every product impl `.py` path `sha` touches holds
      exactly what it held before `reverted` landed.

    The third is what makes a hand-authored near-miss fail even if it somehow
    cleared the other two: a revert that also slips in one new product line
    differs from `<reverted>^` at that path and is refused. A conflict-resolved
    revert (master moved on at the same paths) likewise differs, and is
    likewise outside the exemption — fail-closed, deliberately, because a
    hand-resolved conflict is new code that no commit has evidence for.
    """
    parents = _run(argv=["git", "rev-list", "--parents", "-n", "1", sha])
    if parents.returncode != 0 or len(parents.stdout.split()) != _SINGLE_PARENT_FIELDS:
        return False
    if _run(argv=["git", "merge-base", "--is-ancestor", reverted, base_ref]).returncode != 0:
        return False
    restored = _run(argv=["git", "diff", "--quiet", f"{reverted}^", sha, "--", *product_paths])
    return restored.returncode == 0


def is_forge_authored_revert(
    *,
    sha: str,
    product_paths: list[str],
    base_ref: str,
    trust_root: ForgeTrustRoot = GITHUB_FORGE_TRUST_ROOT,
) -> bool:
    """Whether `sha` is a forge-signed revert restoring already-gated product bytes.

    The conjunction is the whole design — see this module's docstring. The
    signature is checked FIRST and short-circuits, so the ordinary case (an
    unsigned commit missing its trailers, which is every genuine violation)
    costs one `gpg --import` and one `git verify-commit` and never reaches the
    ancestry or content probes.

    `trust_root` defaults to the pinned constant and is passed by exactly one
    caller — the range validator — which never overrides it. The parameter is
    a TEST SEAM, not a lever: it is reachable only in-process, so nothing an
    operator, an environment, or a config file can express changes which key
    the shipped check trusts.
    """
    if not _verifies_against_trust_root(sha=sha, trust_root=trust_root):
        return False
    return any(
        _undoes_ancestor(sha=sha, reverted=reverted, base_ref=base_ref, product_paths=product_paths)
        for reverted in _reverted_shas_from_message(sha=sha)
    )
