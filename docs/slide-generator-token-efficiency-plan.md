# Slide-Generator — Token & Workflow Efficiency Plan

**Date:** 2026-06-23
**Scope:** `.agents/skills/slide-generator/SKILL.md` + `slide-system/scripts/` + `slide-system/workflows/`
**Goal:** Stop the orchestrating agent from pulling large files (0.2–12 MB) into its context, and fix one stale path that makes the documented decompose command fail on real library items.

This plan was produced by a two-subagent audit, then every load-bearing claim was
re-verified directly against the repo. Findings the audit got wrong are corrected below.

---

## How the system is *supposed* to work (and mostly does)

The architecture is correct in principle: **heavy files are read by scripts, not by the agent.**

| Heavy file | Max size | Who reads it | Agent sees |
|---|---|---|---|
| `visual-library.json` | 775 KB | nobody at runtime (source of truth) | — |
| `visual-library-compact.json` | 82 KB | `score_visual_items.py` (default registry) | scorer output only |
| `visual.svg` | **12 MB** | `decompose_svg_objects.py` (`read_text`) | `snippet.html` (small) |
| `text-slots.json` | 119 KB | *(today: the agent, manually)* | **whole file** ⚠ |

Two parts are already optimal and must be preserved as the model to imitate:
- `score_visual_items.py:212` defaults to the **compact** registry (82 KB), never the 775 KB full one.
- `decompose_svg_objects.py` reads the SVG itself and emits a small `snippet.html` + fragment SVGs; the agent only pastes the snippet.

The gap is everything that bypasses that pattern.

---

## Findings (verified, ranked)

### P0 — `artifact/` stale path: documented decompose command FAILS on library items
- **Where:** `SKILL.md:130`, `SKILL.md:133`, `SKILL.md:139`
- **Bug:** the skill tells the agent to run
  `decompose_svg_objects.py --svg <library-path>/artifact/visual.svg` and to fill
  slots from `artifact/text-slots.json`.
- **Reality (verified):** library items are **flat** —
  `slide-system/library/<type>/<item-id>/visual.svg` and `.../text-slots.json`.
  There is **no `artifact/` subdir anywhere under `slide-system/library/`**
  (`find slide-system/library -type d -name artifact` → empty).
- **Impact:** correctness, not just tokens. An agent that follows step 10 literally
  gets "SVG not found" and then improvises — likely falling back to raw CSS, which
  defeats the whole reuse pipeline the script gates are meant to enforce.
- **Fix:** drop the `artifact/` segment in SKILL.md:130/133/139. Correct paths:
  `--svg <library-path>/visual.svg`, slots from `<library-path>/text-slots.json`.
  > Note: the `artifact/` convention is real — but only for *extraction batches*
  > under `outputs/component-extractions/<id>/items/<page>/artifact/`. It leaked
  > into the library-reuse instructions, where it does not apply.

### P1 — No prohibition against Reading the huge artifacts; "load visual.svg" wording invites it
- **Where:** `SKILL.md:41`, `SKILL.md:73` ("load item's `visual.svg` + `text-slots.json`");
  Absolute Prohibitions (`SKILL.md:32–42`) and Token Optimization Rules (`SKILL.md:108–124`)
  cover file *creation/cleanup* but say **nothing about file reading**.
- **Risk:** `sun.component.learning-development/visual.svg` is **12.4 MB**;
  `update-summary` is **1.9 MB**. A single literal `Read` of one of these blows the
  context window. Verified cause: these SVGs are **~100% embedded base64 PNG**
  (learning-development = 7 PNG blobs = 100.0% of bytes; update-summary = 3 blobs = 99.6%).
- **Fix:** add one Absolute Prohibition line:
  > **NEVER `Read`/`cat` `visual.svg`, `evidence/*`, `preview/*`, `catalog-data.json`,
  > or `picker-data.json` into context — they are 0.2–12 MB.** Route them through
  > `decompose_svg_objects.py` / the scorer and consume only the script's compact output.
- **Fix:** reword SKILL.md:41/73 from "load … visual.svg" → "pass the item path to
  `decompose_svg_objects.py`; consume only `snippet.html` + `decompose-manifest.json`."

### P1 — `text-slots.json` read in full when ~13% is enough
- **Where:** `SKILL.md:73`, `SKILL.md:139` — "Fill text slots by role/id from text-slots.json."
- **Verified sizes:** the chart contract is **119 KB / 97 slots**, each slot carries 15
  fields (`typography`, `source_refs`, `style_overrides`, `anchor`, `z_order`, …).
  An HTML-builder only needs `id, role, example_value, bounds` (+ optionally `html_tag`,
  `typography`). A slim projection of those = **15.6 KB ≈ 12.7%** of the file — an ~8×
  token reduction.
