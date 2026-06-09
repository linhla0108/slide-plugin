# Per-Phase Execution Plan

> Legacy contract: preserve this file for historical phase work. New AI slide
> jobs use `.agents/skills/slide-generator/SKILL.md` and `slide-system/`.

`plan.md` is the master contract. This file only divides work, defines phase
gates, and tracks phase-specific inputs and reports. It must not override source
authority, content fidelity, component selection, export, or QA rules from
`plan.md`.

## Agent Startup Order

For a new session:

1. Read `AGENTS.md`.
2. Read `plan.md`.
3. Read this file.
4. Read the active `reports/phase_{number}.md`.
5. Load `sun-studio-design-system`.
6. Load `pptx`.
7. Load `svg-extractor`.
8. Load `make-a-deck` when HTML construction begins.
9. Load `export-as-editable-pptx` for native PPTX export.
10. Load `ppt-master` for the fidelity branch.
11. Load the browser testing skill for visual QA.

## Shared Input

All phases use:

```text
input/SUN.RISER 2026 - Be professional at SUN.STUDIO.pptx
input/SUN.RISER 2026 - Be professional at SUN.STUDIO.pdf
input/SUN.RISER 2026 - Be professional at SUN.STUDIO (PNG)/
input/SUN.RISER 2026 - Be professional at SUN.STUDIO (SVG)/
```

Never use duplicate source files outside `input/`.

## Phase Boundaries

| Phase | Slides | PNG input | SVG input | Report | Output |
|---|---:|---|---|---|---|
| 1 | 1-10 | `1.png`-`10.png` | `1.svg`-`10.svg` | `reports/phase_1.md` | `outputs/phase-01-slides-01-10/` |
| 2 | 11-20 | `11.png`-`20.png` | `11.svg`-`20.svg` | `reports/phase_2.md` | `outputs/phase-02-slides-11-20/` |
| 3 | 21-28 | `21.png`-`28.png` | `21.svg`-`28.svg` | `reports/phase_3.md` | `outputs/phase-03-slides-21-28/` |

Before extraction, verify every expected PNG/SVG pair, validate each SVG with
`xmllint`, and record coverage and checksums in the report and phase manifest.

## Workflow Per Phase

1. Read the master plan, this plan, and the active phase report.
2. Verify shared PPTX/PDF and all numbered PNG/SVG pairs for the phase.
3. Extract PPTX/OOXML, SVG, PNG, and PDF evidence.
4. Create the content manifest and wireframe/semantic map.
5. Select structural components and compatible visual treatments.
6. Present the mapping report and wait for explicit approval.
7. Build and QA the phase's HTML slides.
8. Export and QA the editable PPTX.
9. Run and QA the PPT Master branch from disposable working copies.
10. Update divergence, copy, export-limit, QA, manifest, and phase report files.
11. Present the completed phase and wait for user approval.

Do not begin the next phase while the active report is `blocked` or
`awaiting-approval`.

## Phase Gates

### Mapping Gate

All slides in the phase must have an approved slide-level composition and
region mapping. A blocker on one slide does not prevent independent analysis of
other slides, but phase build cannot be declared complete while any slide
mapping remains unresolved.

### Completion Gate

The phase must satisfy all completion rules in `plan.md`, then receive explicit
user approval. Set report status to `completed` only after that approval.

## Cross-Phase Baseline

- Phase 1 establishes typography, spacing, footer, component treatments, and
  export conventions.
- Phases 2 and 3 inherit the approved baseline.
- Do not change visual language silently between phases.
- Record shared-component changes and impacted slides before applying them.
- Backport a later improvement to an approved phase only after user approval.
- Finalize the reusable workflow after real Phase 1 findings, not from
  assumptions made before execution.

## Report Contract

Each `reports/phase_{number}.md` must contain:

- Status
- Slide range
- Input coverage
- PNG coverage
- SVG coverage
- SVG validation failures
- Missing/broken external references
- Text converted to paths
- Reusable vector assets
- Progress by mapping, HTML, editable PPTX, PPT Master, and QA
- Decisions
- Notes
- Blockers
- Divergences
- Artifacts
- Next action
- User approval

Update the report when starting a phase, finishing extraction, entering either
approval gate, encountering a blocker, finishing an export, completing QA, and
receiving user approval.

Allowed status values:

```text
pending
extracting
mapping
awaiting-mapping-approval
building
exporting
qa
blocked
awaiting-phase-approval
completed
```
