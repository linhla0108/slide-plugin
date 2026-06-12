# Plan: Object separation cho phase export PPTX (skill /slide-generator)

> Trạng thái: **PLAN — chưa triển khai** (duyệt 2026-06-11; đã qua 2 vòng verify đa-agent
> cùng ngày. Vòng 1 — 5 chỉnh sửa: parity enforcement, giữ tên `-bg.png`, audit
> picture-count là phần thêm mới, update REQUIREMENTS.md:44, prototype overlay là gate.
> Vòng 2 — hợp nhất luồng: 1 manifest, 1 evaluate/slide, 1 gate QA duy nhất chạy SAU
> compare, 3 phase, uppercase-fix vào P1, cache key đầy đủ, prototype kèm fallback.
> Vòng 3 — cách ly v1↔v2: bảng mode + 6 luật cách ly ở §1, manifest tự khai version,
> shim chỉ ở flat, regression test flat cố định.
> Vòng 4 — chốt open issues (§10): parity candidate = compose-check (LibreOffice
> chỉ là option dự phòng), ngưỡng parity 2 mức, ưu tiên chất lượng output,
> fixture = input/Interview_Workshop_Sunriser.pdf.
> Vòng 5 — vector không thất lạc: field `vector_source` trong manifest từ P1.
> Vòng 6 — audit toàn trình từng bước: capture sinh 3 ảnh QA tham chiếu (ref-full /
> ref-notext / text-layer), compose-check là bước (c) của orchestrator, regression flat
> định nghĩa "tương đương cấu trúc" thay vì byte-level, gỡ các câu stale trái thứ tự QA).
> Spec gốc: `slide-system/rules/background-rendering.md`.
> Bối cảnh: audit 2026-06-11 xác nhận object KHÔNG được tách khỏi background trong PPTX,
> và chỗ "dính" nằm ở phase export (`capture-slides.js` + `build_hybrid_pptx.py`),
> không phải phase extract (extraction đã tối ưu xong, không đụng lại).
> Cây workflow kèm điểm fix: `SKILL-FLOWS-3LAYER-EXPORT.md`.

## 0. Hiện trạng & gốc rễ (đã xác minh trong code)

Luồng export hiện tại:

1. `slide-system/scripts/capture-slides.js` — mỗi slide: extract text layout → ẩn text
   (leaf elements) → screenshot **một PNG full-slide** (`slide-XX-bg.png`) → `export-layout.json`.
2. `slide-system/scripts/build_hybrid_pptx.py` — mỗi slide PPTX = **1 picture full-slide**
   + các text box native. Hết.

Mọi object phi-text (card, pill, icon, chart, vector decor, ảnh) đều bị nung vào 1 PNG
→ user không di chuyển/scale/xoá được object nào trong PowerPoint. Trong khi đó:

- `rules/background-rendering.md` mandate mô hình 3 lớp và ghi rõ
  *"Do not merge all export-risk visuals into one slide background image"*.
- `workflows/export-editable-pptx.md` ghi *"Complex visual elements … must become separate
  image objects … Never merge those overlays into the background image"*.

→ Spec đã có, **code vi phạm spec**. Plan này đưa code về đúng spec + các optimize đi kèm.

## 1. Kiến trúc đích: contract 3 lớp xuyên suốt

```
HTML deck ──(layer tagging)──► capture v2 ──► 3 artifacts ──► build v2 ──► PPTX 3 lớp
                                              ├ slide-XX-bg.png          (1 picture đáy — GIỮ tên hiện tại)
                                              ├ slide-XX-ov-<id>.png     (N picture rời, transparent)
                                              └ export-manifest.json     (MỘT file: base + objects[] + text[],
                                                                          z hợp nhất, bounds, checksum)
```

Tên file base **giữ nguyên `slide-XX-bg.png`** (không rename thành `-base.png`) — pipeline,
docs và run lịch sử đều đang dùng tên này; ở mode layered nó chỉ còn chứa lớp base.

**Một manifest duy nhất** (quyết định vòng verify 2): không tách `export-objects.json` /
`export-layout.json` — cả hai cùng per-slide, cùng sinh trong 1 pass capture, và build cần
"một danh sách z hợp nhất" kiểu gì cũng phải merge chúng. Source of truth là
`export-manifest.json` `{manifest_version, mode, slide, base, objects[], text[]}` →
z-interleave text↔overlay (C8) thành tự nhiên, 1 schema, validator mở 1 file.
Ở mode flat, manifest không có `objects[]`.

