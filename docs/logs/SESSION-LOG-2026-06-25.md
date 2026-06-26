# Session Log — 2026-06-25

Branch: `feat/harness-enforcement-and-component-recognition`.
Append-only record, one entry per task in request order. Format per
`docs/logs/_TEMPLATE.md` (rule: `AGENTS.md` → "Task Logging").

---

## 2026-06-25.1 — Clean full-page-2 decompose: prove separated + classified components (fix/run/test loop)

**Request:** (sau interview-me) "lên plan để fix các bug và xóa các output và tiến hành chạy test lại, đảm bảo chúng phải tách rời nhau và phân loại chúng ra cái nào giống nhau … tự chạy tự test rồi log bug vào plan … vòng lặp fix+chạy+test cho tới khi hết bug. Trước hết viết plan." Chốt phạm vi: chạy SẠCH toàn **trang 2** (không phải vùng card strip hẹp).
**Actions:**
- Viết plan `tasks/plan-fullpage-decompose-loop.md` (loop protocol + Bug Log + pre-log bug B1: full-bleed background bị coi là component).
- S1 xóa staging cũ `outputs/component-extractions/guideline-level-progression-cards/`. S2 tạo request mới `input/GUIDLINE-page2-fullpage.extraction-request.json` (item `ai-maturity-levels-board`, page 2, region normalized full-page; id qua được `_BANNED_ID`).
- S3 chạy full pipeline: `scaffold_extraction` → `convert_pdf_source --page 2` (PyMuPDF 1.27.2.3) → `extract_editable_text_slots` (57 slots) → `crop_svg_region` (no-op full-page) → `externalize` → `flatten_svg_background` (skip: 0 leading raster) → `externalize` → `optimize_svg` → `apply_text_contract` → `validate_text_slots` (**valid**) → `classify_page_components` → `build_component_catalog`.
- Tự verify 3 mức: manifest (11 instances → **3 classes**, 0 dropped, 0 background) → render từng class fragment ra PNG (đều non-blank, khác biệt) → browser Draft modal (carousel 4 ảnh).
- B1 (pre-logged) **không xảy ra** trên trang 2 (không có rect nền rời) nhưng vẫn hardening: thêm guard loại cluster phủ ≥ `bg_coverage` (mặc định 0.7) khỏi danh sách class, ghi vào `background_candidates` của manifest + cờ `--bg-coverage`. +1 test `test_classify_excludes_fullbleed_background`. 3 class hiện tại không đổi (đều <7% canvas).
**Result:** Loop hội tụ sau iteration 1 — bản implement từ phiên trước decompose đúng ngay lần chạy sạch đầu tiên. Browser-verified tại http://127.0.0.1:8799/slide-system/catalog/ Draft `sun.component.ai-maturity-levels-board`: tile = 1 component deduped; modal carousel = [1/4] `Class 01 (×5)` thẻ Level (đen/largest), [2/4] `Class 02 (×4)` thẻ vai trò trắng (TRANSLATOR/STRATEGIST/DRIVER/COACH), [3/4] `Class 03 (×2)` banner gradient (Revenue/Team Size +30%), [4/4] `Source (original region)` cả trang 2 để so sánh — đúng yêu cầu TÁCH RỜI + PHÂN LOẠI (cùng hình khác màu gộp; khác hình giữ riêng). `test_gates.py` **31/31**. Catalog 79 item (không đụng 78 published). Plan status → ✅.
**Files:** tasks/plan-fullpage-decompose-loop.md, input/GUIDLINE-page2-fullpage.extraction-request.json, slide-system/scripts/classify_page_components.py, slide-system/scripts/test_gates.py, slide-system/catalog/catalog-data.json, outputs/component-extractions/guideline-ai-maturity-levels/ (new staging)
**Symbols:** classify_page_components.process_item, classify_page_components.main
**State:** Not committed (awaiting review).

---

## 2026-06-25.2 — Proximity-run grouping: distinct groups as separate catalog items (variants preserved)

**Request:** (sau interview-me) "phân tách rời đã ổn, giờ đến bước đưa các phần tách rời không giống nhau ra thành 1 component khác, vẫn giữ chung ảnh source." Chốt qua interview: re-detect theo **proximity-run** — các instance CÙNG HÌNH nằm kề nhau (gap nhỏ mỗi trục, không cần thẳng hàng) gộp thành 1 nhóm render NGUYÊN dãy như ảnh gốc (giữ màu/icon từng card, KHÔNG dedup về 1 card); khác hình / đứng riêng → item riêng; mỗi item dùng chung 1 ảnh source toàn trang.
**Actions:**
- `classify_page_components.py`: thêm `_axis_gap` + `_proximity_groups` (union-find trong từng shape-class theo gap mỗi trục ≤ `group_gap_frac × min(size)`). `process_item` đổi từ "1 representative / shape-class" sang "1 fragment / proximity-group" = hợp tất cả leaf-members của các instance trong nhóm (giữ biến thể). Manifest viết lại: `groups[]` (group_id, file, shape_class, member_count, group_bounds, member_bounds) + `shape_class_count`, `group_count`, param `group_gap_frac`. CLI `--group-gap-frac` (default 0.6). Cập nhật docstring + print.
- `build_component_catalog.py`: thêm `expand_group_items(base, item_dir)` — khi manifest có `groups`, nở 1 staging item thành **N catalog item** (id `<base>.gNN`, name `… — group NN`, images = [fragment dãy, "Source (original region)" dùng chung]). `collect_images` đổi nhánh manifest từ `classes` → `groups` (fallback carousel trong-item). Cả 2 nhánh mapping (v1/v2) gọi `items.extend(expand_group_items(...))`.
- `test_gates.py`: +3 test `test_classify_groups_adjacent_same_shape_run`, `test_classify_splits_distant_same_shape`, `test_classify_keeps_different_shapes_separate`.
- Chạy classify (gap_frac 0.6) → 11 instance → 3 shape-class → **3 group** (bounds phủ trọn từng hàng: 1960/1904/1775px). Render 3 fragment ra PNG: g1 = 5 Level card đủ màu vàng→xanh lá→xanh dương→cam→đen (giữ icon Dio); g2 = 4 role card khác icon; g3 = 2 banner cam/xanh — biến thể giữ nguyên, non-blank. Rebuild catalog (81 item). Browser-verify tab Draft: 3 tile riêng (naturalWidth 1966/1910/1782), modal group-01 carousel = ["Group 01 (×5)", "Source (original region)"].
**Result:** Loop hội tụ iteration 1 — không phát sinh bug; `group_gap_frac=0.6` gom đúng ngay lần đầu. Yêu cầu đạt: các nhóm khác nhau tách thành item riêng, mỗi item giữ nguyên dãy biến thể như ảnh gốc, dùng chung ảnh source toàn trang. `test_gates.py` **34/34**. Catalog 81 item (78 published không đụng). Plan status → ✅. Giới hạn đã ghi chú: các group item con dùng chung 1 staging_dir nên Delete xoá cả extraction — chấp nhận cho review Draft; publish theo group ngoài phạm vi đợt này.
**Files:** slide-system/scripts/classify_page_components.py, slide-system/scripts/build_component_catalog.py, slide-system/scripts/test_gates.py, slide-system/catalog/catalog-data.json, tasks/plan-proximity-group-components.md
**Symbols:** classify_page_components._proximity_groups, classify_page_components._axis_gap, classify_page_components.process_item, build_component_catalog.expand_group_items
**State:** Not committed (awaiting review).

