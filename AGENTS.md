# SUN.RISER 2026 Agent Context

@/Users/home/.codex/RTK.md

## Default Entry Points

For new AI slide work, use:

- `.agents/skills/slide-generator/SKILL.md` for deck generation and export.
- `.agents/skills/component-extractor/SKILL.md` for manual, user-selected
  component extraction.

The shared architecture is documented in `slide-system/README.md`.
Historical SUN.RISER planning contracts and phase artifacts have been removed;
use the active skills, rules, workflows, registries, and brand pack instead.

Use `rtk` as required by `/Users/home/.codex/RTK.md`.

## Source Order

For a new slide job, read:

1. `AGENTS.md`
2. The selected orchestrator skill
3. `slide-system/README.md`
4. Relevant workflows and rules under `slide-system/`
5. The selected brand-pack manifest
6. Job inputs and approved requirement package
7. Published items in `slide-system/registries/visual-library.json`

## Task Logging (required)

Keep a detailed, append-only log of work done in this repo. This is mandatory,
not optional.

- **Where:** one file per day at `docs/logs/SESSION-LOG-<YYYY-MM-DD>.md` (date
  from the `currentDate` context). All session logs live in `docs/logs/` — never
  loose in `docs/` or the repo root. Append to that day's file across sessions;
  create it (and the `docs/logs/` folder) if missing.
- **When:** record each task as soon as it is completed (or meaningfully
  advanced) — do not wait until the end of a session.
- **What to record for every task:**
  1. **Request** — what the user asked, in their words or a faithful paraphrase.
  2. **Actions** — concrete steps taken: files created/modified/deleted, scripts
     and commands run, decisions made and why.
  3. **Result** — outcome, and verification run (tests, gates, scans) with their
     status.
  4. **Files** — comma-separated paths touched (or `none`).
  5. **Symbols** — comma-separated code symbols changed (or `none`); resolvable
     later via `codegraph node <symbol>`.
  6. **State** — whether changes were committed; if not, say so explicitly.
- **Faithfulness:** log only what actually happened. No invented steps, no
  guessed outcomes. If a step was skipped or failed, say so.
- Group entries by task in request order; ground file/line/count claims in real
  `git status` / command output rather than memory.
- **Format:** number entries **per day** as `<YYYY-MM-DD>.<n>` (`<n>` restarts at
  1 in each day's file — no global running integer, which breaks across
  sessions/agents). One `##` heading per entry; use the same fields every time.
  Do **not** mix `§`, `Task:`, or a single global integer, and do not create
  per-topic log files (`LOG-<date>-<topic>.md`, `REPORT-*.md`) — an audit/report
  is a task entry inside that day's session log. The canonical template lives at
  `docs/logs/_TEMPLATE.md`:

  ```markdown
  ## <YYYY-MM-DD>.<n> — <Short imperative title>

  **When:** <YYYY-MM-DD HH:MM>   (optional; only if actually known)
  **Request:** <user ask, verbatim or faithful paraphrase>
  **Actions:**
  - <files/commands/decisions + why>
  **Result:** <outcome + verification (tests/gates/scans) and status>
  **Files:** <paths touched, or `none`>
  **Symbols:** <code symbols changed, or `none`>
  **State:** Committed <hash> | Not committed
  ```

  If a later entry overturns an earlier one, add a `> ⚠️ SUPERSEDED by entry <id>`
  note to the old entry instead of rewriting it.

- **Index:** after appending an entry, run
  `python3 slide-system/scripts/build_log_index.py --write` to refresh
  `docs/logs/INDEX.jsonl` (derived from the prose logs; never hand-edit it).
  `--check` exits non-zero when the index is stale.

- **Reading the log efficiently (for agents).** Do NOT read whole session-log
  files top to bottom. Instead:
  1. `rtk grep <file|symbol|keyword> docs/logs/INDEX.jsonl` (or `rtk json`) to
     find the 1–3 relevant entry ids cheaply.
  2. Read only those entries' prose in the referenced `SESSION-LOG-<date>.md`.
  3. A log records the past — its code/number claims may be stale. For the
     **current** state of any symbol it names, run `codegraph node <symbol>`
     rather than trusting the log. Re-verify before asserting.

