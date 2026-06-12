# PPTX Skills — Evaluation Notes

Đánh giá các skill PPTX bên ngoài và những gì đáng lấy cho repo này.
Bối cảnh repo: export bằng **python-pptx** (Python), có bug 3-layer (graphic bị nướng vào 1 PNG nền — xem `project_pptx_object_separation`), và QA step của `slide-generator` còn yếu về font/overflow.

Ngày: 2026-06-11

---

## Skill #1 — "slides" (PptxGenJS, OpenAI-style)

Engine bắt buộc PptxGenJS (JS, write-only). **Xung đột** với stack Python của repo, nhưng phần QA/validation thì language-agnostic và rất đáng lấy.

### ✅ Đáng lấy ngay — script QA chạy trên *mọi* .pptx (độc lập engine)

| Script | Vì sao hữu ích |
|---|---|
| `detect_font.py` | Báo font thiếu / bị LibreOffice thay thế. Bù đúng lỗ hổng font-substitution trong QA hiện tại. |
| `slides_test.py` | Phát hiện content tràn khỏi canvas (overflow). |
| `render_slides.py` + `create_montage.py` | Render PPTX/PDF → PNG rồi ghép contact-sheet để review nhanh bằng mắt (read-back QA trực quan). |
| `ensure_raster_image.py` | Convert SVG/EMF/HEIC/PDF-like → PNG để inspect asset lạ trước khi đặt vào slide. |

→ **Hành động đề xuất:** port các script này vào `slide-system/scripts/` như bộ post-export QA, độc lập engine.

### 🎯 Triết lý đáng học (liên quan trực tiếp bug 3-layer)

- "text should stay text", "simple charts should stay native charts", "editable PowerPoint-native elements" → đúng kỷ luật mà export-phase đang thiếu.
- `warnIfSlideHasOverlaps` / `warnIfSlideElementsOutOfBounds` — gate cảnh báo overlap/out-of-bounds **trước khi deliver**. Có thể viết lại bằng python-pptx (đọc ngược được toạ độ shape; PptxGenJS thì không).

### ❌ Không hợp — đừng theo

- Bắt buộc PptxGenJS, cấm python-pptx (trừ inspection) → ngược với kết luận của repo: giữ python-pptx để **đọc ngược deck cho QA** (PptxGenJS write-only, không mở file được).
- Helper JS (`latexToSvgDataUri()`, `codeToRuns()`, `autoFontSize/calcTextBox`) chỉ tham khảo ý tưởng, không tái dùng trực tiếp.

### Tóm tắt

| Lấy | Bỏ |
|---|---|
| 4–5 QA script (font / overflow / render / montage / raster) | Engine PptxGenJS |
| Kỷ luật "giữ native, đừng flatten" | Quy tắc cấm python-pptx |
| Ý tưởng overlap/out-of-bounds gate (viết lại bằng python-pptx) | Helper JS cụ thể |

---

## Research — top skill PPTX/slide editable trên skills.sh

Tìm bằng `npx skills find <query>` (pptx / slide / presentation / deck). Xếp hạng theo độ liên quan tới repo (python-pptx, pipeline HTML→PPTX, bug 3-layer flatten, QA font/overflow yếu).

### 🥇 #1 — `nexu-io/open-design@pptx-html-fidelity-audit` (1.2K installs) — KHỚP NHẤT, lấy ngay

> `npx skills add nexu-io/open-design@pptx-html-fidelity-audit`

Skill này gần như đo-ni-đóng-giày cho repo: audit một **python-pptx export so với HTML deck nguồn**, phát hiện drift (footer overflow, off-canvas, mất italic/em, hero không center, box bound đè rail, mất styling), rồi **re-export với "footer-rail + cursor-flow layout discipline"**. Đây đúng pipeline HTML→PPTX của bạn.