---

## 2026-06-25.3 — Per-card variants + icon paint-order fix + content-derived titles/tags

**Request:** (sau interview-me) 3 bug: (1) "tiêu đề đặt chưa đúng, cần kiểm tra thêm tag agent tự detect"; (2) g01 extract card còn thiếu icon; (3) đã có variable nguyên hàng nhưng thiếu variable từng cái (giống y hệt icon+màu+hình thì bỏ). Chốt interview: variant trong item nhóm (carousel = nguyên hàng → từng card distinct → source), title/tag tự suy từ text-slots, dedup theo pixel (icon+màu+hình).
**Actions:**
- **Điều tra bug icon (C1):** render g01 → chỉ card 1 có icon. Lần dấu vết: 5 card đều là instance đầy đủ (377×476), dropped_small=0, không lệch child-index (ET==measured). Icon nằm ở group 13 (layer chung 19 path, vẽ SAU cùng trong document). `_build_fragment` copy group theo thứ tự duyệt member (group 13 chèn sớm) → background image của card 2-5 (group 5,7,9,11) vẽ ĐÈ lên icon. **Fix:** copy group theo thứ tự document-index (`for gi in sorted(by_group)`) → icon layer vẽ cuối. Render lại: cả 5 icon hiện đúng (ghost/0101/robot-face/network/building).
- **Per-card variants (C2):** thêm import subprocess/tempfile/hashlib/json/shutil + `_render_hashes` (render_svg.js → md5 pixel). `process_item` 2 pass: pass-1 build fragment nguyên hàng + fragment từng card (instance đơn) vào temp; pass-2 render đồng loạt, hash, `_collapse_duplicates` (giữ first theo hash, None không gộp) → ghi `…-group-NN-card-MM.svg`. Manifest thêm `cards[]`, `distinct_card_count`. Dedup proven: 2 card y hệt → cùng hash; khác → khác hash.
- **Titles/tags (C3):** `_load_text_slots`+`_slots_in` (center normalized→px), `_heading` (top-2 font tier, bỏ body-copy paragraph >3 slot/>24 ký tự, dedup lặp), `_group_title` (chung prefix → "<word> cards", else join heading-like), `_tags_from`. Ghi `title`/`tags` vào manifest group + `title` mỗi card. `build_component_catalog.expand_group_items`: carousel = [Whole row → từng card (label=title) → Source], name = "<base> — <group title>", tags từ manifest.
- `test_gates.py`: +7 test (collapse_duplicates ×2, heading ×2, group_title, tags, slots_in).
- Re-run classify + rebuild catalog (81 item). Browser-verify Draft g01 modal: name "ai-maturity-levels-board — Level cards", carousel [Whole row (×5), Level 1 Spicy Autocomplete, Level 2 AI Coding Assistants, Level 3 Autonomous Development Agents, Level 4 Collaborative Agent Networks, Level 5 Software Factory, Source].
**Result:** 3 bug xử lý xong. g01 hoàn hảo (icon đủ + 5 card distinct có title từ content + nguyên hàng + source chung). g02/g03 hợp lý; g02 role row hạn chế do text-slot nguồn bị gộp ("STRATEGISTDRIVERCOACH" 1 slot, 2 card thiếu heading) → fallback body copy — artifact upstream của extract_editable_text_slots, đã ghi chú. `test_gates.py` **41/41**. Catalog 81 item (78 published không đụng). Plan ✅.
**Files:** slide-system/scripts/classify_page_components.py, slide-system/scripts/build_component_catalog.py, slide-system/scripts/test_gates.py, slide-system/catalog/catalog-data.json, tasks/plan-percard-variants-icons-titles.md, outputs/component-extractions/guideline-ai-maturity-levels/items/ai-maturity-levels-board/artifact/components/
**Symbols:** classify_page_components._render_hashes, classify_page_components._collapse_duplicates, classify_page_components._heading, classify_page_components._group_title, classify_page_components._tags_from, classify_page_components.process_item, build_component_catalog.expand_group_items
**State:** Not committed (awaiting review).

---

## 2026-06-25.4 — Fix role-row title merge (forward-gap tspan split in extract_editable_text_slots)

