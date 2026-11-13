# Board exports — pre-adoption snapshots

These are read-only snapshots of hand-made Honeycomb boards, taken BEFORE the
boards were adopted into this directory's committed definitions. They live in
this subdirectory on purpose: `../apply-boards.sh` converges every `*.json`
directly beside itself (`"${SCRIPT_DIR}"/*.json`), and a snapshot is not a
definition it should apply.

## livespec-family-all-activity.krThv8DvcwS.2026-11-13.json

- Board `livespec family — all activity`, Honeycomb id `krThv8DvcwS`, env
  `livespec`. Exported 2026-11-13 at about 23:50Z by the kubernetes-observability
  seat with a configuration key: `GET /1/boards/krThv8DvcwS`, then each query
  panel's saved query (`GET /1/queries/<dataset>/<query_id>`) and annotation
  (`GET /1/query_annotations/<dataset>/<query_annotation_id>`).
- At export the board had 9 panels (8 query and 1 text). Its first two query
  panels (position 0,0 and 8,0) were already the throughput track's
  "THROUGHPUT — PRs merged green per hour, by repository" and "Merged but NOT
  green" panels over dataset `pr-throughput`. Those were placed by hand before
  this export, so this snapshot is the state immediately before the first
  `apply-boards.sh` write, not the state before any write.
- Input for livespec-dev-tooling-bgespb: its committed definition must carry
  every panel recorded here.

## livespec-family-all-activity.krThv8DvcwS.2026-11-13.pre-throughput.json

- The same board, `krThv8DvcwS`, exported earlier on 2026-11-13 (about 23:3xZ)
  by the throughput-track-organization seat, BEFORE the two throughput panels
  were placed on it. It has 7 panels (6 query and 1 text). It carries the saved
  query and annotation of each query panel under `queries` and `annotations`.
- This is the board's state before ANY write for the throughput track. It is
  the export that livespec-dev-tooling-bgespb's host-captured Definition of Done
  asks for ("taken before the first applied write"). The file above records
  the later, hand-edited state that `apply-boards.sh` first wrote over.
