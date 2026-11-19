#!/usr/bin/env python3
"""Archive-then-remove sweep of the factory workspace root on a factory node.

The node's root filesystem holds one directory per ended factory run. The
kubelet evicts every sandbox once root free space falls under its eviction
threshold plus minimum-reclaim, so ended-run workspaces must leave root.

Every action comes from a COMMITTED manifest (controller-measured evidence: item
state, preservation test, HEAD sha). The host re-verifies what it can before
touching a directory, and any doubt keeps the directory:

  * the directory is inside the root, is not a symlink, and is in the manifest;
  * its HEAD still equals the manifest's HEAD (work has not moved);
  * it is older than the minimum age;
  * no pod on the node references it (a kubectl failure keeps everything).

`delete` rows (preservation test passed on the controller) are removed.
`archive` rows are tarred with zstd into the archive directory (a different
filesystem), the archive is tested and its sha256 is read back from the file,
and only then is the directory removed. Dirty trees are archived whole.

Report-only is the DEFAULT: nothing is written or removed without --apply.
Largest first; it stops once free space on the root reaches --stop-free-gib.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

GIB = 1024**3


def emit(message: str) -> None:
    sys.stdout.write(message + "\n")


def run(argv: list[str], **kw) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, capture_output=True, text=True, check=False, **kw)  # noqa: S603


def free_bytes(root: Path) -> int:
    return shutil.disk_usage(root).free


def referenced_dirs(kubectl: list[str], scope: list[str]) -> set[str] | None:
    done = run([*kubectl, "get", "pods", *scope, "-o", "json"])
    if done.returncode != 0:
        return None
    refs: set[str] = set()
    for pod in json.loads(done.stdout).get("items", []):
        for vol in pod.get("spec", {}).get("volumes", []):
            path = (vol.get("hostPath") or {}).get("path")
            if path:
                refs.add(path)
    return refs


def head_of(directory: Path) -> str:
    return run(
        ["git", "-c", "safe.directory=*", "-C", str(directory), "rev-parse", "HEAD"]
    ).stdout.strip()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def keep_reason(*, row: dict, root: Path, refs: set[str] | None, min_age_s: float) -> str | None:
    directory = root / row["dir"]
    if "/" in row["dir"] or directory.is_symlink() or not directory.is_dir():
        return "not-a-plain-directory"
    if refs is None:
        return "pod-list-unreadable"
    if any(str(directory) == r or r.startswith(str(directory) + "/") for r in refs):
        return "referenced-by-a-pod"
    if time.time() - directory.stat().st_mtime < min_age_s:
        return "under-minimum-age"
    if head_of(directory) != row["head"]:
        return "head-moved-since-manifest"
    return None


def archive(*, root: Path, name: str, dest_dir: Path) -> tuple[Path, str] | str:
    target = dest_dir / f"{name}.tar.zst"
    tar = subprocess.Popen(["tar", "-C", str(root), "-cf", "-", name], stdout=subprocess.PIPE)  # noqa: S603, S607
    zstd = run(["zstd", "-q", "-T4", "-3", "-f", "-o", str(target)], stdin=tar.stdout)
    tar.stdout.close()  # type: ignore[union-attr]
    if tar.wait() != 0 or zstd.returncode != 0:
        return f"archive-failed rc tar/zstd: {zstd.stderr[:120]}"
    if run(["zstd", "-q", "-t", str(target)]).returncode != 0:
        return "archive-failed-integrity-test"
    return target, sha256_file(target)


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--root", required=True)
    ap.add_argument("--archive-dir", required=True)
    ap.add_argument("--stop-free-gib", type=float, default=30.0)
    ap.add_argument("--min-age-hours", type=float, default=24.0)
    ap.add_argument("--kubectl", default="k3s kubectl")
    ap.add_argument(
        "--pod-scope",
        default="-A",
        help="kubectl scope for the pod list, e.g. '-A' or '-n factory'",
    )
    ap.add_argument("--apply", action="store_true")
    return ap.parse_args()


def bump(counts: dict[str, int], key: str) -> None:
    counts[key] = counts.get(key, 0) + 1


def apply_row(*, row: dict, root: Path, dest: Path) -> tuple[dict | None, str | None]:
    """Archive (when the row says so), then remove; returns (record, keep-reason)."""
    record: dict = {
        "dir": row["dir"],
        "action": row["action"],
        "kb": row["kb"],
        "item": row["item"],
        "head": row["head"],
        "class": row["cls"],
    }
    if row["action"] == "archive":
        res = archive(root=root, name=row["dir"], dest_dir=dest)
        if isinstance(res, str):
            return None, res
        record["archive"], record["sha256"] = str(res[0]), res[1]
    shutil.rmtree(root / row["dir"])
    with (dest / "results.jsonl").open("a") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    return record, None


def emit_planned(*, mode: str, row: dict, size: int) -> None:
    emit(
        f"{mode} {row['action'].upper()} {row['dir']} {size / GIB:.2f}GiB "
        f"class={row['cls']} item={row['item']} evidence={row['evidence']}"
    )


def emit_summary(
    *, mode: str, counts: dict[str, int], root: Path, projected: int, freed: int
) -> None:
    emit(
        f"{mode} summary: {json.dumps(counts, sort_keys=True)} "
        f"free_now={free_bytes(root) / GIB:.1f}GiB "
        f"projected={projected / GIB:.1f}GiB freed_bytes={freed}"
    )


def run_rows(
    *, args: argparse.Namespace, rows: list[dict], refs: set[str] | None, root: Path, dest: Path
) -> tuple[dict[str, int], int, int]:
    """One pass over the manifest; returns (counts, projected free bytes, freed bytes)."""
    mode = "APPLY" if args.apply else "REPORT"
    projected = free_bytes(root)
    counts: dict[str, int] = {}
    freed = 0
    for row in rows:
        current = free_bytes(root) if args.apply else projected
        if current >= args.stop_free_gib * GIB:
            bump(counts, "stopped-at-target")
            continue
        min_age_s = args.min_age_hours * 3600
        why = keep_reason(row=row, root=root, refs=refs, min_age_s=min_age_s)
        size = row["kb"] * 1024
        if why:
            bump(counts, f"KEEP {why}")
            emit(f"{mode} KEEP {row['dir']} {why}")
        elif not args.apply:
            projected += size
            bump(counts, row["action"])
            emit_planned(mode=mode, row=row, size=size)
        else:
            record, kept = apply_row(row=row, root=root, dest=dest)
            if record is None:
                bump(counts, f"KEEP {kept}")
                emit(f"APPLY KEEP {row['dir']} {kept}")
            else:
                freed += size
                bump(counts, row["action"])
                emit("APPLY DONE " + json.dumps(record, sort_keys=True))
    return counts, projected, freed


def main() -> int:
    args = parse_args()
    root = Path(args.root)
    dest = Path(args.archive_dir)
    rows = sorted(json.loads(Path(args.manifest).read_text()), key=lambda r: -r["kb"])
    refs = referenced_dirs(args.kubectl.split(), args.pod_scope.split())
    mode = "APPLY" if args.apply else "REPORT"
    emit(
        f"{mode} start: free={free_bytes(root) / GIB:.1f}GiB "
        f"stop-at={args.stop_free_gib}GiB rows={len(rows)}"
    )
    if args.apply:
        dest.mkdir(parents=True, exist_ok=True)
    counts, projected, freed = run_rows(args=args, rows=rows, refs=refs, root=root, dest=dest)
    emit_summary(mode=mode, counts=counts, root=root, projected=projected, freed=freed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