**Request:** "continue fix it" — xử lý nốt hạn chế ghi ở .3: hàng role (g02) title sai do STRATEGIST/DRIVER/COACH bị gộp 1 slot, 2 card fallback body copy.
**Actions:**
- **Root cause:** trong source SVG, 4 heading role nằm trong 1 `<text>`, tspan thứ 2 = "STRATEGISTDRIVERCOACH" với x theo từng glyph nhảy 3 cụm (STRATEGIST x≈970, DRIVER x≈1460, COACH x≈1946) trên CÙNG baseline. `split_runs` cũ chỉ tách khi x lùi (line wrap), không tách khi có KHOẢNG TRỐNG TIẾN lớn → 3 từ dồn 1 slot tại x đầu (card 2); card 3,4 không có heading.
- **Fix:** `extract_editable_text_slots.split_runs` thêm tách theo forward-gap: break khi advance > `max(3×median advance, font_size)` (vẫn giữ tách line-wrap khi lùi). Truyền `font_size` vào.
- **Regen surgical (không đụng visual.svg đã optimize):** xác minh text-slots.json CHỈ do extract sinh (crop region_crop=None no-op; apply_text_contract chỉ đọc slots ghi mapping; optimize không đụng). Chạy extract trong scratch dir từ `evidence/source-with-text.svg` → text-slots.json mới (57→61 slot). Diff: đúng 2 slot gộp bị thay bằng 6 slot tách, 55 slot còn lại y nguyên (không lệch toạ độ). Copy text-slots.json về item. Re-run apply_text_contract (mapping) + validate_text_slots (**valid**) + classify + build_catalog (81 item).
- `test_gates.py`: +3 test split_runs (forward-gap tách, tight không tách, line-wrap vẫn tách).
**Result:** g02 đúng — title "TRANSLATOR / STRATEGIST / DRIVER / COACH", card-01..04 = TRANSLATOR/STRATEGIST/DRIVER/COACH, tags sạch. Browser-verified modal carousel = [Whole row (×4), TRANSLATOR, STRATEGIST, DRIVER, COACH, Source]. Cả 3 nhóm giờ có title từ content + per-card variants + source chung; icon đủ. `test_gates.py` **44/44**. Hạn chế role-row đã đóng (C4). Plan ✅.
**Files:** slide-system/scripts/extract_editable_text_slots.py, slide-system/scripts/test_gates.py, outputs/component-extractions/guideline-ai-maturity-levels/items/ai-maturity-levels-board/artifact/text-slots.json, slide-system/catalog/catalog-data.json, tasks/plan-percard-variants-icons-titles.md
**Symbols:** extract_editable_text_slots.split_runs, extract_editable_text_slots.extract_item
**State:** Not committed (awaiting review).

---

## 2026-06-25.5 — Hardening classify: child-count guard (BUG-1) + surface dropped-small (BUG-2)

**Request:** (sau brainstorm + spec-driven) "check lại và lên plan cho tôi các bug cần fix ngay" → chốt option 1: fix BUG-1 + BUG-2, guard fail-loud, surface qua manifest+stdout. Spec `tasks/spec-classify-hardening.md`.
**Actions:**
- **BUG-1 (child-index misalignment):** `_build_fragment` copy child theo measured child-index nhưng guard cũ chỉ check số group top-level. Thêm `_child_count_mismatch(groups, measured_groups)` → list (group_index, parsed, measured); trong `process_item` sau guard top-level, `raise SystemExit("child-count mismatch …")` nếu lệch. Verify trước: cả 20 group trang 2 đã align (ET==measured) ⇒ guard no-op trên batch hiện tại.
- **BUG-2 (drop component nhỏ âm thầm):** đổi `dropped_small` từ int đếm sang `list[{x,y,w,h,area_frac}]`; manifest giữ `dropped_small_clusters` (= len) + thêm `dropped_small`; `main()` in `WARNING: dropped N small cluster(s) …` khi non-empty.
- `test_gates.py`: +3 test (`test_child_count_mismatch_detects`, `test_child_count_mismatch_clean`, `test_classify_records_dropped_small_with_bounds`).
- Re-run classify trang 2: 3 group / 11 card không đổi, guard im, `dropped_small []`. Rebuild catalog (81 item).
**Result:** 2 bug fix-now đóng. Output trang 2 giữ nguyên. `test_gates.py` **47/47**. Spec status → ✅. Defer (ghi spec): #4 background band 0.5–0.69, #5 publish per-group, #3 dedup render cost.
**Files:** slide-system/scripts/classify_page_components.py, slide-system/scripts/test_gates.py, tasks/spec-classify-hardening.md, slide-system/catalog/catalog-data.json
**Symbols:** classify_page_components._child_count_mismatch, classify_page_components.process_item, classify_page_components.main
**State:** Not committed (awaiting review).

---

## 2026-06-25.6 — Full-deck extraction: delete staging + extract all 5 GUIDLINE pages (decompose + classify)

