
## Task: Brief deck "AI Workflow" nội bộ

- **Request:** Viết brief deck 4-5 slides về chủ đề nội bộ; qua interview chốt chủ đề AI workflow chung cho team mix dev + non-dev; nhiều vòng bổ sung (brand rules, nền so le cam/trắng, model selection, tips, app Desktop vs Code, Chat/Cowork/Code, scheduled/dispatch sơ qua, slide riêng về skills).
- **Actions:** Chạy /interview-me (AskUserQuestion, 4 vòng) chốt intent; đọc brand pack `slide-system/brand-packs/sun-studio/` + `.agents/skills/sun-studio-design-system/SKILL.md`; áp quy tắc SUN.STUDIO (bỏ XO/poster theo yêu cầu, nền so le gradient cam #FF5533 / trắng); viết brief 9 slides ra `docs/intent/ai-workflow-deck-brief.md`.
- **Result:** Brief hoàn chỉnh 9 slides + checklist chỗ cần điền (case thật, policy, channel). Chưa render slide (out of scope). Chưa commit.

## Task: Review + fix brief deck AI Workflow (v2)

- **Request:** Delegate subagent review brief; user chốt quota tier (premium/standard/free), xác nhận Chat/Cowork/Code đúng + cần search docs mới, scheduled/dispatch thuộc Claude Desktop app; còn lại fix theo đề xuất reviewer.
- **Actions:** Subagent review 5 trục (brand, accuracy, audience, structure, gaps); WebSearch xác thực Chat/Cowork/Code tabs, scheduled tasks + Dispatch (Cowork features); viết lại `docs/intent/ai-workflow-deck-brief.md` v2 — làm rõ chỉ bỏ XO wash (layout vocabulary vẫn dùng), "phù hợp nhất cho dev", slide 4 rút gọn theo 3 tab chuẩn docs, slide 5 thêm ví dụ non-dev + dải quota tier, slide 7 đổi visual timeline + note dùng được cả Cowork/Code, slide 8 gộp còn 5 mẹo + tag DEV + footer nâng cao ghi rõ platform, slide 9 thêm điểm bắt đầu (mở Desktop app, kênh cấp quyền) + checkpoint cuối tuần; checklist bổ sung logo trắng + tên gói tier; thêm mục nguồn kiểm chứng.
- **Result:** Brief v2 hoàn chỉnh, claim kỹ thuật có nguồn. Chưa commit.

## Task: Chốt các mục [CẦN ĐIỀN] brief (v3)

- **Request:** User nhắc phải hỏi để chốt brief hoàn chỉnh thay vì để trống.
- **Actions:** Check assets design system (chỉ có logo.png, không bản trắng; DIO poses m0-m8); AskUserQuestion 4 mục — user chốt: case slide 3 = meta-demo viết chính brief này (~30 phút vs nửa ngày), policy slide 6 = nguyên tắc chung (không data khách hàng/hợp đồng/lương/credentials, hỏi lead khi phân vân), slide 9 = xin quyền qua lead + hỗ trợ Linh, tier giữ tên premium/standard/free. Edit brief điền hết, DIO m2-wink (title) + m5-dancing (closing), checklist rút còn 3 mục.
- **Result:** Brief v3 hoàn chỉnh, còn duy nhất tên channel chia sẻ cần điền. Chưa commit.
- **Follow-up:** User bỏ channel — slide 9 đổi thành lưu kết quả vào ghi chú chung (đính kèm ảnh được); checklist bỏ mục channel. Brief hết mục cần điền.
- **Follow-up 2:** User yêu cầu sửa nguồn gốc — XO là custom, không phải brand guideline. Sửa 4 file: `sun-studio-design-system/SKILL.md` (description bỏ "XO or", section Choosing A Slide Language đánh dấu editorial=canonical / XO=custom extension NOT brand guideline), `brand-packs/sun-studio/selection-rules.md`, `assets/system/colors_and_type.css` (comment --xo-paper). Lưu memory project_xo_is_custom_not_brand.md + index MEMORY.md.

---

## Task: Build AI Workflow deck from brief (slide-generator)

**Request:** `/slide-generator` — tạo deck từ brief `docs/intent/ai-workflow-deck-brief.md` (9 slides, tiếng Việt, AI workflow, SUN.STUDIO brand). User chọn output **HTML only**, DIO đúng brief.

**Actions:**
- Case = new-from-brief. Job: `outputs/slide-jobs/ai-workflow-deck/runs/v1`.
- Copied brand assets to `assets/brand/` (colors_and_type.css, Proxima fonts, logo.png, DIO m2-wink + m5-dancing).
- Wrote `analysis/visual-requests.json` (1 entry/slide), ran `score_visual_items.py` against `visual-library.json` (91 published items). All 9 slides scored **custom-local** (best 36–53, below adapt=65 / reuse=75) — content doesn't match existing HR/interview/salary templates.
- `validate_selection_report.py` → PASS.
- Built `deck.html`: 9 slides 1920×1080, so-le bg (odd=orange gradient from #FF5533, even=white), Proxima Nova, CSS-var colors only, inline SVG icons (no emoji), DIO on s1/s9. Layouts: role cards, chevron 4-step flow (s3 đinh), app strip, model ladder + quota strip, numbered lists w/ Do/Don't semantic (s6), skill timeline + capsule (s7), footer strip (s8), CTA capsule (s9).
- `validate_brand_compliance.py` → PASS (emoji OK, fonts OK after switching `var(--font-body)`→literal "Proxima Nova"; swapped 4 off-brand hex for brand tokens; 1 non-brand color under threshold). `validate_component_fidelity.py --warn` → PASS (0 reuse/adapt).
- Visual QA via preview server (localhost:8099): fixed overflow on s4/s7/s8 (tightened paddings/gaps) and DIO/text collisions on s1 (sub max-width) and s9 (CTA capsule left-align). Verified all 9 slides render clean, no overflow.
- `cleanup_run.py` → 0 items (HTML-only, no intermediate artifacts).

**Result / verification:** Deck complete at `outputs/slide-jobs/ai-workflow-deck/runs/v1/deck.html`. All 3 gates PASS; all slides screenshot-verified. No PPTX export (user chose HTML only). Added `.claude/launch.json` (slide-preview config).

**Committed:** No.

---

## Task: Investigate "why no published components" + hybrid reuse rebuild (v2)

**Request:** User challenged why v1 used zero published library components.

**Investigation (honest root-cause):**
- Re-inspected scorer output: only templates + dio surfaced; ZERO `sun.component.*` in any top-4. Cause = my `visual-requests.json` tagged template layout vocab (`three-column`,`grid`,`cards`), NOT component vocab (`circle`,`badge`,`numbered`,`set-of-3`). Component registry tags are sparse/prose → near-zero term overlap → never rank. Proved: a request tagged to match `lorem-ipsum-circle-badge-set` scored 75 (reuse). Scorer works; authoring was the gap.
- Viewed 6 component thumbnails + scaffolded them: the 13 `sun.component.*` are auto-staged/Docling → `scaffold` emits **0 slots** (text baked into SVG) → only reusable verbatim, useless for new copy.
- Slotted **templates** (76) DO support new text (cover=7, summary-grid=17, do-dont=39 slots) BUT: (a) carry the source deck's background (cover=orange ✓, summary-grid/statistics=white+green/purple → breaks brief so-le rule); (b) fixed content shapes — summary-grid has NO description slot; cover title designed for 2 words vs long VN hook; (c) visual.svg is 960×540 (½ canvas) so decompose overlay coords need ×2. Confirmed scorer's custom-local verdict was correct: template content-shapes genuinely don't fit this deck.

**Decision:** User chose hybrid. Built run **v2** = reuse `01-cover` (s1) + `17-closing-thank-you` (s9) — both on-brand orange, short-title fit; kept s2–s8 custom (summary-grid loses descriptions, statistics breaks so-le, flows have no linear template).

**Actions:** `runs/v2/`: copied v1 deck, decomposed cover/summary/statistics/closing visual.svg into `assets/page-NN/` (text-free base + object SVGs), replaced s1/s9 with reused-template versions (base artwork as CSS background, template logo obj scaled ×2, pills/title/subtitle at scaffold slot zones, DIO retained).

**Result / verification:** `validate_brand_compliance.py` on v2 = PASS (1 non-brand color under threshold). Rendered s1+s9 via preview: reused branded backgrounds load, text placed, DIO ok, fixed s9 logo/kicker overlap. Two decks exist: v1 (fully custom, brand-perfect) and v2 (hybrid reuse s1/s9).

**Committed:** No.

## Task: Fix deck fix cứng 1080p không scale (A + B)

- **Request:** Điều tra tại sao slide HTML gen ra fix 1080p không scale theo viewport; đảm bảo export vẫn xem được; fix cả A (rule) lẫn B (gate script).
- **Root cause:** Hệ có sẵn scaling qua web component `deck-stage`/`deck_stage.js` (letterboxed transform:scale khi xem, `noscale` để capture 1:1 pixel-exact — capture-slides.js:700, make-a-deck SKILL:17). Deck fix cứng vì được build thành static `<div id=stage width:1920px>` thay vì `<deck-stage>` + runtime. preview.html/scaffold fix 1080 là cố ý (1:1 slot geometry).
- **Actions (A):** `slide-system/workflows/build-html-deck.md` — Build Rules thay rule "Use a 1920x1080 <deck-stage>" bằng rule đầy đủ: bắt buộc deck_stage.js runtime, copy_starter_component, `<section>` con, giải thích noscale + export resetTransformSelector, ghi rõ preview/scaffold giữ fix 1080 cố ý.
- **Actions (B):** viết `slide-system/scripts/validate_deck_stage_runtime.py` — gate FAIL khi thiếu `<deck-stage>` hoặc thiếu runtime (script src deck_stage.js / inline customElements.define). Wire vào Post-Build Gate của build-html-deck.md (EXIT 0 required, ghi qa/deck-stage-report.json). Test 4 fixture: bad static→FAIL, good src→PASS, good inline define→PASS, deck-stage no-runtime→FAIL. Đúng hết.
- **Result:** A + B xong, gate test pass. Chưa commit.

---

## Task: v3 deck — brand-guideline-strict, component-driven, no arbitrary custom

**Request:** Rebuild from scratch (3 rules): follow brand guideline, use available components, no arbitrary custom.

**Grounding (read brand guideline):** `.agents/skills/sun-studio-design-system/SKILL.md` + `brand-packs/sun-studio/selection-rules.md`. Key: the layout patterns (chevron flow, phase timeline, value/benefit grid, numbered agenda, competency columns, capsule, folio footer) are the brand's **layout vocabulary** — CSS removed, meant to be **rebuilt in-place with brand tokens**. So building these with tokens = brand-compliant, NOT "custom tào lao"; the latter = inventing new grammar / non-brand colors/fonts.

**Component reusability scan (empirical):** grep'd all 13 `sun.component.*` visual.svg — several embed `<image>` = labels baked into raster PNG (Docling extractions) → text uneditable. Pure-vector, image=0: `brand-icon-reference-sheet` (the icon library, 417 pre-split icons under `icons/`). Confirmed card-set scaffold = 0 slots (baked). So the usable component here = the brand icon library.

**Build (`runs/v3/`):**
- Scored (prefer-set sun-presentation) + validated selection = PASS (all custom-local, best 63; cover/closing still reused as stronger-than-scorer decision).
- Used **brand icons** from `sun.component.brand-icon-reference-sheet`: identified glyphs via rendered contact sheets (viewed indices), copied 14 (people/person/trophy/cert/search/play/pencil/copydocs/chat/list/frame/monitor/download/plus) into `assets/icons/`, recolored via CSS `mask` + `background:var(--brand)` (blue on white, orange on orange). Placed on s2 (roles), s4 (apps), s7 (skills timeline: search→download→play, exact semantic match).
- Reused `01-cover` (s1) + `17-closing-thank-you` (s9) template background artwork + slot positions (from v2).
- Content slides = brand layout vocabulary (value grid, chevron flow, ladder, numbered list, phase timeline, capsule) with tokens only.

**Verification:** Screenshots via display:none isolation (transform-scale hack caused black frames) — s2/s4/s7 brand icons render + recolor correctly; mask fetch 200. `validate_brand_compliance.py` = PASS, **0 non-brand colors** (swapped last literal `#FF735A` → `var(--dio-highlight)`). `validate_component_fidelity.py --warn` = PASS. Fonts PASS, no emoji.

**Result:** `runs/v3/deck.html` — brand-strict, icons from published component, layout vocabulary, reused cover/closing. Committed: No.
