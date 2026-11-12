"""The shipped private-sibling minter names an installation coverage refusal."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MINTER = _REPO_ROOT / "ci-runner/k3s/phase2/gates/mint-private-sibling-token.sh"
_TOKEN = "ghs_test_private_sibling_token"


def _fake(*, bin_dir: Path, name: str, body: str) -> None:
    """Install one host-tool double ahead of the real PATH."""
    fake = bin_dir / name
    _ = fake.write_text(f"#!/usr/bin/env bash\nset -euo pipefail\n{body}\n", encoding="utf-8")
    fake.chmod(0o755)


def _run_minter(
    *, tmp_path: Path, repositories: tuple[str, ...], mint_failures: int = 0
) -> tuple[subprocess.CompletedProcess[str], str]:
    """Run the minter with private siblings and return its scoped-token request.

    `mint_failures` makes the token endpoint answer HTTP 500 that many times
    before it answers, the shape GitHub gave a pre-push gate on 2026-11-12.
    """
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    targets = {
        repository.rsplit("/", maxsplit=1)[-1]: {"github_url": f"https://github.com/{repository}"}
        for repository in repositories
    }
    _ = (consumer / ".livespec.jsonc").write_text(
        json.dumps({"cross_repo_targets": targets}, indent=2), encoding="utf-8"
    )
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    requests = tmp_path / "requests"
    scope = tmp_path / "scope"
    _fake(bin_dir=bin_dir, name="git", body="exit 1")
    # The minter pipes into openssl under `pipefail`. A fake that exits without
    # draining stdin hands its still-writing upstream SIGPIPE, and the minter
    # exits 141 at random: 20/120 runs at load 37, 2026-10-27. Real openssl
    # reads all its input, and so must the fake.
    _fake(
        bin_dir=bin_dir,
        name="openssl",
        body='cat >/dev/null\nprintf "%s" "encoded"',
    )
    _fake(
        bin_dir=bin_dir,
        name="jq",
        body=r"""
