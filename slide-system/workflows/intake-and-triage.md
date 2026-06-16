# Intake And Triage

Run this first, before planning or build. It turns any starting point into a
confirmed deck brief.

## Persona

- Treat a new user as non-technical by default. Use plain language; avoid jargon
  like "deck", "DOM", "raster", or format names without a short explanation.
- Attach a guess to every question so the user can react instead of inventing an
  answer. Ask one question at a time.
- Tech escape hatch: if the user pastes a complete brief or says they would
  rather fill it in themselves, switch to short mode and only ask about gaps.

## Confidence Rule

- Keep asking until you can predict the user's next answers, or until about five
  to six questions, whichever comes first.
- Fill anything still unknown with a sensible default and state the default in
  the recap rather than asking more.
- One question per turn, each with a guess. Do not batch.

## Export Format Normalization

- Treat "PowerPoint", "power point", "PPT", and "PPTX" as an explicit request
  for an editable `.pptx`.
- Default that request to layered export so supported content remains separate,
  movable, and editable.
- Do not ask whether the user means `.ppt` versus `.pptx`, or whether the
  PowerPoint should be editable. Record "editable PPTX" in the brief recap.
- Use flat/frozen PPTX only when the user explicitly asks for a flattened,
  image-only, frozen, or non-editable presentation.
- If the user requests PowerPoint plus another format, such as PDF, export both.
- Ask about export format only when the user has not named or clearly implied
  any output format.

## Triage

Read the input, guess the case, and confirm it in plain words before asking
case questions. Route to one case. Every skill below ships in this repo under
`.agents/skills/`; do not depend on skills outside the repo, so the system stays
self-contained when packaged as a plugin.

| Case | Trigger | Uses |
|---|---|---|
| 1 New from idea or brief | Describes content to create, with or without a brief | `plan-slide-deck`, `select-visual-items`, `make-a-deck`, `sun-studio-design-system`, `content-fidelity`, `source-authority` |
| 2 Wants advice | "I don't know where to start", "advise me" | The guided questioning in this workflow, plus `make-a-deck` and `sun-studio-design-system` for direction, then folds into Case 1 |
| 3 Polish existing file | Supplies a `.pptx` or `.pdf` to improve | `pptx`, `content-fidelity`, `verify-render-parity`; `export-as-editable-pptx` or `send-to-canva` when rebuilding |
| 4 Rebuild or redesign from reference | Supplies an image/screenshot/PDF to match or improve | `svg-extractor`, `ppt-master` or `make-a-deck`, `content-fidelity` |
| 5 Iterate a previous run | "change slide 3", "add to yesterday's deck" | `resume-job`, `pptx` |
| 6 Rebrand or localize | "same deck, brand X" or "translate it" | `sun-studio-design-system`, `source-authority`, `pptx` |
| 7 Raw data to slides | Supplies a doc, table, or numbers | `ppt-master` or `make-a-deck`, `content-fidelity`, `select-visual-items` |

Deck size (single slide or asset vs full deck) is one question inside the case,
not a separate case.

## Case Questions

### Case 1 — New from idea or brief
Ask, measuring confidence and skipping anything already supplied: purpose and
context, audience, main content and whether wording is fixed or open, style and
tone. Then, after style and tone but before slide count, offer the published
templates as a starting point — something like "I have N published slide
templates ready to go — want to browse and pick one as a starting point?" If
yes, serve the template picker and record the chosen template id; if no, just
carry on. Then ask slide count, image and icon needs, brand pack, export format.
Apply Export Format Normalization before deciding that export format is missing.
With a full brief, analyze it and ask only about missing or unclear parts.

### Case 2 — Wants advice
Use the guided questioning above (one question at a time, each with a guess) to
surface the real intent — no external interview skill is needed. Offer direction
with the repo's slide-design skills `make-a-deck` (narrative and slide design)
and `sun-studio-design-system` (brand and slide language). When the user is
unsure of a look, offer to browse the published slide templates together and
pick one as a concrete starting point — a real layout is often easier to react
to than an abstract description. Keep advice tied to slide output. Hand the
agreed direction into the Case 1 questions.

### Case 3 — Polish existing file
If the file is directly editable, polish it in place with `pptx` and skip export
setup. If it is not editable (flat PDF, image-only PPTX), explain this simply and
offer to rebuild an editable version, exporting via `export-as-editable-pptx` or
`send-to-canva` as the user prefers. Only recommend a hand-off to
`/component-extractor` if the user wants reusable pieces; never run extraction
here. Preserve wording and numbers per `content-fidelity`.

### Case 4 — Rebuild or redesign from reference
Ask the key split: keep the content as-is (reconstruction, preserve verbatim) or
change the look (redesign, keep the message). Mark redesigns as non-parity. Do
not copy a reference brand's protected artwork.

### Case 5 — Iterate a previous run
Read the existing job and latest run via `resume-job`. Ask only what changes;
do not re-interview from scratch. Confirm referenced inputs and items still
exist.

### Case 6 — Rebrand or localize
Keep content and layout; swap brand pack or language. Watch for layout breaks
from font or text-length changes. Confirm the target brand pack explicitly.

### Case 7 — Raw data to slides
Ask for the main message, which data becomes charts vs tables, and the summary
level. For a source document (PDF/DOCX/URL/Markdown), `ppt-master` converts it
into slides; otherwise plan with `make-a-deck`. Never invent or distort numbers.
Avoid overloading one slide.

## Brief Recap Gate

End intake with a short, plain-language recap of everything gathered:

- Purpose and context
- Audience
- Main content and source fidelity
- Style direction
- Base template (chosen template id, or none)
- Slide count
- Image and icon needs
- Brand pack
- Export format
- Out of scope, if any

Show the recap, let the user skim it, and wait for an explicit confirmation. Do
not start building until the user agrees. The recap becomes the job requirements
and the export contract.

## Non-Interactive Guard

This workflow needs a live user. In a non-interactive context (CI, scheduled
run, loop) with an incomplete brief, stop and report the missing information as
a blocker instead of guessing.
