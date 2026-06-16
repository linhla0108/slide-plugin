# Templates

Published full-slide layout contracts without source-specific copy.

## Layout

Templates are grouped by **set** (the source deck they were extracted from), so
one deck stays one tidy, reusable folder instead of many flat siblings:

```
templates/
  <set-slug>/                     e.g. interview-workshop-sunriser/
    <slide-slug>/                 e.g. 01-cover/
      visual.svg                  passive background (no editable text)
      text-slots.json             editable text contract
      preview/                    thumbnail.png + preview.html
      evidence/                   source-with-text.svg + notes
```

The matching registry id mirrors the path: `sun.<set-slug>.<slide-slug>`
(e.g. `sun.interview-workshop-sunriser.01-cover`). The picker groups slides into
sets from each item's `source.path`, so the folder layout and the id stay in
sync but neither drives grouping on its own.

New templates are written into this layout automatically by
`scripts/publish_extraction.py`.
