# Flow tree — Catalog Publish / Delete directly on the web (non-tech)

> Workflow tree for the **publish / delete visual item directly on the catalog page** feature,
> added to the `SKILL-FLOWS.md` system. Goal: a **non-tech** user only needs to
> *run component-extractor → open the catalog to view the preview → click Publish → done*.
> **Implemented & verified (2026-06-16)** — not a future destination.
>
> Notation: `[KEEP]` unchanged · `[FIX]` modifies old behavior · `[NEW]` newly added

---

## 1. /component-extractor — UNCHANGED

Extraction is still manual-only; it produces `outputs/component-extractions/<batch>/items/<item>/`
with `artifact/` + `evidence/` + `mapping.json` (+ a batch-level `gallery.html` as the review face).
`preview/` is **NOT** created at extract time — per the component-extractor SKILL (§6): the preview
is created *at publish time*. That is why publish must handle the preview itself (see [P2] below).

---

## 2. End-to-end user flow (non-tech, 1 click)

```
[AI] run /component-extractor                                  [KEEP]
        │  → draft items live in outputs/component-extractions/...
        ▼
[A] Regen catalog data  (AUTOMATIC — not a user step)          [FIX] build_component_catalog.py
        │   the extractor (SKILL §5) already ran; the server also auto-regens   + publish_readiness{ready,blockers}
        │   after each mutate. Run it manually only when editing data out-of-band.  + deletable (library/ only) + staging_dir
        │                                                               + preview fallback for published
        ▼
[B] Open the control server (do NOT use http.server)           [NEW] catalog_server.py
        │   python3 slide-system/catalog/catalog_server.py             bind 127.0.0.1:8799, serve repo
        │   → http://127.0.0.1:8799/slide-system/catalog/             + 2 POST endpoints /api/*
        ▼
[C] User opens the Draft tab → clicks an item                  [KEEP] Preview/Info/Compat modal
        │   • preview image shown immediately (taken from evidence/source-with-text.svg)
        │   • manage bar (modal-manage):
        │       Draft     → [ Publish ] (orange)  [ Delete draft ] (red)
        │       Published → [ Delete ] (red)
        ▼
[D] Click PUBLISH  ── 1 click, NO dialog                       [NEW] onPublish() → POST /api/publish
        │   (see tree §3)                                              busy spinner → toast → reload
        ▼
[E] Item moves Draft → Published, modal closes, "Published" toast [NEW]
```

Removed old side branches (dropped to keep it lean for non-tech): the separate **Generate preview**
button, the "missing preview" note line, the **confirmation dialog on Publish**, and the
**type-DELETE confirm on draft delete**. Publish and Delete are now single direct clicks.

**Tile preview image order (2026-06-26):** both Draft and Published catalog tiles show
`evidence/source-with-text.svg` first (same order as the modal preview). Previously published tiles
showed a different image first; this was fixed so draft ↔ published rendering is consistent.

**Brand font injection (2026-06-26):** catalog tiles that contain SVG are served via `<object>` elements
so the browser resolves the document's `@font-face` rules and Proxima Nova renders correctly inside the
tile — previously the font fell back to a system sans-serif inside inline SVGs.

---

## 3. POST /api/publish — server tree (catalog_server.py)

