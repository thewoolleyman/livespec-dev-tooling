# livespec_dev_tooling/charters/

Importable charter-defect detector surface. This package deliberately lives
outside `livespec_dev_tooling/checks/` so detector availability does not create a
new canonical check slug or force fleet-wide just/CI wiring.

Only the package-level exports are the supported consumer surface:
`DETECTORS`, `CHARTER_GLOBS`, `defects_in(text=...)`, and
`charters_in(root=...)`. Helper modules are private implementation detail.