**Request:** "delete all temporary output, and use skill component extraction, extract all slide with full scope @input/GUIDLINE_PRESENTATION_SUN.pdf".
**Actions:**
- **Verified scope:** PyMuPDF reports the PDF as **5 pages** (harness SessionStart note claimed 551 — wrong; trusted the tool). Confirmed `outputs/component-extractions/guideline-ai-maturity-levels` (page-2 staging) is NOT git-tracked (0 tracked files) and the only "temporary output"; published 78 items live in `slide-system/library/` (untouched). `outputs/slide-jobs` is empty scaffolding.
- **Delete:** `rm -rf outputs/component-extractions/guideline-ai-maturity-levels` + `prune_empty_dirs.py`.
- **Request JSON:** rendered 5 preview PNGs (PyMuPDF, scratchpad) → assigned semantic item_ids per page content: `brand-icon-reference-sheet` (p1 ICON), `style-card-sampler-board` (p2 CARD), `feature-step-shape-diagrams` (p3), `content-comparison-table-board` (p4 BOARD), `contributor-and-image-showcase` (p5 IMAGE). Wrote `input/GUIDLINE-fulldeck.extraction-request.json` (extraction_id `guideline-fulldeck`, 5 full-page normalized regions).
- **Preflight:** `check_base_requirements.py --input pdf` → READY (PyMuPDF 1.27.2.3).
- **Pipeline (per item):** scaffold (naming gate passed all 5) → `convert_pdf_source.py` per page → `extract_editable_text_slots.py` → `crop_svg_region.py` (no-op full-page) → batch `externalize_svg_images` → `flatten_svg_background` (0 flattened, all already-flat/too-small) → externalize refresh → `optimize_svg` (SVG 789→712KB, raster 26.6MB→1.2MB) → `apply_text_contract` (5 items) → `validate_text_slots` (**all 5 valid**) → `classify_page_components.py` per page.
- **Classify results:** p1 icons 0 groups (435 tiny icons below area-floor — BUG-2 warning fired as designed; full-page sheet is the artifact); p2 cards 11→3 groups; p3 shapes 4→2; p4 table 1; p5 contributors 5→3. No child-count-mismatch guard fired; all exit 0.
- **ID fix:** p2 `candidate_stable_id` had aliased to old `sun.component.ai-maturity-levels-board` (dedup matched the deleted prior extraction's region fingerprint). Realigned mapping.json → `sun.component.style-card-sampler-board`. (extraction-history append-only audit left intact — records the alias that fired.)
- Rebuilt catalog: **88 items** (78 published + 10 new staging Draft). Catalog server already up on 8799.
**Result:** All 5 guideline pages extracted full-scope: text-free `visual.svg` + `text-slots.json` (all valid) + decomposed/classified component groups. 10 staging items in Draft. `test_gates.py` **47/47** (no script changes this entry — sanity check). Template promotion NOT yet run (deferred to user — these are guideline reference pages, not deck slides; flagged in summary).
**Files:** input/GUIDLINE-fulldeck.extraction-request.json, outputs/component-extractions/guideline-fulldeck/** (5 items), slide-system/catalog/catalog-data.json, slide-system/registries/extraction-history.json
**Symbols:** (pipeline scripts; no source changes)
**State:** Not committed (awaiting review).

## 2026-06-25.7 — Recheck-all + fix page-3 under-segmentation (re-tune classify)

**Request:** "recheck all and loop fix test check until it done" (sau audit so-với-rule/skill).
**Actions:**
- **Recheck-all (render-verified, không chỉ tin manifest):** render visual.svg + group fragments ở đúng aspect (render_svg.js KHÔNG scale → phải khớp viewBox, nếu không sẽ clip):
  - p1 brand-icon: 0 group, 435 icon dưới area-floor (max area_frac=0.0027) — đúng, là icon-library không decompose được thành card. Giữ nguyên.
  - p2 style-card: 3 group / 11 card — đã verify trước, giữ nguyên.
  - p4 content-comparison-table: 1 group = bảng so sánh (header cam + cell rows, liền khối) — đúng 1 component.
  - p5 contributor: 3 group (avatar row / Engagement / Rewards) — hợp lý (ảnh là gray avatar placeholder của template).
- **Fix p3 feature-step-shape-diagrams (under-segment):** hàng hexagon OKR (GOAL+KEY RESULT×TASK) bị drop vì area_frac=0.0144 < floor mặc định 0.015. Verify p1 max area_frac=0.0027 ⟹ hạ floor cho p3 KHÔNG kéo icon p1 vào (an toàn). Re-run `classify_page_components.py --item-dir <p3> --min-area-frac 0.012 --group-gap-frac 1.2`:
  - `--min-area-frac 0.012`: bắt lại 3 hexagon (drop chỉ còn 2 toán tử +/× ở 0.0002/0.0004 — glyph trang trí).
  - `--group-gap-frac 1.2`: gom 3 hexagon vào MỘT proximity run (gutter/​width≈1.1 do toán tử chen giữa) thay vì 3 group lẻ → cho phép dedup phân loại giống/khác (đúng yêu cầu "phân loại cái nào giống nhau").
  - Kết quả: **2 → 3 group**: g01 = 3 glow circle, g02 = "GOAL / KEY RESULT / TASK" hexagon formula (3 card), g03 = step-circle diagram (3 vòng tròn chồng = 1 diagram liền). Render đúng cả 3, title g02 lấy từ text-slots chính xác.
- Rebuild gallery (5 item) + catalog (**88 → 89 item**; p3 staging giờ g01/g02/g03). visual.svg cả 5 vẫn 0 `<text>/<tspan>`.
**Result:** p3 hết under-segment, hàng hexagon được khôi phục thành component riêng có title đúng. Recheck-all 5 trang xong (render-verified). `test_gates.py` **47/47**. Không sửa script (chỉ đổi tham số runtime cho p3). Cosmetic còn lại: p3 g01 card-02 title "01" (đúng phải "02") — artifact OCR text-slot nguồn, không phải lỗi classify; toán tử +/× vẫn drop (glyph 0.0002 area).
**Files:** outputs/component-extractions/guideline-fulldeck/items/feature-step-shape-diagrams/artifact/components/** (regenerated), outputs/component-extractions/guideline-fulldeck/gallery.html, slide-system/catalog/catalog-data.json
**Symbols:** (no source changes — runtime params only)
**State:** Not committed (awaiting review).

## 2026-06-25.8 — Root-cause investigation: classify duplicates & mis-grouping (plan doc)

**Request:** "sun.component.contributor…g01 duplicate; …g02/table chưa tách; g02 vs g03 tách nhầm; feature-step g03 2 item trùng. Các bug fix trước đã tìm root cause chưa? Lên plan + tìm nguyên nhân + hướng fix, chi tiết cẩn thận."
**Actions (investigation, render-verified, no code changed):**
- Honest finding: prior page-3 fix was **param tuning only** (min-area-frac/group-gap-frac), did NOT touch the structural defects → reported bugs are latent in `classify_page_components.py`.
- **RC-1 over-merge** (`_cluster_spatial` unions within merge_gap=6px): rendered `contributor g02` = blue card + photo glued; `content-comparison g01` = whole table 1 instance. Knock-on: g02's glued blue card (1460×597) vs g03 standalone blue card (484×474) → different shape-class → same component split (report 3).
- **RC-2 dedup sub-pixel** (`_build_fragment` integer `math.floor` translate): proved g01's 3 avatars have **byte-identical geometry** (22/22 path `d` equal elementwise) yet 3 different render md5; orange hexagons differ only by translate (−674 vs −1344). Raster byte-hash never matches fractionally-positioned identical instances → report 1.
- **RC-3 single-member twin**: `feature-step…group-03.svg` == `…group-03-card-01.svg` (same MD5 e8b3e35, 71709B) → catalog lists both → report 4. Also contributor g02/g03, content-comparison g01.
- **RC-4 bg baking**: contributor card-01 holds **7 copies** of full-canvas rect `M0 2623.16H2938.83V0H0Z` (7/15 paths) — layer-group bg rects accumulated by whole-group copy; bloats + destabilizes dedup.
- Wrote plan `tasks/plan-classify-dedup-merge-rootcause.md`: 4 fixes ordered (RC-3 → RC-4 → RC-2 translate-invariant content hash → RC-1 overlap-only clustering), each with verify + regression-test plan; flagged 3 decisions (RC-1 split depth, table cell granularity, scope).
**Result:** 4 root causes identified with evidence; bug→cause map done; plan PROPOSED awaiting approval. Recommended RC-1 = overlap-only (splits card/photo, rejoins g02↔g03, keeps single objects + table whole). No code/output changed.
**Files:** tasks/plan-classify-dedup-merge-rootcause.md
**Symbols:** (analysis of classify_page_components: _cluster_spatial, _build_fragment, _collapse_duplicates, process_item)
**State:** Not committed (awaiting review).

## 2026-06-25.9 — Plan refinement: raster-vs-vector dedup split + table/section gap finding

**Request:** user answered 3 decisions (overlap-only ok; table whole but split off unrelated section below; scope priority = my call) + nuance "1 row 2 hình tương tự + 1 khác hoàn toàn".
**Actions (inspection only, no code):**
- **Finding A — dedup is 2 problems:** contributor g01 avatars = pure VECTOR, geometry byte-identical (images=0, 22/22 path d equal) → TRUE duplicates, exact dedup fixes (RC-2a, safe). feature-step g02 hexagons = 4 embedded PNGs each; 2 orange share 3 PNGs but differ in the 4th = inner ICON (6876 vs 6888 B) → same container/different icon, byte-different "tương tự" → needs perceptual/threshold dedup (RC-2b, false-merge risk, policy call). Split RC-2 → RC-2a (exact, ship) + RC-2b (perceptual, defer/badge-only).
- **Finding B — RC-1 gap threshold insufficient for table:** measured table visual leaves → 2 vertical bands (y367..1048, y1049..2883) separated by only ~1px; table cells also touch (~0px). Pure `gap<=k` can't split table-from-section without shattering cells → RC-1 needs a structural-gutter/container signal (higher effort/risk).
- Updated `tasks/plan-classify-dedup-merge-rootcause.md` with both findings + recommended order (RC-3 → RC-4 → RC-2a → RC-1 → RC-2b) + still-open RC-2b decision.
**Result:** plan sharpened; safe high-value fixes (RC-3/RC-4/RC-2a) separated from risky ones (RC-1 structural, RC-2b perceptual). Still PROPOSED — awaiting go-ahead.
**Files:** tasks/plan-classify-dedup-merge-rootcause.md
**Symbols:** (analysis only)
**State:** Not committed (awaiting review).

## 2026-06-25.10 — Implement classify root-cause fixes (RC-1 + RC-2 + RC-3); user chose auto-merge

**Request:** user answered "c" (auto-merge similar raster cards) → implement the plan.
**Actions (code):**
- **RC-3** (`classify_page_components.py` process_item + `build_component_catalog.py` expand_group_items): single-member group reuses the group fragment as its card (no byte-dup `-card-01` twin); catalog shows ONE preview for it.
- **RC-2** unified: replaced md5 pixel-hash with perceptual signature (`_percept_signature`: PIL 32×32 alpha-on-white thumbnail) + MAE distance (`_signature_distance`); `_collapse_duplicates(items, distance, threshold)` now distance-injected; CLI `--dedup-mae` default 3.0. Empirical separation (identical 0.09–0.18, similar-orange-hex 0.63, orange↔blue 111, distinct Level cards 47–171) ⇒ 3.0 has 16× margin. Pillow sanctioned by REQUIREMENTS.md. Removed unused hashlib import.
- **RC-1** (`_split_on_gutter` + wired after `_cluster_spatial`; CLI `--split-gutter-px` default 16): split an instance on a clean ≥16px empty band among LARGE leaves; tiny bridging leaves don't block, assigned to nearer side. Un-glues card↔photo (21px gutter).
- Tests: distance-injected dedup test + threshold-merge test; `_split_on_gutter` separates-bridged + keeps-intact tests.
**Result:** all 4 reported bugs fixed (render-verified): contributor g01 3-avatars→1×3; g02→photo alone; g03→2 blue cards→1×2; feature-step g02 GOAL+KEY→1×2 (blue kept); g03 single preview. Page-2 anchor unchanged (3 groups/11 distinct, no false merge). `test_gates` **50/50**. Catalog 78 published + 11 staging. **Limitation:** comparison-table "section below" not geometrically separable (big-leaf grid, largest vertical gap 1px) — text-only/stripped; needs user region input or text-layer signal. RC-4 deferred (perceptual dedup moots its dedup benefit).
**Files:** slide-system/scripts/classify_page_components.py, slide-system/scripts/build_component_catalog.py, slide-system/scripts/test_gates.py, tasks/plan-classify-dedup-merge-rootcause.md, slide-system/catalog/catalog-data.json, outputs/component-extractions/guideline-fulldeck/** (regenerated)
**Symbols:** classify_page_components._percept_signature, _signature_distance, _render_signatures, _collapse_duplicates, _split_on_gutter, process_item; build_component_catalog.expand_group_items
**State:** Not committed (awaiting review).

---

## 2026-06-25.11 — Multi-deck extraction delegated to 4 worktree subagents + review/root-cause

**Request:** "lên plan extraction component … để delegate cho các subagent, mỗi subagent làm 1 file" for SUN.STUDIO_-_Performance_Review_-_2025.pdf, SUN.SLIDE.pdf, Sun.Presentation.pdf, Salary&Benefits_Sun.Studio_2026_Suner.pdf; then review correctness + root-cause + fix. Chốt qua AskUserQuestion: run mode = **parallel + worktree isolation**, execute now.
**Actions:**
- Wrote `tasks/plan-multideck-extraction-delegation.md` (phase split A extract / B reconcile / C review). Decided catalog build is orchestrator-only because `extraction-history.json` + `catalog-data.json` are shared read-modify-write state; `build_component_catalog.py` rescans all batches so it runs once at the end.
- Launched 4 background `general-purpose` subagents, each `isolation: worktree`, one PDF each. Each authored its `input/<slug>.extraction-request.json` (salary reused existing), ran the full PDF→SVG→crop→externalize→flatten→optimize→text-contract→validate→classify pipeline, stopped before catalog/serve.
- 2 agents (sun-slide, sun-presentation) reported "session limit" notices. Verified actual filesystem state: perf 20/20, sun-presentation 17/17, salary 18/18 complete; **sun-slide 40/40 visual+slots+mapping but 0 comp-manifest** (classify never ran — cut off).
- Phase B (main tree): rsync'd 4 batches into `outputs/component-extractions/`, copied 3 authored request JSONs into `input/`. Found `classify_page_components.py` is git-untracked so worktrees (built from committed state) lacked it → finished sun-slide's validate (40 valid) + classify (40 comp-manifest) in main where the script exists. Union-merged +77 history attempts. Built catalog (154 items). Removed 4 worktrees + branches; pruned.
**Result (review + root cause):** All 95 items pass `validate_text_slots`; full-page region → crop is a correct no-op (viewBox 1920×1080). Catalog served http://127.0.0.1:8799/slide-system/catalog/ (HTTP 200). Apparent "missing from catalog" for perf (0/20 staging), sun-presentation (0/17), salary (5/18) is **not a bug**: `scaffold_extraction.py` fingerprinted each page region (sha256 same PDF + same full region) and matched prior published extractions → marked `status: "duplicate"`, which the builder excludes. Confirmed nothing lost — those decks already exist published (Performance_Review 20 published, Sun.Presentation 17 published, Salary 18 published + 9 new staging). Genuinely new content = **SUN.SLIDE 40 pages → 55 staging groups** + **5 new salary pages → 9 groups**. No fix needed; dedup behaving correctly. zsh gotcha noted: unquoted `$array` not word-split (use zsh arrays + `"${a[@]}"`); `mapfile` absent.
**Files:** tasks/plan-multideck-extraction-delegation.md, input/{performance-review-2025,sun-slide,sun-presentation}.extraction-request.json, outputs/component-extractions/{performance-review-2025-full-pages,sun-slide-full-pages,sun-presentation-full-pages,salary-benefits-sun-studio-2026-suner-full-pages}/**, slide-system/registries/extraction-history.json, slide-system/catalog/catalog-data.json
**State:** Not committed (awaiting review).

---

## 2026-06-25.12 — Move temp request JSONs out of tracked input/; fix 2 root causes (input pollution + publish "Invalid item id")

**Request:** (1) the `*.extraction-request.json` files are temporary and must NOT sit in `input/` — move to the ignored `outputs/`. (2) Root-cause why the agent kept auto-creating them in `input/` and fix it. (3) Root-cause why publishing a group item failed with "Invalid item id".
**Actions:**
- **Cleanup:** `.gitignore:23` ignores `outputs/`; `input/` is tracked (source decks only). Moved the 7 untracked request JSONs (`GUIDLINE-*` x4, `performance-review-2025`, `sun-presentation`, `sun-slide`) -> `outputs/extraction-requests/` (confirmed gitignored). `input/` now has no untracked leftovers. Verified each already-run extraction keeps its own copy at `outputs/component-extractions/<id>/request.json` (`scaffold_extraction.py:57`). Flagged but did NOT remove the 2 already-committed request JSONs (`kick_off_goal_setting_2026_2`, `salary_benefits_sun_studio_2026_suner`) -- removing those needs `git rm` (tracked change), awaiting OK.
- **RC #1 (input pollution):** SKILL.md/workflow never said WHERE to write the request JSON, so the agent improvised next to the source PDF in tracked `input/`. Fix = executable gate (prose is ignored cross-session): `scaffold_extraction.py` now resolves `--request` and `raise SystemExit` if it lives under `input/`, pointing to `outputs/extraction-requests/`. Every extraction passes through scaffold, so this is the single enforcement point.
- **RC #2 (publish "Invalid item id"):** `catalog_server.py:38 ID_PATTERN` matched only 3 dot-segments; decomposed group items are `sun.component.<base>.gNN` (4 segments) -> regex REJECT -> `do_POST` returns 400 "Invalid item id" before the publish route runs. Fix = append optional `(\.g\d+)?` group suffix.
**Result (verified):** scaffold rejects an `input/`-located request with the new message and accepts the moved location (passes guard, then expected dup-id stop). Regex now MATCHes `sun.component.content-comparison-table-board.g01` while still REJECTing `../etc/passwd` and 5-segment ids. Restarted catalog server (killed stale process holding old regex on :8799); end-to-end: POST `/api/publish` with a well-formed group id -> 404 "Draft item not found" (regex passed), malformed `../bad` -> 400 "Invalid item id" (guard intact). Server up at http://127.0.0.1:8799/slide-system/catalog/.
**Files:** slide-system/scripts/scaffold_extraction.py, slide-system/catalog/catalog_server.py, outputs/extraction-requests/** (moved, gitignored)
**Symbols:** scaffold_extraction.main (input/ guard); catalog_server.ID_PATTERN
**State:** Not committed (awaiting review).

---

## 2026-06-25.13 — Split brand-icon-reference-sheet into 417 individual icons + "icon set" catalog tile

**Request:** "check lại sun.component.brand-icon-reference-sheet, trong đó có rất nhiều icon nên tôi cần bạn tách riêng từng icon ra." Chốt qua AskUserQuestion: scope = **toàn sheet** (lưới lớn + nhóm "frequently used"); delivery = **1 catalog item duy nhất, icon nằm bên trong** (không làm ngập catalog hàng trăm tile); naming = **suy tên từ hình**.
**Actions:**
- **Chẩn đoán:** trang 1 cho 0 group vì `classify_page_components` thả hết icon xuống `dropped_small` (435 cluster, area_frac max 0.0027 << floor 0.015). Sheet là lưới dày các glyph KHÁC NHAU — không hợp shape-class/proximity-run; 1 ngưỡng gap không thể vừa giữ icon lớn nguyên vẹn vừa không dính 2 icon kề trong lưới chặt.
- **Viết `slide-system/scripts/split_icon_sheet.py`** (tái dùng `measure`,`_leaf_boxes`,`_cluster_spatial`,`_build_fragment`,`_ancestor_transform`). 2 vùng: (1) **lưới chính** — cluster gap=6 (neighbour ~103px >> icon ~36px → KHÔNG dính, chỉ over-split ~6% icon nhiều nét), gán theo HÀNG (cluster 1-D), rồi trong mỗi hàng GỘP cell có gap ngang < `col_tol`=35 (histogram gap bimodal: intra-icon 0–10px, inter-icon 50–80px, khe trống ở giữa → 35 gộp mảnh vỡ mà không dính icon kề); (2) **hộp "frequently used"** (x≥1580,y≤800) — coarse-merge gap=50, tên từ text-slot label gần nhất theo trục x bên dưới. Ghi 417 SVG tự chứa + `icons-manifest.json` + 7 contact-sheet PNG đánh số.
- **Fix render contact-sheet:** render_svg.js clip về viewport cố định → icon lớn bị cắt; sửa renderer render mỗi icon ở native size rồi PIL thumbnail vào ô. Sau fix 417 ô đều là 1 icon nguyên vẹn (render-verified 7 sheet).
- **Naming (suy hình):** đọc 7 sheet, gán tên kebab best-effort cho 408 icon lưới; 9 freq-used giữ tên label (BOD, Company, Person×2, Engagement, Leadership & Development, Rewards & Recognition, Level Expectation, Learning & Sharing). Dedup slug bằng hậu tố số → 417 slug phân biệt. (Sửa matcher label sang ưu tiên trùng-x bên dưới icon; chuẩn hoá label đa dòng "Development"/"Rewards &".)
- **Catalog (1 tile, icon bên trong):** `build_component_catalog.collect_icon_set(item_dir)` đọc manifest → gắn `item.icon_set={count,icons[]}` (cả nhánh v1/v2, None nếu không manifest). `catalog.js`: khi `item.icon_set` render **lưới icon có ô tìm kiếm** thay carousel (417 dot sẽ vỡ UI) — `compWireIconSet` (lọc tên, click copy path); CSS `.iconset*`. Carousel/zoom gốc được guard ngoài chế độ icon-set.
- Rebuild catalog (154 item). Browser-verify :8799 → modal `sun.component.brand-icon-reference-sheet`: grid 417 ô, tile preview vẫn là sheet gốc; filter "train"→4 (train/train/train-front/train-side); clear→417/417.
**Result:** 417 icon tách rời (408 lưới + 9 freq-used), mỗi icon 1 SVG tự chứa, gói trong 1 catalog tile có lưới + tìm kiếm. +4 test (`test_split_cluster_1d_groups_within_tol`, `test_split_merge_within_fuses_overlap_keeps_distant`, `test_split_per_row_gap_separates_neighbours_fuses_fragments`, `test_build_catalog_collect_icon_set_parses_and_absent`) → `test_gates.py` **54/54** (chạy từ repo root). Hạn chế: tên lưới best-effort (sheet lặp outline/filled → trùng đã hậu-tố); 2 freq label "Person/Honor" bị OCR nguồn gộp thành "Personal"→"Person". visual.svg KHÔNG bị đụng.
**Files:** slide-system/scripts/split_icon_sheet.py (mới), slide-system/scripts/build_component_catalog.py, slide-system/catalog/catalog.js, slide-system/catalog/catalog.css, slide-system/scripts/test_gates.py, slide-system/catalog/catalog-data.json, outputs/component-extractions/guideline-fulldeck/items/brand-icon-reference-sheet/artifact/icons/** (417 SVG + manifest + contact sheets)
**Symbols:** split_icon_sheet.split, split_icon_sheet._cluster_1d, split_icon_sheet._merge_within, split_icon_sheet.render_contact_sheets, build_component_catalog.collect_icon_set, catalog.js:compRenderModal, catalog.js:compWireIconSet
**State:** Not committed (awaiting review).

---

## 2026-06-25.14 — Delete non-GUIDLINE extraction outputs (keep only GUIDLINE_PRESENTATION_SUN.pdf)

**Request:** "giờ tôi cần bạn xóa các output trừ GUIDLINE_PRESENTATION_SUN.pdf".
**Actions:**
- Verified source PDF per batch via each `mapping.json`: `guideline-fulldeck` + `guideline-table-logo` ← GUIDLINE_PRESENTATION_SUN.pdf (KEEP); `performance-review-2025-full-pages`, `salary-benefits-sun-studio-2026-suner-full-pages`, `sun-presentation-full-pages`, `sun-slide-full-pages` ← other 4 decks (DELETE). Confirmed nothing under `outputs/` is git-tracked (`git ls-files outputs/` = 0) → deletion non-destructive to VCS.
- `rm -rf` the 4 non-guideline `component-extractions/` batches + the 3 non-guideline `extraction-requests/*.json` (kept all 4 `GUIDLINE-*.json`). Left `outputs/slide-jobs/` (only .DS_Store + README scaffolding) and `extraction-history.json` (append-only audit registry, not an output) untouched. Did NOT touch `input/` (inputs, not outputs) or published library (`slide-system/library/`, separate from outputs).
- Flagged to user before deleting: `sun-slide-full-pages` (158 MB) held 55 genuinely-new staging groups — discarded per explicit request.
- Rebuilt catalog so it stops referencing removed Draft items.
**Result:** outputs/ 190 MB → 9.1 MB; only `guideline-fulldeck` + `guideline-table-logo` remain. Catalog **154 → 90 items** (78 published untouched + 12 staging, all from the 2 GUIDLINE batches); 0 staging items with a missing dir. brand-icon-reference-sheet still present with `icon_set` count 417. Published library (78) and `visual-library.json` registry unaffected.
**Files:** outputs/component-extractions/{performance-review-2025-full-pages,salary-benefits-sun-studio-2026-suner-full-pages,sun-presentation-full-pages,sun-slide-full-pages}/** (deleted), outputs/extraction-requests/{performance-review-2025,sun-presentation,sun-slide}.extraction-request.json (deleted), slide-system/catalog/catalog-data.json (rebuilt)
**Symbols:** none
**State:** Not committed (awaiting review).

---

## 2026-06-25.5 — Materialize decomposed groups as real, publishable components

**Request:** Implement the materialize-group-components plan: turn each detected group from a virtual catalog card (with no item on disk) into a real staging item so Publish/Delete work through the existing server with no `.gNN`-specific code.

**Actions:**
- **T1** — Added `region_identity_hash()` and `semantic_signature_hash()` to `_common.py`; repointed `scaffold_extraction.py` to use them. Verified byte-identical output.
- **T2** — Added `materialize_groups()` to `classify_page_components.py` with `--materialize-groups` flag (default ON). For each group: computes normalized region from `group_bounds/canvas`, creates a sibling staging item (`items/<base>-gNN/`) with `mapping.json`, copies base `visual.svg` + `text-slots.json` + `assets/` + `evidence/source-with-text.svg`, then runs `crop_svg_region.py` (crop+carve) → `validate_text_slots.py` → batch scripts (`externalize_svg_images`, `optimize_svg`, `apply_text_contract`). Fixed two issues during e2e: (1) missing `evidence/source-with-text.svg` copy, (2) missing `artifact/assets/` copy for externalized images.
- **T3** — Replaced both `items.extend(expand_group_items(base, item_dir))` calls in `build_component_catalog.py` with `items.append(base)`. Deleted the `expand_group_items` function (now dead code — real items list automatically).
- **T4** — Added 3 tests: `test_group_bounds_to_normalized_region`, `test_materialized_mapping_fields`, `test_carved_slots_within_unit_and_subset`. Test count 54 → 57/57 green.
- **T5** — Re-ran classify on `guideline-fulldeck/feature-step-shape-diagrams` (3 groups in manifest → 2 materialized). Rebuilt catalog (86 items, 0 orphan virtual ids). Fixed `publish_extraction.py` `ID_PATTERN` to accept `.gNN` suffix (was blocking publish even though `catalog_server.py` already accepted it). Published `sun.component.feature-step-shape-diagrams.g01` → **200 OK** (was 404). Deleted it to restore 78-item registry. Deleted `g02` draft → only its dir removed, base intact.

**Result:** Group components are now real, independently publishable staging items. The 404 "Draft item not found" bug for `.gNN` ids is fixed end-to-end. No `.gNN`-specific code in `catalog_server.py`.

**Files:**
- `slide-system/scripts/_common.py` — +`region_identity_hash`, +`semantic_signature_hash`
- `slide-system/scripts/scaffold_extraction.py` — repointed to use `_common` helpers
- `slide-system/scripts/classify_page_components.py` — +`materialize_groups()`, +`--materialize-groups` flag, +`_run_script()`
- `slide-system/scripts/build_component_catalog.py` — dropped `expand_group_items`, both call sites → `items.append(base)`
- `slide-system/scripts/publish_extraction.py` — `ID_PATTERN` updated to accept `.gNN` suffix
- `slide-system/scripts/test_gates.py` — +3 tests (57/57)

**Symbols:** `region_identity_hash`, `semantic_signature_hash`, `materialize_groups`, `_run_script`, `expand_group_items` (deleted)
**State:** Not committed (awaiting review).

---

## 2026-06-25.5 — Re-extract 3 staging components with incorrect scope (full-page → component-level split)

**Request:** "phân tích lại các component draft và chúng đang bị extract sai — dùng skill /component-extractor để extractor lại cho chính xác"
**Actions:**
- Analysed 3 staging components that were extracted as full-page captures instead of individual components:
  - `content-comparison-table-board` (page 4, full-page) — contained both a checklist table AND a radial AI diagram
  - `contributor-and-image-showcase` (page 5, full-page) — contained both a contributor circles section AND a Work Environment image cards section
  - `stacked-bars-plus-emblem-rings` (page 4, sub-region) — duplicate of the radial diagram from a different batch
- Determined split boundaries using PyMuPDF text position analysis: page 4 splits at y_norm=0.60, page 5 splits at y_norm=0.51
- Created extraction request `outputs/extraction-requests/guideline-resplit-staging.extraction-request.json` with 4 properly-scoped items:
  1. `goal-setting-checklist-table` — page 4 top (0.0–0.60): 8-row checklist table
  2. `ai-adoption-radial-diagram` — page 4 bottom (0.60–1.0): hub-and-spoke AI strategy diagram
  3. `team-contributor-circles` — page 5 top (0.0–0.51): 3-avatar team layout
  4. `work-environment-image-cards` — page 5 bottom (0.51–1.0): category cards with photos
- Ran full pipeline: `scaffold_extraction` → `convert_pdf_source` (pages 4+5) → `extract_editable_text_slots` → `crop_svg_region` (key step — properly split slots: 64/17 for p4, 14/10 for p5) → `externalize_svg_images` → `flatten_svg_background` (all skip) → `optimize_svg` (8 files 276→252KB, rasters 52MB→2MB) → `apply_text_contract` → `validate_text_slots` (all valid) → `classify_page_components` (table: 0 groups; radial: 2 groups; circles: 1 group ×3; cards: 2 groups)
- `test_gates.py` **57/57** pass
- Rebuilt catalog: 90 items total
- Deleted 3 old incorrect staging items via catalog UI (Delete draft → type DELETE → confirm)
- Final catalog: Published 5, Draft 9 (4 parent components + 5 materialized sub-groups)
- Browser-verified all new components in catalog at http://127.0.0.1:8799/slide-system/catalog/
**Result:** All 4 new components show correctly cropped content in the catalog Draft tab. Each component contains only its intended visual region with properly scoped text slots. The 3 old full-page extractions are removed.
**Files:** outputs/extraction-requests/guideline-resplit-staging.extraction-request.json (new), outputs/component-extractions/guideline-resplit-staging/ (new batch), slide-system/catalog/catalog-data.json (rebuilt)
**State:** Not committed (staging items awaiting publish approval).

---

## 2026-06-25.15 — Publish 3 GUIDLINE components to library

**Request:** Publish the 3 full-page GUIDLINE components to the shared library.
**Actions:**
- Published via catalog UI (`/api/publish`) at 18:21:
  1. `sun.component.brand-icon-reference-sheet` (page 1 — icon reference sheet with 417 split icons)
  2. `sun.component.feature-step-shape-diagrams` (page 3 — step diagrams with glow circles + hexagon formula + circle diagram)
  3. `sun.component.style-card-sampler-board` (page 2 — card sampler with Level/Role/Banner groups)
- Each published to `slide-system/library/components/diagrams/sun.component.<id>/` with artifact, preview (thumbnail.png + preview.html), and evidence.
- Registry `visual-library.json` and `visual-library-compact.json` updated; extraction-history appended.
**Result:** Library now 81 published items. All 3 accessible via catalog Published tab. Directories are untracked (not committed).
**Files:** slide-system/library/components/diagrams/sun.component.{brand-icon-reference-sheet,feature-step-shape-diagrams,style-card-sampler-board}/, slide-system/registries/visual-library.json, slide-system/registries/visual-library-compact.json, slide-system/registries/extraction-history.json
**State:** Not committed (awaiting review).