- **Correction to an earlier idea:** `build_clone_deck.py` is **NOT** the fix here.
  Verified: it globs `<extraction-dir>/items/*/artifact/{visual.svg,text-slots.json}`
  (`build_clone_deck.py:187,191-210`) — the extraction-batch layout, which the flat
  library does not have. It cannot be aimed at a library item. Likewise
  `apply_text_contract.py --batch` needs `<batch>/items/` + `manifest.json`.
- **Fix:** add a tiny reader, e.g. `slide-system/scripts/read_text_slots.py
  --item <library-path> [--slots-only]` that emits the slim `{id,role,example_value,
  bounds,html_tag}` projection to stdout. SKILL.md step 10 invokes it instead of
  having the agent `Read` the 119 KB file. Full schema stays on disk for the
  export/contract stack that genuinely needs `typography`.

### P2 — Icon library: "extract by group/id" implies reading a 223 KB SVG
- **Where:** `SKILL.md:150-151` — load `guideline-icon-library/visual.svg` (223 KB),
  "Extract by group/id."
- **Fix:** instruct `grep -n 'id="<icon>"'` to find the group's line range, then read
  only that range — never `Read` the whole 223 KB file. (A dedicated extractor is
  overkill; grep is the cheap mitigation.)

### P2 — Library-tree glob hazard
- **Where:** `SKILL.md:128` ("Find item in library: …").
- **Risk:** an agent locating the item via `ls`/glob across `library/templates/`
  can incidentally surface/Read the 12 MB and 1.9 MB SVGs and their evidence/preview
  duplicates.
- **Fix:** "Take the item path **verbatim** from `selection-report.json`; do not glob
  `library/`." The scorer already returns the exact path.

### P3 — Orphan doc drift: `build-html-deck.md`
- **Verified:** `slide-system/workflows/build-html-deck.md` exists (6.3 KB) but is
  **not** listed in SKILL.md Conditional Reading, and SKILL.md says "Do NOT read other
  workflow docs." So the agent never reads it — yet it duplicates step 10 and carries
  the same `artifact/` path assumption.
- **Fix:** either delete it, or fold its useful "pre-build gate" content into SKILL.md
  and keep a single source of truth. Do not leave a second, stale copy of the build flow.

### P3 (disk, not agent-context) — triplicated multi-MB raster
- **Verified:** each component stores `visual.svg` + `evidence/source-with-text.svg` +
  `preview/preview.html`, all embedding the **same** PNG blobs. For learning-development
  that is ~12 MB × 3. `evidence/*` and `preview/*` are review-only
  (`apply_text_contract.py:42` — "SVG visual + text-slots is the single source of truth;
  parallel .html/.css … not carried into the artifact manifest").
- **Fix (optional, repo-size only):** externalize the PNGs to a shared file referenced by
  href, or downscale the preview raster. Does not affect agent tokens — purely repo weight.

---

## Action checklist (in order)

1. **[P0] SKILL.md:130/133/139** — remove `artifact/` from the decompose `--svg` path
   and the text-slots path. *Pure doc edit, unblocks the reuse pipeline.*
2. **[P1] SKILL.md Absolute Prohibitions** — add the "NEVER Read visual.svg/evidence/
   preview/catalog/picker" line.
3. **[P1] SKILL.md:41/73** — reword "load visual.svg" → "pass path to decomposer,
   consume snippet only."
4. **[P1] New script `read_text_slots.py --slots-only`** + wire into SKILL.md step 10 so
   the 119 KB contract is never Read in full. *~8× token cut on every reuse slide.*
5. **[P2] SKILL.md:150-151** — grep-by-id for icons, not full-file Read.
6. **[P2] SKILL.md:128** — use `selection-report.json` path verbatim; no library glob.
7. **[P3] build-html-deck.md** — delete or merge; eliminate the stale duplicate flow.
8. **[P3, optional] raster de-dup** — externalize/downscale PNGs in evidence/preview.

Items 1–3 are doc-only and ship immediately. Item 4 is the one new script and the
biggest recurring token win. Items 5–8 are hardening/cleanup.

---

## Verification per change
- **Doc edits (1,2,3,5,6,7):** `npx tsc`/lint not applicable; verify by grepping SKILL.md
  for `artifact/` (should be 0 under the library-reuse section) and for the new
  prohibition line.
- **New script (4):** run `read_text_slots.py --item <library-path> --slots-only` against
  the 119 KB chart contract; assert output is valid JSON, contains 97 slots, and is
  <20 KB. Add a one-line smoke test next to the other `scripts/` tests.
- **End-to-end:** run one reuse slide through the pipeline (score → decompose → build →
  export) and confirm no step Reads a file >82 KB into the agent.
