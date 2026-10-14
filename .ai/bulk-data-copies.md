# Bulk data copies — fpsync is the standard tool

Read this before copying, migrating, or moving a data tree between disks or
hosts on any fleet machine: a container store (`/var/lib/containerd`,
`/var/lib/docker`), a volume, a cache tier, a home or `/data` tree, a
disk-to-disk move. The tool is `fpsync`, from the `fpart` package; the
`fpart` Ansible role installs it on every legacy-inventory host, and each
macOS host declares `brew "fpart"` in its `*-info` repo's Brewfile.

Work-item `livespec-dev-tooling-xpeeku`. Every rule below was paid for on
2026-10-12, during the `hp-xubuntu` `sandbox_storage` cutover
(`livespec-dev-tooling-smrzsj`), which lost hours to the opposite of each.

## Why not plain rsync, and why not your own split

One `rsync` walks a tree on one thread. Over containerd's millions of small
files on a DRAM-less SATA SSD it ran at ~1,100–3,000 `stat`/s (~10 MB/s),
which put the docker-down window at hours. The cost is per FILE, not per
byte, so the bandwidth figure says nothing about how long the copy will take.

A hand-rolled split — one `rsync` per depth-2 directory — collapsed to ONE
unit on that tree, because containerd keeps every snapshot under one depth-2
directory (`io.containerd.snapshotter.v1.overlayfs/snapshots`). A split chosen
by depth splits wherever the directories are, not wherever the files are.

`fpsync` crawls the tree with `fpart`, packs it into chunks bounded by file
count and byte size, and runs N `rsync`s over the chunks. The balance comes
from the data, not from the directory shape.

## 1. Measure the source before choosing anything

The split, the job count and the time estimate all come from the FILE COUNT
and where the files sit. Measure both first:

```bash
sudo du -s --inodes /var/lib/containerd                  # total entries
sudo du --inodes -d 3 /var/lib/containerd | sort -n | tail -20   # where they sit
sudo du -sh /var/lib/containerd                          # total bytes
```

If one directory holds most of the entries, no depth-based split will
parallelize it; that is the case `fpsync` exists for. A tree of a few large
files is the opposite case: one `rsync` is bandwidth-bound and parallelism
buys little.

## 2. Run fpsync with the flags it needs

```bash
sudo fpsync -n 8 -f 20000 -s $((4*1024*1024*1024)) -v \
  -o "-lptgoD -HAX --numeric-ids" \
  /var/lib/containerd/ /srv/new-disk/containerd/
```

- `-n` concurrent `rsync` jobs. Size it from the source disk, not the core
  count: a SATA SSD saturates on small-file `stat`s well before 18 cores do.
  Start at 8 and read `iostat -x 5` before going higher.
- `-f` / `-s` cap each chunk by files and by bytes; whichever is hit first
  closes the chunk.
- `-o` REPLACES fpsync's default rsync options (`-q -lptgoD --numeric-ids`)
  rather than adding to them, so `--numeric-ids` must be restated.
  `-lptgoD` is `-a` without `-r`; add `-HAX` for hard links, ACLs and
  xattrs. **`fpsync` rejects `-a` and `-r`** (and `--delete`): it feeds each
  rsync an explicit file list and handles recursion itself, so `-a` fails the
  option check before anything is copied.
- Source and destination are absolute paths with trailing slashes.
- `-S` runs the crawl and the rsyncs through sudo instead of running all of
  fpsync as root; `-t /dir/` moves the work directory off `/tmp` (default
  `/tmp/fpsync`) when `/tmp` is small or tmpfs.

Two consequences of the chunked design to know before trusting the copy:

- **`-H` only links files that land in the SAME chunk.** Hard links that
  cross a chunk boundary arrive as separate copies. For a tree that depends on
  hard links (some backup stores, `/var/lib/dpkg`-style layouts) either check
  the link count first (`find SRC -type f -links +1 | wc -l`) or finish with
  one plain `rsync -aHAX` pass over the tree.
- **The file-list mode never deletes.** A destination holding files the
  source no longer has keeps them. Copy into an empty destination, or finish
  with an `rsync --delete` pass. `-E` (per-directory mode) turns `--delete`
  on; use it only when that is what you want.

On macOS the bundled `rsync` does not accept every flag above; install
Homebrew's `rsync` and pass it with `-T "$(brew --prefix)/bin/rsync"`.

## 3. Give a long copy a progress log

A copy that runs for more than a few minutes with no output cannot be told
apart from a hung one, and the cutover lost time to exactly that. Run it
DETACHED (`setsid nohup … > copy.log 2>&1 &`) so it outlives the session,
with `-v` (or `-vv`) so the log records each chunk as it starts and finishes.
`fpsync` also writes per-run logs under `<tmpdir>/log/<runid>/`, and
`fpsync -l` lists runs with their status. An interrupted run is resumed, not
restarted: `fpsync -r <runid>` re-runs only the chunks that did not finish.

Report progress from the log as chunks done out of chunks total, never from a
guess. Watch it no more than once a minute.

## 4. Verify AFTER the copy, against a quiet source

Do not checksum during the copy. `rsync -c` reads every byte on both sides;
on hp it ran at ~10 MB/s and turned the copy itself into the bottleneck, and
against a live source a checksum mismatch only says the source moved.

Stop the writers first (the daemons, the service that owns the tree), then
verify:

```bash
sudo rsync -n -c -r -lptgoD -HAX --numeric-ids --delete --itemize-changes \
  /var/lib/containerd/ /srv/new-disk/containerd/
```

An empty itemized list is the verdict. Any line names a file to recopy; a
second, plain `rsync -aHAX --delete` pass over the quiet source fixes it and
also settles the cross-chunk hard links and stale files above. For a quick
first read, the same command without `-c` (size and mtime) is cheap and
catches a missed chunk.