if [[ "$*" == *'.id // empty'* ]]; then
  input="$(cat)"
  if [[ "${input}" =~ \"id\":([0-9]+) ]]; then
    printf '%s' "${BASH_REMATCH[1]}"
  fi
  exit 0
fi
if [[ "$*" == *'.token // empty'* ]]; then
  input="$(cat)"
  if [[ "${input}" =~ \"token\":\"([^\"]+) ]]; then
    printf '%s' "${BASH_REMATCH[1]}"
  fi
  exit 0
fi
if [ "$*" = '-R .' ]; then
  while IFS= read -r name; do
    printf '"%s"\n' "${name}"
  done
  exit 0
fi
if [[ "$*" == *'{repositories: ., permissions: {contents: "read"}}'* ]]; then
  names=()
  while IFS= read -r quoted; do
    names+=("${quoted#\"}")
    names[${#names[@]} - 1]="${names[-1]%\"}"
  done
  printf '{"repositories":['
  for ((index = 0; index < ${#names[@]}; index += 1)); do
    [ "${index}" -eq 0 ] || printf ','
    printf '"%s"' "${names[index]}"
  done
  printf '],"permissions":{"contents":"read"}}'
  exit 0
fi
if [[ "$*" == *'--args '* ]]; then
  token=""
  names=()
  arguments=("$@")
  for ((index = 0; index < ${#arguments[@]}; index += 1)); do
    if [ "${arguments[index]}" = 'token' ]; then
      token="${arguments[index + 1]}"
    fi
    if [ "${arguments[index]}" = '--args' ]; then
      names=("${arguments[@]:index + 2}")
      break
    fi
  done
  printf '{"private_siblings":['
  for ((index = 0; index < ${#names[@]}; index += 1)); do
    [ "${index}" -eq 0 ] || printf ','
    printf '"%s"' "${names[index]}"
  done
  printf '],"token":"%s"}\n' "${token}"
  exit 0
fi
echo "unexpected jq arguments: $*" >&2
exit 99
""",
    )
    _fake(
        bin_dir=bin_dir,
        name="curl",
        body=r"""
url=""
output=""
data=""
arguments=("$@")
for ((index = 0; index < ${#arguments[@]}; index += 1)); do
  case "${arguments[index]}" in
    https://*) url="${arguments[index]}" ;;
    -o) output="${arguments[index + 1]}" ;;
    -d) data="${arguments[index + 1]}" ;;
  esac
done
printf '%s\n' "${url}" >> "${MINT_TEST_REQUESTS}"
respond() {
  body="$1"
  status="$2"
  if [ -n "${output}" ]; then
    printf '%s' "${body}" > "${output}"
    printf '%s' "${status}"
  else
    printf '%s' "${body}"
  fi
}
case "${url}" in
  */repos/acme/covered-one/installation|*/repos/acme/covered-two/installation)
    respond '{"id":17}' 200
    ;;
  */repos/mi-homelab/homelab/installation)
    respond '{"message":"Not Found"}' 404
    ;;
  */access_tokens)
    printf '%s' "${data}" > "${MINT_TEST_SCOPE}"
    if [[ "${data}" == *homelab* ]]; then
      respond '{"message":"Unprocessable Entity"}' 422
      exit 0
    fi
    calls="$(( $(cat "${MINT_TEST_TOKEN_CALLS}" 2>/dev/null || echo 0) + 1 ))"
    printf '%s' "${calls}" > "${MINT_TEST_TOKEN_CALLS}"
    if [ "${calls}" -le "${MINT_TEST_TOKEN_FAILURES}" ]; then
      respond '{"message":"Server Error"}' 500
      exit 0
    fi
    respond '{"token":"ghs_test_private_sibling_token"}' 201
    ;;
  *)
    echo "unexpected curl request: ${url}" >&2
    exit 99
    ;;
esac
""",
    )
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("COVERAGE_", "COV_CORE_"))
    }
    environment.update(
        {
            "GITHUB_APP_ID": "17",
            "GITHUB_PRIVATE_KEY": "-----BEGIN PRIVATE KEY-----key-----END PRIVATE KEY-----",
            "MINT_TEST_REQUESTS": str(requests),
            "MINT_TEST_SCOPE": str(scope),
            "MINT_TEST_TOKEN_CALLS": str(tmp_path / "token-calls"),
            "MINT_TEST_TOKEN_FAILURES": str(mint_failures),
            "MINT_RETRY_BASE_WAIT": "0",
            "PATH": f"{bin_dir}{os.pathsep}{environment['PATH']}",
        }
    )
    completed = subprocess.run(
        ["bash", str(_MINTER), "--repo-root", str(consumer)],
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )
    return completed, scope.read_text(encoding="utf-8") if scope.is_file() else ""


def test_an_uncovered_private_sibling_is_named_before_the_scoped_mint(*, tmp_path: Path) -> None:
    """A 422 never obscures the sibling the App installation does not cover."""
    completed, scope = _run_minter(
        tmp_path=tmp_path,
        repositories=("acme/covered-one", "mi-homelab/homelab"),
    )

    refusal_is_actionable = (
        completed.returncode != 0,
        "mi-homelab/homelab" in completed.stderr,
        "the gate App's installation does not cover it" in completed.stderr,
        "curl: (22)" not in completed.stderr,
    )

    assert all(refusal_is_actionable)
    assert scope == ""


def test_all_covered_private_siblings_keep_the_existing_scoped_mint(*, tmp_path: Path) -> None:
    """Coverage preflight leaves the successful token and its exact scope unchanged."""
    completed, scope = _run_minter(
        tmp_path=tmp_path,
        repositories=("acme/covered-one", "acme/covered-two"),
    )

    assert completed.returncode == 0
    assert json.loads(completed.stdout) == {
        "private_siblings": ["covered-one", "covered-two"],
        "token": _TOKEN,
    }
    assert json.loads(scope) == {
        "repositories": ["covered-one", "covered-two"],
        "permissions": {"contents": "read"},
    }


def test_a_transient_mint_server_error_is_retried_until_the_token_is_minted(
    *, tmp_path: Path
) -> None:
    """A 500 from the token endpoint is retried, and the next good answer mints."""
    completed, _scope = _run_minter(
        tmp_path=tmp_path,
        repositories=("acme/covered-one",),
        mint_failures=2,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["token"] == _TOKEN
    assert (tmp_path / "token-calls").read_text(encoding="utf-8") == "3"
    assert "mint call attempt 1/5: HTTP 500" in completed.stderr
    assert "mint call attempt 3/5: HTTP 201" in completed.stderr
    assert _TOKEN not in completed.stderr


def test_a_persistent_mint_server_error_stops_at_the_bound_naming_github(*, tmp_path: Path) -> None:
    """A 500 that never clears refuses after five attempts as GitHub's failure."""
    completed, _scope = _run_minter(
        tmp_path=tmp_path,
        repositories=("acme/covered-one",),
        mint_failures=99,
    )

    assert completed.returncode != 0
    assert (tmp_path / "token-calls").read_text(encoding="utf-8") == "5"
    assert "GitHub refused to mint an installation token" in completed.stderr
    assert "HTTP 500" in completed.stderr
    assert "does not cover it" not in completed.stderr
