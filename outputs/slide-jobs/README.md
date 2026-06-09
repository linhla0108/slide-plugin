# Slide Jobs

Each job uses:

```text
<job-id>/
├── requirements/
├── inputs/
├── assets/                       shared across all runs; never re-copied per run
└── runs/<run-id>/
    ├── analysis/                 one visual-requests.json + one selection-report.json
    ├── content/
    ├── plan/
    ├── slide-source/html/        references ../../assets and the brand pack in place
    ├── exports/html/
    ├── exports/pptx/editable/
    ├── exports/pptx/ppt-master/
    ├── exports/pptx/image-fallback/
    ├── exports/pdf/
    ├── qa/                       qa-report.md + metrics only; export-renders are ephemeral
    ├── reports/
    └── manifest.json
```

## File-count discipline

- Brand fonts, icons, and brand images load from the brand pack in place. Job
  assets live once in `<job-id>/assets/`. Runs reference, never re-copy them.
- Analysis writes two consolidated JSON files per run, keyed by section — not
  one pair of files per section.
- `qa/export-renders/` capture, overlay, and difference images are intermediate.
  Delete them once render parity passes; keep only the report, metrics, and
  checksums.
- One-off build scripts belong in `slide-system/scripts/`, not in the run.

