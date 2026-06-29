# Plugin User Guide

A quick, easy guide to creating slides with the **Claude desktop app**.
You don't need any technical knowledge — just talk, and Claude does the rest.

> **Reading tip:** Each section includes a **sample conversation box** (what you
> type, what Claude replies), a **step diagram**, and **a spot to insert your
> own real screenshots**.

---

## Before You Begin

- All you need to do is open the **Claude desktop app**.
- Nothing to install. Just talk to Claude in plain words.
- Have your content ready (text, notes, or a file you want to turn into
  slides).

That's it. Now pick what you want to do.

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

Claude can **auto-detect the reusable parts** in a file — charts, tables,
pictures, and the like — and show them to you as suggestions. Nothing is saved
from a suggestion until you pick the ones you want and approve them, exactly
like above. It's just a faster way to find candidates in a big file.

Each suggestion starts with a placeholder name. Before anything is saved you
can **review and rename** it — give it a clear name (like
"kickoff-2026-hero-visual"), add a short description and a few tags, then mark
it **approved**. Reviewing and approving here does *not* save or publish the
part yet; it just gets the suggestion ready. You still approve the final save
exactly like above.

### What you'll get

1. Tell Claude **which file** and **which part** you want (a slide, a range of
   pages, or something specific like "the footer" or "the title").
2. Claude extracts that part and shows you a preview.
3. You say **"yes, save it"**, and it's saved so you (or Claude) can drop it
   into later slides.

**Good to know:**

- This only happens when you ask — Claude never takes any part on its own.
- You approve each part before it's saved. Auto-detect only *suggests* parts;
  a suggestion never becomes a saved, reusable item until you approve it.

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