```
receive { id }
        │
        ├─ ID doesn't match stable-id regex ───────────────► 400 "Invalid item id"   [NEW] guard
        │   valid forms: sun.component.base.name  OR  .gNN suffix (e.g. sun.component.base.g01)
        │
        ▼
[P1] find_staging(id): scan outputs/.../items/*/mapping.json    [NEW]
        │   match candidate_stable_id | id | folder name
        │   not found ───────────────────────────────► 404 "Draft item not found"
        ▼
[P2] preview/ missing? → AUTO-CREATE                           [NEW] generate_item_preview.py
        │   python3 generate_item_preview.py --item-dir <item>          (reason: extract doesn't create
        │     ├─ type == template ─► generate_template_preview.py        preview/, publish must handle it)
        │     └─ atomic (component/asset/style/icon/…)
        │             render_svg.js (Playwright) render
        │            evidence/source-with-text.svg | artifact/visual.svg
        │            → preview/thumbnail.png + preview.html
        │   gen fail ─────────────────────────────────► 500 "Could not build a preview"
        ▼
[P3] Record approval: mapping.approval = approved              [NEW] CLICK PUBLISH = the human's
        │   { status:"approved", approved_by:"catalog-ui", approved_at }      approval (the script's
        │                                                                      approval gate requires it)
        ▼
[P4] publish_extraction.py --extraction-dir <batch> --item-id <folder>  [KEEP] existing promote script
        │     ├─ copy artifact/ → library/<TYPE_FOLDER>/<stable_id>/
        │     ├─ copy preview/ + evidence/ into it
        │     ├─ fix evidence SVG: "../artifact/assets/" → "../assets/"
        │     ├─ upsert entry into registries/visual-library.json
        │     │     (approval.approved_by + approved_at carried from mapping.json → registry entry)
        │     ├─ mapping.status = published (+ published_at, published_path)
        │     └─ append registries/extraction-history.json
        │   script FAIL (untested compat gate / missing evidence) ─► 500 "Publish failed" + log
        ▼
[P5] prune_staging(item_dir)                                    [NEW] clean up leftover staging:
        │   rm -rf outputs/.../items/<item>; rmdir items/ + batch/      the artifact now lives in library/,
        │   if empty (outputs/ gitignored, ephemeral)                   staging is just a temp copy
        ▼
[P6] regen_catalog()                                            [NEW] build_component_catalog.py
        ▼
200 { ok, message:"Published to library" }
        ▼
[UI] closeModal() → loadData() → toast                          [NEW] Published tab +1, Draft −1
```

---

## 4. POST /api/delete — server tree

```
receive { id, status }
        │
        ├─ status == "published"                                [NEW]
        │     ├─ find_published(id) in registry
        │     ├─ canonical GUARD: paths.artifact must start with    [NEW] protects AGENTS.md:
        │     │     "slide-system/library/" — if not ─► 403            logo/dio live in .agents/,
        │     │     "protected/canonical asset"                         deletable=False, NOT deletable
        │     ├─ target ∈ library/ (within_repo) — if not ─► 403
        │     ├─ target.is_dir() → rmtree · is_file() → unlink     [NEW] handles artifact-file too
        │     ├─ remove entry from visual-library.json
        │     └─ regen_catalog()
        │     → safe: file is git-tracked, RECOVERABLE via git checkout
        │
        └─ status == "draft" | "staging"                        [NEW]
              ├─ find_staging(id)
              ├─ guard: target lives inside outputs/component-extractions/
              ├─ rm -rf <item_dir>            (artifact+evidence+mapping)
              └─ regen_catalog()
              → WARNING: outputs/ is gitignored → LOST FOREVER, cannot be reverted

[UI] delete fires IMMEDIATELY — NO confirmation dialog           [FIX 2026-06-26]
        ├─ published, deletable=False → Delete button hidden (canonical: logo, dio)
        └─ published / draft, deletable=True → single click, fires at once (no typing, no confirm)
              → WARNING for draft: outputs/ is gitignored → LOST FOREVER, no undo
```

---

## 5. Gate table — what BLOCKS the Publish button (publish_readiness)

```
Draft item conditions
        │
        ├─ artifact/ empty ──────────────────────► BLOCK "No artifacts in this extraction"
        ├─ evidence/ empty ──────────────────────► BLOCK "No source evidence in this extraction"
        ├─ compatibility has value "untested" ───► BLOCK "Compatibility not tested: …"
        │
        ├─ preview/ missing ─────────────────────► does NOT block  (P2 auto-creates at publish)
        └─ approval == pending ──────────────────► does NOT block  (P3 click = approval)
```

`ready=True` → Publish button enabled (orange). `ready=False` → Publish dimmed + tooltip + note line
"Can't publish yet: …". The 4 current draft guidelines are all `ready=True` (artifact+evidence present,
compat tested) → just 1 click needed.

---

## 6. Hard rules

