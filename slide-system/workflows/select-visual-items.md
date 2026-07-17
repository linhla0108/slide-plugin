# Select Visual Items

Use `<project-python>` below: `.venv\Scripts\python.exe` on Windows and
`.venv/bin/python3` on macOS/Linux.

1. Load only `published` items from `registries/visual-library.json`.
2. Reject deprecated, staging, brand-incompatible, or export-incompatible items.
3. Write `analysis/visual-requests.json` with one request per slide. Each request
   must include: `request_id`, `intent`, `tags`, `content_structure`,
   `content_shape`, `density`, `brand`, `required_exports`. `content_shape` is
   REQUIRED: it must be one of the shapes in the single shared vocabulary
   `SHAPE_TYPE_MAP` in `slide-system/scripts/_common.py` — the one source of
   truth the scorer and validator share; do not copy the list here. It drives
   shape-aware candidate eligibility, so a missing or wrong `content_shape`
   changes selection (and fails the strict validation in step 5).
   Include `content_plan` — the structured expansion of the user's brief for this
   slide: the ACTUAL content items the approved plan holds, one string per item
   (the three distinct next-steps, not one merged sentence). Write it BEFORE
   selection, so the plan drives the component choice instead of the component
   silently capping the content. Its length is the planned item count. Selection
   compares that count against each candidate's capacity (`content_blocks` — how
   many distinct content items the component's own slot contract can hold): a
   component that cannot hold the plan is barred from AUTOMATIC reuse, because
   reusing it would force approved content to be cut down to fit (a one-headline
   CTA slide can never auto-serve a 4-item checklist). It is a FLOOR, so a 1-item
   plan still fits a 1-block component and sparse-by-design covers/CTAs/closings
   keep working. An explicit `component_id` may still pick a component that does
   not fit, but the decision records a plain capacity warning (`capacity_conflict`)
   and stays subject to the scaffold/fidelity/export gates — choosing it is not
   evidence the content fits. Omit `content_plan` when the slide has no itemised
   plan: the check is then a no-op.
   Optionally include `item_count` (integer — how many parallel content items the
   slide carries, e.g. 4 roles) for a slide that states a count without listing the
   copy; the scorer also penalizes components whose declared `set-of-N` size cannot
   fit it. It does NOT override `content_plan`: when a request carries both they
   MUST agree, and a mismatch fails validation before scoring (step 5) rather than
   being silently resolved by precedence.
   Optionally include a type-intent hint so all-types scoring does not let a
   full-slide template out-rank a genuinely relevant component: set
   `prefer_type` to `component` or `template`, or carry the wording in a
   free-text `query` (e.g. `reusable component ...`, `full slide template ...`).
   When component intent is explicit, `type: template` items are demoted a
   modest, bounded amount (surfaced in `reasons`); template intent and neutral
   requests demote nothing, and component-only scoring is unaffected.
4. Run the scorer in **batch mode** to score ALL item types (templates AND
   standalone components — cover, timeline, checklist, comparison, closing, CTA,
   statistics, dividers, layouts) for every slide:
   ```bash
   <project-python> slide-system/scripts/score_visual_items.py \
       --batch-request <run>/analysis/visual-requests.json \
       --output <run>/analysis/selection-report.json
   ```
   When the brief has `base_template` from a template set, pass
   `--prefer-set <set-prefix>` for same-set scoring bonus.
   Do NOT use `--item-type template` — score ALL types so standalone
   components (cover-hero, timeline, checklist, etc.) are also considered.

   The scorer automatically broadens lexical matching with
   `registries/component-retrieval-index.jsonl` (published items only; pass
   `--retrieval-index none` to disable). Keywords, `component_type`,
   `layout_role`, `visual_summary`, `retrieval_notes`, and `use_cases`
   matches earn reduced, capped credit that improves ranking but can never
   cross the semantic floor on its own — canonical `intent`/`tags` overlap is
   still what makes an item selectable, so generic metadata overlap cannot
   force a bad pick. Anti-use-case hits, `set-of-N` vs `item_count`
   mismatches, and components with zero editable text slots subtract score
   with explicit `reasons`; each candidate carries a `retrieval` block
   explaining its matches. Selection score still != buildability — verify
   geometry/count/domain fit before building (see the 2026-07-07 session
   lessons). If the highest raw scorer is below the semantic floor, the
   decision may select the best semantically valid runner-up; that selected
   item is still emitted in `candidates` with its score and reasons. Keep the
   index fresh via
   `build_component_retrieval_index.py --check`.
