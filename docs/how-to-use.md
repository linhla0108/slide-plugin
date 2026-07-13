# Plugin User Guide

A quick Windows guide for Claude Code, Codex, and OpenCode. After the one-time
setup, you can describe the slide or component you want in plain language.

> **Reading tip:** Each section includes a **sample conversation box** (what you
> type, what Claude replies), a **step diagram**, and **a spot to insert your
> own real screenshots**.

---

## Before You Begin

- Open PowerShell in the `slide-plugin` folder and run the one-time setup:

  ```powershell
  powershell -ExecutionPolicy Bypass -File .\slide-system\scripts\setup.ps1
  ```

- The setup is local to this folder. It uses `.venv\Scripts\python.exe` and the
  existing project requirements; it does not install a global Python package.
- Start your chosen host from the repository root so it can discover the skills.
- Have your content ready (text, notes, or a file you want to turn into slides).

### Install or discover the skills

- **Claude Code:** run `/plugin marketplace add E:\slide-plugin`, then
  `/plugin install sun-riser@slide-plugin`. Use
  `/sun-riser:slide-generator` or `/sun-riser:component-extractor`.
- **Codex:** no install copy is needed. Codex discovers `.agents/skills`
  automatically from the repo. Mention `$slide-generator` or
  `$component-extractor` in your prompt.
- **OpenCode:** no install copy is needed. OpenCode discovers `.agents/skills`
  automatically. Type `/component <PDF path and what to extract>` for the
  supported PDF Draft workflow, or ask naturally for slide generation.

There is no portable universal `/component` command. The names above are the
native entrypoints supported by each host.

<!--
  INSERT IMAGE: The Claude app's home screen with an empty chat box.
  ![Claude home screen](./images/01-man-hinh-chinh.png)
-->

---

## 1. Create Slides — "Slide Generator"

Use this when you want a brand-new presentation.

### Step diagram

```text
  ┌────────────────────────────────────┐
  │ 1. You say:                        │
  │    "Create a presentation for me…" │
  └──────────────┬─────────────────────┘
                 ▼
  ┌────────────────────────────────────┐
  │ 2. Claude asks a few simple Qs     │◀──────────┐
  └──────────────┬─────────────────────┘           │
                 ▼                                  │
  ┌────────────────────────────────────┐           │
  │ 3. Claude gives a short plan       │           │
  └──────────────┬─────────────────────┘           │
                 ▼                                  │
            ┌──────────┐  "Change it…"              │
            │ You read │ ───────────────────────────┘
            │ & approve│
            └────┬─────┘
                 │ "Go ahead"
                 ▼
  ┌────────────────────────────────────┐
  │ 4. Claude builds the slides        │
  └──────────────┬─────────────────────┘
                 ▼
  ┌────────────────────────────────────┐
  │ 5. Get an editable PowerPoint      │
  │    (.pptx) file ✅                 │
  └────────────────────────────────────┘
```

### Sample conversation

```text
┌─────────────────────────────────────────────────────────────┐
│  YOU:                                                        │
│  Create a 5-slide presentation for me about the new          │
│  employee onboarding program.                                │
└─────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│  CLAUDE:                                                     │
│  Great! A couple of quick questions:                         │
│  • The audience is new employees, right? (hint: Yes)         │
│  • Do you want a young, energetic style? (hint: Yes)         │
│  Just answer "yes" or pick a hint.                           │
└─────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│  YOU:  Yes to all.                                           │
└─────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│  CLAUDE:                                                     │
│  Here's the 5-slide plan:                                    │
│   1. Welcome      2. Goals      3. Schedule                  │
│   4. Contacts     5. Next steps                              │
│  Approve it and I'll start building?                         │
└─────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│  YOU:  Go ahead.                                             │
└─────────────────────────────────────────────────────────────┘
```

**Or if you already have notes/a file ready:**

> "Turn this document into a slide deck." *(then attach or paste your content)*

### What you'll get

1. Claude asks a few simple questions (topic, number of slides, style). Each
   one comes with a hint — you just say "yes" or pick one.
2. Claude gives a short plan before building. Look it over, then say **"go
   ahead"** when it looks good.
3. Claude builds the slides and gives you a **PowerPoint (.pptx) file** that you
   can open and edit yourself.

**Good to know:**

- If you say "PowerPoint", "PPT", or "PPTX", you'll get an editable PowerPoint
  file (the default).
- You can always ask for changes: *"Shorten slide 3"* or *"Use brighter
  colors."*

<!--
  INSERT IMAGE: Claude asking the simple questions + the slide plan.
  ![Claude asks and gives a plan](./images/02-tao-slide.png)

  INSERT IMAGE: The resulting .pptx PowerPoint file opened up.
  ![Resulting PowerPoint file](./images/03-ket-qua-pptx.png)
-->

---

## 2. Take a Part From a Slide — "Component Extractor"

Use this when you like **a part of an existing slide** and want to reuse it —
for example a chart, a title block, a background, or a whole slide.

### Step diagram

