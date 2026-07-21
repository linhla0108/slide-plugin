# Select Visual Items

Use `<project-python>` below: `.venv\Scripts\python.exe` on Windows and
`.venv/bin/python3` on macOS/Linux.

1. Load only `published` items from `registries/visual-library.json`.
2. Reject deprecated, staging, brand-incompatible, or export-incompatible items.
3. Write `analysis/visual-requests.json` with one request per slide. Each request
   must include: `request_id`, `intent`, `tags`, `content_structure`, `density`,
   `brand`, `required_exports`. Optionally include `item_count` (integer — how
   many parallel content items the slide carries, e.g. 4 roles): the scorer
   penalizes components whose declared `set-of-N` size cannot fit it.
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
   matches earn reduced, capped credit that improves ranking. Anti-use-case
   hits, `set-of-N` vs `item_count`
   mismatches, and components with zero editable text slots subtract score
   with explicit `reasons`; each candidate carries a `retrieval` block
   explaining its matches. The top published candidate is reusable when it
   passes the editable-content, count, visual-unit, and content-shape gates.
   Declare `repeatable-set-of-N` in `content_structure` alongside `item_count: N`
   whenever a slide is N parallel peer items: that evidence lets T1 shape-lock
   also accept a published component declaring the same set size, so a 4-card
   role set can host a 4-item checklist. Without both signals the base
   shape-lock applies unchanged. A
   candidate that repeats a different number of native units than the request's
   `item_count` (2 or more) stays ranked but is not buildable, so selection falls
   through to the next compatible published component or to `text-only`. Semantic score
   orders those candidates but does not block reuse. A source-topic mismatch is
   retained as a review warning rather than a blocker. When no published item
   is physically buildable, the decision is `text-only`. Keep the index fresh via
   `build_component_retrieval_index.py --check`.
5. **Validate the selection report (BLOCKING):**
   ```bash
   <project-python> slide-system/scripts/validate_selection_report.py \
       --selection-report <run>/analysis/selection-report.json \
       --visual-requests <run>/analysis/visual-requests.json
   ```
   EXIT 0 required before HTML build. EXIT 1 = re-run step 4.
   The T2 `visual_unit_lock` re-checks visual-unit fit here as defense in depth.
   The scorer already applies it during selection, so a passing report is the
   normal outcome; a failure here means the report was hand-edited or produced
   with `--unit-registry none`.
6. Reuse the top published candidate that passes the editable-content, count,
   and content-shape gates. Score orders candidates; it is not an approval band.
7. When no buildable candidate exists, generate a `text-only` slide from approved
   copy. Do not make a slide-local visual or custom component.
8. Record selected and rejected candidates with reasons.
9. Record an extraction recommendation when useful. Never trigger extraction;
   a user must explicitly approve any new component work.

Write one `analysis/visual-requests.json` and one `analysis/selection-report.json`
per run. Do not emit a separate file per section.

Select structure by semantic intent before visual resemblance.

Hand-writing `selection-report.json` is a pipeline violation — the validator
detects fake reports by checking schema, candidates array, criteria sub-scores,
and provenance fields.