- **`catalog_server.py` is the ONLY mutate gateway.** A static page (`http.server`/`file://`)
  cannot edit files → the Publish/Delete buttons will report *"Control server not running. Start it
  with: python3 slide-system/catalog/catalog_server.py"*. There is no other mutate path.
- **`fetch` uses an origin-relative path (`/api/delete`)** → the POST goes to the EXACT origin
  serving the page. Therefore you must open the page FROM `127.0.0.1:8799`, not from a different server:
  - `python3 -m http.server` → POST **501** ("control server not running") — view-only.
  - VS Code **Live Server** (`:5500`) → POST **405 Method Not Allowed**.
  Opening via either of those two leaves the Delete/Publish buttons dead even if `catalog_server.py` is
  running on 8799 — because the request never reaches 8799. Always open **http://127.0.0.1:8799/slide-system/catalog/**.
- **Local only.** The server binds `127.0.0.1`; it is an authoring tool that deletes/writes files — do NOT expose
  it to the network.
- **Clicking Publish = the human's approval** (P3). Do not auto-approve anywhere else;
  the `approval=approved` gate of `publish_extraction.py` is satisfied only by this action.
- **The preview is auto-created by publish** (P2), without requiring user action — in line with
  the component-extractor §6 spirit of "author preview at publish".
- **Reuse tested scripts**, do not reimplement in JS: promote = `publish_extraction.py`,
  preview = `generate_item_preview.py` (→ `generate_template_preview.py` | `render_svg.js`),
  catalog = `build_component_catalog.py`. JS only calls `fetch()`.
- **Deleting published = git-recoverable; deleting draft = permanent** → delete fires immediately (no confirmation dialog, no typing required); there is no undo for draft deletion.
- **Only delete items belonging to `slide-system/library/`.** Canonical items (logo, Dio in `.agents/…`)
  have `deletable=False` → the UI hides the Delete button and the server returns 403 (protection per AGENTS.md).
- **Every mutate → regen catalog** then the UI runs `loadData()` (cache-bust `?t=`); do NOT edit
  `catalog-data.json` by hand (it's a generated file). The extractor (SKILL §5) + server auto-regen —
  a non-tech user does not need to run `build_component_catalog.py` manually.
- Path guard: id must match the stable-id regex; published rm only within `library/`;
  draft rm only within `outputs/component-extractions/`.
- **Atomic preview dependency:** `render_svg.js` needs `node` + Playwright/Chromium. Missing →
  publish returns 500 "Could not build a preview" (run preflight/`setup.sh` first).
- **After publish, the staging copy is auto-cleaned** (P5: rm item + prune empty batch) — the artifact already
  lives in `library/`. No leftover junk in `outputs/`.
- **There is no "regenerate preview" button/endpoint.** Re-rendering from the same SVG source yields
  an IDENTICAL preview (deterministic) → pointless. To get a nicer preview you must edit the source =
  **re-extract** (the `/component-extractor` agent's job), not a web action.
- The server is single-user, with no concurrency locking (1 local user).

---

## 7. Files & commands

```
slide-system/catalog/catalog_server.py        [NEW] server 127.0.0.1:8799 + POST /api/{publish,delete}
                                                     (publish: auto-preview + promote + clean staging)
slide-system/scripts/generate_item_preview.py [NEW] preview by type (template | atomic) — called INTERNALLY in publish
slide-system/scripts/build_component_catalog.py [FIX] publish_readiness + deletable + staging_dir + preview fallback published
slide-system/catalog/index.html               [FIX] add <div id="modal-manage">
slide-system/catalog/catalog.js               [FIX] renderManageBar + onPublish(1-click) + onDelete(confirm) + api() + loadData()
slide-system/catalog/catalog.css              [FIX] .manage-btn / -primary / -danger / .manage-note

# Existing scripts reused (DO NOT modify)
slide-system/scripts/publish_extraction.py    [KEEP] promote staging → library + registry + history
slide-system/scripts/generate_template_preview.py [KEEP] preview for full-slide template (PyMuPDF)
slide-system/scripts/render_svg.js            [KEEP] render SVG → PNG (Playwright)

# Run
python3 slide-system/catalog/catalog_server.py
# → http://127.0.0.1:8799/slide-system/catalog/
```
