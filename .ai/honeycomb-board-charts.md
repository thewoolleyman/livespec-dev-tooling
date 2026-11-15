# Honeycomb board charts: readable at a glance

A board chart exists so a reader can see at a glance whether a number is improving, getting worse or holding steady. Every
chart change is judged by that, before it is applied.

## Never chart an outlier series beside the trend line

Do not add a series whose values are orders of magnitude off the line a reader compares over time. That includes a breakdown
by a confound column, an incident's held population, or a "slowed" class. The y-axis rescales to the outlier and the line
that matters goes flat.

- **Chart only the comparable population.** Filter the chart to it, for example `pr.disruption = clean` and one definition
  (`pr.lead_rule = new start rule`).
- **Show the excluded population as COUNTS, not lines.** Put it in a separate table panel, named so it says what the
  charts leave out and why, and in the board text.
- **Keep definitions apart.** Two definitions of one metric, such as lead time under the old and new start rules, never
  share a chart. Chart the current definition and leave the old one in a table until a rebuild makes them comparable.

Before applying a board change, ask of every chart: will its largest series dwarf the one a reader compares over time? If
yes, filter that series out of the chart and move it to a table.

## Why

On 2026-11-15 plan throughput-metric made the livespec throughput board's confounds visible by breaking its M2 and M3 charts
down by `pr.disruption`. The confounds were merge-quiet holds and the CI pool stall. The "held" lines were orders of
magnitude above the clean line and flattened it. The maintainer:

> The "held" line here is orders of magnitude bigger than the other lines. It makes the chart unusable for an eyeball
> improvement. ... that line doesn't give any useful ongoing information as a huge outlier. Your goal is to make charts that
> give info AT A GLANCE.

The fix kept the confound visible and moved it off the chart. The charts filter to the clean, new-rule series. One table
counts what they exclude. The board text names each window, rendered from
`ci-runner/observability/throughput/disruption-windows.json`.