Vì sao đáng lấy:
- **Geometry-based verification, không visual-diff** — `verify_layout.py` walk mọi shape, assert `top+height ≤ CONTENT_MAX_Y` (rail footer), `≤ CANVAS_H` (off-canvas), `left+width ≤ CANVAS_W`. Exit code ≠0 → cắm thẳng vào CI. Đây đúng QA overflow/out-of-bounds bạn đang thiếu, **viết sẵn bằng python-pptx** (không phải port từ JS như Skill #1).
- **`extract_pptx.py`** — dump mọi shape (text, top/left, w/h, per-run font/size/bold/italic/color) ra JSON để audit. Dùng được làm read-back QA cho `slide-generator`.
- **Cursor-flow + footer-rail discipline** — biến overflow từ "bug hình ảnh âm thầm" thành "build error ồn ào": block nào vượt rail thì raise `OverflowError`. Hero slide dùng "budget centering". Đây là **cơ chế python-pptx cụ thể** chống flatten/drift — bù đúng hướng fix bug 3-layer (`project_pptx_object_separation`).
- **`references/font-discipline.md`** — audit font 5 lớp: variable-vs-static trap (PowerPoint âm thầm đổi sang Calibri/JhengHei), 3 slot ngôn ngữ XML (`latin`/`ea`/`cs`), CJK fallback, **không fake-italic chữ Han/CJK**. Trực tiếp giải quyết vấn đề font-substitution của repo, sâu hơn `detect_font.py` của Skill #1.
- Có sẵn `references/layout-discipline.md` (rule cho hero/content/pipeline/two-column/grid) + `audit-table-template.md` (bảng severity 🔴🟠🟡🟢).

Lưu ý: rail mặc định 16:9 footer mỏng — override hằng số `CONTENT_MAX_Y/CANVAS_*` cho design system của repo.

→ **Khuyến nghị mạnh:** đây là skill nên adopt đầu tiên. Nó vừa bù QA (verify_layout/extract_pptx) vừa cho cơ chế chống flatten — đúng cả hai lỗ hổng lớn của repo, lại cùng engine python-pptx nên không phải dịch code.

### 🥈 #2 — `claude-office-skills/skills@pptx-manipulation` (3.1K installs)

python-pptx, generate + edit + extract (text/shapes/images/charts/tables). Cùng engine, qua 3 security audit (Socket/Snyk/Agent Trust Hub). Nhưng **mỏng**: không nêu rõ tooling validation, template/placeholder hay font handling. Giá trị: tham khảo pattern generate/extract chuẩn; **không bù được QA**. Mức ưu tiên: thấp hơn #1 nhiều.

### 🥉 #3 — `minimax-ai/skills@pptx-generator` (4K installs)

Đa hướng: markitdown (phân tích), XML manipulation (sửa template), **PptxGenJS** (tạo mới). Có design system sẵn (palette/font/style recipe), giữ editable. Điểm hay: **sửa template bằng XML manipulation** (giữ formatting) — ý tưởng đáng tham khảo cho template-based gen. Nhưng engine tạo-mới là JS (không hợp stack) và không có QA script rõ ràng.

### Loại — không hợp mục tiêu "editable pptx"

- `getsentry/skills@presentation-creator` — output **HTML standalone** (React+Vite+Recharts), KHÔNG phải pptx editable. Điểm hay duy nhất: kỷ luật "Data Assessment" (chỉ vẽ chart khi có data thật) — tham khảo cho QA nội dung, không liên quan pptx.
- `anthropics/skills@pptx` (141K installs) — chính là bộ pptx Anthropic bạn đã có sẵn trong session.
- `antfu/skills@slidev`, `claude-office-skills/skills@html-slides`, `raffaelecamanzo/skills@marp-deck-gen` — slide bằng HTML/Markdown/Marp/Slidev, không xuất pptx editable native.
- `open.feishu.cn@lark-slides` (204K), `googleworkspace/cli@gws-slides` — bind vào Feishu/Google Slides API, không phải .pptx local.

### Kết luận research

| Skill | Engine | Hợp repo | QA tooling | Chống flatten | Ưu tiên |
|---|---|---|---|---|---|
| **pptx-html-fidelity-audit** | python-pptx + HTML | ✅✅ trùng pipeline | ✅ verify_layout + extract_pptx | ✅ cursor/rail + font 5-lớp | 🥇 adopt ngay |
| pptx-manipulation | python-pptx | ✅ cùng engine | ❌ | ❌ | tham khảo |
| minimax pptx-generator | PptxGenJS + XML | ⚠️ một phần | ❌ | ⚠️ XML edit | tham khảo template |
| Skill #1 (PptxGenJS) | PptxGenJS | ❌ JS | ✅ port được | triết lý | lấy QA script |

**Hành động đề xuất:** adopt `pptx-html-fidelity-audit` làm nền QA + layout discipline (cùng python-pptx, bù đúng 2 lỗ hổng lớn), bổ sung thêm render/montage script từ Skill #1 cho review trực quan.

---

## Integration test — đã cài & chạy thật lên output repo (2026-06-11)

Đã `npx skills add nexu-io/open-design@pptx-html-fidelity-audit` (project scope, `.agents/skills/`). Chạy 2 script lên `outputs/component-extractions/gpt-5.4-mini-slides-1-5/gpt-5.4-mini-editable.pptx`. python-pptx đã sẵn trong `.venv`.

### Mô hình export hiện tại của repo (`slide-system/scripts/build_hybrid_pptx.py`)
"Hybrid editable": mỗi slide = **1 PNG full-canvas** (`slide-XX-bg.png`, 0,0→13.333×7.5 — nướng MỌI graphic, đây đúng bug 3-layer) + **text box native** đặt theo toạ độ DOM từ `export-layout.json` (capture-slides.js). → **Text đã editable sẵn**; vấn đề là graphic bị flatten + thiếu QA.

### Kết quả chạy

| Script | Tương thích | Phát hiện |
|---|---|---|
| `extract_pptx.py` | ✅ **drop-in** | Dump sạch text/pos/font/italic/color. Dùng làm read-back QA, diff với `export-layout.json`. |
| `verify_layout.py` | ⚠️ **cần 1 chỉnh nhỏ** | Báo false-positive trên `Picture 1` (PNG nền full-canvas, bottom 7.5") ở cả 5 slide. Footer text box (top 7.019) thì exempt đúng. |

### 3 phát hiện cụ thể (bug thật trong repo)

1. **`italic: null` ở mọi run** → `add_text_box` (build_hybrid_pptx.py:153-158) **không bao giờ set italic** (chỉ có bold). Nếu HTML nguồn có `<em>` thì mất hẳn — đúng drift mode #3 của skill. **Bug thật.**
2. **Không có language-slot CJK/Vietnamese** → chỉ set `run.font.name` (Proxima Nova), không có slot `<a:ea>`/`<a:cs>`. Với nội dung tiếng Việt/CJK, PowerPoint dễ fallback font. `references/font-discipline.md` (5 lớp) giải đúng chỗ này.
3. **Box height ×1.35** (build_hybrid_pptx.py:129, "35% taller for wrapping") → đúng kiểu "box bounds intruding" (drift mode #5): text vừa nhưng bounding box phình, có thể vượt rail/off-canvas. `verify_layout.py` bắt được — nhưng cần exempt PNG nền trước.

### Adapt cần làm để dùng `verify_layout.py` trên repo
- PNG nền full-canvas bị tính là "content shape" vượt rail. Fix 1 dòng: hoặc đặt tên shape nền chứa "background"/"bg" + thêm vào `FOOTER_NAME_HINTS`-style exempt, hoặc skip PICTURE phủ trọn canvas. Sau đó script bắt đúng overflow text box.
- Override rail cho design system repo qua `--content-max-y / --canvas-*` (mặc định 16:9 footer mỏng).

### Tóm lại — giá trị thực tế cho repo
- **Lấy ngay, không sửa:** `extract_pptx.py` làm read-back QA (đã chứng minh chạy).
- **Lấy, sửa 1 dòng:** `verify_layout.py` làm post-export gate (exempt PNG nền).
- **Áp vào fix bug:** thêm italic + language-slot (`<a:ea>`) vào `add_text_box` theo `font-discipline.md` — đây là 2 bug thật đã xác nhận, không chỉ lý thuyết.
- Cursor-flow/footer-rail discipline KHÔNG áp trực tiếp (repo pin toạ độ DOM, không flow) — chỉ tham khảo box-bound.