## Product Direction

This workspace serves SUN.STUDIO slide creators, reviewers, mentors, and
internal teams producing training, onboarding, workshop, and presentation
materials from structured prompts and approved brand resources.

Outputs should be content-faithful, on brand, editable where required, and
packaged with source authority, QA evidence, checksums, and delivery manifests.

Use a friendly, skilled, reliable voice: energetic but professional, coaching
rather than lecturing, and concise enough for internal presentations.

## Canonical SUN.STUDIO Assets

Do not move or duplicate the canonical design system. It remains at:

- `.agents/skills/sun-studio-design-system/SKILL.md`
- `.agents/skills/sun-studio-design-system/assets/system/`

Use its token stylesheet, Proxima Nova fonts, logo, Dio poses, canonical
components, and reference slides. `slide-system/brand-packs/sun-studio/`
references these assets through a portable manifest.

Primary brand values:

- Orange: `#FF5533`
- Blue: `#3333FF`
- Warm paper: `#FFFDF8`
- Ink: `#171717`
- Canvas: `1920x1080`, 16:9

`#3531FF` is a documented legacy source value and is not a canonical token.

## Shared Visual Library

- Generation may read only items with `status: published`.
- `qa` and `staging` items remain review-only.
- Select by semantic intent and content structure before appearance.
- Keep full-slide templates separate from atomic components and styles.
- Keep semantic foreground content editable where required.
- Use separate raster layers for export-risk visuals: background-only PNG for
  passive canvas treatments, and independent transparent PNG overlays for
  complex elements, blur, shadows, glow, masks, filters, blend modes, and
  blended gradients that must stay visually faithful.
- Never trigger extraction automatically from slide generation.

## Output Boundaries

New slide jobs:

`outputs/slide-jobs/<job-id>/`

Manual extraction jobs:

`outputs/component-extractions/<extraction-id>/`

Do not mix job outputs, extraction staging packages, shared library artifacts,
or canonical brand assets.

## Approval

Slide generation has one approval gate before build. Component extraction is
manual-only and requires source path, slide or page, and exact region or object.
Each item requires explicit approval before publication.

## Content And Quality

- Preserve approved source content exactly unless the user approves edits.
- Record copy suggestions separately.
- Avoid generic AI slide templates, stock-looking visuals, overused glass
  cards, decorative gradients without content purpose, unsupported staging
  components, and unapproved changes to generated outputs.
- Preserve source authority before visual invention.
- Use one strong visual anchor per slide.
- Prefer published reusable resources before creating slide-local structures.
- Keep foreground content editable and reviewable.
- Target clear projection readability at `1920x1080`, strong text contrast,
  restrained motion with reduced-motion support, no overlapping text, and slide
  layouts that remain legible when scaled in the deck viewer.
- Record source authority, selected/rejected visual candidates, overrides,
  export limitations, and checksums.
- Verify HTML content, editable PPTX objects, PDF render, PPTX ZIP integrity,
  font availability, image crop and z-order, and HTML-versus-PPTX evidence.

<!-- CODEGRAPH_START -->
## CodeGraph

In repositories indexed by CodeGraph (a `.codegraph/` directory exists at the repo root), reach for it BEFORE grep/find or reading files when you need to understand or locate code:

- **MCP tools** (when available): `codegraph_explore` answers most code questions in one call — the relevant symbols' verbatim source plus the call paths between them. `codegraph_node` returns one symbol's source + callers, or reads a whole file with line numbers. If the tools are listed but deferred, load them by name via tool search.
- **Shell** (always works): `codegraph explore "<symbol names or question>"` and `codegraph node <symbol-or-file>` print the same output.

If there is no `.codegraph/` directory, skip CodeGraph entirely — indexing is the user's decision.
<!-- CODEGRAPH_END -->