```text
  ┌────────────────────────────────────┐
  │ 1. You say:                        │
  │    "Take the … from slide …"       │
  └──────────────┬─────────────────────┘
                 ▼
  ┌────────────────────────────────────┐
  │ 2. Tell which file + which part    │◀────────────┐
  └──────────────┬─────────────────────┘             │
                 ▼                                    │
  ┌────────────────────────────────────┐             │
  │ 3. Claude extracts that part       │             │
  └──────────────┬─────────────────────┘             │
                 ▼                                    │
  ┌────────────────────────────────────┐             │
  │ 4. Claude shows you a preview      │             │
  └──────────────┬─────────────────────┘             │
                 ▼                                    │
            ┌──────────┐ "Not this one"                │
            │ You read │ ──────────────────────────────┘
            │ & approve│
            └────┬─────┘
                 │ "Save it"
                 ▼
  ┌────────────────────────────────────┐
  │ 5. That part is saved for reuse ✅ │
  └────────────────────────────────────┘
```

### Sample conversation

```text
┌─────────────────────────────────────────────────────────────┐
│  YOU:                                                        │
│  Take the orange chart on slide 4 and save it so I can reuse.│
└─────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│  CLAUDE:                                                     │
│  Done! I've extracted the orange chart from slide 4.         │
│  Here's a preview 👇  Want me to save it?                    │
│  [ chart preview ]                                           │
└─────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│  YOU:  Yes, save it.                                         │
└─────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│  CLAUDE:                                                     │
│  Saved! Next time just say the word and I'll drop it back    │
│  into a new slide for you.                                   │
└─────────────────────────────────────────────────────────────┘
```

**Or take the whole set:**

> "Save every slide in this file as reusable parts."
> *(then share the file)*

**Or let Claude find the parts for you:**

> "Look through this file and suggest the reusable parts."
> *(then share the file)*

Claude can **auto-detect the reusable parts** in a file — tables, pictures,
cards, diagrams, and the like — then automatically prepare them as **Draft**
items.
You do not need to rename raw candidates or approve an intermediate queue.
For PDFs, the detection runs page by page so one difficult page does not stop
the whole file.
The supported entrypoint runs requirements preflight automatically before every
PDF analysis and Draft staging run. If optional Docling is not installed, it
uses the approved local PyMuPDF fallback and does not install anything.
For PPTX files, use the normal manual extraction flow until PPTX Draft artifact
generation is added.
When a slide title or heading only explains a visual, Claude can keep that text
as search metadata without making a second duplicate Draft.
Data charts such as pie, bar, or line charts are skipped by auto-detect; ask for
that exact chart only when you truly want to save it as a reusable part.

After auto-detect finishes, open **Components → Draft**. Each detected part has
a preview and information panel. Review the Draft, adjust the metadata if
needed, then choose **Publish** or **Delete draft**. Nothing becomes reusable in
new slide generation until you publish it from Draft.
Claude runs a basic quality pass before showing Drafts, so obviously blank
carousel entries and empty component lists are removed. This is still a review
queue, not an automatic publish step.

If several detected parts belong together, they may appear as one grouped Draft.
Use the carousel to review the full component first, then each smaller variant
inside it.
If the same component pattern appears on several pages with different text,
Claude keeps one representative Draft instead of showing every duplicate.
For a strip of repeated cards, the same Draft can also show each individual card
and each card's text-free version in the carousel.
For a large diagram or a row of repeated cards, the carousel can show each
horizontal row or each card/cell as its own reviewable component pair.

### What you'll get

1. Tell Claude **which file** and **which part** you want (a slide, a range of
   pages, or something specific like "the footer" or "the title").
2. Claude prepares matching parts as Drafts and opens the Draft review area.
3. You review each Draft and choose **Publish** only for the parts you want to
   reuse later.

**Good to know:**

- This only happens when you ask — Claude never takes any part on its own.
- Auto-detect can create Drafts, but a Draft is not published. It becomes a
  reusable library item only after you click **Publish**.

To open the catalog on Windows, run this in PowerShell and leave the window open:

```powershell
& .\.venv\Scripts\python.exe .\slide-system\catalog\catalog_server.py
```

Then open **http://127.0.0.1:8799/slide-system/catalog/**. Do not use a bare
static server: only `catalog_server.py` provides the Publish/Delete actions.

<!--
  INSERT IMAGE: Claude showing a preview of the extracted part.
  ![Preview of the extracted part](./images/04-xem-truoc-component.png)
-->

---

## Simple Tips

- **Talk normally.** No special commands needed — full sentences work best.
- **Do one thing at a time.** Create slides *or* extract a part, finish, then
  move to the next task.
- **Say "yes" or "change it".** Claude always checks with you before the big
  steps, so nothing happens without your approval.
- **Stuck?** Just type *"help me get started"* and Claude will walk you through
  it step by step.

You're all set. Have fun making slides!

---

### Notes for whoever inserts the images

The `<!-- INSERT IMAGE ... -->` lines above are suggested spots to paste real
screenshots. How to add an image:

1. Take a screenshot of the Claude app matching the description.
2. Save the image into the `docs/images/` folder (name it as suggested, e.g.
   `02-tao-slide.png`).
3. Remove the `<!-- -->` so the `![...](...)` line shows up as an image.