### Cách ly v1 ↔ v2 (luật cứng — không để hai version dính nhau)

Định nghĩa mode (gỡ mâu thuẫn flat/keep-bg-text từ vòng verify 1):

| Mode | Là gì | Hành vi |
|---|---|---|
| `--mode flat` | **= v1 hôm nay, đóng băng** | 1 bg.png full-slide đã strip text + text box native. Output phải **tương đương cấu trúc** với pipeline hiện tại (định nghĩa ở luật #5 — byte-level là bất khả thi vì PPTX là zip có timestamp) |
| `--mode layered` | v2 | base + overlays + text theo manifest |
| `--keep-bg-text` | flag độc lập của capture (không phải mode) | biến thể full-image của v1: text nằm trong PNG. Kết hợp với `flat`, không định nghĩa lại |

Sáu luật cách ly:

1. **Script cũ giữ default v1.** Chạy trực tiếp `capture-slides.js` / `build_hybrid_pptx.py`
   không flag mới → hành vi hôm nay, không đổi. Layered là opt-in ở mức script. Default
   `--mode layered` CHỈ tồn tại ở `export_pptx.py` (orchestrator MỚI, chưa có caller cũ nào
   để phá). Mọi lệnh cũ trong docs/workflows chạy lại vẫn ra v1.
2. **Manifest tự khai version + mode** (`"manifest_version": 2`, `"mode": "layered"|"flat"`).
   Script mới từ chối input thiếu 2 field này — fail tường minh, không đoán.
3. **Shim `export-layout.json` CHỈ được emit ở mode flat** (nơi bg.png mang đúng ngữ nghĩa v1).
   Mode layered TUYỆT ĐỐI không emit shim — nếu emit, build v1 sẽ ăn layout.json + bg.png
   chỉ-còn-lớp-base → deck mất toàn bộ overlay mà không lỗi nào báo. Đây là kịch bản trộn
   v1/v2 nguy hiểm nhất; thiếu layout.json làm build v1 crash là hành vi ĐÚNG.
4. **Ngữ nghĩa `slide-XX-bg.png` xác định bằng manifest, không bằng tên file** (flat: cả slide
   trừ text; layered: chỉ lớp base). Validator mode-aware: `mode=flat` → check 1 picture +
   text + parity; `mode=layered` → check đủ objects. Không bao giờ suy ngữ nghĩa từ tên PNG.
5. **Regression guard cho v1:** `test_export_stack.py` giữ một test flat-mode cố định chạy
   trên fixture deck (§10.4) — P1/P2 không được làm thay đổi output flat. Định nghĩa
   "không đổi" = **tương đương cấu trúc**, vì byte-identical là bất khả thi (PPTX = zip có
   timestamp): (a) PNG so pixel-diff (ngưỡng 0); (b) PPTX so cấu trúc XML — số slide, số
   shape, loại shape, geometry EMU, text run content; (c) `export-layout.json` so nội dung
   JSON. Manifest mới là artifact BỔ SUNG ở mode flat — sự tồn tại của nó không tính là
   "output đổi". Đây là tiêu chí nghiệm thu, không phải khuyến nghị.
6. **Deck cũ không có tag `data-export-*` chạy layered** → 0 overlay, output tương đương flat
   + warning "untagged" per element — degrade an toàn, không error, không lai tạp.

**Contract mới ở phase build HTML** (mấu chốt — separation phải được *khai báo*, không đoán):

| Attribute | Ý nghĩa | Capture xử lý |
|---|---|---|
| `data-export-layer="base"` | Canvas thụ động (gradient nền, texture, wash) | Nằm lại trong base PNG |
| `data-export-layer="overlay"` + `data-export-id` | Object/nhóm visual phức tạp | Chụp riêng thành PNG trong suốt, bounds + z riêng |
| `data-export-group="<name>"` | Gom nhiều element thành 1 overlay semantic (vd: cả chart) | 1 PNG cho cả nhóm |
| `data-export-native="rect\|line\|ellipse"` *(phase 2)* | Shape đơn giản → autoshape native | Không raster, build vẽ shape PPTX thật |
| `data-export-skip` | Text không tái tạo được (gradient text…) | Giữ hành vi hiện tại — nung vào raster |
| *(không tag)* | Mặc định | Heuristic: con trực tiếp của slide root không phải text → cảnh báo "untagged element", fallback vào base |

Lý do tag-first: heuristic tự đoán element nào là object sẽ không ổn định giữa các LLM
khác nhau; attribute là contract máy-đọc-được (nguyên tắc "rules must be executable").

## 2. Các case có thể xảy ra + hướng giải quyết

- **C1 — Gradient/texture nền full-slide** → `base`. Render 1920×1080 đúng rule hiện hành.
- **C2 — Vector decor (blob, đường lượn) chồng lên content** → mỗi cụm semantic = 1 overlay.
  Chụp `element.screenshot({omitBackground:true})` sau khi ẩn base + siblings → PNG trong suốt
  đúng kích thước hiển thị.
- **C3 — Chart/diagram** → 1 overlay group (`data-export-group`). Rule cho phép flatten khi
  "one semantic visual group, same z-order".
- **C4 — Shadow/glow tràn ra ngoài bbox** *(dễ sai nhất)* → bbox DOM không chứa phần blur.
  Capture đọc computed `filter` / `box-shadow`, nở rect chụp thêm `blur-radius + spread +
  |offset|` mỗi phía; manifest ghi cả `bounds` (đặt vào PPTX) lẫn `visual_bounds`
  (bbox gốc) để QA đối chiếu.
- **C5 — `backdrop-filter` (frosted glass)** → không tách được thành PNG trong suốt vì pixel
  phụ thuộc nền sau nó. (a) phía sau chỉ có base → chụp overlay **không trong suốt** kèm pixel
  nền trong rect; (b) phía sau có overlay khác → buộc bake vào base + warning. Validator phải
  bắt case này, không im lặng cho qua.
- **C6 — `mix-blend-mode`** → như C5: kết quả phụ thuộc lớp dưới. Mặc định bake vào base;
  chỉ tách nếu chỉ blend với base (chụp kèm nền, không trong suốt).
- **C7 — Text nằm trong overlay (label trong chart)** → text user cần sửa → native text box,
  capture loại nó khỏi PNG overlay (strip trong phạm vi group); text trang trí →
  `data-export-skip` để nung vào overlay.
- **C8 — Z-order xen kẽ text ↔ object** (text nằm *dưới* một object) → `export-manifest.json`
  ghi z toàn cục (thứ tự DOM + z-index đã resolve); build chèn shape theo đúng thứ tự đó.
  Build hiện tại luôn đặt text trên cùng — sẽ sai với case này.
- **C9 — Element xoay / transform** → `rotate(θ)` thuần: ghi góc, PPTX hỗ trợ `rot` trên
  picture/textbox. Skew / matrix phức tạp: bake vào base + warning.
- **C10 — Ảnh photo bo góc / mask** → overlay PNG trong suốt (mask giữ trong pixel). Phase 2:
  native picture + crop nếu mask là hình chữ nhật bo góc.
- **C11 — Deck cố ý ship dạng full-image** → dùng flag `--keep-bg-text` sẵn có (text nằm
  trong PNG, không strip) — đây là flag độc lập, kết hợp được với `--mode flat`. KHÔNG gộp
  nó vào định nghĩa mode (xem "Cách ly v1 ↔ v2" §1): `--mode flat` = hành vi v1 hybrid
  (strip text, text box native), còn `--keep-bg-text` = biến thể full-image của v1.
- **C12 — Card/pill/divider fill đặc** → phase 2: autoshape native (rounded rect, line) với
  fill/stroke/radius đọc từ computed style → user scale không vỡ, file nhẹ hơn PNG.
- **C13 — Hai overlay chồng nhau cùng vùng z** → cho phép, miễn z ghi đúng; shadow của cái
  trên "ăn" vào cái dưới (C4) nằm trong PNG của cái trên — chấp nhận vì thứ tự compose giữ nguyên.

## 3. Thay đổi theo từng script (mô tả, chưa code)

### 3.1 `capture-slides.js` → v2 (multi-pass, vẫn 1 browser session)

Mỗi slide, trong **một** lần load page (không relaunch):

1. **MỘT lần `page.evaluate`** trả `{canvasW, canvasH, text[], objects[]}` — gộp extract
   text layout (như cũ, mở rộng — xem §4) và object inventory (quét `data-export-layer/group`:
   id, bbox, z toàn cục, transform, filter-extent) trong cùng 1 DOM state. Capture hiện tại
   đã extract text trong 1 evaluate (`capture-slides.js:268`) — chỉ mở rộng hàm đó, đỡ 1
   round-trip/slide.
2. Pass REF-FULL: chụp nguyên slide (đủ text + mọi lớp) → `slide-XX-ref-full.png` —
   **ảnh tham chiếu** cho parity tier-2 (§10.2). Chụp TRƯỚC khi strip để màu text còn thật.
3. Pass REF-NOTEXT: strip text, mọi lớp còn lại visible → `slide-XX-ref-notext.png` —
   tham chiếu tier-1. (Đây chính là ảnh bg.png của v1; ở mode flat nó được ghi thẳng thành
   `slide-XX-bg.png` — không chụp 2 lần.)
4. Pass BASE: ẩn text + ẩn mọi overlay → `slide-XX-bg.png` (1920×1080, giữ tên hiện tại).
5. Pass OVERLAY (lặp): hiện đúng 1 group, ẩn base + mọi thứ khác, `omitBackground` →
   `slide-XX-ov-<id>.png` clip theo rect đã nở blur.
6. Pass TEXT-LAYER: chỉ text visible, `omitBackground` → `slide-XX-text.png` — nguyên liệu
   để compose candidate tier-2 (§10.1).
7. Restore → slide kế. Ghi `export-manifest.json` (schema §6) kèm sha256 từng PNG.

Ba ảnh QA (`ref-full`, `ref-notext`, `text`) là **trung gian ephemeral** — theo rule sẵn có
của `qa/export-renders/`: xoá sau khi parity pass, chỉ giữ metrics + checksums. Mode flat
không cần pass 5–6 (không có overlay, text-layer); mode layered thêm tối đa 3 pass + N pass
overlay mỗi slide — chấp nhận theo quyết định ưu-tiên-chất-lượng §10.3, bù bằng cache §3.4.

**Lỗi vận hành thuộc capture:** font brand không load (`document.fonts.ready` + kiểm font
thật sự active) → capture **exit non-zero tại đây** — đây là check của capture, KHÔNG phải
của build (font load lúc Playwright chụp, không phải lúc python compose).

**Tái dùng hạ tầng có sẵn, không viết lại:** cơ chế strip/restore text (`__export_strip_target__`),
`data-export-skip`, và chrome-hide qua class `export-hidden` trong shadow root deck-stage đều đã
hoạt động — pass base/overlay chỉ mở rộng cùng kỹ thuật ẩn/hiện đó cho lớp object.

Thêm: chờ `document.fonts.ready` + disable animation/transition trước khi chụp (hiện chỉ
`waitForTimeout` — nguồn lệch render giữa các máy).

### 3.2 `build_hybrid_pptx.py` → v2 (composition theo manifest)

- Đọc **một** `export-manifest.json`, chèn theo danh sách z hợp nhất có sẵn trong manifest:
  base → (overlay | textbox xen kẽ theo z) → chrome. Không còn bước merge 2 file.
- Mỗi overlay: `add_picture` tại bounds EMU riêng, `shape.name = "Overlay: <id>"` (user thấy
  tên có nghĩa trong selection pane).
- **Ranh giới lỗi (quyết định vòng verify 2):** build chỉ **crash trên lỗi vận hành** —
  thiếu file render, manifest **unparseable** (JSON lỗi, thiếu field bắt buộc). Build KHÔNG
  ra verdict chất lượng: audit text-run có sẵn (chỉ print) giữ nguyên dạng thông tin; mọi
  đánh giá pass/fail (picture-count, bounds, parity) dồn về gate duy nhất §3.3. Phân biệt rõ:
  manifest *hỏng* (unparseable) → build crash; manifest *hợp lệ nhưng PPTX không khớp*
  (khai 3 overlay, PPTX có 1 picture) → verdict của validator, không phải của build.
- `--mode flat` = code path v1 đóng băng (không chạm); `--keep-bg-text` vẫn là flag capture
  riêng cho deck full-image (C11). Xem bảng mode + 6 luật cách ly ở §1.

### 3.3 Script mới `validate_export_objects.py` — gate QA DUY NHẤT

Vì các LLM ngoài Claude bỏ qua prose, mọi verdict chất lượng dồn về MỘT script (quyết định
vòng verify 2 — trước đó pass/fail rải ở 3 chỗ: build audit, validator, compare):

- Mở PPTX (zip + XML), đối chiếu `export-manifest.json` — số shape, bounds (dung sai
  ~0.02in), z-order, tên shape; **fail nếu slide chỉ có 1 picture trong khi manifest khai
  overlay**.
- Đọc `report.json` của `compare_renders.py`, so `mean_absolute_error` /
  `changed_pixel_ratio` với ngưỡng cấu hình.
- Validate manifest theo JSON Schema.
- Một exit code quyết định pass/fail cho cả chuỗi QA.

**Thứ tự bắt buộc: validator chạy SAU `compare_renders.py`** (vì nó tiêu thụ `report.json`
của compare). Chuỗi orchestrator đầy đủ: capture → build → **compose candidate (§10.1)** →
compare (chỉ emit metrics/evidence) → validate (verdict duy nhất).
`compare_renders.py` giữ nguyên thuần đo đạc.
Mở rộng `test_export_stack.py` để smoke-test toàn pipeline mới.

### 3.4 Script mới `export_pptx.py` (orchestrator — tiết kiệm token lớn nhất)

Hiện LLM phải tự nối 3–4 lệnh (serve HTML → capture → build → parity), mỗi lần vài trăm token
prompt + nguy cơ sai tham số. Gom thành 1 lệnh:

```
python3 slide-system/scripts/export_pptx.py --run-dir <run> [--mode layered|flat]
```

Tự serve deck local rồi chạy đúng thứ tự: **(a) capture v2 → (b) build v2 →
(c) compose candidate (PIL, §10.1) → (d) compare_renders (emit metrics) →
(e) validate_export_objects (gate duy nhất, §3.3)** → (f) in **JSON kết quả máy-đọc**
(pass/fail + metrics).

**Cache capture (làm ngay ở P1, không đợi P3):** Playwright là bước đắt nhất; dev loop
P1/P2 hưởng lợi ngay. Cache key bắt buộc gồm đủ 3 thành phần —
`sha(capture-slides.js) + sha(HTML + assets) + version pin Playwright/Chromium` — vì:
(a) lúc dev, thứ đổi nhiều nhất là chính script capture, key chỉ theo HTML sẽ trả "render ma";
(b) đổi Chromium → pixel đổi → key thiếu pin vẫn trả render của engine cũ. Kèm `--no-cache`
làm escape hatch.

**Lưu ý parity (đã xác minh code):** `compare_renders.py` KHÔNG phải gate — nó chỉ tính
metrics, ghi `report.json` và luôn exit 0 (chỉ fail khi 2 render lệch size). Enforcement
ngưỡng nằm trong `validate_export_objects.py` (§3.3). Không sửa `compare_renders.py`
(giữ nó thuần đo đạc, dùng chung cho nhiều flow).

## 4. Text box: render chính xác, không vỡ layout

| Vấn đề | Hiện trạng | Hướng fix |
|---|---|---|
| Chiều cao box | hack `h × 1.35` (`build_hybrid_pptx.py` box_inches) | Bỏ hack; set `line_spacing` chính xác từ `lineHeight/fontSize` đã capture, giữ h gốc + slack nhỏ |
| Wrap khác PowerPoint → tràn dòng | không kiểm soát | Capture đếm **số dòng thật** (Range API per line); build giữ width; QA check "line count parity" |
| `text-transform: uppercase` | textContent gốc (chữ thường) vào PPTX → **sai chữ** | Capture ghi computed `text-transform`, build áp transform vào chuỗi. **Thuộc P1** (vòng verify 2): đây là bug sai ký tự, không phải polish — fix ~1 dòng, để P2 nghĩa là MVP xuất chữ sai |
| `letter-spacing` | bỏ qua | Capture ghi; build set `spc` (XML run property) |
| Font cứng `Proxima Nova` toàn deck | 1 font cho mọi item | Capture ghi `fontFamily` từng item; build map qua bảng font brand-pack, set cả `latin` + `cs/ea` typeface (quan trọng cho **tiếng Việt có dấu** — tránh PowerPoint tự thay font cho glyph dấu) |
| Lệch dọc baseline | y = top line-box DOM, PPTX anchor khác | Bù `(lineHeight − fontSize×k)/2` khi line-height > 1; xác minh bằng overlay diff trong parity QA |
| Style trộn trong 1 leaf (bold giữa câu) | 1 run duy nhất | Capture đã lấy leaf span nên phần lớn ổn; case còn lại: tách run theo child text node có style khác nhau (phase 2) |
| `rgba` alpha trên màu chữ | bị bỏ | python-pptx không hỗ trợ trực tiếp; chèn `<a:alpha>` thủ công vào XML run (phase 2) |

## 5. Vector object scale "ổn áp"

1. **Mức an toàn (phase 1):** render overlay PNG ở **2× kích thước hiển thị** (đề xuất sửa
   rule "final display pixel size" cho overlay nhỏ), đặt vào PPTX ở size 1× → user scale tới
   ~200% vẫn nét. **Giới hạn đầu tư:** 2× chỉ là một tham số render (`deviceScaleFactor` khi
   screenshot + field `scale_factor` trong manifest) — không dựng subsystem quanh nó, vì với
   overlay gốc-vector nó sẽ bị svgBlip (P2) thay thế.
2. **Mức đúng bản chất (phase 2):** PowerPoint 2016+/365 hỗ trợ SVG native qua `svgBlip`
   (SVG + PNG fallback trong cùng shape — PNG fallback là BẮT BUỘC theo chuẩn OOXML, nên
   PNG 2× của P1 không phí: nó trở thành chính fallback đó). python-pptx không hỗ trợ sẵn
   → inject XML part thủ công. Với overlay nguồn gốc vector (extraction đã giữ `<path>`
   riêng trong `visual.svg`), chèn `svgBlip` → scale vô hạn không vỡ. Shape đơn giản đi
   đường autoshape native (C12) còn tốt hơn SVG.

**Vector không được phép thất lạc giữa pipeline (vòng 5):** ngay từ P1, manifest ghi
`vector_source` cho mỗi overlay có nguồn vector xác định (đường dẫn tới SVG trong library /
job assets; `null` nếu nguồn là raster/CSS thuần). PNG ở P1 là *cách nhúng tạm*, không phải
*sự thay thế*: sang P2, svgBlip chỉ việc đọc `vector_source` sẵn có — không phải dò ngược
thủ công, không re-capture. Capture cũng nên ghi kèm cảnh báo khi overlay có `vector_source`
nhưng element bị CSS effect làm khác bản gốc (filter/shadow/blend) — khi đó SVG gốc không
còn trung thực với cái hiển thị, svgBlip P2 phải cân nhắc từng case.

## 6. Schema contract (để mọi LLM tạo/tiêu thụ thống nhất)

`export-manifest.json` (mới, MỘT file thay cho cặp objects+layout) — mỗi slide:

```json
{
  "manifest_version": 2,
  "mode": "layered",
  "slide": 1,
  "base": {"png": "slide-01-bg.png", "sha256": "…"},
  "objects": [
    {
      "id": "hero-chart",
      "role": "complex-overlay",
      "png": "slide-01-ov-hero-chart.png",
      "bounds": {"x": 960, "y": 120, "w": 820, "h": 640, "unit": "px@1920x1080"},
      "visual_bounds": {"x": 980, "y": 140, "w": 780, "h": 600},
      "z": 12,
      "transparent": true,
      "rotation": 0,
      "scale_factor": 2,
      "vector_source": "library/decor/hero-chart/visual.svg",
      "sha256": "…"
    }
  ],
  "text": [
    {
      "text": "DOANH THU Q4",
      "z": 14,
      "x": 120, "y": 96, "w": 600, "h": 72,
      "fontSize": "48px", "fontWeight": "700", "color": "rgb(248,250,252)",
      "align": "left", "lineHeight": "56px",
      "textTransform": "uppercase", "letterSpacing": "0.02em",
      "fontFamily": "Proxima Nova", "lineCount": 1
    }
  ]
}
```

`objects[]` và `text[]` dùng chung trục `z` → build chèn xen kẽ đúng C8 mà không cần merge.
`manifest_version` + `mode` là field bắt buộc (luật cách ly #2, §1); mode flat không có
`objects[]`. Đặt JSON Schema của manifest vào
`slide-system/scripts/_reference/` (hoặc thư mục schema riêng) và validator kiểm bằng
schema — không chỉ bằng văn mô tả.

## 7. Optimize giảm luồng dư thừa & tiết kiệm token

1. **Orchestrator 1 lệnh** (§3.4) — LLM không tự nối pipeline, không đọc log dài; chỉ đọc
   1 JSON kết quả.
2. **Capture cache theo fingerprint** — không re-capture/re-render khi không gì thay đổi
   (Playwright là bước đắt nhất). Key đầy đủ + `--no-cache`: xem §3.4. Làm ngay ở P1.
3. **QA bằng số, không bằng ảnh** — giữ rule xoá `qa/export-renders/` sau khi parity pass;
   LLM chỉ đọc metrics JSON, không mở screenshot.
4. **Một browser session** cho mọi pass của mọi slide.
5. **SKILL.md chỉ thêm ~3 dòng**: trỏ vào `export_pptx.py` + 2 mode + gate; chi tiết nằm
   trong workflow doc đọc-khi-cần (lean skills).
6. **Không sinh script per-job** — mọi logic vào `slide-system/scripts/`, run chỉ chứa output
   (rule có sẵn, validator enforce).

## 8. Bổ sung REQUIREMENTS.md cho LLM ngoài Claude app

**Không thêm row mới** (stack giống hệt row "Standalone machine" sẵn có) — **update row đó**
trong bảng "Requirements per flow" (`REQUIREMENTS.md:44`) để gọi tên flow export tường minh:

```
| Standalone machine (no Claude app) / Export editable PPTX 3 lớp — `export_pptx.py`
| Node.js 18+ → `./slide-system/scripts/setup.sh` (installs Playwright, python-pptx, Pillow) |
```

Ràng buộc thực thi được (agent ngoài không đọc prose):

- `check_base_requirements.py` thêm check cho chuỗi export (node, playwright chromium,
  python-pptx, Pillow).
- **Font phải có thật trên máy capture** — capture chờ `document.fonts.ready` và fail
  (không warning suông) nếu font brand không load: font fallback lúc chụp làm sai cả base PNG
  lẫn metrics text.
- Pin version trong setup.sh (Playwright 1.60 / chromium-1223 đang dùng) để render
  deterministic giữa các máy/agent.
- Quy tắc một-đường-duy-nhất kiểu PyMuPDF: **`export_pptx.py` là entry point duy nhất cho
  export PPTX** — cấm agent tự viết generator ad-hoc (nguồn gốc các bản build per-job cũ).

## 9. Lộ trình & tiêu chí nghiệm thu

3 phase (vòng verify 2 gộp P0 doc-only vào P1 — schema ship cùng validator là thứ tiêu thụ nó):

| Phase | Nội dung | Nghiệm thu (đo được) |
|---|---|---|
| **P1 (MVP)** | **Bước 0 — prototype transparent-overlay 1 slide (GATE, làm trước mọi code khác)**: 1 slide mẫu có 1 overlay → chứng minh ẩn-siblings + `omitBackground` (kể cả ẩn CSS background của slide root) cho ra PNG trong suốt đúng pixel khi compose lại. **Fallback nếu prototype FAIL** (quyết định trước, không cắm đầu code tiếp): chuyển toàn bộ overlay sang đường C5 bake-with-background (PNG đục kèm pixel nền trong rect, vẫn là object rời di chuyển được trên nền tĩnh) hoặc dừng lại rethink layered approach — không build capture v2 trên kỹ thuật chưa chứng minh. Sau gate: schema manifest + sửa rule/workflow docs + bảng case (§2) thành rule file + capture v2 (1 evaluate, multi-pass kèm 3 ảnh QA tham chiếu §3.1) + build v2 layered + compose-check (§10.1) + `validate_export_objects.py` (gate duy nhất, sau compare) + orchestrator + **cache fingerprint (key 3 thành phần §3.4)** + **fix `text-transform: uppercase`** + **regression test flat-mode (tương đương cấu trúc, luật cách ly #5)** | Prototype pass; schema lint pass; mở PPTX: kéo 1 overlay ra → base còn nguyên, không lủng; số shape khớp manifest; parity metrics trong ngưỡng (validator enforce); text không vỡ dòng, chữ HOA đúng trên deck mẫu; **test flat-mode pass — output v1 không đổi so với trước P1** |
| **P2** | Native autoshapes, svgBlip vector (thay PNG 2× cho overlay gốc-vector), rich text còn lại (letter-spacing/per-item font/multi-run), z xen kẽ hoàn chỉnh | Scale overlay 200% không vỡ; deck tiếng Việt không bị thay font dấu |
| **P3** | Update REQUIREMENTS.md:44, mở rộng `test_export_stack.py`, smoke-test bằng 1 agent ngoài Claude | Re-export deck không đổi < vài giây (cache P1); agent ngoài chạy 1 lệnh ra PPTX pass toàn bộ gate |

**Rollback an toàn:** `--mode flat` là code path v1 đóng băng + 6 luật cách ly §1 (script cũ
giữ default v1, shim chỉ ở flat, manifest tự khai version, regression test flat cố định);
deck cũ và run lịch sử không bị ảnh hưởng (rule "keep historical phase outputs unchanged"
vẫn đúng).

**Rủi ro chính:** C5/C6 (backdrop-filter, blend-mode) không tách được về mặt vật lý — xử lý
bằng quy tắc fallback tường minh + validator cảnh báo, không hứa tách 100% mọi element.

## 10. Quyết định chốt các open issue (vòng 4 — user duyệt 2026-06-12)

### 10.1 Candidate render cho parity ở mode layered → compose-check (PIL)

PPTX layered không còn 1 PNG full-slide để so trực tiếp. Quyết định: **compose-check** —
là **bước (c) của orchestrator** `export_pptx.py` (KHÔNG nằm trong `compare_renders.py`,
script đó giữ thuần đo đạc), chạy giữa build và compare. Thuần PIL, không mở browser lần 2
— mọi nguyên liệu đã được capture sinh sẵn (§3.1):

- Candidate **tier-1** = PIL ghép `bg.png` (base) + các `ov-*.png` theo `bounds`/`z`
  trong manifest → so với `ref-notext.png`.
- Candidate **tier-2** = tier-1 + `text.png` (text-layer đã chụp) → so với `ref-full.png`.

**Giới hạn ghi nhận (trung thực về cái nó chứng minh):** tier-1 chứng minh *tách lớp không
mất pixel* — rủi ro cốt lõi của layered. Tier-2 chứng minh *thứ tự compose + strip/restore
sạch*; nó KHÔNG chứng minh engine text của PowerPoint render đẹp (text-layer là render HTML,
không phải render PPTX). Độ trung thực text trong PowerPoint được validator check bằng SỐ
(bounds/font/line-count vs manifest), không bằng pixel.

**Option dự phòng (note lại, chưa làm):** nếu compose-check không đáp ứng nhu cầu (cần
verify chính render PowerPoint), nâng cấp candidate thành LibreOffice headless PPTX→PNG.
Đây là dependency mới — REQUIREMENTS.md hiện chỉ cho phép LibreOffice ở flow `pptx` skill —
nên CHỈ thêm khi user duyệt lại, không tự ý cài.

### 10.2 Ngưỡng parity layered (quyết định kỹ thuật, calibrate ở P1)

Hai mức so sánh, số khởi điểm lấy từ ngưỡng đã chứng minh của flatten gate:

| So sánh | Ngưỡng khởi điểm | Ghi chú |
|---|---|---|
| Tier-1: compose(base + overlays) vs `ref-notext.png` | `mean_err ≤ 0.5`, `changed_ratio ≤ 0.001` | tái dùng ngưỡng flatten_svg_background đã pass 6/6 item với err=0.000; chứng minh tách lớp không mất pixel |
| Tier-2: compose(tier-1 + text-layer) vs `ref-full.png` | `mean_err ≤ 1.0`, `changed_ratio ≤ 0.005` | nới hơn vì anti-aliasing biên overlay; chứng minh thứ tự compose + strip sạch (xem giới hạn §10.1) |

Calibrate trên fixture (§10.4) trong P1 rồi **đóng băng vào 1 file config** mà validator
đọc — không hard-code rải rác trong script.

### 10.3 Ưu tiên chất lượng output (user quyết)

- Overlay render 2× là mặc định cho MỌI overlay — không hạ để tiết kiệm dung lượng/thời gian.
- Tốc độ bù bằng cache (§3.4), không bằng giảm chất lượng.
- Deck quá nặng → orchestrator **cảnh báo + báo số liệu** trong JSON kết quả, không bao giờ
  tự động giảm chất lượng. Quyền đánh đổi thuộc về user.

### 10.4 Fixture chuẩn: `input/Interview_Workshop_Sunriser.pdf`

Đã kiểm bằng PyMuPDF (2026-06-12): 12 trang 1920×1080, thuần vector + text (không ảnh
raster); trang 1 có 78 vector paths; toàn bộ text tiếng Việt có dấu. Một fixture phục vụ
cả 3 việc:

1. **Prototype bước 0** (P1): lấy 1 slide có vector decor làm overlay thử nghiệm
   transparent-capture.
2. **Regression test flat-mode** (luật cách ly #5): deck HTML sinh từ PDF này được build
   1 lần, đóng băng làm chuẩn — flat-mode output phải không đổi qua P1/P2.
3. **Calibrate ngưỡng** §10.2 + nghiệm thu font tiếng Việt (cs/ea typeface, P2).