5. **Validate the selection report (BLOCKING):**
   ```bash
   <project-python> slide-system/scripts/validate_selection_report.py \
       --selection-report <run>/analysis/selection-report.json \
       --visual-requests <run>/analysis/visual-requests.json \
       --strict-shape
   ```
   EXIT 0 required before HTML build. EXIT 1 = re-run step 4. `--strict-shape`
   makes a missing or unknown `content_shape` a hard failure, so shape-aware
   selection is always enforced in the normal workflow (never silently skipped).
6. `reuse` (AUTOMATIC) only when the top candidate is published, shape-compatible,
   slot/render-compatible, **auto-reuse-eligible** (no recorded full-slide QA
   failure — see `auto_reuse` below), unused elsewhere in the deck, AND clears the
   high-confidence bar: total score `>= 78` AND `semantic_intent >= 24.5`
   (`0.7 × 35`). A mediocre total never authorises reuse — the semantic sub-score
   is the discriminator. Deck allocation considers the FULL scored pool; `--top-n`
   only trims what the report displays.
7. `needs_component` for everything else automatic — low confidence, no fit, or
   duplicate-only. Build NOTHING. The decision carries a plain reason, suggested
   search terms, top safe candidates, and the exact next user action: search the
   web catalog, copy a component's ID (or its prompt), and set `component_id` on
   the slide; or set `unresolved_policy: "custom-local"`.
8. `custom-local` ONLY when the user explicitly approves it (`unresolved_policy:
   "custom-local"`) after reviewing the library. The scorer never auto-creates a
   custom layout. `adapt-local` is retired.
9. A user may name a component explicitly with `component_id` (a stable id or the
   catalog "Copy prompt" text). It bypasses the auto bar but still validates
   (published + shape/type + editable slots + render fidelity); on failure the
   slide stays `needs_component`.
10. No published component is auto-reused on two slides. A slide whose only
    high-confidence candidates are already assigned becomes `needs_component`
    unless it sets `allow_component_reuse: true` (recorded + shown in review).
11. A published component may carry `auto_reuse: {eligible:false, reason}` when its
    full-slide materialization/render QA actually failed. It stays published and
    catalog/retrieval-browseable for human review, but is NEVER auto-selected; an
    explicit `component_id` for it is recorded with the warning and the fidelity
    gate rejects the build.
12. Record selected and rejected candidates with reasons, and an extraction
    recommendation when useful. Never trigger extraction.

## The artifact users edit: `<run>/analysis/visual-requests.json`

Per-slide selections live in the batch visual-request artifact — **not** in
`job-requirements.json`. `score_visual_items.py` validates it BEFORE any scoring;
a bad field exits non-zero with a plain reason and writes no report. The contract
is documented in `slide-system/schemas/visual-requests.schema.json` and enforced in
code by `validate_batch_request()` — the file is not evaluated as JSON Schema at
runtime (no `jsonschema` dependency), but a parity test reads it and proves the code
enforces every field and type it declares. To resolve a `needs_component` slide,
edit that slide object and re-run steps 4–5:

```jsonc
{
  "job_id": "my-job",
  "slides": [
    {
      "request_id": "s5-model-tiers",
      "intent": ["comparison", "tiers"],
      "content_structure": ["label"],
      "content_shape": "tiers",
      // paste a stable id OR the catalog "Copy prompt" text:
      "component_id": "sun.component.foundation-top1-microsoft-overlap-circle-set",
      "allow_component_reuse": false,      // true only to reuse an already-assigned component
      "unresolved_policy": null            // "custom-local" = explicit approval to build custom
    }
  ]
}
```

Write one `analysis/visual-requests.json` and one `analysis/selection-report.json`
per run. Do not emit a separate file per section.

Select structure by semantic intent before visual resemblance.

Hand-writing `selection-report.json` is a pipeline violation — the validator
detects fake reports by checking schema, candidates array, criteria sub-scores,
and provenance fields.
